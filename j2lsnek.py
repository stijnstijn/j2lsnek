"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Thanks to DJazz for a reference implementation and zepect for some misc tips.
"""

import urllib.request
import urllib.error
import subprocess
import importlib
import logging
import sqlite3
import socket
import json
import time
import sys
import os
from logging.handlers import RotatingFileHandler

import config
import helpers.servernet
import helpers.functions
import helpers.listener
import helpers.interact
import helpers.serverpinger
import helpers.webhooks
import helpers.jj2


class listserver:
    """
    Main list server thread
    Sets up port listeners and broadcasts data to connected mirror list servers
    """
    looping = True  # if False, will exit
    sockets = {}  # sockets the server is listening it
    mirrors = []  # ServerNet connections
    last_ping = 0  # last time this list server has sent a ping to ServerNet
    last_sync = 0  # last time this list server asked for a full sync
    reboot_mode = "quit"  # "quit" (default), "restart" (reload everything), or "reboot" (restart complete list server)
    banlist = {}

    def __init__(self):
        """
        Sets up the database connection, logging, and starts port listeners
        """

        self.start = int(time.time())
        self.address = socket.gethostname()

        # initialise logger
        self.log = logging.getLogger("j2lsnek")
        self.log.setLevel(logging.INFO)

        # first handler: output to console, only show warnings (i.e. noteworthy messages)
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter("%(asctime)-15s | %(message)s", "%d-%m-%Y %H:%M:%S"))
        self.log.addHandler(console)

        # second handler: rotating log file, max 5MB big, log all messages
        handler = RotatingFileHandler("j2lsnek.log", maxBytes=5242880, backupCount=1)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)-15s | %(message)s", "%d-%m-%Y %H:%M:%S"))
        self.log.addHandler(handler)

        # third and fourth handlers (optional): webhook handlers
        if config.WEBHOOK_DISCORD:
            handler = helpers.webhooks.DiscordLogHandler(config.WEBHOOK_DISCORD, self.address)
            handler.setLevel(logging.ERROR)
            self.log.addHandler(handler)

        if config.WEBHOOK_SLACK:
            handler = helpers.webhooks.SlackLogHandler(config.WEBHOOK_SLACK, self.address)
            handler.setLevel(logging.WARN)
            self.log.addHandler(handler)


        # try to get own IP
        try:
            self.ip = json.loads(str(urllib.request.urlopen("http://httpbin.org/ip", timeout=5).read().decode("ascii", "ignore")))["origin"]
        except (ValueError, urllib.error.URLError, socket.timeout) as e:
            self.log.info("Could not retrieve own IP via online API - guessing")
            self.ip = helpers.functions.get_own_ip()  # may be wrong, but best we got

        # say hello
        os.system("cls" if os.name == "nt" else "clear")  # clear screen
        print("\n                          .-=-.          .--.")
        print("              __        .' s n '.       /  \" )")
        print("      _     .'  '.     / l .-. e \     /  .-'\\")
        print("     ( \   / .-.  \   / 2 /   \ k \   /  /   |\\ ssssssssssssss")
        print("      \ `-` /   \  `-' j /     \   `-`  /")
        print("       `-.-`     '.____.'       `.____.'\n")
        self.log.warning("Starting list server! This one's name is: %s (%s)" % (self.address, self.ip))
        print("Current time: %s" % time.strftime("%d-%M-%Y %H:%M:%S"))
        print("Enter 'q' to quit (q + enter).")
        print("")

        self.prepare_database()

        # let other list servers know we're live and ask them for the latest
        self.broadcast(action="request", data=[{"from": self.address}])

        # only listen on port 10059 if auth mechanism is available
        # check if certificates are available for auth and encryption of port 10059 traffic
        can_auth = os.path.isfile(config.CERTFILE) and os.path.isfile(config.CERTKEY) and os.path.isfile(
            config.CERTCHAIN)
        ports = [10053, 10054, 10055, 10056, 10057, 10058, 10059]
        if not can_auth:
            ports.remove(10059)
            self.log.warning("Not listening on port 10059 as SSL certificate authentication is not available")

        # "restart" to begin with, then assume the script will quit afterwards. Value may be modified back to
        # "restart" in the meantime, which will cause all port listeners to re-initialise when listen_to finishes
        self.reboot_mode = "restart"
        while self.reboot_mode == "restart":
            self.reboot_mode = "quit"
            self.looping = True
            self.listen_to(ports)

        # restart script if that mode was chosen
        if self.reboot_mode == "reboot":
            if os.name == "nt":
                from subprocess import Popen
                import signal
                p = Popen([sys.executable] + sys.argv)
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                p.wait()
                sys.exit(p.returncode)
            else:
                interpreter = sys.executable.split("/")[-1]
                os.execvp(sys.executable, [interpreter] + sys.argv)

    def listen_to(self, ports):
        """
        Set up threaded listeners at given ports

        :param ports: A list of ports to listen at
        :return: Nothing
        """
        self.log.info("Opening port listeners...")
        for port in ports:
            self.sockets[port] = helpers.listener.port_listener(port=port, ls=self)
            self.sockets[port].start()
        self.log.info("Listening.")
        print("Port listeners started.")

        # have a separate thread wait for input so this one can go on sending pings every so often
        poller = helpers.interact.key_poller(ls=self)
        poller.start()

        # have a separate thread ping servers every so often
        pinger = helpers.serverpinger.pinger(ls=self)
        pinger.start()

        while self.looping:
            current_time = int(time.time())

            if self.last_ping < current_time - 120:
                # let other servers know we're still alive
                self.broadcast(action="ping", data=[{"from": self.address}])
                self.last_ping = current_time

            if self.last_sync < current_time - 900:
                # ask for sync from all servers - in case we missed any servers being listed
                self.broadcast(action="request", data=[{"from": self.address, "fragment": "servers"}])
                self.last_sync = current_time

            time.sleep(config.MICROSLEEP)

        self.log.warning("Waiting for listeners to finish...")
        for port in self.sockets:
            self.sockets[port].halt()

        for port in self.sockets:
            self.sockets[port].join()

        pinger.halt()
        pinger.join()

        self.log.info("j2lsnek succesfully shut down.")
        print("Bye!")

        return

    def broadcast(self, action, data, recipients=None, ignore=None):
        """
        Send data to servers connected via ServerNET

        :param action: Action with which to call the API
        :param data: Data to send
        :param recipients: List of IPs to send to, will default to all known mirrors
        :param ignore: List of IPs *not* to send to
        :return: Nothing
        """
        if not self.looping:
            return False  # shutting down

        data = json.dumps({"action": action, "data": data, "origin": self.address})

        if not recipients:
            recipients = helpers.functions.all_mirrors()

        if ignore is None:
            ignore = []

        for ignored in ignore:
            if ignored in recipients:
                recipients.remove(ignored)

        transmitters = {}

        for mirror in recipients:
            if mirror == "localhost" or mirror == "127.0.0.1" or mirror == self.ip:
                continue  # may be a mirror but should never be sent to because it risks infinite loops
            transmitters[mirror] = helpers.servernet.broadcaster(ip=mirror, data=data, ls=self)
            transmitters[mirror].start()

        return

    def halt(self):
        """
        Halt program execution

        Sets self.looping to False, which ends the main loop and allows the thread to start halting other threads.

        :return:
        """
        self.looping = False

    def prepare_database(self):
        """
        Creates database tables if they don't exist yet

        No lock is required for the database action since no other database shenanigans should be going on at this point
        as this is before threads get started

        :return: result of connection.commit()
        """

        dbconn = sqlite3.connect(config.DATABASE)
        dbconn.row_factory = sqlite3.Row
        db = dbconn.cursor()

        # servers is emptied on restart, so no harm in recreating the table (just in case any columns were added/changed)
        db.execute("DROP TABLE IF EXISTS servers")
        db.execute(
                "CREATE TABLE servers (id TEXT UNIQUE, ip TEXT, port INTEGER, created INTEGER DEFAULT 0, lifesign INTEGER DEFAULT 0, last_ping INTEGER DEFAULT 0, private INTEGER DEFAULT 0, remote INTEGER DEFAULT 0, origin TEXT, version TEXT DEFAULT '1.00', plusonly INTEGER DEFAULT 0, mode TEXT DEFAULT 'unknown', players INTEGER DEFAULT 0, max INTEGER DEFAULT 0, name TEXT, prefer INTEGER DEFAULT 0)")


        try:
            db.execute("SELECT * FROM settings")
        except sqlite3.OperationalError:
            self.log.info("Table 'settings' does not exist yet, creating and populating.")
            db.execute("CREATE TABLE settings (item TEXT UNIQUE, value TEXT)")
            db.execute("INSERT INTO settings (item, value) VALUES (?, ?), (?, ?), (?, ?)", ("motd", "", "motd-updated", "0", "motd-expires", int(time.time()) + (3 * 86400)))

        # was not a setting initially, so may need to add entry
        setting = db.execute("SELECT * FROM settings WHERE item = ?", ("motd-expires", )).fetchone()
        if not setting:
            db.execute("INSERT INTO settings (item, value) VALUES (?, ?)", ("motd-expires", int(time.time()) + (3 * 86400)))

        try:
            db.execute("SELECT * FROM banlist").fetchall()
        except sqlite3.OperationalError:
            self.log.info("Table 'banlist' does not exist yet, creating.")
            db.execute("CREATE TABLE banlist (address TEXT, type TEXT, note TEXT, origin TEXT, reserved TEXT DEFAULT '')")
        try:
            db.execute("SELECT reserved FROM banlist")
        except sqlite3.OperationalError:
            db.execute("ALTER TABLE banlist ADD COLUMN reserved TEXT DEFAULT ''")

        try:
            db.execute("SELECT * FROM mirrors")
        except sqlite3.OperationalError:
            self.log.info("Table 'mirrors' does not exist yet, creating.")
            db.execute("CREATE TABLE mirrors (name TEXT, address TEXT, lifesign INTEGER DEFAULT 0)")
            try:
                master_fqdn = "list.jj2.plus"
                master = socket.gethostbyname(master_fqdn)
                if master != self.address:  # don't add if *this* server has that hostname
                    self.log.info("Adding %s as mirror" % master_fqdn)
                    db.execute("INSERT INTO mirrors (name, address) VALUES (?, ?)", (master_fqdn, master))
            except socket.gaierror:
                self.log.error("Could not retrieve IP for %s - no master list server available!" % master_fqdn)

        # if this method is run, it means the list server is restarted, which breaks all open connections, so clear all
        # servers and such - banlist will be synced upon restart
        db.execute("DELETE FROM banlist WHERE origin != ?", (self.address, ))
        db.execute("DELETE FROM servers")

        result = dbconn.commit()

        db.close()
        dbconn.close()

        return result

    def reload(self, mode=1):
        """
        Reload list server

        Depending on the mode, the configuration is reload; modules are re-imported; or the list server is shut down and
        completely restarted.
        :param mode: "reload" (config only), "restart" (reload modules), "reboot" (restart list server
        :return:
        """
        if mode == 2 or mode == 3:
            self.log.warning("Pulling latest code from github...")
            subprocess.call("git reset HEAD --hard".split(" "))
            subprocess.call("git pull origin master".split(" "))

        if mode == 2:
            self.log.warning("Reloading modules...")
            importlib.reload(helpers.servernet)
            importlib.reload(helpers.functions)
            importlib.reload(helpers.listener)
            importlib.reload(helpers.jj2)
            self.reboot_mode = "restart"
            self.halt()
        elif mode == 3:
            self.log.warning("Restarting list server...")
            self.reboot_mode = "reboot"
            self.halt()
        else:
            self.log.warning("Reloading configuration...")
            importlib.reload(config)

    def bridge(self):
        """
        Mirror server data from another list

        For testing purposes only
        :return:
        """
        listserver = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listserver.settimeout(4)
        listserver.connect(("178.32.55.196", 10057))

        buffer = ""
        while True:
            try:
                add = listserver.recv(1024).decode("ascii", "ignore")
            except UnicodeDecodeError:
                break
            if not add or add == "":
                break
            buffer += add

        servers = buffer.split("\n")
        payload = []
        for server in servers:
            try:
                bits = server.split(" ")
                if len(bits) < 9:
                    continue
                key = bits[0]
                ip = bits[0].split(":")[0]
                port = bits[0].split(":")[1]
                private = 1 if bits[2] == "private" else 0
                mode = bits[3]
                version = bits[4]
                rest = " ".join(bits[7:]) if bits[7] != " " else " ".join(bits[8:])
                bits = rest.split(" ")
                created = int(time.time()) - int(bits[0])
                players = int(bits[1][1:-1].split("/")[0])
                max_players = int(bits[1][1:-1].split("/")[1])
                name = " ".join(bits[2:]).strip()
                data = {"id": key, "ip": ip, "port": port, "created": created, "lifesign": int(time.time()),
                        "private": private, "remote": 1, "origin": self.address, "version": version, "mode": mode,
                        "players": players, "max": max_players, "name": name}
                payload.append(data)

                srv = helpers.jj2.jj2server(key)
                for item in data:
                    if item != "id":
                        srv.set(key, data[key])

            except ValueError:
                continue

        self.broadcast(action="server", data=payload)
        self.log.warning("Retrieved server data from external list")
        listserver.shutdown(socket.SHUT_RDWR)
        listserver.close()


listserver()  # all systems go

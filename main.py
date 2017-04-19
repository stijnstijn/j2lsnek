"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Thanks to DJazz for a reference implementation and zepect for some misc tips.
"""

import importlib
import threading
import logging
import sqlite3
import socket
import json
import time
import os
from logging.handlers import RotatingFileHandler

import config
from handlers.binarylist import binary_handler
from handlers.liveserver import server_handler
from handlers.statistics import stats_handler
from handlers.api import servernet_handler
from handlers.asciilist import ascii_handler
from handlers.motd import motd_handler
from helpers.functions import banned, whitelisted


class listserver():
    """
    Main list server thread
    Sets up port listeners and broadcasts data to connected remote list servers
    """
    looping = True
    sockets = {}  # sockets the server is listening it
    remotes = []  # ServerNet connections
    log = None

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
        console.setFormatter(logging.Formatter("%(asctime)-15s | %(message)s", "%d-%M-%Y %H:%M:%S"))
        self.log.addHandler(console)

        # second handler: rotating log file, max 5MB big, log all messages
        handler = RotatingFileHandler("j2lsnek.log", maxBytes = 5242880)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)-15s | %(message)s", "%d-%M-%Y %H:%M:%S"))
        self.log.addHandler(handler)

        # say hello
        os.system("cls" if os.name == "nt" else "clear")  # clear screen
        print("\n                          .-=-.          .--.")
        print("              __        .' s n '.       /  \" )")
        print("      _     .'  '.     / l .-. e \     /  .-'\\")
        print("     ( \   / .-.  \   / 2 /   \ k \   /  /   |\\ ssssssssssssss")
        print("      \ `-` /   \  `-' j /     \   `-`  /")
        print("       `-.-`     '.____.'       `.____.'\n")
        self.log.warning("Starting list server! Address for this server: %s" % self.address)
        self.log.warning("Current time: %s" % time.strftime("%d-%M-%Y %H:%M:%S"))
        self.log.warning("Enter 'q' to quit (q + enter).")
        self.log.warning("")

        self.prepare_database()

        # let other list servers know we're live and ask them for the latest
        self.broadcast(action="request", data=[{"from": self.address}])

        self.listen_to([10053, 10054, 10055, 10056, 10057, 10058, 10059])

    def listen_to(self, ports):
        """
        Set up threaded listeners at given ports

        :param ports: A list of ports to listen at
        :return: Nothing
        """
        for port in ports:
            self.sockets[port] = port_listener(port=port, ls=self)
            self.sockets[port].start()

        while self.looping:
            cmd = input("")
            if cmd == "q":
                self.looping = False

        self.log.warning("Waiting for listeners to finish...")
        for port in self.sockets:
            self.sockets[port].halt()

        for port in self.sockets:
            self.sockets[port].join()

        self.log.warning("Bye!")

        return

    def broadcast(self, action, data, recipients=None, ignore=[]):
        """
        Send data to servers connected via ServerNET

        :param action: Action with which to call the API
        :param data: Data to send
        :param recipients: List of IPs to send to, will default to all known remotes
        :return: Nothing
        """
        data = json.dumps({"action": action, "data": data, "origin": self.address})

        if not recipients:
            recipients = self.remotes

        for ignored in ignore:
            if ignored in recipients:
                recipients.remove(ignored)

        transmitters = {}

        for remote in recipients:
            if remote == "localhost" or remote == "127.0.0.1":
                continue  # may be a remote but should never be sent to because it risks infinite loops
            transmitters[remote] = servernet_sender(ip=remote, data=data, ls=self)
            transmitters[remote].start()

        return

    def halt(self, reason = "Unknown error"):
        """
        Halt program execution

        Sets self.looping to False, which ends the main loop and allows the thread to start halting other threads. That
        latter bit yet to be implemented.

        :param reason: Reason for quitting, a stringitem
        :return:
        """
        self.looping = False
        print("HALTED: %s" % reason)

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

        try:
            test = db.execute("SELECT * FROM servers")
        except sqlite3.OperationalError:
            db.execute(
                "CREATE TABLE servers (id TEXT UNIQUE, ip TEXT, port INTEGER, created INTEGER DEFAULT 0, lifesign INTEGER DEFAULT 0, private INTEGER DEFAULT 0, remote INTEGER DEFAULT 0, origin TEXT, version TEXT DEFAULT '1.00', mode TEXT DEFAULT 'unknown', players INTEGER DEFAULT 0, max INTEGER DEFAULT 0, name TEXT)")

        try:
            test = db.execute("SELECT * FROM settings")
        except sqlite3.OperationalError:
            db.execute("CREATE TABLE settings (item TEXT UNIQUE, value TEXT)")
            db.execute("INSERT INTO settings (item, value) VALUES (?, ?), (?, ?)", ("motd", "", "motd-updated", "0"))

        try:
            test = db.execute("SELECT * FROM banlist")
        except sqlite3.OperationalError:
            db.execute("CREATE TABLE banlist (address TEXT, type TEXT, origin TEXT, note TEXT, global INTEGER)")

        try:
            test = db.execute("SELECT * FROM remotes")
        except sqlite3.OperationalError:
            db.execute("CREATE TABLE remotes (name TEXT, address TEXT)")

        # if this method is run, it means the list server is restarted, which breaks all open connections, so clear all
        # servers and such - banlist will be synced upon restart
        db.execute("DELETE FROM banlist WHERE origin != ?", (self.address,))
        db.execute("DELETE FROM servers")

        result = dbconn.commit()

        remotes = db.execute("SELECT * FROM remotes").fetchall()
        if remotes:
            self.remotes = [remote["address"] for remote in remotes]
            
        db.close()
        dbconn.close()

        return result

    def add_remote(self, address):
        """
        Add ServerNet remote

        Does not add remote to database (that's the APIs' job) but only to internal list

        :param address: Address (IP) of ServerNet remote
        :return:
        """
        if address not in self.remotes:
            self.remotes.append(address)

    def delete_remote(self, address):
        """
        Delete ServerNet remote

        Does not delete remote from database (that's the APIs' job) but only from internal list

        :param address: Address (IP) of ServerNet remote
        :return:
        """
        if address in self.remotes:
            self.remotes.remove(address)

    def reload(self):
        importlib.reload(config)


class port_listener(threading.Thread):
    """
    Threaded port listener
    Opens a socket that listens on a port and creates handlers when someone connects
    """
    connections = {}
    ticker = {}
    looping = True

    def __init__(self, port=None, ls=None):
        """
        Check if all data is available and assign object vars

        :param port: Port at which to listen
        :param ls: List server object, for logging etc
        """
        threading.Thread.__init__(self)

        if not port or not ls:
            raise TypeError("port_handler expects port and list server object as argument")

        self.port = port
        self.ls = ls

    def run(self):
        """
        Loops infinitely; when a client connects, a handler is started in a new thread to process the connection

        :return: Nothing
        """
        server = socket.socket()
        address = "" if self.port != 10059 else "localhost"  # 10059 should only be accessible via localhost
        try:
            server.bind((address, self.port))
        except OSError:
            self.ls.log.error("WARNING! Port %s:%s is already in use! List server is NOT listening at this port!" % (address, self.port))
            return
        except ConnectionRefusedError:
            self.ls.log.error("WARNING! OS refused listening at %s:%s! List server is NOT listening at this port!" % (address, self.port))
            return

        server.listen(5)
        server.settimeout(5)
        self.ls.log.info("Opening socket listening at port %s" % self.port)

        while self.looping:
            try:
                client, address = server.accept()
            except socket.timeout:
                continue # no problemo, just listen again - this only times out so it won't hang the entire app when
                         # trying to exit, as there's no other way to easily interrupt accept()

            # check if banned (unless whitelisted)
            is_whitelisted = whitelisted(address[0])  # needed later, so save value
            if banned(address[0]) and not is_whitelisted:
                self.ls.log.warning("IP %s attempted to connect but matches banlist, refused" % address[0])
                continue

            # check if to be throttled - each connection made adds a "tick", and when those exceed a max value
            # connection is refused until the tick count decays below that max value
            now = int(time.time())
            ticks = 0
            if not is_whitelisted and address[0] in self.ticker:
                ticks = self.ticker[address[0]][0]
                last_tick = self.ticker[address[0]][1]
                decay = (now - last_tick) * config.TICKSDECAY
                ticks -= decay

                if ticks > config.TICKSMAX:
                    self.ls.log.warning("IP %s hit rate limit, throttled" % address[0])
                    self.ticker[address[0]] = [ticks, now]
                    continue

            if not is_whitelisted:
                self.ticker[address[0]] = [max(ticks + 1, 1), now]

            key = address[0] + ":" + str(address[1])

            if self.port == 10053:
                self.connections[key] = binary_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10054:
                self.connections[key] = server_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10055:
                self.connections[key] = stats_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10056 or self.port == 10059:
                self.connections[key] = servernet_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10057:
                self.connections[key] = ascii_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10058:
                self.connections[key] = motd_handler(client=client, address=address, ls=self.ls)
            else:
                raise NotImplementedError("No handler class available for port %s" % self.port)
            self.connections[key].start()

            # remove IPs that haven't been seen for a long time
            for ip in self.ticker:
                if self.ticker[ip][1] < now - config.TICKSMAXAGE:
                    self.ticker.pop(ip, None)

            # remove connections that have finished
            stale_connections = []
            for key in self.connections:
                if not self.connections[key].is_alive():
                    stale_connections.append(key)  # can't change self.connections while we're looping through it

            for key in stale_connections:
                del self.connections[key]

            del stale_connections

            time.sleep(config.MICROSLEEP)

        return

    def halt(self):
        """
        Stop listening

        Stops the main loop and signals all active handlers to stop what they're doing and rejoin the listener thread.

        :return:
        """
        self.looping = False

        self.ls.log.info("Waiting for handlers on port %s to finish..." % self.port)
        for key in self.connections:
            self.connections[key].halt()
            self.connections[key].join()


class servernet_sender(threading.Thread):
    """
    Send message to connected remote ServerNet mirrors

    To be threaded, as multiple messages may need to be sent and messages may time out, etc
    """
    def __init__(self, ip=None, data=None, ls=None):
        """
        Set up sender

        Note that this does no checking of whether the address is a valid remote; this is done in the main thread

        :param ip: IP address of remote to send to
        :param data: Data to send
        :param ls: List server thread reference, for logging etc
        """
        threading.Thread.__init__(self)

        self.ip = ip
        self.data = data
        self.ls = ls

    def run(self):
        """
        Send message

        Connects to the remote on port 10056, and sends the message; timeout is set at 5 seconds, which should be
        plenty.

        :return: Nothing
        """
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(5)

        try:
            connection.connect((self.ip, 10056))

            sent = 0
            while sent < len(self.data):
                length_sent = connection.send(self.data[sent:].encode("ascii"))
                if length_sent == 0:
                    break
                sent += length_sent
            self.ls.log.info("Sent message to remote %s" % self.ip)
        except socket.timeout:
            self.ls.log.warning("Timeout while sending to ServerNet remote %s" % self.ip)
        except ConnectionRefusedError:
            self.ls.log.warning("ServerNet remote %s refused connection: likely not listening" % self.ip)
        except (socket.gaierror, OSError):
            self.ls.log.error("ServerNet remote address %s does not seem to be valid" % self.ip)
            self.ls.delete_remote(self.ip)

        connection.close()

        return


listserver()  # all systems go

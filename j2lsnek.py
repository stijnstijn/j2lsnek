"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Thanks to DJazz for a reference implementation and zepect for some misc tips.
"""

import importlib
import json
import logging
import os
import socket
import sqlite3
import time
from logging.handlers import RotatingFileHandler

import config
from helpers.broadcaster import broadcaster
from helpers.functions import get_own_ip
from helpers.port_listener import port_listener


class listserver():
    """
    Main list server thread
    Sets up port listeners and broadcasts data to connected mirror list servers
    """
    looping = True
    sockets = {}  # sockets the server is listening it
    mirrors = []  # ServerNet connections
    log = None
    can_auth = False

    def __init__(self):
        """
        Sets up the database connection, logging, and starts port listeners
        """

        self.start = int(time.time())
        self.address = socket.gethostname()
        self.ip = get_own_ip()

        # initialise logger
        self.log = logging.getLogger("j2lsnek")
        self.log.setLevel(logging.INFO)

        # first handler: output to console, only show warnings (i.e. noteworthy messages)
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter("%(asctime)-15s | %(message)s", "%d-%M-%Y %H:%M:%S"))
        self.log.addHandler(console)

        # second handler: rotating log file, max 5MB big, log all messages
        handler = RotatingFileHandler("j2lsnek.log", maxBytes=5242880)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)-15s | %(message)s", "%d-%M-%Y %H:%M:%S"))
        self.log.addHandler(handler)

        # check if certificates are available for auth and encryption of port 10059 traffic
        can_auth = os.path.isfile(config.CERTFILE) and os.path.isfile(config.CERTKEY) and os.path.isfile(config.CERTCHAIN)

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

        # only listen on port 10059 if auth mechanism is available
        ports = [10053, 10054, 10055, 10056, 10057, 10058, 10059]
        if self.can_auth:
            ports.remove(10059)
            self.ls.log.warning("Not listening on port 10059 as auth files are not available")

        self.listen_to(ports)

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
        :param recipients: List of IPs to send to, will default to all known mirrors
        :return: Nothing
        """
        data = json.dumps({"action": action, "data": data, "origin": self.address})

        if not recipients:
            recipients = self.mirrors

        for ignored in ignore:
            if ignored in recipients:
                recipients.remove(ignored)

        transmitters = {}

        for mirror in recipients:
            if mirror == "localhost" or mirror == "127.0.0.1" or mirror == self.ip:
                continue  # may be a mirror but should never be sent to because it risks infinite loops
            transmitters[mirror] = broadcaster(ip=mirror, data=data, ls=self)
            transmitters[mirror].start()

        return

    def halt(self, reason="Unknown error"):
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
            self.log.info("Table 'servers' does not exist yet, creating.")
            db.execute(
                "CREATE TABLE servers (id TEXT UNIQUE, ip TEXT, port INTEGER, created INTEGER DEFAULT 0, lifesign INTEGER DEFAULT 0, private INTEGER DEFAULT 0, remote INTEGER DEFAULT 0, origin TEXT, version TEXT DEFAULT '1.00', mode TEXT DEFAULT 'unknown', players INTEGER DEFAULT 0, max INTEGER DEFAULT 0, name TEXT)")

        try:
            test = db.execute("SELECT * FROM settings")
        except sqlite3.OperationalError:
            self.log.info("Table 'settings' does not exist yet, creating and populating.")
            db.execute("CREATE TABLE settings (item TEXT UNIQUE, value TEXT)")
            db.execute("INSERT INTO settings (item, value) VALUES (?, ?), (?, ?)", ("motd", "", "motd-updated", "0"))

        try:
            test = db.execute("SELECT * FROM banlist")
        except sqlite3.OperationalError:
            self.log.info("Table 'banlist' does not exist yet, creating.")
            db.execute("CREATE TABLE banlist (address TEXT, type TEXT, origin TEXT, note TEXT, global INTEGER)")

        try:
            test = db.execute("SELECT * FROM mirrors")
        except sqlite3.OperationalError:
            self.log.info("Table 'mirrors' does not exist yet, creating.")
            db.execute("CREATE TABLE mirrors (name TEXT, address TEXT, lifesign INTEGER)")

        # if this method is run, it means the list server is restarted, which breaks all open connections, so clear all
        # servers and such - banlist will be synced upon restart
        db.execute("DELETE FROM banlist WHERE origin != ?", (self.address,))
        db.execute("DELETE FROM servers")

        result = dbconn.commit()

        mirrors = db.execute("SELECT * FROM mirrors").fetchall()
        if mirrors:
            self.mirrors = [socket.gethostbyname(mirror["address"]) for mirror in mirrors]  # use IPs

        db.close()
        dbconn.close()

        return result

    def add_mirrore(self, address):
        """
        Add ServerNet mirror

        Does not add mirror to database (that's the APIs' job) but only to internal list

        :param address: Address (IP) of ServerNet mirror
        :return:
        """
        if address not in self.mirrors:
            self.mirrors.append(address)

    def delete_mirror(self, address):
        """
        Delete ServerNet mirror

        Does not delete mirror from database (that's the APIs' job) but only from internal list

        :param address: Address (IP) of ServerNet mirror
        :return:
        """
        if address in self.mirrors:
            self.mirrors.remove(address)

    def reload(self):
        self.log.warning("Reloading modules...")
        importlib.reload(config)


listserver()  # all systems go

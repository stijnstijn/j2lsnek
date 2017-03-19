"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Thanks to DJazz for a reference implementation and zepect for some misc tips.
"""

import threading
import sqlite3
import socket
import json
import time
import sys

import config

from handlers.port10053 import binary_handler
from handlers.port10054 import server_handler
from handlers.port10055 import stats_handler
from handlers.port10056 import servernet_handler
from handlers.port10057 import ascii_handler
from handlers.port10058 import motd_handler
from handlers.port10059 import api_handler



class listserver():
    """
    Main list server thread
    Sets up port listeners and broadcasts data to connected remote list servers
    """
    looping = True
    sockets = {}
    remotes = []

    def __init__(self):
        """
        Sets up the database connection, which is really only used to clear stale servers from the database
        """
        self.dbconn = sqlite3.connect(config.DATABASE)
        self.dbconn.row_factory = sqlite3.Row
        self.db = self.dbconn.cursor()

        self.start = int(time.time())
        self.address = socket.gethostname()

        self.prepare_database()

        self.db.execute("DELETE FROM banlist WHERE origin != ?", (self.address,))
        self.db.execute("DELETE FROM servers")  # if this method is run, it means the list server is restarted,
        self.dbconn.commit()  # which breaks all open connections, so clear all servers and such

        remotes = self.db.execute("SELECT * FROM remotes").fetchall()
        if remotes:
            self.remotes = [remote["address"] for remote in remotes]

        self.broadcast({"action": "request"})  # let other list servers know we're live and ask them for the latest
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

        #while self.looping:  # always True but could add some mechanism to quit in the future
        #    pass

        return

    def log(self, message):
        """
        Logs status messages

        :param message: Message to log
        :return: Nothing
        """
        print(("T=%s " + message) % (int(time.time()) - self.start))  # maybe add logging to file or something later
        return

    def broadcast(self, data, recipient=None):
        """
        Send data to servers connected via ServerNET

        :param data: Data to send - will be JSON-encoded
        :param recipient: Who should receive it. If not specified, will be sent to all known list servers
        :return: Nothing
        """
        data = json.dumps(data)
        if not recipient:
            recipients = self.remotes

        transmitters = {}

        for remote in self.remotes:
            transmitters[remote] = servernet_sender(ip=remote, data=data)
            transmitters[remote].start()

        pass  # to be implemented...

    def prepare_database(self):
        """
        Creates database tables if they don't exist yet

        :return: result of connection.commit()
        """
        try:
            test = self.db.execute("SELECT * FROM servers")
        except sqlite3.OperationalError:
            self.db.execute(
                "CREATE TABLE servers (id TEXT UNIQUE, ip TEXT, port INTEGER, created INTEGER DEFAULT 0, lifesign INTEGER DEFAULT 0, private INTEGER DEFAULT 0, remote INTEGER DEFAULT 0, origin TEXT, version TEXT DEFAULT '1.00', mode TEXT DEFAULT 'unknown', players INTEGER DEFAULT 0, max INTEGER DEFAULT 0, name TEXT)")

        try:
            test = self.db.execute("SELECT * FROM settings")
        except sqlite3.OperationalError:
            self.db.execute("CREATE TABLE settings (item TEXT UNIQUE, value TEXT)")
            self.db.execute("INSERT INTO settings (item, value) VALUES (?, ?)", ("motd", ""))

        try:
            test = self.db.execute("SELECT * FROM banlist")
        except sqlite3.OperationalError:
            self.db.execute("CREATE TABLE banlist (address TEXT, type TEXT, origin TEXT, global INTEGER)")

        try:
            test = self.db.execute("SELECT * FROM remotes")
        except sqlite3.OperationalError:
            self.db.execute("CREATE TABLE remotes (name TEXT, address TEXT)")

        return self.dbconn.commit()


class port_listener(threading.Thread):
    """
    Threaded port listener
    Opens a socket that listens on a port and creates handlers when someone connects
    """
    connections = {}

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
        address = "" if self.port != 10059 else "localhost"
        server.bind((address, self.port))
        server.listen(5)
        self.ls.log("Opening socket listening at port %s" % self.port)

        while True:
            client, address = server.accept()
            key = address[0] + ":" + str(address[1])

            if self.port == 10053:
                self.connections[key] = binary_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10054:
                self.connections[key] = server_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10055:
                self.connections[key] = stats_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10056:
                self.connections[key] = servernet_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10057:
                self.connections[key] = ascii_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10058:
                self.connections[key] = motd_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10059:
                self.connections[key] = api_handler(client=client, address=address, ls=self.ls)
            else:
                raise NotImplementedError("No handler class available for port %s" % self.port)
            self.connections[key].start()

        return


class servernet_sender(threading.Thread):
    def __init__(self, ip=None, data=None):
        threading.Thread.__init__(self)

        self.ip = ip
        self.data = data

    def run(self):
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(5)
        connection.connect((self.ip, 10056))

        sent = 0
        while sent < len(self.data):
            length_sent = connection.send(self.data[sent:].encode("ascii"))
            if length_sent == 0:
                break
            sent += length_sent

        connection.close()

        return


listserver()  # all systems go

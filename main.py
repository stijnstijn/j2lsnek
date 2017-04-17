"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Thanks to DJazz for a reference implementation and zepect for some misc tips.
"""

import json
import socket
import sqlite3
import threading
import time

import config
from handlers.port10053 import binary_handler
from handlers.port10054 import server_handler
from handlers.port10055 import stats_handler
from handlers.port10056 import servernet_handler
from handlers.port10057 import ascii_handler
from handlers.port10058 import motd_handler
from handlers.port10059 import api_handler
from helpers.functions import banned, whitelisted


class listserver():
    """
    Main list server thread
    Sets up port listeners and broadcasts data to connected remote list servers
    """
    looping = True
    sockets = {}  # sockets the server is listening it
    remotes = []  # ServerNet connections

    def __init__(self):
        """
        Sets up the database connection, which is really only used to clear stale servers from the database
        """

        self.start = int(time.time())
        self.address = socket.gethostname()

        self.prepare_database()

        # let other list servers know we're live and ask them for the latest
        self.broadcast({"action": "request", "data": {}})
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

        self.log("Waiting for listeners to finish...")
        for port in self.sockets:
            self.sockets[port].halt()

        for port in self.sockets:
            self.sockets[port].join()

        self.log("Bye!")

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
            transmitters[remote] = servernet_sender(ip=remote, data=data, ls=self)
            transmitters[remote].start()

        return

    def halt(self, reason = "Unknown error"):
        """
        Halt program execution

        Sets self.looping to False, which ends the main loop and allows the thread to start halting other threads. That
        latter bit yet to be implemented.

        :param reason: Reason for quitting, a string
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
            db.execute("INSERT INTO settings (item, value) VALUES (?, ?)", ("motd", ""))

        try:
            test = db.execute("SELECT * FROM banlist")
        except sqlite3.OperationalError:
            db.execute("CREATE TABLE banlist (address TEXT, type TEXT, origin TEXT, global INTEGER)")

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


class port_listener(threading.Thread):
    """
    Threaded port listener
    Opens a socket that listens on a port and creates handlers when someone connects
    """
    connections = {}
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
            self.ls.log("WARNING! Port %s:%s is already in use! List server is NOT listening at this port!" % (address, self.port))
            return
        except ConnectionRefusedError:
            self.ls.log("WARNING! OS refused listening at %s:%s! List server is NOT listening at this port!" % (address, self.port))
            return

        server.listen(5)
        server.settimeout(5)
        self.ls.log("Opening socket listening at port %s" % self.port)

        while self.looping:
            try:
                client, address = server.accept()
            except socket.timeout:
                continue # no problemo, just listen again - this only times out so it won't hang the entire app when
                         # trying to exit, as there's no other way to easily interrupt accept()

            if banned(address[0]) and not whitelisted(address[0]) and address[0] != "127.0.0.1":  # check if banned
                self.ls.log("IP %s attempted to connect, but matches banlist" % address[0])
                continue

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

            time.sleep(config.MICROSLEEP)

        return

    def halt(self):
        """
        Stop listening

        Stops the main loop and signals all active handlers to stop what they're doing and rejoin the listener thread.

        :return:
        """
        self.looping = False

        self.ls.log("Waiting for handlers on port %s to finish..." % self.port)
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
            self.ls.log("Sent message to remote %s" % self.ip)
        except socket.timeout:
            self.ls.log("Timeout while sending to ServerNet remote %s" % self.ip)
        except ConnectionRefusedError:
            self.ls.log("ServerNet remote %s refused connection: likely not listening" % self.ip)

        connection.close()

        return


listserver()  # all systems go

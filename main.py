"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Program logic:

,-------------,                     ,-> Client connection handler 1
| Main thread |-+-> Port listener 1 +-> Client connection handler 2
`-------------` |                   `-> etc
       |        |
       |        `-> Port listener 2 ,-> Client connection handler 1
       |                            `-> etc
       |
       `-> ServerNet broadcaster ,-> Broadcast to remote list server 1
                                 `-> etc

All these are in separate threads, except for the ServerNet broadcaster which lives inside main thread. Each port has
its own handler class, specified in a separate file, e.g. port10054.py contains the handler that processes clients
sending data about their servers. These handlers extend a basic handler class that can be found in helper.py along with
a few other helper functions.

The main thread can send messages to connected remote mirror list servers, and will create a new thread for each such
message sent (which terminates once it is sent).

Server data is stored in an SQLite database; this data is removed once the server is delisted. A database is used so
other applications can easily access server data.

ServerNet communication does not use Epic's binary protocol but a new JSON-based protocol. The advantage of this is that
server data can easily be serialised and synchronised between servers (and it's a lot easier to debug). There are no
separate commands for each updated property any more; rather, when a server's info changes, its full data is broadcast
by the list server it is listed on, and other list servers replace their database records accordingly. Another new
feature is that bans, whitelistings and settings like the MOTD can also be synchronised.
"""

import threading
import sqlite3
import config
import socket
import json
import time

from port10053 import binary_handler
from port10054 import server_handler
from port10055 import stats_handler
from port10056 import servernet_handler
from port10057 import ascii_handler
from port10058 import motd_handler


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

        self.db.execute("DELETE FROM banlist WHERE origin != ?", (self.address, ))
        self.db.execute("DELETE FROM servers")  # if this method is run, it means the list server is restarted,
        self.dbconn.commit()                    # which breaks all open connections, so clear all servers and such

        remotes = self.db.execute("SELECT * FROM remotes").fetchall()
        if remotes:
            self.remotes = [remote["address"] for remote in remotes]

        self.broadcast({"action": "hello"})  # let other list servers know we're live
        self.listen_to([10053, 10054, 10055, 10056, 10057, 10058])

    def listen_to(self, ports):
        """
        Set up threaded listeners at given ports

        :param ports: A list of ports to listen at
        :return: Nothing
        """
        for port in ports:
            self.sockets[port] = port_listener(port=port, ls=self)
            self.sockets[port].start()

        while self.looping:  # always True but could add some mechanism to quit in the future
            pass

        return

    def log(self, message):
        """
        Logs status messages

        :param message: Message to log
        :return: Nothing
        """
        print(("T=%s " + message) % (int(time.time()) - self.start))  # maybe add logging to file or something later
        return

    def broadcast(self, data, recipient = None):
        """
        Send data to servers connected via ServerNET

        :param data: Data to send - will be JSON-encoded
        :param recipient: Who should receive it. If not specified, will be sent to all connected list servers
        :return: Nothing
        """
        data = json.dumps(data)
        if not recipient:
            recipients = self.remotes

        pass  # to be implemented...


class port_listener(threading.Thread):
    """
    Threaded port listener
    Opens a socket that listens on a port and creates handlers when someone connects
    """
    connections = {}

    def __init__(self, port = None, ls = None):
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
        server.bind((socket.gethostname(), self.port))
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
            else:
                raise NotImplementedError("No handler class available for port %s" % self.port)
            self.connections[key].start()

        return


class servernet_sender(threading.Thread):
    def __init__(self, ip = None, data = None):
        threading.Thread.__init__(self)

        self.ip = ip
        self.data = data

    def run(self):
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(5)
        connection.connect((self.ip, 10056))

        sent = 0
        while sent < len(self.data):
            length_sent = connection.send(self.data[sent:])
            if sent == 0:
                break
            sent += length_sent

        connection.close()

        return


listserver()  # all systems go
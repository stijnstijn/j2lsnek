"""
j2lsnek, a python-based list server for Jazz Jackrabbit 2
By Stijn (https://stijn.chat)

Program logic:

Main thread -> Port listener 1 -> Client connection handler 1
                               -> Client connection handler 2
                               -> etc
            -> Port listener 2 -> Client connection handler 1
                               -> etc

All these are in separate threads. Each port has its own handler class, specified in a separate file, e.g. port10054.py
contains the handler that processes clients sending data about their servers. These handlers extend a basic handler
class that can be found in helper.py along with a few other helper functions.

Server data is stored in an SQLite database; this data is removed once the server is delisted. A database is used so
other applications can easily access server data.
"""

import threading
import sqlite3
import config
import socket
import time

from port10053 import binary_handler
from port10054 import server_handler
from port10055 import stats_handler
from port10057 import ascii_handler
from port10058 import motd_handler


class listserver():
    """
    Main list server thread
    Sets up port listeners and does little else
    """
    looping = True
    sockets = {}
    start = 0

    def __init__(self):
        """
        Sets up the database connection, which is really only used to clear stale servers from the database
        """
        self.start = int(time.time())
        self.dbconn = sqlite3.connect(config.DATABASE)
        self.dbconn.row_factory = sqlite3.Row
        self.db = self.dbconn.cursor()

        self.db.execute("DELETE FROM servers")
        self.dbconn.commit()

        self.listen_to([10053, 10054, 10055, 10057, 10058])

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
            elif self.port == 10057:
                self.connections[key] = ascii_handler(client=client, address=address, ls=self.ls)
            elif self.port == 10058:
                self.connections[key] = motd_handler(client=client, address=address, ls=self.ls)
            else:
                raise NotImplementedError("No handler class available for port %s" % self.port)
            self.connections[key].start()

        return


listserver()  # all systems go
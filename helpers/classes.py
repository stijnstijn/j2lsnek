import threading
import sqlite3
import config
import time


class jj2server():
    """
    Class that represents a jj2 server: offers a few basic methods to transparently interface with the database
    record that belongs to the server
    """
    def __init__(self, id):
        """
        Set up database connection (they're not thread-safe) and retrieve server info from database. If not available
        (which is likely), create a new record

        :param id: Server ID, usually in the format "127.0.0.1:86400" but could be anything
        """
        self.dbconn = sqlite3.connect(config.DATABASE)
        self.dbconn.row_factory = sqlite3.Row
        self.db = self.dbconn.cursor()

        self.id = id

        self.data = self.db.execute("SELECT * FROM servers WHERE id = ?", (self.id,)).fetchone()

        if not self.data:
            self.db.execute("INSERT INTO servers (id, created, lifesign) VALUES (?, ?, ?)", (self.id, int(time.time()), int(time.time())))
            self.dbconn.commit()
            self.data = self.db.execute("SELECT * FROM servers WHERE id = ?", (self.id,)).fetchone()

        if not self.data:
            raise NotImplementedError  # there's something very wrong if this happens

        datadict = {}
        for column in self.data.keys():
            datadict[column] = self.data[column]

        self.data = datadict

    def set(self, item, value):
        """
        Update server record

        :param item: Property to update. Raises IndexError if property doesn't exist
        :param value: New value
        :return: Nothing
        """
        if item not in self.data:
            raise IndexError("%s is not a server property" % item)

        self.data[item] = value
        self.db.execute("UPDATE servers SET %s = ?, lifesign = ? WHERE id = ?" % item, (value, time.time(), self.id))
        # not escaping column names above is okay because the column name is always a key in self.data which is also
        # a valid column name

        self.dbconn.commit()

        return

    def get(self, item):
        """
        Get server property

        :param item: Property to get. Raises IndexError if property doesn't exist
        :return: Property value
        """
        if item not in self.data:
            raise IndexError("%s is not a server property" % item)

        return self.data[item]

    def ping(self):
        """
        Let the database know the server is still alive (updates the "last seen" property, 'lifesign')

        :return: Nothing
        """
        self.set("lifesign", time.time())

        return

    def forget(self):
        """
        Delete server from database

        :return: Nothing
        """
        self.db.execute("DELETE FROM servers WHERE id = ?", (self.id,))
        self.dbconn.commit()

        return

class port_handler(threading.Thread):
    """
    Generic data handler: receives data from a socket and processes it
    handle_data() method is to be defined by descendant classes, which will be called from the listener loop
    """

    dbconn = False
    db = False
    buffer = bytearray()

    def __init__(self, client = None, address = None, ls = None):
        """
        Check if all data is available and assign object vars

        :param client: Socket through which the client is connected
        :param address: Address (tuple with IP and connection port)
        :param ls: List server object, for logging etc
        """
        threading.Thread.__init__(self)

        if not client or not address or not ls:
            raise TypeError("port_handler expects client, address and list server object as arguments")

        self.client = client
        self.address = address
        self.ip = self.address[0]
        self.key = self.address[0] + ":" + str(self.address[1])
        self.ls = ls

    def run(self):
        """
        Set up a database connection (they can't be shared between threads) and call the data handler

        :return: Nothing
        """
        self.dbconn = sqlite3.connect(config.DATABASE)
        self.dbconn.row_factory = sqlite3.Row
        self.db = self.dbconn.cursor()

        self.handle_data()
        return

    def msg(self, string):
        """
        Send text message to connection - for ascii server list etc, and error messages

        :param string: Text message, will be encoded as ascii
        :return: Return result of socket.sendall()
        """
        return self.client.sendall(string.encode("ascii"))

    def error_msg(self, string):
        """
        Just msg() with a warning before the message

        :param string: Error message to send
        :return: Return result of self.msg()
        """
        return self.msg("/!\ GURU MEDITATION /!\ " + string)

    def acknowledge(self):
        """
        Just msg() but with a standardised ACK-message

        :return: Return result of self.msg()
        """
        return self.msg("ACK")

    def end(self):
        """
        End the connection: close the socket

        :return: Return result of socket.close()
        """
        return self.client.close()

    def query(self, query, replacements = tuple()):
        self.db.execute(query, replacements)
        self.dbconn.commit()
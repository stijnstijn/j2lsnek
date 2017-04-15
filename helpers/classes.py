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
        self.lock = threading.Lock()

        self.id = id

        self.data = self.fetch_one("SELECT * FROM servers WHERE id = ?", (self.id,))

        if not self.data:
            self.query("INSERT INTO servers (id, created, lifesign) VALUES (?, ?, ?)",
                       (self.id, int(time.time()), int(time.time())))
            self.data = self.fetch_one("SELECT * FROM servers WHERE id = ?", (self.id,))

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
        self.query("UPDATE servers SET %s = ?, lifesign = ? WHERE id = ?" % item, (value, time.time(), self.id))
        # not escaping column names above is okay because the column name is always a key in self.data which is also
        # a valid column name

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
        self.query("DELETE FROM servers WHERE id = ?", (self.id,))

        return

    def acquire_lock(self):
        """
        Acquire lock

        To be used before the database is manipulated.
        """
        self.locked = True
        self.lock.acquire()

    def release_lock(self):
        """
        Release lock

        To be done when done manipulating the database.
        """
        self.locked = False
        self.lock.release()

    def query(self, query, replacements=tuple(), autolock=True, mode="execute"):
        """
        Execute sqlite query

        Acquires a Lock before querying, so the database doesn't run into concurrent reads/writes etc. Database
        connection is set up and closed for each query - the overhead is not too bad and this way we can be sure that
        there will be no conflicts

        :param query: Query string
        :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
        :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
        :return: Query result
        """
        if autolock:
            self.acquire_lock()

        dbconn = sqlite3.connect(config.DATABASE)
        dbconn.row_factory = sqlite3.Row

        db = dbconn.cursor()

        if mode == "fetchone":
            result = db.execute(query, replacements).fetchone()
        elif mode == "fetchall":
            result = db.execute(query, replacements).fetchall()
        else:
            result = db.execute(query, replacements)

        dbconn.commit()

        db.close()
        dbconn.close()

        if autolock:
            self.release_lock()

        return result

    def fetch_one(self, query, replacements=tuple(), autolock=True):
        return self.query(query, replacements, autolock, "fetchone")

    def fetch_all(self, query, replacements=tuple(), autolock=True):
        return self.query(query, replacements, autolock, "fetchall")


class port_handler(threading.Thread):
    """
    Generic data handler: receives data from a socket and processes it
    handle_data() method is to be defined by descendant classes, which will be called from the listener loop
    """
    buffer = bytearray()
    locked = False

    def __init__(self, client=None, address=None, ls=None):
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

        self.lock = threading.Lock()

    def run(self):
        """
        Call the data handler

        :return: Nothing
        """
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

    def acquire_lock(self):
        """
        Acquire lock

        To be used before the database is manipulated.
        """
        self.locked = True
        self.lock.acquire()

    def release_lock(self):
        """
        Release lock

        To be done when done manipulating the database.
        """
        self.locked = False
        self.lock.release()

    def query(self, query, replacements=tuple(), autolock=True, mode="execute"):
        """
        Execute sqlite query

        Acquires a Lock before querying, so the database doesn't run into concurrent reads/writes etc. Database
        connection is set up and closed for each query - the overhead is not too bad and this way we can be sure that
        there will be no conflicts

        :param query: Query string
        :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
        :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
        :return: Query result
        """
        if autolock:
            self.acquire_lock()

        try:
            dbconn = sqlite3.connect(config.DATABASE)
            dbconn.row_factory = sqlite3.Row

            db = dbconn.cursor()

            if mode == "fetchone":
                result = db.execute(query, replacements).fetchone()
            elif mode == "fetchall":
                result = db.execute(query, replacements).fetchall()
            else:
                result = db.execute(query, replacements)

            dbconn.commit()

            db.close()
            dbconn.close()

        except sqlite3.OperationalError as e:
            self.ls.halt("SQLite error: %s" % str(e))

        except sqlite3.ProgrammingError as e:
            self.ls.halt("SQLite error: %s" % str(e))

        if autolock:
            self.release_lock()

        return result


    def fetch_one(self, query, replacements=tuple(), autolock=True):
        return self.query(query, replacements, autolock, "fetchone")


    def fetch_all(self, query, replacements=tuple(), autolock=True):
        return self.query(query, replacements, autolock, "fetchall")
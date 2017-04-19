import threading
import sqlite3
import socket
import config
import time


class port_handler(threading.Thread):
    """
    Generic data handler: receives data from a socket and processes it
    handle_data() method is to be defined by descendant classes, which will be called from the listener loop
    """
    buffer = bytearray()
    locked = False

    def __init__(self, client=None, address=None, ls=None, port=None):
        """
        Check if all data is available and assign object vars

        :param client: Socket through which the client is connected
        :param address: Address (tuple with IP and connection port)
        :param ls: List server object, for logging etc
        """
        threading.Thread.__init__(self)

        if not client or not address or not ls or not port:
            raise TypeError("port_handler expects client, address and list server object as arguments")

        self.client = client
        self.address = address
        self.ip = self.address[0]
        self.port = port
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

    def halt(self):
        """
        Halt handler

        Most handlers don't need to do anything for halting, but some may be looping or maintaining connections, in
        which case this method can be used to properly end that.

        :return:
        """
        pass

    def msg(self, string):
        """
        Send text message to connection

        For ascii server list etc, and error messages

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
        self.client.shutdown(socket.SHUT_RDWR)
        return self.client.close()

    def cleanup(self):
        """
        Housekeeping

        Not critical, but should be called before some user-facing actions (e.g. retrieving server lists)
        :return:
        """
        self.query("DELETE FROM servers WHERE remote = 1 AND lifesign < ?", (int(time.time()) - config.TIMEOUT,))

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

        .fetchone() and .fetchall() can't be used once the cursor is closed, so this method accepts an optional
        parameter to return the result of either of those instead of the raw query result, which is in most cases
        useless.

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
        """
        Fetch one row resulting from a database query

        :param query: Query string
        :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
        :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
        :return: Query result, dictionary
        """
        return self.query(query, replacements, autolock, "fetchone")

    def fetch_all(self, query, replacements=tuple(), autolock=True):
        """
        Fetch all rows resulting from a database query

        :param query: Query string
        :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
        :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
        :return: Query result, list of dictionaries
        """
        return self.query(query, replacements, autolock, "fetchall")

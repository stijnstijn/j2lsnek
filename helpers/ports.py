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
            self.ls.error("SQLite error: %s" % str(e))
            self.ls.halt()

        except sqlite3.ProgrammingError as e:
            self.ls.error("SQLite error: %s" % str(e))
            self.ls.halt()

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


import socket
import ssl
import threading
import time

import config
from handlers.api import servernet_handler
from handlers.asciilist import ascii_handler
from handlers.binarylist import binary_handler
from handlers.liveserver import server_handler
from handlers.motd import motd_handler
from handlers.statistics import stats_handler
from helpers.functions import whitelisted, banned


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
        # in case of port 10059, we authenticate via SSL certificates, since else anyone running on localhost
        # may interact with the list server API
        if self.port == 10059:
            unwrapped_server = socket.socket()
            server = ssl.wrap_socket(unwrapped_server, server_side=True, certfile=config.CERTFILE,
                                     ca_certs=config.CERTCHAIN, keyfile=config.CERTKEY)
            address = "localhost"
        else:
            server = socket.socket()
            address = ""

        try:
            server.bind((address, self.port))
        except OSError:
            self.ls.log.error("WARNING! Port %s:%s is already in use! List server is NOT listening at this port!" % (
                address, self.port))
            return
        except ConnectionRefusedError:
            self.ls.log.error("WARNING! OS refused listening at %s:%s! List server is NOT listening at this port!" % (
                address, self.port))
            return

        server.listen(5)
        server.settimeout(5)
        self.ls.log.info("Opening socket listening at port %s" % self.port)

        while self.looping:
            try:
                client, address = server.accept()
            except socket.timeout:
                continue  # no problemo, just listen again - this only times out so it won't hang the entire app when
                # trying to exit, as there's no other way to easily interrupt accept()
            except ssl.SSLError as e:
                self.ls.log.error("Could not establish SSL connection: %s" % e)
                continue

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
                self.connections[key] = binary_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10054:
                self.connections[key] = server_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10055:
                self.connections[key] = stats_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10056 or self.port == 10059:
                self.connections[key] = servernet_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10057:
                self.connections[key] = ascii_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10058:
                self.connections[key] = motd_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10059:
                self.connections[key] = servernet_handler(client=client, address=address, ls=self.ls, port=self.port)
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

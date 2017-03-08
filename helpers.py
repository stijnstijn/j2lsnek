import threading
import sqlite3
import config
import math


def decode_mode(mode):
    """
    JJ2 uses numbers instead of strings, but strings are easier for humans to work with

    :param mode: Mode number as sent by the client
    :return: Mode string ("ctf", "treasure", "battle" or "unknown")
    """
    if mode == 3:
        return "ctf"
    if mode == 2:
        return "treasure"
    if mode == 1:
        return "battle"

    return "unknown"


def decode_version(version):
    """
    Not a lot to decode for the version string, but people aren't actually playing 1.21

    :param version: Version as sent by the client
    :return: Version string as used by list server
    """
    version = version.decode("ascii")
    version_string = ""

    if version_string[0:2] == "21":
        version_string = "1.23"
    else:
        version_string = "1.24"

    return version_string + version[2:]


def fancy_time(time):
    """
    Formats time nicely so timespans are more intuitively understandable

    :param time: Time to format in seconds
    :return: Fancy formatted string, e.g. "1wk 3d 14h 35m 56s"
    """
    day = 86400
    string = ""
    weeks = days = hours = minutes = 0

    if time > day * 7:
        weeks = math.floor(time / (days * 7))
        time -= (weeks * days * 7)
        string += str(weeks) + "wk "

    if time > day or weeks > 0:
        days = math.floor(time / day)
        time -= (days * day)
        string += str(days) + "d "

    if time > 3600 or days > 0 or weeks > 0:
        hours = math.floor(time / 3600)
        string += str(hours) + "h "
        time -= (hours * 3600)

    if time > 60 or hours > 0 or days > 0 or weeks > 0:
        minutes = math.floor(time / 60)
        string += str(minutes) + "m "
        time -= (minutes * 60)

    string += str(time) + "s"

    return string


class port_handler(threading.Thread):
    """
    Generic data handler: receives data from a socket and processes it
    handle_data() method is to be defined by descendant classes, which will be called from the listener loop
    """

    dbconn = False
    db = False

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

    def end(self):
        """
        End the connection: close the socket

        :return: Return result of socket.close()
        """
        return self.client.close()
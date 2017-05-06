import threading
import socket
import config
import time

from helpers.functions import query


class port_handler(threading.Thread):
    """
    Generic data handler: receives data from a socket and processes it
    handle_data() method is to be defined by descendant classes, which will be called from the listener loop
    """
    buffer = bytearray()
    locked = False
    looping = True

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
        self.looping = False

    def msg(self, string):
        """
        Send text message to connection

        For ascii server list etc, and error messages

        :param string: Text message, will be encoded as ascii
        :return: Return result of socket.sendall()
        """
        try:
            return self.client.sendall(string.encode("ascii"))
        except Exception:
            self.end()
            return False

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
        try:
            self.client.shutdown(socket.SHUT_WR)
            return self.client.close()
        except Exception:
            return False

    def cleanup(self):
        """
        Housekeeping

        Not critical, but should be called before some user-facing actions (e.g. retrieving server lists)
        :return:
        """
        query("DELETE FROM servers WHERE remote = 1 AND lifesign < ?", (int(time.time()) - config.TIMEOUT,))
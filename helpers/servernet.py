import socket
import threading


class broadcaster(threading.Thread):
    """
    Send message to connected ServerNet mirrors

    To be threaded, as multiple messages may need to be sent and messages may time out, etc
    """

    def __init__(self, ip=None, data=None, ls=None):
        """
        Set up sender

        Note that this does no checking of whether the address is a valid mirror; this is done in the main thread

        :param ip: IP address of mirror to send to
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

        Connects to the mirror on port 10056, and sends the message; timeout is set at 5 seconds, which should be
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
            self.ls.log.info("Sent message to mirror %s (%s)" % (self.ip, self.data))
        except (socket.timeout, TimeoutError):
            self.ls.log.info("Timeout while sending to ServerNet mirror %s" % self.ip)
        except ConnectionRefusedError:
            self.ls.log.info("ServerNet mirror %s refused connection: likely not listening" % self.ip)
        except (socket.gaierror, OSError):
            self.ls.log.error("ServerNet mirror address %s does not seem to be valid" % self.ip)

        connection.close()

        return

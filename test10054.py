"""
ghetto test suite
"""
import socket
import random
import time

LIST_SERVER = "localhost"


class fake_server():
    """
    Simulate a jazz jackrabbit 2 server and send various types of updates to test whether list server
    is able to handle them
    """
    def run(self):
        """
        Open a socket on port 10054 with the list server, send handshake, and then send a random type of update every
        5 seconds until the script is halted
        :return: Nothing
        """
        print("Trying to list server on %s" % LIST_SERVER)
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(5)
        connection.connect((LIST_SERVER, 10054))
        print("Connection with list server %s opened" % LIST_SERVER)

        # create "handshake"
        hello = bytearray()
        port = 10052
        hello.extend(port.to_bytes(2, byteorder="little"))  # port
        hello.extend("test server".ljust(33).encode("ascii"))  # name
        hello.append(1)  # player count
        hello.append(32)  # max players
        hello.append(0)  # flags, not tested in this script
        hello.extend("21  ".encode("ascii"))  # version

        connection.sendall(hello)

        start = int(time.time())

        type = 1
        while True:
            now = int(time.time())
            if now - start >= 5:  # send every 5 seconds, give or take
                start = now
                # update random player count
                if type == 1:
                    players = random.randint(1, 25)
                    connection.sendall(bytes([0x00, players]))
                    print("Sent: update player count to %s" % players)

                # update server name, semi-random "x is a random number" string
                elif type == 2:
                    number = random.randint(11,99)
                    name = "%s is a random number" % number
                    message = bytearray([0x02])
                    message.extend(name.encode("ascii"))
                    connection.sendall(message)
                    print("Sent: change server name to %s" % name)

                # update max player count, random between 10 and 25
                elif type == 3:
                    players = random.randint(10, 25)
                    connection.sendall(bytes([0x03, players]))
                    print("Sent: update max player count to %s" % players)

                # public/private, either 0 or 1 randomly
                elif type == 4:
                    priv = random.randint(0,1)
                    connection.sendall(bytes([0x04, priv]))
                    print("Sent: set public/private to %s" % priv)

                # cycle to next type of update
                if type == 4:
                    type = 1
                else:
                    type += 1

        return

# go!
server = fake_server()
server.run()  # threadable but threading not really needed here
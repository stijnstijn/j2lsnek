import socket
import config
import time

from helpers.functions import decode_mode, decode_version, whitelisted

from helpers.jj2 import jj2server
from helpers.ports import port_handler


class server_handler(port_handler):
    """
    Handle server status updates
    """
    looping = True

    def handle_data(self):
        """
        Handle the connection with live servers; update server data and list/delist when needed
        """

        server = jj2server(self.key)
        new = True  # server is always new when connection is opened
        self.client.settimeout(10)  # time out in 10 seconds unless further data is received
        self.ls.log.info("Server connected from %s" % self.key)

        # keep connection open until server disconnects (or times out)
        ping = 0
        while self.looping:
            try:
                data = self.client.recv(1024)
                ping = 0
            except socket.timeout:
                ping += 1
                # if no lifesign for 20 seconds, ping to see if the server is still alive
                if ping < 2:
                    self.client.sendall(bytearray[0])
                    continue
                else:
                    self.ls.log.info("Server from %s timed out" % self.key)
                    break

            # new server wants to get listed
            if new and data and len(data) == 42:
                # check for spamming
                other = self.fetch_one("SELECT COUNT(*) FROM servers WHERE ip = ?", (self.ip,))[0]
                if other >= 2 and not whitelisted(self.ip):
                    self.ls.log.warning("IP %s attempted to list server, but has 2 listed servers already")
                    self.error_msg("Too many connections from this IP address")
                    break

                self.ls.log.info("Server listed from %s" % self.key)
                self.client.settimeout(20)  # should have some form of communication every 20

                new = False

                port = int.from_bytes(data[0:2], byteorder="little")
                name = data[2:35].decode("ascii", "ignore")

                players = int(data[35])
                max = int(data[36])
                flags = int(data[37])
                version = data[38:]

                mode = (flags >> 1) & 3
                mode = 0 if mode > 3 else mode

                server.set("name", name)
                server.set("private", flags & 1)
                server.set("ip", self.ip)
                server.set("port", port)
                server.set("players", players)
                server.set("max", max)
                server.set("mode", decode_mode(mode))
                server.set("version", decode_version(version))
                server.set("origin", self.ls.address)

                broadcast = True

            # existing server sending an update
            elif not new and data and (len(data) == 2 or data[0] == 0x02):
                broadcast = True
                if data[0] == 0:
                    if server.get("players") != data[1]:
                        self.ls.log.info("Updating player count for server %s" % self.key)
                        server.set("players", data[1])
                    else:
                        self.ls.log.info("Received ping from server %s" % self.key)
                        server.ping()
                elif data[0] == 0x02:
                    self.ls.log.info("Updating server name for server %s" % self.key)
                    server.set("name", data[1:33].decode("ascii", "ignore"))
                elif data[0] == 0x03:
                    self.ls.log.info("Updating max players for server %s" % self.key)
                    server.set("max", data[1])
                elif data[0] == 0x04:
                    self.ls.log.info("Updating public/private for server %s" % self.key)
                    server.set("private", data[1] & 1)

            # server wants to be delisted, goes offline or sends strange data
            else:
                if not new:
                    self.ls.log.info("Server from %s was delisted; invalid data received" % self.key)
                else:
                    self.ls.log.warning("Server from %s provided faulty listing data: not listed" % self.key)

                if data:
                    self.error_msg("Invalid data received")  # all valid commands are either 42 or 2 bytes long

                break

            # broadcast updates to connected mirrors
            if broadcast:
                self.ls.broadcast(action="server", data=[server.data])

            time.sleep(config.MICROSLEEP)

        # server presumed dead, remove from database
        server.forget()

        # make sure mirrors also delist the server
        self.ls.broadcast(action="delist", data=[server.data])

        self.end()

    def halt(self):
        """
        Halt port handler

        Most other handlers don't need to do anything in particular to halt, but this one maintains connections with
        listed servers, so signal that those need to be closed after the next ping.

        :return:
        """
        self.looping = False

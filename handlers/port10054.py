import socket
import config
import time

from helpers.functions import decode_mode, decode_version, whitelisted

from helpers.jj2server import jj2server
from helpers.port_handler import port_handler


class server_handler(port_handler):
    """
    Handle server status updates
    """

    def handle_data(self):
        """
        Handle the connection with live servers; update server data and list/delist when needed
        """

        server = jj2server(self.key)
        new = True  # server is always new when connection is opened
        self.client.settimeout(10)  # time out in 10 seconds unless further data is received
        self.ls.log("Server connected from %s" % self.key)

        # keep connection open until server disconnects (or times out)
        while True:
            try:
                data = self.client.recv(1024)
            except socket.timeout:
                self.ls.log("Server from %s timed out" % self.key)
                break

            broadcast = False

            # new server wants to get listed
            if new and data and len(data) == 42:
                # check for spamming
                other = self.fetch_one("SELECT COUNT(*) FROM servers WHERE ip = ?", (self.ip,))[0]
                if other >= 2 and not whitelisted(self.ip):
                    self.ls.log("IP %s attempted to list server, but has 2 listed servers already")
                    self.error_msg("Too many connections from this IP address")
                    break

                self.ls.log("Server listed from %s" % self.key)
                self.client.settimeout(35)  # should update player count every 30s, allow for a little lag

                new = False

                port = int.from_bytes(data[0:2], byteorder = "little")
                name = data[2:35].decode('ascii')
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
                        self.ls.log("Updating player count for server %s" % self.key)
                        server.set("players", data[1])
                    else:
                        self.ls.log("Received ping from server %s" % self.key)
                elif data[0] == 0x02:
                    self.ls.log("Updating server name for server %s" % self.key)
                    server.set("name", data[1:33].decode("ascii"))
                elif data[0] == 0x03:
                    self.ls.log("Updating max players for server %s" % self.key)
                    server.set("max", data[1])
                elif data[0] == 0x04:
                    self.ls.log("Updating public/private for server %s" % self.key)
                    server.set("private", data[1] & 1)

            # server wants to be delisted, goes offline or sends strange data
            else:
                if not new:
                    self.ls.log("Server from %s was delisted; invalid data received" % self.key)
                else:
                    self.ls.log("Server from %s provided faulty listing data: not listed" % self.key)

                if data:
                    self.error_msg("Invalid data received")  # all valid commands are either 42 or 2 bytes long

                break

            # broadcast updates to connected remotes
            if broadcast:
                self.ls.broadcast({"action": "server", "data": server.data})

            time.sleep(config.MICROSLEEP)

        # server presumed dead, remove from database
        server.forget()

        # make sure remotes also delist the server
        self.ls.broadcast({"action": "delist", "data": server.data})

        self.end()
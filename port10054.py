import socket

from helpers import port_handler, decode_mode, decode_version
from jj2server import jj2server


## Server settings
class server_handler(port_handler):
    def handle_data(self):
        """
        Handle the connection with live servers; update server data and list/delist when needed
        """

        server = jj2server(self.key)
        new = True  # server is always new when connection is opened

        self.client.settimeout(10)  # time out in 10 seconds unless further data is received

        self.ls.log("Server connected from %s" % self.ip)
        while True:  # keep connection open until server disconnects (or times out)
            try:
                data = self.client.recv(1024)
            except socket.timeout:
                self.ls.log("Server from %s timed out before being listed" % self.ip)
                break

            if new and data and len(data) == 42:
                # check for spamming
                other = self.db.execute("SELECT COUNT(*) FROM servers WHERE ip = ?", (self.ip,)).fetchone()[0]
                if other > 3:
                    self.error_msg("Too many connections from this IP address")
                    break

                # new server
                self.ls.log("Server listed from %s" % self.ip)
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
                server.set("private", 1 if flags & 1 else 0)
                server.set("ip", self.ip)
                server.set("port", port)
                server.set("players", players)
                server.set("max", max)
                server.set("mode", self.decode_mode(mode))
                server.set("version", self.decode_version(version))

            elif not new and data and len(data) == 2:
                # capacity update
                if data[0] == 0:
                    self.ls.log("Updating player count for server %s" % self.ip)
                    server.set("players", data[1])

            else:
                if not new:
                    self.ls.log("Server delisted from %s" % self.ip)
                if data:
                    self.error_msg("Invalid data received")  # all valid commands are either 42 or 2 bytes long
                break

        server.forget()  # server presumed dead, remove from database
        self.end()
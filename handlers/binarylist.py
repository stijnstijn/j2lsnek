import socket

from helpers.handler import port_handler
from helpers.functions import fetch_all


class binary_handler(port_handler):
    """
    Serve binary server list
    """

    def handle_data(self):
        """
        Show the binary server list and immediately close connection
        """
        self.ls.log.info("Sending binary server list to %s" % self.ip)

        self.cleanup()
        servers = fetch_all(
            "SELECT * FROM servers WHERE max > 0 AND plusonly = 0 ORDER BY prefer DESC, private ASC, (players = max) ASC, players DESC, created ASC")

        binlist = bytearray([7])
        binlist.extend("LIST".encode("ascii"))
        binlist.extend([1, 1])

        # this will only be seen by vanilla players, because JJ2+ fetches the
        # ascii server list from port 10057 instead, so we can use this to
        # advertise JJ2+ to vanilla players!
        # use fake IPs that will always remain pinging
        servers = [{"port": 80, "ip": "192.0.2.0", "name": "Get JJ2 Plus, a mod for Jazz 2!"},
                   {"port": 80, "ip": "192.0.2.1", "name": "Download at |||www.jj2.plus"},
                   {"port": 80, "ip": "192.0.2.2", "name": "-----------------------------"},
                   *servers]

        for server in servers:
            length = len(server["name"])
            length += 7
            binlist.append(length)

            ip = server["ip"].split(".")[::-1]
            for component in ip:
                binlist.append(int(component))

            binlist.extend(server["port"].to_bytes(2, byteorder="little"))
            binlist.extend(server["name"].encode("ascii", "ignore"))

        try:
            self.client.sendall(binlist)  # can't use client.msg here, that's for text messages
        except (socket.timeout, TimeoutError, ConnectionError):
            pass
        self.end()

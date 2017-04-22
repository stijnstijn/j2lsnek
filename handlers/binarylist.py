from helpers.handler import port_handler


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
        servers = self.fetch_all(
            "SELECT * FROM servers WHERE players > 0 AND max > 0 ORDER BY private ASC, players DESC, created ASC")

        binlist = bytearray([7])
        binlist.extend("LIST".encode("ascii"))
        binlist.extend([1, 1])

        for server in servers:
            length = len(server["name"])
            length += 7
            binlist.append(length)

            ip = server["ip"].split(".")[::-1]
            for component in ip:
                binlist.append(int(component))

                binlist.extend(server["port"].to_bytes(2, byteorder="little"))
                binlist.extend(server["name"].encode("ascii"))

        self.client.sendall(binlist)  # can't use client.msg here, that's for text messages
        self.end()

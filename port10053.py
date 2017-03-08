from helpers import port_handler


## Binary server list
class binary_handler(port_handler):
    def handle_data(self):
        """
        Show the binary server list and immediately close connection
        """
        self.ls.log("Sending binary server list to %s" % self.ip)
        servers = self.db.execute("SELECT * FROM servers WHERE players > 0").fetchall()

        list = bytearray([7])
        list.extend("LIST".encode("ascii"))
        list.extend([1, 1])

        for server in servers:
            length = len(server["name"])
            length += 6
            list.append(length)

            ip = server["ip"].split(".")
            for component in ip:
                list.append(int(component))

            list.extend(server["port"].to_bytes(2, byteorder = "little"))
            list.extend(server["name"].encode("ascii"))

        self.client.sendall(list)  # can't use client.msg here, that's for text messages
        self.end()
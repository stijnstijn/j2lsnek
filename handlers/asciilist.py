import time

from helpers.ports import port_handler


class ascii_handler(port_handler):
    """
    Serve ASCII server list
    """

    def handle_data(self):
        """
        Show a nicely formatted server list and immediately close connection
        """
        self.ls.log.info("Sending ascii server list to %s" % self.ip)

        self.cleanup()
        servers = self.fetch_all(
            "SELECT * FROM servers WHERE players > 0 ORDER BY private ASC, players DESC, created ASC")
        asciilist = ""

        for server in servers:
            asciilist += server['ip'] + ':' + str(server['port']) + ' '  # ip:port
            asciilist += 'local ' if server['remote'] == 0 else 'mirror '  # 'local' or 'mirror'
            asciilist += 'public ' if server['private'] == 0 else 'private '  # 'public' or 'private'
            asciilist += server['mode'] + ' '  # game mode
            asciilist += server['version'][:6].ljust(6, ' ') + ' '  # version
            asciilist += str(int(time.time()) - int(server['created'])) + ' '  # uptime in seconds
            asciilist += '[' + str(server['players']) + '/' + str(server['max']) + '] '  # [players/max]
            asciilist += server['name'] + "\r\n"  # server name

        self.msg(asciilist)
        self.end()

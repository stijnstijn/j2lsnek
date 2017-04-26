import time

from helpers.handler import port_handler


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
            "SELECT * FROM servers WHERE max > 0 ORDER BY private ASC, (players = max) ASC, players DESC, created ASC")
        asciilist = ""

        for server in servers:
            try:
                entry = server['ip'] + ':' + str(server['port']) + ' '  # ip:port
                entry += 'local ' if server['remote'] == 0 else 'mirror '  # 'local' or 'mirror'
                entry += 'public ' if server['private'] == 0 else 'private '  # 'public' or 'private'
                entry += server['mode'] + ' '  # game mode
                entry += server['version'][:6].ljust(6, ' ') + ' '  # version
                entry += str(int(time.time()) - int(server['created'])) + ' '  # uptime in seconds
                entry += '[' + str(server['players']) + '/' + str(server['max']) + '] '  # [players/max]
                entry += server['name'] + "\r\n"  # server name
                asciilist += entry
            except TypeError:
                continue

        self.msg(asciilist)
        self.end()

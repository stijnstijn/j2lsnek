import time

from helpers.port_handler import port_handler


class ascii_handler(port_handler):
    """
    Serve ASCII server list
    """

    def handle_data(self):
        """
        Show a nicely formatted server list and immediately close connection
        """
        self.ls.log("Sending ascii server list to %s" % self.ip)

        servers = self.fetch_all("SELECT * FROM servers WHERE players > 0 ORDER BY private ASC, players DESC, created ASC")
        list = ""

        for server in servers:
            list += server['ip'] + ':' + str(server['port']) + ' '                  # ip:port
            list += 'local ' if server['remote'] == 0 else 'mirror '                # 'local' or 'mirror'
            list += 'public ' if server['private'] == 0 else 'private '              # 'public' or 'private'
            list += server['mode'] + ' '                                            # game mode
            list += server['version'][:6].ljust(6, ' ') + ' '                       # version
            list += str(int(time.time()) - int(server['created'])) + ' '            # uptime in seconds
            list += '[' + str(server['players']) + '/' + str(server['max']) + '] '  # [players/max]
            list += server['name']                                                  # server name
            list += "\r\n"

        self.msg(list+"\r\n")
        self.end()
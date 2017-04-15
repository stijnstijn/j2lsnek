import time
from datetime import datetime

import config
from helpers.functions import fancy_time
from helpers.port_handler import port_handler


class stats_handler(port_handler):
    """
    Serve server statistics
    """

    def handle_data(self):
        """
        Calculate some list server statistics, show a nicely formatted list and immediately close connection
        """
        self.ls.log("Sending list stats to %s" % self.ip)

        running_since = datetime.fromtimestamp(self.ls.start)
        servers = self.fetch_all("SELECT * FROM servers WHERE players > 0")

        total = 0
        mirrored = 0
        local = 0
        players = 0
        max = 0

        for server in servers:
            total += 1
            if server["remote"] == 1:
                mirrored += 1
            else:
                local += 1

            players += server["players"]
            max += server["max"]

        stats  = "+----------------------------------------------------------------------+\n\n"
        stats += "                Jazz Jackrabbit 2 List Server statistics\n"
        stats += "\n"
        stats += "\n"
        stats += "  Serving you since                : " + running_since.strftime("%d %b %Y %H:%M") + "\n"
        stats += "  Uptime                           : " + fancy_time(int(time.time() - self.ls.start)) + "\n"
        stats += "\n"
        stats += "  Servers in list                  : " + str(local) + "\n"
        stats += "  Mirrored servers                 : " + str(mirrored) + "\n"
        stats += "\n"
        stats += "  Players in servers               : [" + str(players) + "/" + str(max) + "]\n"
        stats += "\n"
        stats += "  Connected list server mirrors    : " + str(len(self.ls.remotes)) + " remote list servers\n"

        for remote in self.ls.remotes:
            stats += "                                     -> " + remote + "\n"

        stats += "\n"
        stats += "  Running j2lsnek v" + config.VERSION + " by stijn\n"
        stats += "  Source available at https://github.com/stijnstijn/j2lsnek\n\n"
        stats += "  Bye!\n\n"
        stats += "+----------------------------------------------------------------------+\n"

        self.msg(stats)
        self.end()
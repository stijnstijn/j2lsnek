import time
from datetime import datetime

import config
from helpers.functions import fancy_time, fetch_all
from helpers.handler import port_handler


class stats_handler(port_handler):
    """
    Serve server statistics
    """

    def handle_data(self):
        """
        Calculate some list server statistics, show a nicely formatted list and immediately close connection
        """
        self.ls.log.info("Sending list stats to %s" % self.ip)

        running_since = datetime.fromtimestamp(self.ls.start)
        self.cleanup()
        servers = fetch_all("SELECT * FROM servers WHERE name != ''")
        mirrors = fetch_all("SELECT * FROM mirrors ORDER BY lifesign DESC")

        total = 0
        mirrored = 0
        local = 0
        players = 0
        max_players = 0

        for server in servers:
            total += 1
            if server["remote"] == 1:
                mirrored += 1
            else:
                local += 1

            players += server["players"]
            max_players += server["max"]

        # don't count ourselves
        mirror_count = len(mirrors) - 1
        suffix = "" if mirror_count == 1 else "s"

        stats = "+----------------------------------------------------------------------+\n\n"
        stats += "                Jazz Jackrabbit 2 List Server statistics\n"
        stats += "\n"
        stats += "\n"
        stats += "  This server                      : " + self.ls.address + "\n"
        stats += "  Serving you since                : " + running_since.strftime("%d %b %Y %H:%M") + "\n"
        stats += "  Uptime                           : " + fancy_time(int(time.time() - self.ls.start)) + "\n"
        stats += "\n"
        stats += "  Servers listed locally           : " + str(local) + "\n"
        stats += "  Mirrored servers                 : " + str(mirrored) + "\n"
        stats += "  Total                            : " + str(mirrored + local) + "\n"
        stats += "\n"
        stats += "  Players in servers               : [" + str(players) + "/" + str(max_players) + "]\n"
        stats += "\n"
        stats += "  Connected list server mirrors    : " + str(mirror_count) + " other list server" + suffix + "\n"

        for mirror in mirrors:
            if mirror["address"] == self.ls.ip:  # don't count ourselves
                continue
            stats += "                                     -> " + mirror["name"]
            if int(mirror["lifesign"]) < int(time.time()) - 600:
                stats += " (inactive)\n"
            else:
                stats += "\n"

        stats += "\n"
        stats += "  Running j2lsnek v" + config.VERSION + " by stijn\n"
        stats += "  Source available at https://github.com/stijnstijn/j2lsnek\n\n"
        stats += "  Bye!\n\n"
        stats += "+----------------------------------------------------------------------+\n"

        self.msg(stats)
        self.end()

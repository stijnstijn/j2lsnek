import time

from helpers.handler import port_handler


class motd_handler(port_handler):
    """
    Serve Message of the Day
    """

    def handle_data(self):
        """
        Return MOTD and immediately close connection
        """
        self.ls.log.info("Sending MOTD to %s" % self.ip)

        motd = self.fetch_one("SELECT value FROM settings WHERE item = ?", ('motd',))
        expires = self.fetch_one("SELECT value FROM settings WHERE item = ?", ('motd_expires',))

        if not expires:
            expires = {"value": time.time() + 10}

        if motd and motd != "" and int(time.time()) < expires["value"]:
            self.msg(motd["value"] + "\n")
        else:
            self.msg("")

        self.end()

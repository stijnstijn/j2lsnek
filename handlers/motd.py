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

        if motd:
            self.msg(motd["value"] + "\n")
        else:
            self.msg("jj2 aint dead\n")

        self.end()

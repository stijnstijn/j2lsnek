from helpers.classes import port_handler


class motd_handler(port_handler):
    """
    Serve Message of the Day
    """

    def handle_data(self):
        """
        Return MOTD and immediately close connection
        """
        self.ls.log("Sending MOTD to %s" % self.ip)

        motd = self.query("SELECT value FROM settings WHERE item = ?", ('motd',)).fetchone()

        if motd:
            self.msg(motd["value"] + "\n")
        else:
            self.msg("jj2 aint dead\n")

        self.end()
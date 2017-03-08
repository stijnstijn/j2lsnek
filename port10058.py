import time

from helpers import port_handler


## Message of the day
class motd_handler(port_handler):
    def handle_data(self):
        """
        Return MOTD and immediately close connection
        """
        motd = "jj2 aint dead\n"

        self.msg(motd)
        self.end()
import socket
import ssl
import threading
import time

import config
from handlers.api import servernet_handler
from handlers.asciilist import ascii_handler
from handlers.binarylist import binary_handler
from handlers.liveserver import server_handler
from handlers.motd import motd_handler
from handlers.statistics import stats_handler
from helpers.functions import whitelisted, banned


class port_listener(threading.Thread):
    """
    Threaded port listener
    Opens a socket that listens on a port and creates handlers when someone connects
    """
    connections = {}
    ticker = {}
    looping = True

    def __init__(self, port=None, ls=None):
        """
        Check if all data is available and assign object vars

        :param port: Port at which to listen
        :param ls: List server object, for logging etc
        """
        threading.Thread.__init__(self)

        if not port or not ls:
            raise TypeError("port_handler expects port and list server object as argument")

        self.port = port
        self.ls = ls

    def run(self):
        """
        Loops infinitely; when a client connects, a handler is started in a new thread to process the connection

        :return: Nothing
        """
        server = socket.socket()
        address = "" if self.port != 10059 else "localhost"  # 10059 should only be accessible via localhost

        try:
            server.bind((address, self.port))
        except OSError:
            self.ls.log.error("WARNING! Port %s:%s is already in use! List server is NOT listening at this port!" % (
            address, self.port))
            return
        except ConnectionRefusedError:
            self.ls.log.error("WARNING! OS refused listening at %s:%s! List server is NOT listening at this port!" % (
            address, self.port))
            return

        server.listen(5)
        server.settimeout(5)
        self.ls.log.info("Opening socket listening at port %s" % self.port)

        while self.looping:
            try:
                # in case of port 10059, we authenticate via SSL certificates, since else anyone running on localhost
                # may interact with the list server API
                if self.port == 10059:
                    unwrapped_client, address = server.accept()
                    client = ssl.wrap_socket(unwrapped_client, server_side=True, certfile=config.CERTFILE,
                                             keyfile=config.KEYFILE)
                else:
                    client, address = server.accept()
            except socket.timeout:
                continue  # no problemo, just listen again - this only times out so it won't hang the entire app when
                # trying to exit, as there's no other way to easily interrupt accept()
            except ssl.SSLError as e:
                self.ls.log.error("Could not establish SSL connection: %s" % e)
                continue

            # check if banned (unless whitelisted)
            is_whitelisted = whitelisted(address[0])  # needed later, so save value
            if banned(address[0]) and not is_whitelisted:
                self.ls.log.warning("IP %s attempted to connect but matches banlist, refused" % address[0])
                continue

            # check if to be throttled - each connection made adds a "tick", and when those exceed a max value
            # connection is refused until the tick count decays below that max value
            now = int(time.time())
            ticks = 0
            if not is_whitelisted and address[0] in self.ticker:
                ticks = self.ticker[address[0]][0]
                last_tick = self.ticker[address[0]][1]
                decay = (now - last_tick) * config.TICKSDECAY
                ticks -= decay

                if ticks > config.TICKSMAX:
                    self.ls.log.warning("IP %s hit rate limit, throttled" % address[0])
                    self.ticker[address[0]] = [ticks, now]
                    continue

            if not is_whitelisted:
                self.ticker[address[0]] = [max(ticks + 1, 1), now]

            key = address[0] + ":" + str(address[1])

            if self.port == 10053:
                self.connections[key] = binary_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10054:
                self.connections[key] = server_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10055:
                self.connections[key] = stats_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10056 or self.port == 10059:
                self.connections[key] = servernet_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10057:
                self.connections[key] = ascii_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10058:
                self.connections[key] = motd_handler(client=client, address=address, ls=self.ls, port=self.port)
            elif self.port == 10059:
                self.connections[key] = servernet_handler(client=client, address=address, ls=self.ls, port=self.port)
            else:
                raise NotImplementedError("No handler class available for port %s" % self.port)
            self.connections[key].start()

            # remove IPs that haven't been seen for a long time
            for ip in self.ticker:
                if self.ticker[ip][1] < now - config.TICKSMAXAGE:
                    self.ticker.pop(ip, None)

            # remove connections that have finished
            stale_connections = []
            for key in self.connections:
                if not self.connections[key].is_alive():
                    stale_connections.append(key)  # can't change self.connections while we're looping through it

            for key in stale_connections:
                del self.connections[key]

            del stale_connections

            time.sleep(config.MICROSLEEP)

        return

    def halt(self):
        """
        Stop listening

        Stops the main loop and signals all active handlers to stop what they're doing and rejoin the listener thread.

        :return:
        """
        self.looping = False

        self.ls.log.info("Waiting for handlers on port %s to finish..." % self.port)
        for key in self.connections:
            self.connections[key].halt()
            self.connections[key].join()

import threading
import socket
import time
import ssl

import config
from handlers.api import servernet_handler
from handlers.asciilist import ascii_handler
from handlers.binarylist import binary_handler
from handlers.liveserver import server_handler
from handlers.motd import motd_handler
from handlers.statistics import stats_handler
from helpers.functions import banned, whitelisted


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
        if not self.looping:
            return False  # shutting down, don't accept new connections

        # in case of port 10059, we authenticate via SSL certificates, since else anyone running on localhost
        # may interact with the list server API
        if self.port == 10059:
            unwrapped_server = socket.socket()
            server = ssl.wrap_socket(unwrapped_server, server_side=True, certfile=config.CERTFILE,
                                     ca_certs=config.CERTCHAIN, keyfile=config.CERTKEY)
            address = "localhost"
        else:
            server = socket.socket()
            address = ""

        # this makes sure sockets are available immediate after closing instead of waiting for late packets
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # because we may still run into TIME_WAIT, try opening the socket every 5 seconds until we have a connection
        # or 5 minutes have passed, in the latter case we assume there's something wrong and give up
        has_time = True
        start_trying = int(time.time())
        while has_time:
            has_time = start_trying > time.time() - 300  # stop trying after 5 minutes
            try:
                server.bind((address, self.port))
                break
            except OSError as e:
                if has_time and self.looping:
                    self.ls.log.info("Could not open port %s yet (%s), retrying in 5 seconds" % (self.port, e.strerror))
                    time.sleep(5.0)  # wait a few seconds before retrying
                    continue
                self.ls.log.error(
                    "WARNING! Port %s:%s is already in use and could not be released! List server is NOT listening at this port!" % (
                        address, self.port))
                return
            except ConnectionRefusedError:
                self.ls.log.error(
                    "WARNING! OS refused listening at %s:%s! List server is NOT listening at this port!" % (
                        address, self.port))
                return

        server.listen(5)
        server.settimeout(5)
        self.ls.log.info("Opening socket listening at port %s" % self.port)

        while self.looping:
            try:
                client, address = server.accept()
            except (socket.timeout, TimeoutError):
                if not self.looping:
                    break
                continue  # no problemo, just listen again - this only times out so it won't hang the entire app when
                # trying to exit, as there's no other way to easily interrupt accept()
            except ssl.SSLError as e:
                if not self.looping:
                    break
                self.ls.log.error("Could not establish SSL connection: %s" % e)
                continue

            # if halt signal was given between calling server.accept() and someone connecting
            if not self.looping:
                self.ls.log.info("Not accepting connection from %s, restarting has priority" % address[0])
                client.shutdown(socket.SHUT_WR)
                client.close()
                break  # shutting down, don't accept new connections

            # check if banned, don't start handler if so
            if banned(address[0]):
                self.ls.log.warning("IP %s attempted to connect but matches banlist, refused" % address[0])
                continue

            # check if to be throttled - each connection made adds a "tick", and when those exceed a max value
            # connection is refused until the tick count decays below that max value
            now = int(time.time())
            #ticks = 0
            #is_whitelisted = whitelisted(address[0])
            #if not is_whitelisted and address[0] in self.ticker:
            #    ticks = self.ticker[address[0]][0]
            #    last_tick = self.ticker[address[0]][1]
            #    decay = (now - last_tick) * config.TICKSDECAY
            #    ticks -= decay

            #    if ticks > config.TICKSMAX:
            #        self.ls.log.warning("IP %s hit rate limit, throttled" % address[0])
            #        self.ticker[address[0]] = [ticks, now]
            #        continue

            #if not is_whitelisted:
            #    self.ticker[address[0]] = [max(ticks + 1, 1), now]

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

        self.ls.log.info("Waiting for handlers on port %s to finish..." % self.port)
        server.close()

        # give all handlers the signal to stop whatever they're doing
        for key in self.connections:
            if self.connections[key].looping:
                self.connections[key].halt()

        # now make sure they're all finished
        for key in self.connections:
            self.connections[key].join()

        return

    def halt(self):
        """
        Stop listening

        Stops the main loop and signals all active handlers to stop what they're doing and rejoin the listener thread.

        :return:
        """
        self.looping = False

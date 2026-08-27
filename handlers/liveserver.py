import socket
import config
import time

from helpers.functions import decode_mode, decode_version

from helpers.jj2 import jj2server
from helpers.handler import port_handler
from helpers.functions import banned, whitelisted, fetch_one


class server_handler(port_handler):
    """
    Handle server status updates
    """

    def handle_data(self):
        """
        Handle the connection with live servers; update server data and list/delist when needed
        """

        server = jj2server(self.key)
        new = True  # server is always new when connection is opened
        self.client.settimeout(10)  # time out in 10 seconds unless further data is received
        self.ls.log.info(f"Server connected from {self.key}")
        broadcast = False

        # keep connection open until server disconnects (or times out)
        try:
            while self.looping:
                try:
                    data = self.client.recv(1024)
                except (socket.timeout, TimeoutError):
                    # if no lifesign for 30 seconds, ping to see if the server is still alive
                    data = None
                    try:
                        ping = self.client.send(bytearray([0]))
                    except (socket.timeout, TimeoutError, ConnectionError) as e:
                        self.ls.log.info(f"Server {self.key} did not respond to ping ({e}), delisting")
                        break
                    if ping == 1:
                        self.ls.log.info(f"Ping from server {self.key}")
                        server.update_lifesign()
                    else:
                        self.ls.log.info(f"Server from {self.key} timed out")
                        break
                except Exception as e:
                    self.ls.log.info(f"Server {self.key} closed: {e.__class__.__name__} ({e})")
                    break

                if banned(self.ip):
                    self.ls.log.warning(f"Delisting server from banned IP {self.ip}")
                    break

                # new server wants to get listed
                if new and data and len(data) == 42:
                    # check for spamming
                    other = fetch_one("SELECT COUNT(*) FROM servers WHERE ip = ?", (self.ip,))[0]
                    if other >= config.MAXSERVERS and not whitelisted(self.ip):
                        self.ls.log.warning(f"IP {self.ip} attempted to list server, but has 2 listed servers already")
                        self.error_msg("Too many connections from this IP address")
                        break

                    self.ls.log.info(f"Server listed from {self.key}")
                    self.client.settimeout(32)  # should have some form of communication every 30 seconds, with some leeway

                    new = False

                    port = int.from_bytes(data[0:2], byteorder="little")
                    exists = fetch_one("SELECT COUNT(*) FROM servers WHERE ip = ? AND port = ?", (self.ip, port))[0]
                    if exists > 0:
                        self.ls.log.warning(f"Server {self.ip} tried to connect on port {port}, but port already in use; refusing")
                        self.error_msg("Reconnecting too fast: please wait a few seconds before relisting")
                        break

                    name = server.validate_name(data[2:32].decode("ascii", "ignore"), self.ip,
                                                f"Server on {self.ip}")

                    players = int(data[35])
                    max_players = int(data[36])
                    flags = int(data[37])
                    version = data[38:]

                    mode = (flags >> 1) & 31

                    server.set("name", name)
                    server.set("private", flags & 1)
                    server.set("plusonly", flags & 128)
                    server.set("ip", self.ip)
                    server.set("port", port)
                    server.set("players", players)
                    server.set("max", max_players)
                    server.set("mode", decode_mode(mode))
                    server.set("version", decode_version(version))
                    server.set("origin", self.ls.address)

                    broadcast = True

                # existing server sending an update
                elif not new and data and (len(data) == 2 or data[0] == 0x02):
                    broadcast = True
                    if data[0] == 0:
                        if server.get("players") != data[1]:
                            self.ls.log.info(f"Updating player count for server {self.key}")
                            server.set("players", data[1])
                        else:
                            self.ls.log.info(f"Received ping from server {self.key}")
                            server.update_lifesign()
                    elif data[0] == 0x01:
                        self.ls.log.info(f"Updating game mode for server {self.key}")
                        server.set("mode", decode_mode(int(data[1])))
                    elif data[0] == 0x02:
                        self.ls.log.info(f"Updating server name for server {self.key}")
                        name = server.validate_name(data[1:33].decode("ascii", "ignore"), self.ip,
                                                    f"Server on {self.ip}")
                        server.set("name", name)
                    elif data[0] == 0x03:
                        self.ls.log.info(f"Updating max players for server {self.key}")
                        server.set("max", data[1])
                    elif data[0] == 0x04:
                        self.ls.log.info(f"Updating public/private for server {self.key}")
                        server.set("private", data[1] & 1)
                    elif data[0] == 0x05:
                        self.ls.log.info(f"Updating plusonly for server {self.key}")
                        server.set("plusonly", data[1] & 1)

                # server wants to be delisted, goes offline or sends strange data
                else:
                    if not new:
                        if data is not None and ( len(data) == 0 or (data[0] == 0x00 and len(data) > 16) ):
                            # this usually means the server has closed
                            if len(data) > 16:
                                self.ls.log.info(f"Server sent goodbye: {data}")
                            self.ls.log.info(f"Server from {self.key} closed; delisting")
                            break
                        elif data is not None:
                            self.ls.log.info(f"Received empty data from server {self.key} ({data}), ignoring")
                    else:
                        self.ls.log.warning(f"Server from {self.key} provided faulty listing data: not listed")
                        self.error_msg("Invalid data received")
                        break

                # broadcast updates to connected mirrors
                if broadcast:
                    self.ls.broadcast(action="server", data=[server.flush_updates()])

                time.sleep(config.MICROSLEEP)

        except Exception as e:
            self.ls.log.info(f"Server {self.key} raised unexpected exception during handling and will be unlisted: "
                             f"{e.__class__.__name__} ({e})")

        finally:
            # server presumed dead, remove from database
            server.forget()

        # make sure mirrors also delist the server
        self.ls.broadcast(action="delist", data=[server.data])

        self.end()

import socket
import json
import time

from helpers.port_handler import port_handler

from helpers.jj2server import jj2server


class servernet_handler(port_handler):
    """
    Sync data between list servers

    Lots of checking to ensure that incoming data is kosher
    """
    def handle_data(self):
        self.client.settimeout(5)  # should really be enough
        loops = 0
        payload = None
        self.buffer = bytearray()

        # only allowed remotes, plus localhost since that's where admin interfaces live
        if self.port == 10059:
            if self.ip != "127.0.0.1":
                self.ls.log.error("Outside IP %s tried connection to remote admin API" % self.ip)
                self.end()
                return
            # SSL validity check here?
        elif self.ip not in self.ls.remotes:
            self.ls.log.error("Unauthorized ServerNet connection from %s:%s" % (self.ip, self.port))
            self.end()
            return

        # receive API call
        while True:
            try:
                self.buffer.extend(self.client.recv(2048))
                loops += 1
            except socket.timeout:
                self.ls.log.warning("Server from %s timed out" % self.key)
                break

            try:
                payload = json.loads(self.buffer.decode("ascii"))
                break
            except ValueError:  # older python3s don't support json.JSONDecodeError
                pass

            if loops > 12:  # even our patience knows its limits
                break

        # if API call not received or readable for whatever reason, give up
        if not payload:
            self.ls.log.error("ServerNet update received from %s, but could not acquire valid payload" % self.ip)
            self.end()
            return

        # same for incomplete call
        if "action" not in payload or "data" not in payload or "origin" not in payload:
            self.ls.log.error("ServerNet update received from %s, but JSON was incomplete" % self.ip)
            self.end()
            return

        # this shouldn't happen, but just in case...
        if payload["origin"] == self.ls.address:
            self.end()
            return

        # payload data should be a list, though usually with 0 or 1 items
        try:
            pass_on = []
            for item in payload["data"]:
                if self.process_data(payload["action"], item):
                    pass_on.append(item)
        except TypeError:
            self.ls.log.error("ServerNet update received from %s, but data was not iterable" % self.ip)
            self.end()
            return

        # ok, payload is valid, process it
        self.ls.log.info("Received ServerNet update from %s: %s" % (self.ip, payload["action"]))

        # switch on the engine, pass it on
        no_broadcast = ["hello", "request", "delist"]
        if len(pass_on) > 0 and payload["action"] not in no_broadcast and payload["action"][0:4] != "get-" and payload["origin"] == "web":
            self.ls.broadcast(action=payload["action"], data=pass_on, ignore=[self.ip])

        self.end()
        return

    def process_data(self, action, data):
        """
        Process API calls

        :param action: Action/API call
        :param data: List of items to process for this action
        :return: True if call was succesful and can be passed on, False on failure or error
        """
        # server listings
        if action == "server":
            try:
                server = jj2server(data["id"])
            except KeyError:
                self.ls.log.error("Received incomplete server data from ServerNet connection %s" % self.ip)
                return False

            try:
                [server.set(key, data[key]) for key in data]
            except IndexError:
                self.ls.log.error("Received incomplete server data from ServerNet connection %s (unknown field %s)" % (self.ip, key))
                server.forget()
                return False
            server.set("remote", 1)

        # ban list (and whitelist) entries
        elif action == "add-banlist":
            if "origin" not in data:
                data["origin"] = self.ls.address

            try:
                if not self.fetch_one("SELECT * FROM banlist WHERE address = ? AND origin = ? AND type = ? AND note = ?",
                                         (data["address"], data["origin"], data["type"], data["note"])):
                    self.query("INSERT INTO banlist (address, origin, type, note) VALUES (?, ?, ?, ?)", (data["address"], data["origin"], data["type"], data["note"]))
            except KeyError:
                self.ls.log.error("Received incomplete banlist entry from ServerNet connection %s" % self.ip)
                return False

            self.ls.log.info("Added banlist entry via ServerNet connection %s" % self.ip)

        # removal of ban/whitelist entries
        elif action == "delete-banlist":
            if "origin" not in data:
                data["origin"] = self.ls.address

            try:
                self.fetch_one("DELETE FROM banlist WHERE address = ? AND origin = ? AND type = ? AND note = ?",
                                (data["address"], data["origin"], data["type"], data["note"]))
            except KeyError:
                self.ls.log.error("Received incomplete banlist deletion request from ServerNet connection %s" % self.ip)
                return False

            self.ls.log.info("Removed banlist entry via ServerNet connection %s" % self.ip)

        # server delistings
        elif action == "delist":
            try:
                server = jj2server(data["id"])
                if server.get("remote") == 1:
                    server.forget()
            except KeyError:
                self.ls.log.error("Received incomplete server data from ServerNet connection %s" % self.ip)
                return False

            self.ls.log.info("Delisted server via ServerNet connection %s" % self.ip)

        # add remote
        elif action == "add-remote":
            try:
                if self.fetch_one("SELECT * FROM remotes WHERE name = ? OR address = ?", (data["name"], data["address"])):
                    self.ls.log.info("Remote %s tried adding remote %s, but name or address already known" % (self.ip, data["address"]))
                    return True
            except KeyError:
                self.ls.log.error("Received incomplete remote info from ServerNet connection %s" % self.ip)
                return False

            if data["name"] == "web":
                self.ls.log.error("'web' is a reserved name for remotes, %s tried using it" % self.ip)
                return False

            self.query("INSERT INTO remotes (name, address) VALUES (?, ?)", (data["name"], data["address"]))
            self.ls.add_remote(data["address"])
            self.ls.broadcast(action="hello", data=[{"from": self.ls.address}], recipients=[data["address"]])

            self.ls.log.info("Added remote %s via ServerNet connection %s" % (data["address"], self.ip))

        # delete remote
        elif action == "delete-remote":
            try:
                if not self.fetch_one("SELECT * FROM remotes WHERE name = ? AND address = ?", (data["name"], data["address"])):
                    self.ls.log.info("Remote %s tried removing remote %s, but not known" % (self.ip, data["address"]))
                    return True
            except KeyError:
                self.ls.log.error("Received incomplete remote deletion request from ServerNet connection %s" % self.ip)
                return False

            self.query("DELETE FROM remotes WHERE name = ? AND address = ?", (data["name"], data["address"]))
            self.ls.delete_remote(data["address"])

            self.ls.log.info("Deleted remote %s via ServerNet connection %s" % (data["address"], self.ip))

        # motd updates
        elif action == "set-motd":
            try:
                timestamp = self.fetch_one("SELECT value FROM settings WHERE item = ?", ("motd-updated",))
                if timestamp and int(timestamp["value"]) > int(data["motd-updated"]):
                    self.ls.log.info("Received MOTD update from %s, but own MOTD was more recent" % self.ip)
                    return False
            except KeyError:
                self.ls.log.error("Received incomplete MOTD from ServerNet connection %s" % self.ip)
                return False

            self.query("UPDATE settings SET value = ? WHERE item = ?", (data["motd"], "motd"))
            self.query("UPDATE settings SET value = ? WHERE item = ?", (int(time.time()), "motd-updated"))

            self.ls.log.info("Updated MOTD via ServerNet connection %s" % self.ip)

        # sync requests: send all data
        elif action == "request" or action == "hello":
            # in case of "hello", also send a request for data to the other server
            if action == "hello":
                self.ls.broadcast(action="request", data=[{"from": self.ls.address}], recipients=[self.ip])

            self.cleanup()  # removes stale servers, etc

            # servers
            servers = self.fetch_all("SELECT * FROM servers WHERE players > 0 AND origin = ?", (self.ls.address,))
            self.ls.broadcast(action="server", data=[{key: server[key] for key in server.keys()} for server in servers], recipients=[self.ip])

            # banlist
            banlist = self.fetch_all("SELECT * FROM banlist WHERE global = 1 AND origin = ?", (self.ls.address,))
            self.ls.broadcast(action="ban", data=[{key: ban[key] for key in ban.keys()} for ban in banlist], recipients=[self.ip])

            # remotes
            remotes = self.fetch_all("SELECT * FROM remotes")
            self.ls.broadcast(action="add-remote", data=[{key: remote[key] for key in remote.keys()} for remote in remotes], recipients=[self.ip])

            # motd
            settings = self.fetch_all("SELECT * FROM settings WHERE item IN (?, ?)", ("motd", "motd-updated"))
            self.ls.broadcast(action="set-motd", data=[{item["item"]: item["value"] for item in settings}], recipients=[self.ip])

            self.ls.log.info("Sent sync data to ServerNet connection %s" % self.ip)

        # retrieve server list
        elif action == "get-servers":
            self.cleanup()
            servers = self.fetch_all("SELECT * FROM servers ORDER BY private ASC, players DESC, created ASC")

            self.msg(json.dumps([dict(servers[i]) for i, value in enumerate(servers)]))

        # retrieve banlist
        elif action == "get-banlist":
            banlist = self.fetch_all("SELECT * FROM banlist")

            self.msg(json.dumps([dict(banlist[i]) for i, value in enumerate(banlist)]))

        # retrieve motd
        elif action == "get-motd":
            motd = self.fetch_one("SELECT * FROM settings WHERE item = ?", ("motd",))

            self.msg(json.dumps(motd["value"]))

        # retrieve remotes
        elif action == "get-remotes":
            remotes = self.fetch_all("SELECT * FROM remotes")

            self.msg(json.dumps([dict(remotes[i]) for i, value in enumerate(remotes)]))

        return True
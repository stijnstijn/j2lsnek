import datetime
import pathlib
import socket
import json
import time

from helpers.handler import port_handler
from helpers.jj2 import jj2server
from helpers.functions import all_mirrors, query, fetch_all, fetch_one
from helpers.exceptions import ServerUnknownException


class servernet_handler(port_handler):
    """
    Sync data between list servers
    """
    reload_mode = None

    def handle_data(self):
        """
        Handle incoming API calls

        Lots of checking to ensure that incoming data is kosher, then processing and passing it on to other mirrors
        """
        self.client.settimeout(5)  # should really be enough
        loops = 0
        payload = None
        self.buffer = bytearray()

        # only allowed mirrors, plus localhost for 10059 since that's where admin interfaces live
        if self.port == 10059:
            if self.ip != "127.0.0.1":
                self.ls.log.warning("Outside IP %s tried connection to remote admin API" % self.ip)
                self.end()
                return
        elif self.port == 10056:
            if self.ip not in all_mirrors() or self.ip == "127.0.0.1" or self.ip == self.ls.ip:
                self.ls.log.warning("Unauthorized ServerNet connection from %s:%s" % (self.ip, self.port))
                self.end()
                return
            query("UPDATE mirrors SET lifesign = ? WHERE address = ?", (int(time.time()), self.ip))

        # receive API call
        while True:
            try:
                self.buffer.extend(self.client.recv(2048))
                loops += 1
            except (socket.timeout, TimeoutError):
                self.ls.log.error("ServerNet connection from %s timed out while receiving data" % self.key)
                break

            try:
                payload = json.loads(self.buffer.decode("ascii", "ignore"))
                break
            except ValueError:  # older python3s don't support json.JSONDecodeError
                pass

            if loops > 12:  # even our patience knows its limits
                break

        # if API call not received or readable for whatever reason, give up
        if not payload:
            if len(self.buffer) > 0:
                self.ls.log.error("ServerNet update received from %s, but could not acquire valid payload (got %s)" % (
                self.ip, self.buffer.decode("ascii", "ignore")))
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
        no_broadcast = ["hello", "request", "delist", "request-log", "send-log", "request-log-from"]
        if self.port == 10059 and len(pass_on) > 0 and payload["action"] not in no_broadcast and \
                        payload["action"][0:4] != "get-" and payload["origin"] == "web":
            self.ls.broadcast(action=payload["action"], data=pass_on, ignore=[self.ip])

        self.end()

        # was a reload command given?
        if self.reload_mode is not None:
            self.ls.reload(mode=self.reload_mode)

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
                self.ls.log.error(
                    "Received incomplete server data from ServerNet connection %s (unknown field in %s)" % (
                        self.ip, repr(data)))
                server.forget()
                return False
            server.set("remote", 1)

            # we can't do anything with partial data
            if server.new and (server.get("ip") is None or server.get("port") is None):
                # this means we got a server update before the server has been first 'registered'
                # that could happen if an earlier all-server update is missed somehow
                server.forget()

        # ban list (and whitelist) entries
        elif action == "add-banlist":
            if "origin" not in data:
                data["origin"] = self.ls.address
            try:
                if not fetch_one(
                        "SELECT * FROM banlist WHERE address = ? AND type = ? AND note = ? AND origin = ? AND reserved = ?",
                        (data["address"], data["type"], data["note"], data["origin"], data["reserved"])):
                    query("INSERT INTO banlist (address, type, note, origin, reserved) VALUES (?, ?, ?, ?, ?)",
                               (data["address"], data["type"], data["note"], data["origin"], data["reserved"]))
            except KeyError:
                self.ls.log.error("Received incomplete banlist entry from ServerNet connection %s" % self.ip)
                return False

            self.ls.log.info("Added banlist entry via ServerNet connection %s" % self.ip)

        # removal of ban/whitelist entries
        elif action == "delete-banlist":
            if "origin" not in data:
                data["origin"] = self.ls.address
            try:
                fetch_one("DELETE FROM banlist WHERE address = ? AND type = ? AND note = ? AND origin = ? AND reserved = ?",
                               (data["address"], data["type"], data["note"], data["origin"], data["reserved"]))
            except KeyError:
                self.ls.log.error("Received incomplete banlist deletion request from ServerNet connection %s" % self.ip)
                return False

            self.ls.log.info("Removed banlist entry via ServerNet connection %s" % self.ip)

        # server delistings
        elif action == "delist":
            try:
                server = jj2server(data["id"], create_if_unknown=False)
                if server.get("remote") == 1 or server.new:
                    server.forget()
                else:
                    self.ls.log.error("Mirror %s tried delisting server %s, but server is not remote!" % (self.ip, data["id"]))
            except ServerUnknownException:
                # trying to delist a server we have no memory of? no
                self.ls.log.error(
                    "Mirror %s tried delisting server %s, but server is unknown" % (self.ip, data["id"]))
                return False
            except KeyError:
                self.ls.log.error("Received incomplete server data from ServerNet connection %s" % self.ip)
                return False

            self.ls.log.info("Delisted server via ServerNet connection %s" % self.ip)

        # add mirror
        elif action == "add-mirror":
            try:
                if fetch_one("SELECT * FROM mirrors WHERE name = ? OR address = ?",
                                  (data["name"], data["address"])):
                    self.ls.log.info("Mirror %s tried adding mirror %s, but name or address already known" % (
                        self.ip, data["address"]))
                    return True
            except KeyError:
                self.ls.log.error("Received incomplete mirror info from ServerNet connection %s" % self.ip)
                return False

            if data["name"] == "web":
                self.ls.log.error("'web' is a reserved name for mirrors, %s tried using it" % self.ip)
                return False

            query("INSERT INTO mirrors (name, address) VALUES (?, ?)", (data["name"], data["address"]))
            self.ls.broadcast(action="hello", data=[{"from": self.ls.address}], recipients=[data["address"]])

            self.ls.log.info("Added mirror %s via ServerNet connection %s" % (data["address"], self.ip))

        # delete mirror
        elif action == "delete-mirror":
            try:
                if not fetch_one("SELECT * FROM mirrors WHERE name = ? AND address = ?",
                                      (data["name"], data["address"])):
                    self.ls.log.info("Mirror %s tried removing mirror %s, but not known" % (self.ip, data["address"]))
                    return True
            except KeyError:
                self.ls.log.error("Received incomplete mirror deletion request from ServerNet connection %s" % self.ip)
                return False

            query("DELETE FROM mirrors WHERE name = ? AND address = ?", (data["name"], data["address"]))

            self.ls.log.info("Deleted mirror %s via ServerNet connection %s" % (data["address"], self.ip))

        # motd updates
        elif action == "set-motd":
            if "expires" not in data or data["expires"] == "":
                t = datetime.datetime.utcfromtimestamp(time.time() + 86400 * 3)
                data["expires"] = t.strftime("%d-%m-%Y %H:%M")
            try:
                timestamp = fetch_one("SELECT value FROM settings WHERE item = ?", ("motd-updated",))
                if timestamp and int(timestamp["value"]) > int(data["motd-updated"]):
                    self.ls.log.info("Received MOTD update from %s, but own MOTD was more recent" % self.ip)
                    return False
            except KeyError:
                self.ls.log.error("Received incomplete MOTD from ServerNet connection %s" % self.ip)
                return False

            try:
                expires = datetime.datetime.strptime(data["expires"], "%d-%m-%Y %H:%M")
                expires = expires.timestamp()
            except (ValueError, OSError):
                expires = int(time.time()) + 86400 * 3

            query("UPDATE settings SET value = ? WHERE item = ?", (data["motd"], "motd"))
            query("UPDATE settings SET value = ? WHERE item = ?", (int(time.time()), "motd-updated"))
            query("UPDATE settings SET value = ? WHERE item = ?", (int(expires), "motd-expires"))

            self.ls.log.info("Updated MOTD via ServerNet connection %s" % self.ip)

        # sync requests: send all data
        elif action == "request" or action == "hello":
            # in case of "hello", also send a request for data to the other server
            if action == "hello":
                self.ls.broadcast(action="request", data=[{"from": self.ls.address}], recipients=[self.ip])

            self.cleanup()  # removes stale servers, etc

            # servers
            if "fragment" not in data or "servers" in data["fragment"]:
                servers = fetch_all("SELECT * FROM servers WHERE players > 0 AND origin = ?", (self.ls.address,))
                self.ls.broadcast(action="server", data=[{key: server[key] for key in server.keys()} for server in servers],
                              recipients=[self.ip])

            # banlist
            if "fragment" not in data or "banlist" in data["fragment"]:
                banlist = fetch_all("SELECT * FROM banlist")
                self.ls.broadcast(action="add-banlist", data=[{key: ban[key] for key in ban.keys()} for ban in banlist],
                              recipients=[self.ip])

            # mirrors
            if "fragment" not in data or "mirrors" not in data["fragment"]:
                mirrors = fetch_all("SELECT name, address FROM mirrors")
                self.ls.broadcast(action="add-mirror",
                              data=[{key: mirror[key] for key in mirror.keys()} for mirror in mirrors],
                              recipients=[self.ip])

            # motd
            if "fragment" not in data or "motd" in data["fragment"]:
                settings = fetch_all("SELECT * FROM settings WHERE item IN (?, ?)", ("motd", "motd-updated"))
                self.ls.broadcast(action="set-motd", data=[{item["item"]: item["value"] for item in settings}],
                              recipients=[self.ip])

            self.ls.log.info("Sent sync data to ServerNet connection %s" % self.ip)

        elif action == "request-log-from":
            # make the list server request logs from a mirror
            if "from" not in data:
                return False

            try:
                lines = int(data["lines"])
            except (ValueError, KeyError):
                lines = 10

            self.ls.broadcast(action="request-log", data={"lines": lines}, recipients=[data["from"]])

        elif action == "request-log":
            # request recent x lines of log data from a mirror
            try:
                lines = int(data["lines"])
            except (ValueError, KeyError):
                lines = 10

            lines = min(1, lines)

            log_file = pathlib.Path(__file__).parent.parent.joinpath("j2lsnek.log")
            if not log_file.exists():
                return False

            log = []
            with log_file.open() as input:
                for line in input:
                    if len(log) > lines:
                        log = log[1:]

                    log.append(line)

            self.ls.broadcast(action="send-log", data=log, recipients=[self.ip])

        elif action == "send-log":
            # send recent lines of log data upon request
            recv_log_file = pathlib.Path(__file__).parent.parent.joinpath("log-recv-%s-%i.log" % (self.ip, int(time.time())))
            with recv_log_file.open("w") as output:
                for line in data:
                    output.write(line)

        # reload config, etc
        elif action == "reload":
            if "mode" in data:
                if data["mode"] == "restart":
                    self.reload_mode = 2
                if data["mode"] == "reboot":
                    self.reload_mode = 3
            else:
                self.reload_mode = 1
            return True

        # retrieve server list
        elif action == "get-servers":
            self.cleanup()
            servers = fetch_all("SELECT * FROM servers ORDER BY prefer DESC, private ASC, (players = max) ASC, players DESC, created ASC")

            self.msg(json.dumps([dict(servers[i]) for i, value in enumerate(servers)]))

        # retrieve banlist
        elif action == "get-banlist":
            banlist = fetch_all("SELECT * FROM banlist")

            self.msg(json.dumps([dict(banlist[i]) for i, value in enumerate(banlist)]))

        # retrieve motd
        elif action == "get-motd":
            expires = fetch_one("SELECT * FROM settings WHERE item = ?", ("motd-expires",))
            if not expires:
                expires = time.time() + 10  # idk
            else:
                expires = expires["value"]

            if time.time() > int(expires):
                motd = {"value": ""}
            else:
                motd = fetch_one("SELECT * FROM settings WHERE item = ?", ("motd",))

            self.msg(json.dumps(motd["value"]))

        # retrieve motd
        elif action == "get-motd-expires":
            motd = fetch_one("SELECT * FROM settings WHERE item = ?", ("motd-expires",))

            if not motd or motd["value"] == "":
                self.msg(json.dumps(int(time.time())))
            else:
                self.msg(json.dumps(motd["value"]))

        # retrieve mirrors
        elif action == "get-mirrors":
            mirrors = fetch_all("SELECT name, address FROM mirrors")

            self.msg(json.dumps([dict(mirrors[i]) for i, value in enumerate(mirrors)]))

        # ping, no response required, lifesign already updated above
        elif action == "ping":
            return False

        return True

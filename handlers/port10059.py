import socket
import json
import time

from helpers.port_handler import port_handler


class api_handler(port_handler):
    """
    Remote admin API

    Allows list server admins to manage the server. The front-end can be anything (e.g. a website) - it should
    call this API to manipulate JJ2 servers, banlist entries or server settings.

    Calls should follow the same general template as ServerNet messages, e.g. a JSON-encoded dictionary with two
    keys, "action" and "data" (both required).

    For security, this API can only be called from localhost, so the front-end should be hosted on the same machine
    as the list server itself (or use some sort of gateway if you really don't want to do that)

    Available commands are add-banlist, delete-banlist, add-remote, delete-remote and motd. See the code below for
    details, shorthand versions and data requirements.
    """

    def handle_data(self):
        """
        Handle calls and run ServerNet broadcasts when needed
        """
        if self.ip != "127.0.0.1":  # only available via localhost: end silently if called from outside
            self.end()

        # accept message
        self.client.settimeout(5)  # should really be enough
        loops = 0
        payload = None
        self.buffer = bytearray()

        while True:
            try:
                self.buffer.extend(self.client.recv(2048))
                loops += 1
            except socket.timeout:
                self.ls.log("API call timed out")
                break

            try:
                payload = json.loads(self.buffer.decode("ascii"))
                break
            except ValueError:  # older python3s don't support json.JSONDecodeError
                pass

            if loops > 12:  # even our patience knows its limits
                break

        if not payload:  # payload not received or readable for whatever reason, give up
            self.ls.log("API call with empty or unavailable payload received")
            self.error_msg("Malformed API request")
            self.end()
            return

        if not isinstance(payload, dict) or "action" not in payload or "data" not in payload or not isinstance(payload["data"], dict):
            self.ls.log("API call with malformed payload received")
            self.error_msg("Malformed API request")
            self.end()
            return

        # shorthand command for global ban/whitelisting; forward to handler for add-banlist
        if payload["action"] == "ban" or payload["action"] == "whitelist":
            if "address" not in payload["data"]:
                self.ls.log("Malformed API request (%s)" % payload["action"])
                self.error_msg("Malformed API request")
                self.end()
                return

            payload["data"] = {"address": payload["data"]["address"], "type": payload["action"], "origin": self.ls.address, "global": 1, "note": "(added via shorthand)"}
            payload["action"] = "add-banlist"

        # shorthand command for global unban/unwhitelisting; forward to handler for delete-banlist
        if payload["action"] == "unban" or payload["action"] == "unwhitelist":
            if "address" not in payload["data"]:
                self.ls.log("Malformed API request (%s)" % payload["action"])
                self.error_msg("Malformed API request")
                self.end()
                return

            payload["data"] = {"address": payload["data"]["address"], "type": payload["action"][2:], "origin": self.ls.address, "global": 1}
            payload["action"] = "delete-banlist"

        # add entry to banlist/whitelist
        if payload["action"] == "add-banlist":
            if "address" not in payload["data"] or "type" not in payload["data"] or "global" not in payload["data"] or "note" not in payload["data"]:
                self.ls.log("Malformed API request (add-banlist)")
                self.error_msg("Malformed API request")
                self.end()
                return

            if "origin" not in payload["data"]:
                payload["data"]["origin"] = self.ls.address

            self.query("INSERT INTO banlist (address, type, origin, global, note) VALUES (?, ?, ?, ?, ?)",
                            (payload["data"]["address"], payload["data"]["type"], payload["data"]["origin"], payload["data"]["global"], payload["data"]["note"]))

            if str(payload["data"]["global"]) == "1":
                self.ls.broadcast({"action": "ban", "data": payload["data"]})
            self.ls.log("Banlist entry added via API (%s)" % payload["data"]["address"])
            self.acknowledge()

        # remove entry from banlist/whitelist
        elif payload["action"] == "delete-banlist":
            if "address" not in payload["data"] or "type" not in payload["data"] or "origin" not in payload["data"] or "global" not in payload["data"] or "note" not in payload["data"]:
                self.ls.log("Malformed API request (delete-banlist)")
                self.error_msg("Malformed API request")
                self.end()
                return

            self.ls.log(repr(payload))
            self.query("DELETE FROM banlist WHERE address = ? AND type = ? AND origin = ? AND global = ? AND note = ?",
                            (payload["data"]["address"], payload["data"]["type"], payload["data"]["origin"], payload["data"]["global"], payload["data"]["note"]))

            if str(payload["data"]["global"]) == "1":
                self.ls.broadcast({"action": "unban", "data": payload["data"]})
            self.ls.log("Banlist entry deleted via API (%s)" % payload["data"]["address"])
            self.acknowledge()

        # add remote list server
        elif payload["action"] == "add-remote":
            if "name" not in payload["data"] or "address" not in payload["data"]:
                self.ls.log("Malformed API request (add-remote)")
                self.error_msg("Malformed API request")
                self.end()
                return

            self.query("INSERT INTO remotes (name, address) VALUES (?, ?)",
                            (payload["data"]["name"], payload["data"]["address"]))

            self.ls.remotes.append(payload["data"]["address"])
            self.ls.broadcast({"action": "add-remote", "data": payload["data"]})
            self.ls.log("Remote added via API (%s)" % payload["data"]["address"])
            self.acknowledge()

        # remove remote list server
        elif payload["action"] == "delete-remote":
            if "name" not in payload["data"] or "address" not in payload["data"]:
                self.ls.log("Malformed API request (delete-remote)")
                self.error_msg("Malformed API request")
                self.end()
                return

            self.query("DELETE FROM remotes WHERE name = ? AND address = ?",
                            (payload["data"]["name"], payload["data"]["address"]))

            self.ls.remotes.remove(payload["data"]["address"])
            self.ls.broadcast({"action": "delete-remote", "data": payload["data"]})
            self.ls.log("Remote deleted via API (%s)" % payload["data"]["address"])
            self.acknowledge()

        # update MOTD
        elif payload["action"] == "set-motd":
            if "motd" not in payload["data"]:
                self.ls.log("Malformed API request (set-motd)")
                self.error_msg("Malformed API request")
                self.end()
                return

            self.query("UPDATE settings SET value = ? WHERE item = ?", (payload["data"]["motd"], "motd"))
            self.query("UPDATE settings SET value = ? WHERE item = ?", (int(time.time()), "motd-updated"))
            payload["data"]["updated"] = int(time.time())

            self.ls.broadcast({"action": "motd", "data": payload["data"]})
            self.ls.log("MOTD updated via API")
            self.acknowledge()

        # retrieve server list
        elif payload["action"] == "get-servers":
            self.cleanup()
            servers = self.fetch_all("SELECT * FROM servers ORDER BY private ASC, players DESC, created ASC")

            self.msg(json.dumps([dict(servers[i]) for i, value in enumerate(servers)]))

        # retrieve banlist
        elif payload["action"] == "get-banlist":
            banlist = self.fetch_all("SELECT * FROM banlist")

            self.msg(json.dumps([dict(banlist[i]) for i, value in enumerate(banlist)]))

        # retrieve motd
        elif payload["action"] == "get-motd":
            motd = self.fetch_one("SELECT * FROM settings WHERE item = ?", ("motd",))

            self.msg(json.dumps(motd["value"]))

        # retrieve remotes
        elif payload["action"] == "get-remotes":
            remotes = self.fetch_one("SELECT * FROM remotes")

            self.msg(json.dumps([dict(remotes[i]) for i, value in enumerate(remotes)]))

        # initiate reload
        elif payload["action"] == "reload":
            self.ls.reload()
            self.acknowledge()

        self.end()
        return
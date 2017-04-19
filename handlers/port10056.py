import socket
import json
import time

from helpers.port_handler import port_handler

from helpers.jj2server import jj2server


class servernet_handler(port_handler):
    """
    Sync data between list servers
    """

    def handle_data(self):
        self.client.settimeout(5)  # should really be enough
        loops = 0
        payload = None
        self.buffer = bytearray()

        if self.ip not in self.ls.remotes:
            self.ls.log.error("Unauthorized ServerNet connection from %s" % self.ip)
            self.end()
            return

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

        if not payload:  # payload not received or readable for whatever reason, give up
            self.ls.log.error("ServerNet update received from %s, but could not acquire valid payload" % self.ip)
            self.end()
            return

        if "action" not in payload or "data" not in payload:
            self.ls.log.error("ServerNet update received from %s, but JSON was malformed" % self.ip)
            self.end()
            return

        # ok, payload is valid, process it
        self.ls.log.info("Received ServerNet update from %s: %s" % (self.ip, payload["action"]))

        # server listings
        if payload["action"] == "server":
            if "id" not in payload["data"]:
                self.ls.log.error("Received malformed server data from ServerNet connection %s" % self.ip)
                return

            server = jj2server(payload["data"]["id"])
            for key in payload["data"]:
                try:
                    server.set(key, payload["data"][key])
                except IndexError:
                    self.ls.log.error("Received malformed server data from ServerNet connection %s (unknown field %s)" % (self.ip, key))
                    server.forget()
                    self.end()
                    return
            server.set("remote", 1)

        # ban list (and whitelist) entries
        elif payload["action"] == "ban":
            if "address" not in payload["data"] or "type" not in payload["data"] or "origin" not in payload["data"] or "note" not in payload["data"]:
                self.ls.log.error("Received malformed banlist entry from ServerNet connection %s" % self.ip)
                self.end()
                return

            exists = self.fetch_one("SELECT COUNT(*) FROM banlist WHERE address = ? AND origin = ? AND type = ? AND note = ?",
                                     (payload["data"]["address"], payload["data"]["origin"], payload["data"]["type"], payload["data"]["note"]))
            if not exists:
                self.query("INSERT INTO banlist (address, origin, type) VALUES (?, ?, ?)", (payload["data"]["address"], payload["data"]["origin"], payload["data"]["type"]))

            self.ls.log.info("Added banlist entry via ServerNet connection %s" % self.ip)

        # removal of ban/whitelist entries
        elif payload["action"] == "unban":
            if "address" not in payload["data"] or "type" not in payload["data"] or "origin" not in payload["data"] or "note" not in payload["data"]:
                self.ls.log.error("Received malformed banlist entry from ServerNet connection %s" % self.ip)
                self.end()
                return

            self.fetch_one("DELETE FROM banlist WHERE address = ? AND origin = ? AND type = ? AND note = ?",
                            (payload["data"]["address"], payload["data"]["origin"], payload["data"]["type"], payload["data"]["note"]))

            self.ls.log.info("Removed banlist entry via ServerNet connection %s" % self.ip)

        # server delistings
        elif payload["action"] == "delist":
            if "id" not in payload["data"]:
                self.ls.log.error("Received malformed server data from ServerNet connection %s" % self.ip)
                self.end()
                return
            server = jj2server(payload["data"]["id"])
            if server.get("remote") == 1:
                server.forget()

            self.ls.log.info("Delisted server via ServerNet connection %s" % self.ip)

        # add remote
        elif payload["action"] == "add-remote":
            if "address" not in payload["data"] or "name" not in payload["data"]:
                self.ls.log.error("Received malformed remote info from ServerNet connection %s" % self.ip)
                self.end()
                return

            exists = self.fetch_one("SELECT * FROM remotes WHERE name = ? OR address = ?", (payload["data"]["name"], payload["data"]["address"]))
            if exists:
                self.ls.log.info("Remote %s tried adding remote %s, but name or address already known" % (self.ip, payload["data"]["address"]))
                self.end()

            self.query("INSERT INTO remotes (name, address) VALUES (?, ?)", (payload["data"]["name"], payload["data"]["address"]))
            self.ls.add_remote(payload["data"]["address"])
            self.ls.broadcast({"action": "hello", "data": {"from": self.ls.address}}, [payload["data"]["address"]])

            self.ls.log.info("Added remote %s via ServerNet connection %s" % (payload["data"]["address"], self.ip))

        # delete remote
        elif payload["action"] == "delete-remote":
            if "address" not in payload["data"] or "name" not in payload["data"]:
                self.ls.log.error("Received malformed remote info from ServerNet connection %s" % self.ip)
                self.end()
                return

            exists = self.fetch_one("SELECT * FROM remotes WHERE name = ? AND address = ?", (payload["data"]["name"], payload["data"]["address"]))
            if not exists:
                self.ls.log.info("Remote %s tried removing remote %s, but not known" % (self.ip, payload["data"]["address"]))
                self.end()

            self.query("DELETE FROM remotes WHERE name = ? AND address = ?", (payload["data"]["name"], payload["data"]["address"]))
            self.ls.delete_remote(payload["data"]["address"])

            self.ls.log.info("Deleted remote %s via ServerNet connection %s" % (payload["data"]["address"], self.ip))

        # motd updates
        elif payload["action"] == "motd":
            if "motd" not in payload["data"]:
                self.ls.log.error("Received malformed MOTD from ServerNet connection %s" % self.ip)
                self.end()
                return

            timestamp = self.fetch_one("SELECT value FROM settings WHERE item = ?", ("motd-updated",))
            if timestamp and "updated" in payload["data"] and int(timestamp) > (payload["data"]["updated"]):
                self.ls.log.info("Received MOTD update from %s, but own MOTD was more recent" % self.ip)
                self.end()

            self.query("UPDATE settings SET value = ? WHERE item = ?", (payload["data"]["motd"], "motd"))
            self.query("UPDATE settings SET value = ? WHERE item = ?", (int(time.time()), "motd-updated"))

            self.ls.log.info("Updated MOTD via ServerNet connection %s" % self.ip)

        # sync requests: send all data
        elif payload["action"] == "request" or payload["action"] == "hello":

            # in case of "hello", also send a request for data to the other server
            if payload["action"] == "hello":
                self.ls.broadcast({"action": "request", "data": {"from": self.ls.address}}, [self.ip])

            self.cleanup()  # removes stale servers, etc

            # servers
            servers = self.fetch_all("SELECT * FROM servers WHERE players > 0 AND origin = ?", (self.ls.address,))
            for server in servers:
                payload_data = {}
                for property in server.keys():
                    payload_data[property] = server[property]

                self.ls.broadcast({"action": "server", "data": payload_data}, [self.ip])

            # banlist
            banlist = self.fetch_all("SELECT * FROM banlist WHERE global = 1 AND origin = ?", (self.ls.address,))
            for listing in banlist:
                payload_data = {}
                for property in listing.keys():
                    payload_data[property] = listing[property]

                self.ls.broadcast({"action": "ban", "data": payload_data}, [self.ip])

            # motd
            motd = self.fetch_one("SELECT value FROM settings WHERE item = ?", ("motd",))
            updated = self.fetch_one("SELECT value FROM settings WHERE item = ?", ("motd-updated",))

            motd = motd["value"] if motd else "jj2 aint dead\n"
            self.ls.broadcast({"action": "motd", "data": {"motd": motd, "updated": updated["value"] if updated else 0}}, [self.ip])

            # remotes
            remotes = self.fetch_all("SELECT * FROM remotes")
            for remote in remotes:
                payload_data = {}
                for property in remote.keys():
                    payload_data[property] = remote[property]

                self.ls.broadcast({"action": "add-remote", "data": payload_data}, [self.ip])

            self.ls.log.info("Sent sync data to ServerNet connection %s" % self.ip)

        self.end()
        return
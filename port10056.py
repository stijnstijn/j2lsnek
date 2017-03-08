import socket
import json

from helpers import port_handler
from jj2server import jj2server


class servernet_handler(port_handler):
    """
    Sync data between list servers
    """

    def handle_data(self):
        self.client.settimeout(5)  # should really be enough
        loops = 0

        while True:
            try:
                self.buffer.extend(self.client.recv(2048))
                loops += 1
            except socket.timeout:
                self.ls.log("Server from %s timed out" % self.key)
                break


            try:
                payload = json.loads(self.buffer.encode("UTF-8"))
                break
            except json.JSONDecodeError:
                pass

            if loops > 12:  # even our patience knows its limits
                break

        if not payload:  # payload not received or readable for whatever reason, give up
            self.ls.log("ServerNet update received from %s, but could not acquire valid payload" % self.ip)
            self.end()
            return

        if not payload.action or not payload.data:
            self.ls.log("ServerNet update received from %s, but JSON was malformed" % self.ip)
            self.end()
            return

        # ok, payload is valid, process it

        # server listings
        if payload.action == "server":
            if "id" not in payload.data:
                self.ls.log("Received malformed server data from ServerNet connection %s" % self.ip)
                return

            server = jj2server(payload.data["id"])
            for key in payload.data:
                try:
                    server.set(key, payload.data[key])
                except IndexError:
                    self.ls.log("Received malformed server data from ServerNet connection %s" % self.ip)
                    self.end()
                    return
            server.set("remote", 1)

        # ban list (and whitelist) entries
        elif payload.action == "ban":
            if "address" not in payload.data or "type" in payload.data or "origin" not in payload.data:
                self.ls.log("Received malformed banlist entry from ServerNet connection %s" % self.ip)
                self.end()
                return

            exists = self.db.execute("SELECT COUNT(*) FROM banlist WHERE address = ? AND origin = ? AND type = ?",
                                     (payload.data["address"], payload.data["origin"], payload.data["type"])).fetchone()
            if not exists:
                self.db.execute("INSERT INTO banlist (address, origin, type) VALUES (?, ?, ?)", (payload.data["address"], payload.data["origin"], payload.data["type"]))

        # removal of ban/whitelist entries
        elif payload.action == "unban":
            if "address" not in payload.data or "type" in payload.data or "origin" not in payload.data:
                self.ls.log("Received malformed banlist entry from ServerNet connection %s" % self.ip)
                self.end()
                return

            self.db.execute("DELETE FROM banlist WHERE address = ? AND origin = ? AND type = ?",
                            (payload.data["address"], payload.data["origin"], payload.data["type"])).fetchone()

        # server delistings
        elif payload.action == "delist":
            if "id" not in payload.data:
                self.ls.log("Received malformed server data from ServerNet connection %s" % self.ip)
                self.end()
                return
            server = jj2server(payload.data["id"])
            if server.get("remote") == 1:
                server.forget()

        # motd updates
        elif payload.action == "motd":
            if "motd" not in payload.data:
                self.ls.log("Received malformed MOTD from ServerNet connection %s" % self.ip)
                self.end()
                return

            self.db.execute("UPDATE settings SET value = ? WHERE item = ?", (payload.data["motd"], "motd"))

        # sync request: send all data
        elif payload.action == "request":
            #servers
            servers = self.db.execute("SELECT * FROM servers WHERE players > 0 AND origin = ?", (self.ls.address,)).fetchall()
            for server in servers:
                payload_data = {}
                for property in server.keys():
                    payload_data[property] = server[property]

                self.ls.broadcast({"action": "server", "data": payload_data}, [self.ip])

            #banlist
            blackwhite = self.db.execute("SELECT * FROM blackwhite WHERE global = 1 AND origin = ?", (self.ls.address,)).fetchall()
            for listing in blackwhite:
                payload_data = {}
                for property in listing.keys():
                    payload_data[property] = listing[property]

                self.ls.broadcast({"action": "ban", "data": payload_data}, [self.ip])

            #motd
            motd = self.db.execute("SELECT value FROM settings WHERE item = ?", ("motd")).fetchone()
            motd = motd["value"] if motd else "jj2 aint dead\n"
            self.ls.broadcast({"action": "motd", "data": {"motd": motd}}, [self.ip])

        self.end()
        return
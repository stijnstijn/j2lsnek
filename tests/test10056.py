import socket
import json
import time

LIST_SERVER = "localhost"


class fake_apicaller:
    def run(self):
        type = 1
        start = int(time.time())

        while True:
            now = int(time.time())
            if now - start >= 2:  # send every 5 seconds, give or take
                start = now
                connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                connection.settimeout(4)
                connection.connect((LIST_SERVER, 10056))
                print("Connection with list server %s opened" % LIST_SERVER)
                payload = ""

                if type == 1:
                    payload = {"action": "add-banlist", "data": [
                        {"address": "0.0.0.0", "type": "ban", "origin": "localhost", "global": 1,
                         "note": "(added via test)"}]}
                    print("Sending valid add-banlist API command")
                if type == 2:
                    payload = {"action": "add-banlist",
                               "data": [{"address": "0.0.0.0", "type": "ban", "origin": "localhost"}]}
                    print("Sending invalid add-banlist API command (missing property)")
                if type == 3:
                    payload = {"action": "add-banlist", "data": None}
                    print("Sending invalid add-banlist API command (empty data)")
                if type == 4:
                    payload = {"action": "add-banlist"}
                    print("Sending invalid add-banlist API command (no data)")

                if type == 5:
                    payload = {"action": "delete-banlist", "data": [
                        {"address": "0.0.0.0", "type": "ban", "origin": "localhost", "global": 1,
                         "note": "(added via test)"}]}
                    print("Sending valid delete-banlist API command")
                if type == 6:
                    payload = {"action": "delete-banlist",
                               "data": [{"address": "0.0.0.0", "type": "ban", "origin": "localhost"}]}
                    print("Sending invalid delete-banlist API command (missing property)")
                if type == 7:
                    payload = {"action": "delete-banlist", "data": None}
                    print("Sending invalid delete-banlist API command (empty data)")
                if type == 8:
                    payload = {"action": "delete-banlist"}
                    print("Sending invalid delete-banlist API command (no data)")

                if type == 9:
                    payload = {"action": "add-mirror", "data": [{"address": "0.0.0.0", "name": "test mirror"}]}
                    print("Sending valid add-mirror API command")
                if type == 10:
                    payload = {"action": "add-mirror", "data": [{"address": "INSANE TEST", "name": "invalid mirror"}]}
                    print("Sending invalid add-mirror API command (invalid address)")
                if type == 11:
                    payload = {"action": "add-mirror", "data": [{"address": "0.0.0.0"}]}
                    print("Sending invalid add-mirror API command (missing property)")
                if type == 12:
                    payload = {"action": "add-mirror", "data": None}
                    print("Sending invalid add-mirror API command (empty data)")
                if type == 13:
                    payload = {"action": "add-mirror"}
                    print("Sending invalid add-mirror API command (no data)")

                if type == 14:
                    payload = {"action": "delete-mirror", "data": [{"address": "0.0.0.0", "name": "test mirror"}]}
                    print("Sending valid delete-mirror API command")
                if type == 15:
                    payload = {"action": "delete-mirror", "data": [{"address": "0.0.0.0"}]}
                    print("Sending invalid delete-mirror API command (missing property)")
                if type == 16:
                    payload = {"action": "delete-mirror", "data": None}
                    print("Sending invalid delete-mirror API command (empty data)")
                if type == 17:
                    payload = {"action": "delete-mirror"}
                    print("Sending invalid delete-mirror API command (no data)")

                if type == 18:
                    payload = {"action": "set-motd", "data": [{"motd": "test motd", "motd-updated": int(time.time())}]}
                    print("Sending valid set-motd API command")
                if type == 19:
                    payload = {"action": "set-motd", "data": {"motd": "test motd"}}
                    print("Sending invalid set-motd API command (missing property)")
                if type == 20:
                    payload = {"action": "set-motd", "data": None}
                    print("Sending invalid set-motd API command (empty data)")
                if type == 21:
                    payload = {"action": "set-motd"}
                    print("Sending invalid set-motd API command (no data)")

                if type == 18:
                    payload = {"action": "get-motd", "data": [{"from": "localhost"}]}
                    print("Sending valid get-motd API command")
                if type == 19:
                    payload = {"action": "get-mirrors", "data": [{"from": "localhost"}]}
                    print("Sending invalid get-mirrors API command")
                if type == 20:
                    payload = {"action": "get-banlist", "data": [{"from": "localhost"}]}
                    print("Sending invalid get-banlist API command")
                if type == 21:
                    payload = {"action": "get-servers"}
                    print("Sending invalid get-servers API command")

                payload["origin"] = "web"
                connection.sendall(json.dumps(payload).encode("ascii"))
                try:
                    data = connection.recv(1024)
                    print("Response: %s" % data.decode("ascii"))
                except socket.timeout:
                    print("API call timed out")

                connection.close()

                type += 1
                if type > 20:
                    type = 1


tester = fake_apicaller()
tester.run()

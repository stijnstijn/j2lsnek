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
                connection.connect((LIST_SERVER, 10059))
                print("Connection with list server %s opened" % LIST_SERVER)
                payload = ""

                if type == 1:
                    payload = {"action": "add-banlist", "data": {"address": "0.0.0.0", "type": "ban", "origin": "localhost", "global": 1}}
                    print("Sending valid add-banlist API command")
                if type == 2:
                    payload = {"action": "add-banlist", "data": {"address": "0.0.0.0", "type": "ban", "origin": "localhost"}}
                    print("Sending invalid add-banlist API command (missing property)")
                if type == 3:
                    payload = {"action": "add-banlist", "data": None}
                    print("Sending invalid add-banlist API command (empty data)")
                if type == 4:
                    payload = {"action": "add-banlist"}
                    print("Sending invalid add-banlist API command (no data)")

                if type == 5:
                    payload = {"action": "delete-banlist", "data": {"address": "0.0.0.0", "type": "ban", "origin": "localhost", "global": 1}}
                    print("Sending valid delete-banlist API command")
                if type == 6:
                    payload = {"action": "delete-banlist", "data": {"address": "0.0.0.0", "type": "ban", "origin": "localhost"}}
                    print("Sending invalid delete-banlist API command (missing property)")
                if type == 7:
                    payload = {"action": "delete-banlist", "data": None}
                    print("Sending invalid delete-banlist API command (empty data)")
                if type == 8:
                    payload = {"action": "delete-banlist"}
                    print("Sending invalid delete-banlist API command (no data)")

                if type == 9:
                    payload = {"action": "add-remote", "data": {"address": "0.0.0.0", "name": "test remote"}}
                    print("Sending valid add-remote API command")
                if type == 10:
                    payload = {"action": "add-remote", "data": {"address": "0.0.0.0"}}
                    print("Sending invalid add-remote API command (missing property)")
                if type == 11:
                    payload = {"action": "add-remote", "data": None}
                    print("Sending invalid add-remote API command (empty data)")
                if type == 12:
                    payload = {"action": "add-remote"}
                    print("Sending invalid add-remote API command (no data)")

                if type == 13:
                    payload = {"action": "delete-remote", "data": {"address": "0.0.0.0", "name": "test remote"}}
                    print("Sending valid delete-remote API command")
                if type == 14:
                    payload = {"action": "delete-remote", "data": {"address": "0.0.0.0"}}
                    print("Sending invalid delete-remote API command (missing property)")
                if type == 15:
                    payload = {"action": "delete-remote", "data": None}
                    print("Sending invalid delete-remote API command (empty data)")
                if type == 16:
                    payload = {"action": "delete-remote"}
                    print("Sending invalid delete-remote API command (no data)")

                if type == 17:
                    payload = {"action": "set-motd", "data": {"motd": "test motd"}}
                    print("Sending valid set-motd API command")
                if type == 18:
                    payload = {"action": "set-motd", "data": {}}
                    print("Sending invalid set-motd API command (missing property)")
                if type == 19:
                    payload = {"action": "set-motd", "data": None}
                    print("Sending invalid set-motd API command (empty data)")
                if type == 20:
                    payload = {"action": "set-motd"}
                    print("Sending invalid set-motd API command (no data)")

                connection.sendall(json.dumps(payload).encode("ascii"))
                try:
                    data = connection.recv(1024)
                    print("Response: %s" % data.decode("ascii"))
                except socket.timeout:
                    print("API call timed out")

                connection.close()

                type += 1
                if type > 16:
                    type = 1



tester = fake_apicaller()
tester.run()
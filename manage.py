"""
Barebones management script for list servers

Allows giving API commands via a command-line interface, a GUI would be nicer though
"""
import socket
import json
import time
import sys
import ssl


def send(action, payload):
    """
    Send message to server

    Always tries to connect to localhost on port 10059, since that's where the API will be listening
    :param action: API action, string
    :param payload: API payload, dictionary
    :return: API response, or timeout message in case of timeout
    """
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(5)
    ssl_sock = ssl.wrap_socket(connection, ca_certs="server.crt", cert_reqs=ssl.CERT_REQUIRED)
    ssl_sock.connect(("localhost", 10059))

    msg = json.dumps({"action": action, "data": [payload], "origin": "web"})
    ssl_sock.sendall(msg.encode("ascii"))

    try:
        response = ssl_sock.recv(2048)
        response = response.decode("ascii")
    except socket.timeout:
        response = "(Connection timed out)"

    ssl_sock.shutdown(socket.SHUT_RDWR)
    ssl_sock.close()

    return response


if len(sys.argv) < 2 or sys.argv[1] not in ["ban", "unban", "whitelist", "unwhitelist", "add-banlist", "delete-banlist",
                                            "add-mirror", "delete-mirror", "set-motd", "reload"]:
    print(" Syntax: python3 manage.py [command] [arguments]\n")
    print(" Shorthand commands:")
    print("  ban [IP] (bans globally)")
    print("  unban [IP] (removes global ban)")
    print("  whitelist [IP] (whitelists globally")
    print("  unwhitelist [IP] (removes global whitelist)")
    print("  set-motd [text]")
    print("")
    print(" Advanced commands:")
    print("  add-banlist [IP] [ban/whitelist] [origin] [global: 1/0]")
    print("  delete-banlist [IP] [ban/whitelist] [origin] [global: 1/0]")
    print("  add-mirror [name] [IP]")
    print("  delete-mirror [name] [IP]")
    print("  reload")
    sys.exit()

action = sys.argv[1]
if sys.argv[1] in ["ban", "unban", "whitelist", "unwhitelist"]:
    action = \
    {"ban": "add-banlist", "unban": "delete-banlist", "whitelist": "add-banlist", "unwhitelist": "delete-whitelist"}[
        action]
    type = "ban" if action.split("-")[1] == "banlist" else "whitelist"
    if len(sys.argv) != 3:
        print("Syntax:\n %s [IP]" % sys.argv[1])
        sys.exit()

    payload = {"address": sys.argv[2], "note": "(added via CLI)", "type": type, "global": 1}

elif sys.argv[1] in ["add-banlist", "delete-banlist"]:
    if len(sys.argv) != 3:
        print("Syntax:\n %s [IP] [ban/whitelist] [origin] [global: 1/0]" % sys.argv[1])
        sys.exit()

    payload = {"address": sys.argv[2], "type": sys.argv[3], "origin": sys.argv[4], "global": int(sys.argv[5])}

elif sys.argv[1] in ["add-mirror", "delete-mirror"]:
    if len(sys.argv) != 4:
        print("Syntax:\n %s [name] [IP]" % sys.argv[1])
        sys.exit()

    payload = {"name": sys.argv[2], "address": sys.argv[3]}

elif sys.argv[1] == "set-motd":
    if len(sys.argv) < 3:
        print("Syntax:\n set-motd [text]")
        sys.exit()

    payload = {"motd": " ".join(sys.argv[2:]), "motd-updated": int(time.time())}

elif sys.argv[1] == "reload":
    payload = {"from": "cli"}

result = send(action, payload)

if result == "ACK":
    print("Command successful.")
else:
    print("Response: %s" % result)

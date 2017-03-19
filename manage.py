"""
Barebones management script for list servers

Allows giving API commands via a command-line interface, a GUI would be nicer though
"""
import socket
import json
import sys


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
    connection.connect(("localhost", 10059))

    msg = json.dumps({"action": action, "data": payload})
    connection.sendall(msg.encode("ascii"))

    try:
        response = connection.recv(2048)
        response = response.decode("ascii")
    except socket.timeout:
        response = "(Connection timed out)"

    return response

if len(sys.argv) < 2 or sys.argv[1] not in ["ban", "unban", "whitelist", "unwhitelist", "add-banlist", "delete-banlist", "add-remote", "delete-remote", "set-motd"]:
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
    print("  add-remote [name] [IP]")
    print("  delete-remote [name] [IP]")
    sys.exit()

if sys.argv[1] in ["ban", "unban", "whitelist", "unwhitelist"]:
    if len(sys.argv) != 3:
        print("Syntax:\n %s [IP]" % sys.argv[1])
        sys.exit()

    payload = {"address": sys.argv[2]}

elif sys.argv[1] in ["add-banlist", "delete-banlist"]:
    if len(sys.argv) != 3:
        print("Syntax:\n %s [IP] [ban/whitelist] [origin] [global: 1/0]" % sys.argv[1])
        sys.exit()

    payload = {"address": sys.argv[2], "type": sys.argv[3], "origin": sys.argv[4], "global": int(sys.argv[5])}

elif sys.argv[1] in ["add-remote", "delete-remote"]:
    if len(sys.argv) != 4:
        print("Syntax:\n %s [name] [IP]" % sys.argv[1])
        sys.exit()

    payload = {"name": sys.argv[2], "address": sys.argv[3]}

elif sys.argv[1] == "set-motd":
    if len(sys.argv) < 3:
        print("Syntax:\n set-motd [text]")
        sys.exit()

    payload = {"motd": " ".join(sys.argv[2:])}


result = send(sys.argv[1], payload)

if result == "ACK":
    print("Command successful.")
else:
    print("Response: %s" % result)

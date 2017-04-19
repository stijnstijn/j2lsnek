import socket
import time
import json

while True:
    listserver = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listserver.settimeout(4)
    listserver.connect(("178.32.55.196", 10057))

    buffer = ""
    while True:
        add = listserver.recv(1024).decode("ascii")
        if not add or add == "":
            break
        buffer += add

    servers = buffer.split("\n")
    payload = []
    for server in servers:
        try:
            bits = server.split(" ")
            if len(bits) < 9:
                continue
            id = bits[0]
            ip = bits[0].split(":")[0]
            port = bits[0].split(":")[1]
            private = 1 if bits[2] == "private" else 0
            mode = bits[3]
            version = bits[4]
            rest = " ".join(bits[7:]) if bits[7] != " " else " ".join(bits[8:])
            bits = rest.split(" ")
            created = int(time.time()) - int(bits[0])
            players = int(bits[1][1:-1].split("/")[0])
            max = int(bits[1][1:-1].split("/")[1])
            name = " ".join(bits[2:]).strip()
            payload.append({"id": id, "ip": ip, "port": port, "created": created, "lifesign": int(time.time()), "private": private, "remote": 1, "origin": "bridge", "version": version, "mode": mode, "players": players, "max": max, "name": name})
        except ValueError:
            continue

    payload = {"action": "server", "data": servers, "origin": "bridge"}

    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(4)
    connection.connect(("localhost", 10056))
    connection.sendall(json.dumps(payload).encode("ascii"))

    try:
        data = connection.recv(1024)
        print("Synced server %s" % name)
    except socket.timeout:
        print("API call timed out")

    connection.close()

    listserver.close()

    time.sleep(30)
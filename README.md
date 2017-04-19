j2lsnek 🐍
===

Jazz Jackrabbit 2 List Server: New Edition k. Run `main.py` to start serving lists. Needs Python 3.

The "list server" is what Jazz Jackrabbit 2 multiplayer servers connect to to let people know they're live. Other people
connect to the list server to retrieve an up-to-date list of servers they can join. But if you're reading this you
probably knew that.

Program logic
---
```
,-------------,                     ,-> Client connection handler 1
| Main thread |-+-> Port listener 1 +-> Client connection handler 2
`-------------` |                   `-> etc
       |        |
       |        `-> Port listener 2 ,-> Client connection handler 1
       |                            `-> etc
       |
       `-> ServerNet broadcaster ,-> Broadcast to remote list server 1
                                 `-> etc
```

All these are in separate threads, except for the ServerNet broadcaster which lives inside main thread. Each port has
its own handler class, specified in a separate file, e.g. `liveserver.py` contains the handler that processes clients
sending data about their servers, on port 10054. These handlers extend a basic handler class that can be found in
`port_handler.py`.

The main thread can send messages to connected remote mirror list servers, and will create a new thread for each such
message sent (which terminates once it is sent).

Server data is stored in an SQLite database; this data is removed once the server is delisted. A database is used so
data is persistent between restarts and easy to manipulate in a standardised way.

APIs
---
ServerNet communication does not use Epic's binary protocol but a new JSON-based protocol. The advantage of this is that
server data can easily be serialised and synchronised between servers (and it's a lot easier to debug). There are no
separate commands for each updated property any more; rather, when a server's info changes, its full data is broadcast
by the list server it is listed on, and other list servers replace their database records accordingly. Another new
feature is that bans, whitelistings and settings like the MOTD can also be synchronised.

ServerNet syncing treats all connected list servers as equal. This means all servers can add and remove items like bans;
origin does not matter, i.e. server A can remove a global ban set by server B. If this is a problem you should probably
be looking for more trustworthy list server hosts.

Remote administration is available via the ServerNet API, though it uses a different port (10059 instead of 10056).
Connections on port 10059 need to come from localhost, so whatever interface you whip up needs to be on the same machine
as the list server itself. To ensure that only known interfaces can use the API, an SSL certificate is used for
authentication on port 10059.

Abuse protection
---
This list server adds a number of constraints that should make it better equipped to handle abuse than the original and
node.js-based list servers. It limits the amount of connections per IP, synchronises bans among mirrors and sanitises
server data. Managing bans and whitelistings is made easier via a remote admin interface (which is separate from this
repository).
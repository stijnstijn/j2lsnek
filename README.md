j2lsnek 🐍
===

Jazz Jackrabbit 2 List Server: New Edition k. See code comments for info on how it works. Run main.py to start serving lists.

##Program logic
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
its own handler class, specified in a separate file, e.g. port10054.py contains the handler that processes clients
sending data about their servers. These handlers extend a basic handler class that can be found in helper.py along with
a few other helper functions.

The main thread can send messages to connected remote mirror list servers, and will create a new thread for each such
message sent (which terminates once it is sent).

Server data is stored in an SQLite database; this data is removed once the server is delisted. A database is used so
other applications can easily access server data.

##APIs
ServerNet communication does not use Epic's binary protocol but a new JSON-based protocol. The advantage of this is that
server data can easily be serialised and synchronised between servers (and it's a lot easier to debug). There are no
separate commands for each updated property any more; rather, when a server's info changes, its full data is broadcast
by the list server it is listed on, and other list servers replace their database records accordingly. Another new
feature is that bans, whitelistings and settings like the MOTD can also be synchronised.

Remote administration is available via an API. The API can only be called from localhost; thus any interface should be
hosted on the same machine as the list server. See port10059.py for API details.

##Todo:
- Test whether stuff actually works and can't easily be broken
- Maybe some extra abuse detection and mitigation

"""
Not a lot to configure
"""
VERSION = "03"
DATABASE = "servers.db"
MICROSLEEP = 0.2
MAXPLAYERS = 32
TIMEOUT = 40  # time until a server is delisted

# ssl chain (for the server), certificates and keys that are used to authenticate remote admin interfaces - these
# can be left empty and the list server will still work, port 10059 will just be unavailable if they're empty
# or invalid
CERTFILE = "/srv/tcp/list/ssl/intermediate/certs/listserver_serverside.cert.pem"
CERTCHAIN = "/srv/tcp/list/ssl/intermediate/certs/ca-chain.cert.pem"
CERTKEY = "/srv/tcp/lists/ssl/intermediate/private/list.jazz2online.com.key.pem"
CLIENTCERT = "/srv/tcp/list/ssl/intermediate/certs/listserver_clientside.pem"
CLIENTKEY = "/srv/tcp/lists/ssl/intermediate/private/list/listserver_clientside.key.pem"

# the following three values are for throttling/rate limiting
# TICKSMAX is the max amount of ticks per IP - when reached the connection will be refused
# TICKSDECAY is the rate per second at which ticks decay, e.g. for rate 1, every second one tick is "forgotten"
# if TICKSMAX and TICKSDECAY are equal, one connection per second can be made
# TICKSMAXAGE is the amount of time after which an IP will be forgotten by the rate limiter, if it hasn't connected
TICKSMAX = 10
TICKSDECAY = 2
TICKSMAXAGE = 86400

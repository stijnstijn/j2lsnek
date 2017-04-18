"""
Not a lot to configure
"""
VERSION = "02"
DATABASE = "servers.db"
MICROSLEEP = 0.2
MAXPLAYERS = 32
TIMEOUT = 40  # time until a server is delisted

# the following two values are for throttling/rate limiting
# TICKSMAX is the max amount of ticks per IP - when reached the connection will be refused
# TICKSDECAY is the rate per second at which ticks decay, e.g. for rate 1, every second one tick is "forgotten"
# if TICKSMAX and TICKSDECAY are equal, one connection per second can be made
# TICKSMAXAGE is the amount of time after which an IP will be forgotten by the rate limiter, if it hasn't connected
TICKSMAX = 10
TICKSDECAY = 2
TICKSMAXAGE = 86400
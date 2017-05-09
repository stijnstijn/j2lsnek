# this is just a dummy file that imports the local configuration file if it exists, or the defaults if it doesn't
# this way other files can still import "config" and always get the right values

from defaultconfig import *
try:
    from localconfig import *
except ImportError:
    pass
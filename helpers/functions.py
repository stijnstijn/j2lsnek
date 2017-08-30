import threading
import fnmatch
import sqlite3
import socket
import config
import math

lock = threading.Lock();


def decode_mode(mode):
    """
    JJ2 uses numbers instead of strings, but strings are easier for humans to work with
    
    CANNOT use spaces here, as list server scripts may not expect spaces in modes in port 10057 response

    :param mode: Mode number as sent by the client
    :return: Mode string
    """
    if mode == 16:
        return "headhunters"
    if mode == 15:
        return "domination"
    if mode == 14:
        return "tlrs"
    if mode == 13:
        return "flagrun"
    if mode == 12:
        return "deathctf"
    if mode == 11:
        return "jailbreak"
    if mode == 10:
        return "teambattle"
    if mode == 9:
        return "pestilence"
    if mode == 8:
        return "xlrs"
    if mode == 7:
        return "lrs"
    if mode == 6:
        return "roasttag"
    if mode == 5:
        return "coop"
    if mode == 4:
        return "race"
    if mode == 3:
        return "ctf"
    if mode == 2:
        return "treasure"
    if mode == 1:
        return "battle"

    return "unknown"


def encode_mode(mode):
    """
    JJ2 uses numbers instead of strings, but strings are easier for humans to work with
    
    CANNOT use spaces here, as list server scripts may not expect spaces in modes in port 10057 response

    :param mode: Mode number as sent by the client
    :return: Mode string
    """
    if mode == 16:
        return "headhunters"
    if mode == 15:
        return "domination"
    if mode == 14:
        return "tlrs"
    if mode == 13:
        return "flagrun"
    if mode == 12:
        return "deathctf"
    if mode == 11:
        return "jailbreak"
    if mode == 10:
        return "teambattle"
    if mode == 9:
        return "pestilence"
    if mode == 8:
        return "xlrs"
    if mode == 7:
        return "lrs"
    if mode == 6:
        return "roasttag"
    if mode == 5:
        return "coop"
    if mode == 4:
        return "race"
    if mode == 3:
        return "ctf"
    if mode == 2:
        return "treasure"
    if mode == 1:
        return "battle"

    return "unknown"


def decode_version(version):
    """
    Not a lot to decode for the version string, but people aren't actually playing 1.21

    :param version: Version as sent by the client
    :return: Version string as used by list server
    """
    version = version.decode("ascii", "ignore")

    if version[0:2] == "21":
        version_string = "1.23"
    else:
        version_string = "1.24"

    return version_string + version[2:]


def udpchecksum(bytes):
    """"
    Prepend UDP checksum
    
    JJ2 expects UDP datagrams to be perceded by a two-byte checksum - this method adds that checksum
    Thanks to DJazz for the PHP reference implementation!
    
    :param bytes: Bytearray to checksum
    :return: Bytearray with checksum
    """
    x = 1
    y = 1
    byte_count = len(bytes)
    for i in range(2, byte_count):
        x += bytes[i]
        y += x

    bytes[0] = x % 251
    bytes[1] = y % 251

    return bytes


def fancy_time(time):
    """
    Formats time nicely so timespans are more intuitively understandable

    :param time: Time to format in seconds
    :return: Fancy formatted string, e.g. "1wk 3d 14h 35m 56s"
    """
    day = 86400
    string = ""
    weeks = days = hours = minutes = 0

    if time > day * 7:
        weeks = math.floor(time / (day * 7))
        time -= (weeks * days * 7)
        string += str(weeks) + "wk "

    if time > day or weeks > 0:
        days = math.floor(time / day)
        time -= (days * day)
        string += str(days) + "d "

    if time > 3600 or days > 0 or weeks > 0:
        hours = math.floor(time / 3600)
        string += str(hours) + "h "
        time -= (hours * 3600)

    if time > 60 or hours > 0 or days > 0 or weeks > 0:
        minutes = math.floor(time / 60)
        string += str(minutes) + "m "
        time -= (minutes * 60)

    string += str(time) + "s"

    return string


def get_own_ip():
    """
    Get outside IP address of current internet connection

    Connects to google's DNS server and sees what IP that gives us. So reliant on that server being up, but that's a
    rather safe assumption.

    :return: IP address
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.shutdown(socket.SHUT_RDWR)
    s.close()

    return ip


def banned(address, type="ban", name=False):
    """
    Check if address is banned

    Checks the database and sees whether the address matches a banlist entry. Mirrors are never banned and always
    whitelisted

    :param address: Complete IP address to check
    :param whitelisted: Check for whitelist instead of ban
    :return: True if banned/whitelisted, False if not
    """
    lock.acquire()

    dbconn = sqlite3.connect(config.DATABASE)
    dbconn.row_factory = sqlite3.Row
    cursor = dbconn.cursor()

    mirrors = cursor.execute("SELECT * FROM mirrors").fetchall()
    banlist = cursor.execute("SELECT * FROM banlist").fetchall()

    mirrors = [mirrors[i]["address"] for i, value in enumerate(mirrors)]
    banlist = [dict(banlist[i]) for i, value in enumerate(banlist)]

    cursor.close()
    dbconn.close()

    lock.release()

    if type == "prefer" or type == "unprefer":
        for ban in banlist:
            if fnmatch.filter([address], ban["address"]) and ban["type"] == type:
                if name and ban["reserved"] != "":
                    return (fnmatch.filter([name.lower()], ban["reserved"].lower()) != [])
                else:
                    return True
        return False

    if address in mirrors:
        return True if type == "whitelist" else False

    if type == "ban" and (address == "127.0.0.1" or address == "localhost"):
        return False

    for ban in banlist:
        if fnmatch.filter([address], ban["address"]) and ban["type"] == type:
            return True

    return False


def whitelisted(address):
    """
    Check if address is whitelisted

    Alias for banned(address, "whitelist")

    :param address: Complete IP address to check
    :return: True if whitelisted, False if not
    """
    return banned(address, "whitelist")


def preferred(address=False, name=False):
    """
    Check if address is preferred

    Alias for banned(address, "prefer")

    :param address: Complete IP address to check
    :return: True if whitelisted, False if not
    """
    return banned(address, "prefer", name)


def unpreferred(address=False, name=False):
    """
    Check if address is preferred

    Alias for banned(address, "prefer")

    :param address: Complete IP address to check
    :return: True if whitelisted, False if not
    """
    return banned(address, "unprefer", name)


def all_mirrors():
    """
    Get list of mirrors

    Checks the database and returns all mirror IP addresses

    :return: List of addresses
    """
    lock = threading.Lock()
    lock.acquire()

    dbconn = sqlite3.connect(config.DATABASE)
    dbconn.row_factory = sqlite3.Row
    cursor = dbconn.cursor()

    mirrors = cursor.execute("SELECT * FROM mirrors").fetchall()
    mirrors = [mirrors[i]["address"] for i, value in enumerate(mirrors)]

    cursor.close()
    dbconn.close()

    lock.release()

    return mirrors


def acquire_lock():
    """
    Acquire lock

    To be used before the database is manipulated.
    """
    lock.acquire()


def release_lock():
    """
    Release lock

    To be done when done manipulating the database.
    """
    lock.release()


def query(sqlquery, replacements=tuple(), autolock=True, mode="execute"):
    """
    Execute sqlite query

    Acquires a Lock before querying, so the database doesn't run into concurrent reads/writes etc. Database
    connection is set up and closed for each query - the overhead is not too bad and this way we can be sure that
    there will be no conflicts

    .fetchone() and .fetchall() can't be used once the cursor is closed, so this method accepts an optional
    parameter to return the result of either of those instead of the raw query result, which is in most cases
    useless.

    :param query: Query string
    :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
    :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
    :param mode: Return mode: "fetchone" (one row), "fetchall" (list of rows), "execute" (raw query result)
    :return: Query result
    """
    if autolock:
        acquire_lock()

    dbconn = sqlite3.connect(config.DATABASE)
    dbconn.row_factory = sqlite3.Row

    db = dbconn.cursor()

    if mode == "fetchone":
        result = db.execute(sqlquery, replacements).fetchone()
    elif mode == "fetchall":
        result = db.execute(sqlquery, replacements).fetchall()
    else:
        result = db.execute(sqlquery, replacements)

    dbconn.commit()

    db.close()
    dbconn.close()

    if autolock:
        release_lock()

    return result


def fetch_one(sqlquery, replacements=tuple(), autolock=True):
    """
    Fetch one row resulting from a database query

    :param query: Query string
    :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
    :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
    :return: Query result, dictionary
    """
    return query(sqlquery, replacements, autolock, "fetchone")


def fetch_all(sqlquery, replacements=tuple(), autolock=True):
    """
    Fetch all rows resulting from a database query

    :param query: Query string
    :param replacements: Replacements, viz. sqlite3.execute()'s second parameter
    :param autolock: Acquire lock? Can be set to False if locking is done manually, e.g. for batches of queries
    :return: Query result, list of dictionaries
    """
    return query(sqlquery, replacements, autolock, "fetchall")

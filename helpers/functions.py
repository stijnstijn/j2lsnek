import threading
import fnmatch
import sqlite3
import socket
import config
import math


def decode_mode(mode):
    """
    JJ2 uses numbers instead of strings, but strings are easier for humans to work with

    :param mode: Mode number as sent by the client
    :return: Mode string ("ctf", "treasure", "battle" or "unknown")
    """
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
    version_string = ""

    if version_string[0:2] == "21":
        version_string = "1.23"
    else:
        version_string = "1.24"

    return version_string + version[2:]


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
        weeks = math.floor(time / (days * 7))
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


def banned(address, whitelisted=False):
    """
    Check if address is banned

    Checks the database and sees whether the address matches a banlist entry. Mirrors are never banned and always
    whitelisted

    :param address: Complete IP address to check
    :param whitelisted: Check for whitelist instead of ban
    :return: True if banned/whitelisted, False if not
    """
    lock = threading.Lock()
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

    if address in mirrors:
        return whitelisted

    for ban in banlist:
        if fnmatch.filter([address], ban["address"]) and whitelisted == (banlist["type"] == "whitelist"):
            return True

    return False


def whitelisted(address):
    """
    Check if address is whitelisted

    Alias for banned(address, True)

    :param address: Complete IP address to check
    :return: True if whitelisted, False if not
    """
    return banned(address, True)


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

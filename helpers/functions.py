import threading
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
    version = version.decode("ascii")
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

def whitelisted(ip):
    return True if ip == "127.0.0.1" else banned(ip, whitelisted=True)

def banned(ip, whitelisted=False):
    lock = threading.Lock()
    lock.acquire()
    dbconn = sqlite3.connect(config.DATABASE)
    db = dbconn.cursor()
    type = "ban" if not whitelisted else "whitelist"
    matches = db.execute("SELECT COUNT(*) FROM banlist WHERE ? LIKE REPLACE(address, '*', '%') AND type = ?", (ip, type)).fetchone()[0]
    lock.release()

    return matches > 0

def get_own_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()

    return ip
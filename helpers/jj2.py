import threading
import fnmatch
import sqlite3
import config
import time
import re

from helpers.functions import query, fetch_all, fetch_one
from helpers.exceptions import ServerUnknownException


class jj2server:
    """
    Class that represents a jj2 server

    Offers a few basic methods to transparently interface with the database record that belongs to the server
    """
    new = False
    forbidden_characters = "#%&[]^{}~"  # not displayed by jj2 and should therefore never be part of server names

    def __init__(self, key, create_if_unknown=True):
        """
        Set up database connection (they're not thread-safe) and retrieve server info from database. If not available
        (which is likely), create a new record

        :param key: Server ID, usually in the format "127.0.0.1:86400" but could be anything
        :param create_if_unknown:  Create server in database if it does not exist yet. If
        `False`, an exception is raised instead.
        """
        self.id = key
        self.updated = {"id": key}

        self.data = fetch_one("SELECT * FROM servers WHERE id = ?", (self.id,))

        if not self.data:
            if not create_if_unknown:
                raise ServerUnknownException()

            query("INSERT INTO servers (id, created, lifesign) VALUES (?, ?, ?)",
                  (self.id, int(time.time()), int(time.time())))
            self.data = fetch_one("SELECT * FROM servers WHERE id = ?", (self.id,))
            self.new = True

        if not self.data:
            raise NotImplementedError  # there's something very wrong if this happens

        datadict = {key: self.data[key] for key in self.data.keys()}
        self.data = datadict

    def set(self, item, value):
        """
        Update server record

        :param item: Property to update. Raises IndexError if property doesn't exist
        :param value: New value
        :return: Nothing
        """
        if item not in self.data:
            raise IndexError("%s is not a server property" % item)

        if item == "name":
            value = self.strip(value)

        if item == "max" or item == "players":
            if value > config.MAXPLAYERS:
                value = config.MAXPLAYERS
            if value < 0:
                value = 0

        if self.data[item] != value:
            self.updated[item] = value

        self.data[item] = value
        query("UPDATE servers SET %s = ?, lifesign = ? WHERE id = ?" % item, (value, int(time.time()), self.id))
        # not escaping column names above is okay because the column name is always a key in self.data which is also
        # a valid column name

        return

    def validate_name(self, name, ip, alternative):
        """
        Checks if a name is not reserved
        
        If the name is reserved (i.e. a whitelist entry's reserved filter matches the server name) an alternative
        server name is returned, otherwise the original name is.
        
        :param name: Server name as sent by host 
        :param ip: Server IP
        :param alternative: Alternative name to use if name is reserved by someone else
        :return: Either the original or alternative name
        """
        reserved = fetch_all("SELECT * FROM banlist WHERE type = ? AND reserved != ''", ('whitelist',))
        name = self.strip(name)
        check = name.replace(" ", "").replace("|", "")

        if check == "":
            return alternative

        for mask in reserved:
            check_against = mask["reserved"].replace(" ", "")
            ip_matches = fnmatch.filter([ip], mask["address"]) != []
            name_matches = fnmatch.filter([check.lower()], check_against.lower()) != []
            if name_matches and not ip_matches:
                return alternative

        return name

    def get(self, item):
        """
        Get server property

        :param item: Property to get. Raises IndexError if property doesn't exist
        :return: Property value
        """
        if item not in self.data:
            raise IndexError("%s is not a server property" % item)

        return self.data[item]

    def flush_updates(self):
        """
        Get updates to server and reset track record

        :return: Dictionary of updates, also always contains ID-field
        """
        updates = self.updated
        self.updated = {"id": updates["id"]}
        return updates

    def update_lifesign(self):
        """
        Let the database know the server is still alive (updates the "last seen" property, 'lifesign')

        :return: Nothing
        """
        self.set("lifesign", int(time.time()))

        return

    def forget(self):
        """
        Delete server from database

        :return: Nothing
        """
        query("DELETE FROM servers WHERE id = ?", (self.id,))

        return

    def strip(self, string):
        """
        Remove unwanted characters from string (e.g. server name)
        
        Removes anything not between ascii values 32 (space) and 126, and collapses repeated spaces
        
        :param string: String to strip
        :return: Stripped string
        """
        string = re.sub(r'[^\x20-\x7d]', r' ', string)
        string = re.sub(r"[ ]+", r" ", string).strip(" \t\r\n\0")

        invisible = str.maketrans(dict.fromkeys(self.forbidden_characters))
        string = string.translate(invisible)

        return string

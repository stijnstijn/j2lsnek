import threading
import sqlite3
import config
import time
import re

from helpers.functions import query, fetch_all, fetch_one


class jj2server:
    """
    Class that represents a jj2 server

    Offers a few basic methods to transparently interface with the database record that belongs to the server
    """
    new = False

    def __init__(self, key):
        """
        Set up database connection (they're not thread-safe) and retrieve server info from database. If not available
        (which is likely), create a new record

        :param id: Server ID, usually in the format "127.0.0.1:86400" but could be anything
        """
        self.id = key
        self.updated = {"id": key}

        self.data = fetch_one("SELECT * FROM servers WHERE id = ?", (self.id,))

        if not self.data:
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
            value = re.sub(r'[^\x20-\x7f]', r' ', value)  # no funny business with crazy characters
            value = re.sub(r"[ ]+", r" ", value).strip(" \t\r\n\0")

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

    def ping(self):
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
import sqlite3
import config
import time


class jj2server():
    """
    Class that represents a jj2 server: offers a few basic methods to transparently interface with the database
    record that belongs to the server
    """
    def __init__(self, id):
        """
        Set up database connection (they're not thread-safe) and retrieve server info from database. If not available
        (which is likely), create a new record

        :param id: Server ID, usually in the format "127.0.0.1:86400" but could be anything
        """
        self.dbconn = sqlite3.connect(config.DATABASE)
        self.dbconn.row_factory = sqlite3.Row
        self.db = self.dbconn.cursor()

        self.id = id

        self.data = self.db.execute("SELECT * FROM servers WHERE id = ?", (self.id,)).fetchone()

        if not self.data:
            self.db.execute("INSERT INTO servers (id, created, lifesign) VALUES (?, ?, ?)", (self.id, int(time.time()), int(time.time())))
            self.dbconn.commit()
            self.data = self.db.execute("SELECT * FROM servers WHERE id = ?", (self.id,)).fetchone()

        if not self.data:
            raise NotImplementedError  # there's something very wrong if this happens

        datadict = {}
        for column in self.data.keys():
            datadict[column] = self.data[column]

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

        self.data[item] = value
        self.db.execute("UPDATE servers SET %s = ?, lifesign = ? WHERE id = ?" % item, (value, time.time(), self.id))
        # not escaping column names above is okay because the column name is always a key in self.data which is also
        # a valid column name

        self.dbconn.commit()

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

    def ping(self):
        """
        Let the database know the server is still alive (updates the "last seen" property, 'lifesign')

        :return: Nothing
        """
        self.set("lifesign", time.time())

        return

    def forget(self):
        """
        Delete server from database

        :return: Nothing
        """
        self.db.execute("DELETE FROM servers WHERE id = ?", (self.id,))
        self.dbconn.commit()

        return
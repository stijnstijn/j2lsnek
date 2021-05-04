class J2lsnekException(BaseException):
    """
    Basic j2lsnek exception
    """
    pass


class ServerUnknownException(J2lsnekException):
    """
    To be raised when trying to manipulate data for a server that we have no
    record of
    """
    pass

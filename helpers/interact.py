import threading


class key_poller(threading.Thread):
    """
    Interaction poller

    Waits for key input and shuts down the list server if right input is received. Threadable, so the main thread can
    go on doing whatever it does in the meantime.
    """
    ls = None
    looping = True

    def __init__(self, ls=None):
        """
        Set up interaction poller

        :param ls: Reference to list server
        """
        self.ls = ls
        threading.Thread.__init__(self)

    def run(self):
        """
        Wait for input

        If input = "q", stop looping and send signal to main thread to initiate shutdown. Else just wait for next input.
        :return:
        """
        while self.looping:
            cmd = input("")
            if cmd == "q":
                self.looping = False
                self.ls.halt()

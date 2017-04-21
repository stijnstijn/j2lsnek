import threading


class interact(threading.Thread):
    ls = None
    looping = True

    def __init__(self, ls=None):
        self.ls = ls
        threading.Thread.__init__(self)

    def run(self):
        while self.looping:
            cmd = input("")
            if cmd == "q":
                self.looping = False
                self.ls.halt()

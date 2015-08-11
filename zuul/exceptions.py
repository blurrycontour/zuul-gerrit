class ChangeNotFound(Exception):
    def __init__(self, number, ps):
        self.number = number
        self.ps = ps
        self.change = "%s,%s" % (str(number), str(ps))
        message = "Change %s not found" % self.change
        super(ChangeNotFound, self).__init__(message)

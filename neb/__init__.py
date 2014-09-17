

class NebError(Exception):
    """A standard NEB error, which can be sent back to the user."""

    def __init__(self, code=0, msg=""):
        Exception.__init__(self, msg)
        self.code = code
        self.msg = msg

    def as_str(self):
        return "(%s) : %s" % (self.code, self.msg)
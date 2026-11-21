"""Fixed public errors, deliberately independent of exceptions and input."""
class PublicError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

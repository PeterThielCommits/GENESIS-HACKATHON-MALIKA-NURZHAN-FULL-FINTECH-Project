"""Opaque in-memory cursor handles authenticated by an injected replay key."""
import copy
import base64
import hashlib
import hmac
from .state import canonical
from .errors import PublicError

class Cursors:
    def __init__(self, key, snapshot):
        self.key, self.snapshot, self.handles = key, snapshot, {}

    def issue(self, table, filters, last):
        payload = [1, self.snapshot, table, filters, last]
        token = base64.urlsafe_b64encode(hmac.new(self.key, canonical(payload), hashlib.sha256).digest()).decode().rstrip('=')
        self.handles[token] = (table, copy.deepcopy(filters), last)
        return token

    def read(self, token, table, filters):
        if not isinstance(token, str) or len(token) != 43 or token not in self.handles:
            raise PublicError('BAD_CURSOR')
        t, f, last = self.handles[token]
        if t != table or f != filters:
            raise PublicError('BAD_CURSOR')
        return last

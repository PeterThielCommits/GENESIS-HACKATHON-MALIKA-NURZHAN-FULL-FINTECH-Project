"""Stateless, namespace-separated identifiers; no mutation or row-order input."""
import hashlib
import hmac
import json


def make_id(key: bytes, namespace: str, entity_key: str, family: str) -> str:
    if not isinstance(key, bytes) or not key or not all(
        isinstance(s, str) and s for s in (namespace, entity_key)
    ):
        raise ValueError('key, namespace and stable entity key required')
    payload = json.dumps([family, namespace, entity_key], separators=(',', ':')).encode()
    token = hmac.new(key, payload, hashlib.sha256).hexdigest()[:24]
    if family == 'A':
        return f'{namespace.upper()}-{token.upper()}'
    if family == 'B':
        return f'{namespace.upper()}/{token[:8]}/{token[8:]}'
    if family == 'C':
        return f'{namespace.lower()}_{token}'
    if family == 'D':
        number = int(token, 16)
        return f'{number:029d}{(-number * 10) % 7}'  # entire ID divisible by seven
    raise ValueError('unknown ID family')

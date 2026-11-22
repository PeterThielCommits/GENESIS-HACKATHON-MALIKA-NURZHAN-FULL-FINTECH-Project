"""Regression tests for the opaque pagination cursor codec (REQ-ENV-012).

Official check C05 requires that *every* source row is reachable by walking
the cursors the environment hands out, with no gaps and no repeats. The token
format must therefore never depend on a byte value occurring (or not
occurring) inside the signature.

BUG-TL-0002: the original layout was ``raw || b"." || sig``, split with
``rsplit(b".", 1)``. The signature is 16 uniformly random HMAC bytes, so
roughly 6% of issued tokens contained ``0x2E`` inside the signature; the split
then produced a wrong ``raw`` and verification failed with
``BAD_CURSOR: cursor signature verification failed``. Walking a 214-row ledger
in pages of 50 died on page 4 (offset 200). The layout is now
``sig || raw`` with a fixed-width prefix, so no delimiter byte matters.
"""

from __future__ import annotations

import base64
import unittest

from env.cursors import CursorCodec
from env.errors import EnvError

KEY = b"regression-key-0123456789"


class TestCursorRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self.codec = CursorCodec(KEY)

    def test_every_offset_round_trips(self) -> None:
        """No offset may be unusable; the old layout failed ~6% of them."""
        for offset in range(1000):
            with self.subTest(offset=offset):
                token = self.codec.encode("ledger", {}, offset)
                self.assertEqual(self.codec.decode(token, "ledger", {}), offset)

    def test_offsets_that_broke_the_delimiter_layout(self) -> None:
        """The specific offsets whose signature contained 0x2E must now work."""
        for offset in (4, 13, 41, 60, 67):
            with self.subTest(offset=offset):
                token = self.codec.encode("ledger", {}, offset)
                self.assertEqual(self.codec.decode(token, "ledger", {}), offset)

    def test_token_is_opaque_and_short(self) -> None:
        token = self.codec.encode("ledger", {}, 500)
        self.assertLessEqual(len(token), 512)
        self.assertNotIn("500", token)
        self.assertNotIn("ledger", token)

    def test_signature_prefix_has_fixed_width(self) -> None:
        """Layout is sig||raw: identical raw at different keys differ only in prefix."""
        token = self.codec.encode("ledger", {}, 7)
        decoded = base64.urlsafe_b64decode(token.encode("ascii"))
        self.assertEqual(decoded[CursorCodec._SIG_LEN :][:1], b"{")


class TestCursorTamperResistance(unittest.TestCase):
    def setUp(self) -> None:
        self.codec = CursorCodec(KEY)

    def _tamper(self, offset: int, index: int) -> str:
        decoded = bytearray(
            base64.urlsafe_b64decode(self.codec.encode("ledger", {}, offset).encode("ascii"))
        )
        decoded[index] ^= 0x01
        return base64.urlsafe_b64encode(bytes(decoded)).decode("ascii")

    def test_flipped_signature_byte_rejected(self) -> None:
        with self.assertRaises(EnvError) as ctx:
            self.codec.decode(self._tamper(300, 3), "ledger", {})
        self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_flipped_payload_byte_rejected(self) -> None:
        with self.assertRaises(EnvError) as ctx:
            self.codec.decode(self._tamper(300, CursorCodec._SIG_LEN + 2), "ledger", {})
        self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_wrong_table_rejected(self) -> None:
        token = self.codec.encode("ledger", {}, 5)
        with self.assertRaises(EnvError) as ctx:
            self.codec.decode(token, "invoices", {})
        self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_wrong_filters_rejected(self) -> None:
        token = self.codec.encode("ledger", {"a": 1}, 5)
        with self.assertRaises(EnvError) as ctx:
            self.codec.decode(token, "ledger", {})
        self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_truncated_and_empty_tokens_rejected(self) -> None:
        token = self.codec.encode("ledger", {}, 9)
        for bad in ("", token[:8], token[: CursorCodec._SIG_LEN]):
            with self.subTest(bad=bad):
                with self.assertRaises(EnvError) as ctx:
                    self.codec.decode(bad, "ledger", {})
                self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_trailing_garbage_rejected(self) -> None:
        """BUG-TL-0003: base64 silently drops trailing junk.

        ``base64.urlsafe_b64decode(token + "x")`` returns the original bytes,
        so a modified token used to pass verification. The decoder now
        requires the token to re-encode to itself byte for byte.
        """
        token = self.codec.encode("ledger", {}, 2)
        for suffix in ("x", "xy", "=", "..", "A", "AAA"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(EnvError) as ctx:
                    self.codec.decode(token + suffix, "ledger", {})
                self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_non_canonical_trailing_bits_rejected(self) -> None:
        """Corrupting the ignored low bits of the last data char is detected.

        Tokens are padded (``=``), so the last *data* character carries bits
        that base64 decoders discard. Flipping those bits leaves the decoded
        bytes unchanged, so only a canonical re-encode check catches it.
        """
        token = self.codec.encode("ledger", {}, 3)
        self.assertTrue(token.endswith("="), "fixture assumption: padded token")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        index = alphabet.index(token[-2])
        mutated = token[:-2] + alphabet[index ^ 0b01] + token[-1]
        self.assertNotEqual(mutated, token)
        with self.assertRaises(EnvError) as ctx:
            self.codec.decode(mutated, "ledger", {})
        self.assertEqual(ctx.exception.code, "BAD_CURSOR")

    def test_non_string_token_rejected(self) -> None:
        for bad in (None, 12, b"bytes"):  # type: ignore[list-item]
            with self.subTest(bad=bad):
                with self.assertRaises(EnvError) as ctx:
                    self.codec.decode(bad, "ledger", {})  # type: ignore[arg-type]
                self.assertEqual(ctx.exception.code, "BAD_CURSOR")


if __name__ == "__main__":
    unittest.main()

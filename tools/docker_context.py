#!/usr/bin/env python3
"""Faithful ``.dockerignore`` semantics and the resulting Docker build context.

Docker matches ``.dockerignore`` patterns against the **context-relative
path**, one path element at a time:

* a pattern that contains a slash is anchored at the context root
  (``episodes/*/sealed/`` matches exactly ``<root>/episodes/<x>/sealed/``);
* a pattern **without** a slash is anchored at the context root as well --
  ``__pycache__`` matches only ``<root>/__pycache__``, **not**
  ``<root>/contracts/__pycache__`` (the Docker documentation's own example
  ``temp?`` matches ``/tempa`` but not ``/somedir/tempa``);
* ``*`` does not cross a path separator, ``**`` does;
* when a directory matches, its whole subtree is excluded;
* the **last** matching pattern wins, so a later ``!pattern`` re-includes.

This module implements exactly those rules. It exists because the repository
once shipped a ``.dockerignore`` whose root-anchored patterns did not match
the real layout (``episodes/dev/<ep>/sealed/``) and therefore baked sealed
truth into the submission image (defect ``D-16-02``), and because the
root-anchored ``__pycache__`` / ``*.pem`` / ``.env`` patterns silently left
nested copies of the same material in the build context.

The module is stdlib-only and import-safe: it performs no I/O at import time.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent


class IgnoreRule(NamedTuple):
    """One ``.dockerignore`` rule."""

    pattern: str
    negated: bool
    directory_only: bool
    regex: re.Pattern[str]


def _compile(pattern: str) -> IgnoreRule:
    """Translate one Docker ignore pattern into a path regex."""
    raw = pattern.strip()
    negated = raw.startswith("!")
    if negated:
        raw = raw[1:]
    directory_only = raw.endswith("/")
    raw = raw.rstrip("/")

    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if raw[index : index + 2] == "**":
            index += 2
            if raw[index : index + 1] == "/":
                index += 1
                out.append("(?:.*/)?")
            else:
                out.append(".*")
            continue
        if char == "*":
            out.append("[^/]*")
            index += 1
            continue
        if char == "?":
            out.append("[^/]")
            index += 1
            continue
        out.append(re.escape(char))
        index += 1
    body = "".join(out)
    # A pattern matches the path itself and everything under it.
    regex = re.compile("^" + body + "(/.*)?$")
    return IgnoreRule(pattern=pattern, negated=negated, directory_only=directory_only, regex=regex)


class DockerIgnore:
    """The ``.dockerignore`` rules of a repository."""

    def __init__(self, patterns: Iterable[str]) -> None:
        self.rules: list[IgnoreRule] = []
        for raw in patterns:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            self.rules.append(_compile(line))

    @classmethod
    def from_file(cls, path: Path) -> "DockerIgnore":
        if not path.is_file():
            return cls(())
        return cls(path.read_text(encoding="utf-8", errors="replace").splitlines())

    def match(self, rel_path: str) -> bool:
        """Whether ``rel_path`` matches this rule set (last match wins)."""
        decision = False
        for rule in self.rules:
            if not rule.regex.match(rel_path):
                continue
            decision = not rule.negated
        return decision

    def excluded(self, rel_path: str) -> bool:
        """Whether a context path is excluded (parents included)."""
        if self.match(rel_path):
            return True
        parent = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
        while parent:
            if self.match(parent):
                return True
            parent = parent.rsplit("/", 1)[0] if "/" in parent else ""
        return False


def iter_context_files(root: Path, ignore: DockerIgnore) -> Iterator[str]:
    """Yield the context-relative paths ``COPY . /app`` would copy."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part == ".git" for part in rel.parts):
            continue
        posix = rel.as_posix()
        if ignore.excluded(posix):
            continue
        yield posix


def build_context(root: Path = REPO_ROOT, ignore: DockerIgnore | None = None) -> list[str]:
    """The sorted list of files in the Docker build context."""
    rules = ignore if ignore is not None else DockerIgnore.from_file(root / ".dockerignore")
    return sorted(iter_context_files(root, rules))

#!/usr/bin/env python3
"""Generate a bootstrap password hash without placing plaintext in shell history."""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Sequence

from protocol_studio.security import hash_password, normalize_username, validate_new_password


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="FEIAN")
    args = parser.parse_args(argv)
    username = normalize_username(args.username)

    first = getpass.getpass("New bootstrap password: ")
    second = getpass.getpass("Confirm bootstrap password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    errors = validate_new_password(first, username)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(hash_password(first))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

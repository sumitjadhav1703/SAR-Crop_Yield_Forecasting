"""Measured word count for the Kaggle write-up. Round 2's estimates were wrong three
sessions running, so the limit is checked by a script and never by eye.

Counts whitespace-separated tokens on the raw markdown, which is the strictest reading:
it charges for every markdown marker that is attached to a word. Kaggle's own counter is
not published, so overcounting is the safe direction.
"""

import sys

LIMIT = 2000

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "writeup.md"
    with open(path) as fh:
        n = len(fh.read().split())
    print(f"{path}: {n} words (limit {LIMIT}, {LIMIT - n:+d})")
    sys.exit(0 if n <= LIMIT else 1)

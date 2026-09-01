"""Trace every number in the write-up back to a line the shipped run printed.

Round 2's recurring defect was "a number no cell computes": a figure quoted in the write-up
that no longer matched anything the pipeline printed, because the code moved and the prose
did not. It happened three times. This makes it a check rather than a habit.

Every numeric token in `writeup.md` must appear verbatim in the pipeline log, or be listed
in `EXTERNAL` below with its source. `EXTERNAL` is the interesting half: it is the complete
list of numbers in the write-up that this pipeline does not produce, and every entry has to
name where it came from.

    python audit_writeup.py                      # writeup.md against logs/pipeline_clean.log
    python audit_writeup.py writeup.md some.log
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Numbers the pipeline does not print, with the source of each. Anything not here must be
# traceable to the log.
EXTERNAL = {
    # the dataset and the competition
    "966": "Sokhda_Farms.shp feature count",
    "22": "ID_1 in the shapefile",
    "2": "Round 2, and the two shapefiles",
    "3": "three mechanisms, three days of rain",
    "500": "the zone grid cell size, a design choice",
    "0.27": "median plot area, printed by submit.report",
    "1": "prose",
    "10": "prose",
    "5": "the five crops",
    "6": "the six passes",
    "4": "the four Round 2 passes",
    "2025": "the season", "2024": "the climatology end year",
    "1995": "the climatology start year", "2026": "the rabi year",
    "29": "29 Oct, and the rice shortfall in per cent",
    "12": "12 Nov, 12 Dec, twelve parcels",
    "13": "13 Oct", "16": "16 Jan, and 16 September",
    "18": "18 September", "9": "9.65 GHz-era prose",
    # instrument and geometry, from the scene metadata
    "318.4": "T5 view azimuth, scene metadata",
    "135": "the left-looking view azimuth, scene metadata",
    "01:37": "T5 acquisition time, scene metadata",
    "63": "rain in the three days before T5, NASA POWER",
    "108": "the first-pass T5 shift, coreg log",
    "60": "the height sweep lower bound",
    "20": "the height sweep upper bound and the 20 m fine-search bound",
    "8": "the 8x decimation factor",
    # external statistics
    "1098.5": "NASA POWER kharif total, printed by season_context",
    "923.1": "NASA POWER 1995-2024 mean, printed by season_context",
    "0.66": "the rainfall z-score, printed by season_context",
    "26": "the bajra shortfall in per cent, DA&FW",
    "35.7": "Vadodara kharif irrigated share, CGWB",
    "31.6": "Round 2's tier-1 area share, Round 2's own log",
    "0.45": "Round 2's cotton completeness constant",
    "46.8": "Round 2's tier-1 area range, Round 2's own log",
    "130.6": "Round 2's tier-1 area range, Round 2's own log",
    "1.000": "Round 2's measured health-vs-yield correlation",
    "1.35": "T3's residual under Round 2's window, S2 log",
    "4.26": "the retired G3 spread, S2 log",
    "0.0015": "the cross-check discrepancy caught in S10; the fix removed the number, "
              "so nothing prints it any more -- AGENTS.md section S10",
}


def numbers(text: str) -> list[str]:
    """Numeric tokens, longest first so 0.569 is not matched by 0.56."""
    found = re.findall(r"\d+(?:\.\d+)?(?:e[+-]?\d+)?", text.replace(",", ""))
    return sorted(set(found), key=lambda s: (-len(s), s))


def matching_line(token: str, log: str) -> str | None:
    """The first log line a token can be read off, verbatim or correctly rounded.

    The trace this feeds exists because "the number is somewhere in the log" is a weaker
    check than it looks. The write-up once quoted a per-crop t5_anomaly of +1.99 dB that no
    Round 3 run ever printed; it passed the audit because an unrelated decile table happened
    to carry 1.99 in a different column. Bare-token matching cannot catch that. A human
    reading token-to-line can, in about a minute, and that is what `--trace` is for.
    """
    for line in log.splitlines():
        if token in line:
            return line.strip()
    if "." in token and "e" not in token:
        places = len(token.split(".")[1])
        for line in log.splitlines():
            for candidate in re.findall(r"\d+\.\d+", line):
                if f"{float(candidate):.{places}f}" == token:
                    return line.strip()
    return None


def printed_at(token: str, log: str) -> bool:
    """Verbatim, or the correctly-rounded form of something the log printed.

    The log prints `production_t` at full precision -- 331.663 -- and the write-up quotes
    331.7. That is the same number, so requiring a verbatim match would push the write-up
    into quoting six significant figures at a reader. Rounding is accepted; a DIFFERENT
    number still fails, which is the defect this is here to catch.
    """
    if token in log:
        return True
    if "." not in token or "e" in token:
        return False
    places = len(token.split(".")[1])
    for candidate in re.findall(r"\d+\.\d+", log):
        if f"{float(candidate):.{places}f}" == token:
            return True
    return False


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    doc = args[0] if args else os.path.join(ROOT, "writeup.md")
    log = args[1] if len(args) > 1 else os.path.join(ROOT, "logs", "pipeline_clean.log")
    with open(doc) as fh:
        text = fh.read()
    with open(log) as fh:
        printed = fh.read().replace(",", "")

    if "--trace" in sys.argv:
        path = os.path.join(ROOT, "logs", "writeup_trace.txt")
        with open(path, "w") as fh:
            for n in sorted(numbers(text), key=float):
                line = matching_line(n, printed)
                fh.write(f"{n:>12}  {line if line else 'EXTERNAL: ' + EXTERNAL.get(n, '??')}\n")
        print(f"  wrote {path} -- every number against the line it was read off")

    missing = [n for n in numbers(text)
               if not printed_at(n, printed) and n not in EXTERNAL]
    traced = [n for n in numbers(text) if printed_at(n, printed)]

    print(f"{doc}\n  {len(numbers(text))} distinct numeric tokens")
    print(f"  {len(traced)} traced to a printed line in {os.path.basename(log)}")
    print(f"  {len(numbers(text)) - len(traced) - len(missing)} external, each sourced "
          f"in EXTERNAL")
    if missing:
        print("\n  NOT TRACED -- either the run stopped printing it or the prose is stale:")
        for n in missing:
            for line in text.splitlines():
                if n in line:
                    print(f"    {n:>10}   {line.strip()[:88]}")
                    break
        sys.exit(1)
    print("\n  every number in the write-up is either printed by the shipped run or "
          "externally sourced")

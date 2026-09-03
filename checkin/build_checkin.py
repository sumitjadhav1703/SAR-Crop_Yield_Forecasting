"""Render checkin.html to a two-page PDF with headless Chrome.

PDF only, strictly two pages, is a submission requirement, so the page count is asserted
rather than eyeballed. There is no pandoc or wkhtmltopdf on this machine; Chrome honours
`@page` and prints the local `figures/*.png` straight off disk.

Chrome writes the PDF and then does not exit under this environment -- the renderer stays
alive with `task_policy_set` errors on stderr -- so the process is polled for the output
file and then terminated, rather than waited on. Waiting on it hangs forever.

    python checkin/build_checkin.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "checkin.html")
OUT = os.path.join(HERE, "Midnight_Checkin_Sokhda.pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGES = 2
DEADLINE_S = 120


def build() -> str:
    if os.path.exists(OUT):
        os.remove(OUT)
    profile = tempfile.mkdtemp(prefix="checkin-chrome-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--disable-background-networking",
         "--disable-sync", "--disable-extensions", f"--user-data-dir={profile}",
         "--no-pdf-header-footer", f"--print-to-pdf={OUT}", f"file://{SRC}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        started = time.time()
        while time.time() - started < DEADLINE_S:
            if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
                time.sleep(1.0)          # let the last write flush
                break
            time.sleep(0.5)
        else:
            raise SystemExit(f"Chrome produced no PDF within {DEADLINE_S}s")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)

    n = len(PdfReader(OUT).pages)
    if n != PAGES:
        raise SystemExit(f"{OUT} is {n} pages; the submission requires exactly {PAGES}")
    print(f"{OUT}\n{n} pages, {os.path.getsize(OUT) / 1024:,.0f} KB")
    return OUT


if __name__ == "__main__":
    build()

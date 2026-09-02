# What is in this directory

**`pipeline_clean.log` is the shipped run**, and it is the only log tracked in git. Every
number in `writeup.md` is printed by it, and `audit_writeup.py --trace` writes the
token-to-log-line mapping to `writeup_trace.txt`, which is tracked beside it. If a number in
the write-up and a number here disagree, the log is right and the write-up is a defect.

Everything else you may see here in a working tree is a development stage log
(`s<stage>_<what>.log`) or an earlier whole-chain run. Those are **gitignored** — `.gitignore`
has `logs/*`, and the two files above are tracked because they were added before it. They are
evidence for the `AGENTS.md` sections that cite them, not part of the submission, and a fresh
clone will not have them.

Nothing in here is read by any module. These are records, not inputs.

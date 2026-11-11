# Who leaves federal agencies first

Which federal agencies and job types lose people fastest, and how much of that is people choosing to quit? I answered it from OPM's public workforce files, FY2012 to FY2026, with a check that runs before any ranking: when an agency stops sending complete data, the raw numbers make it look like nobody left.

![Dashboard: separations reported each month and the agency ranking](docs/dashboard-light.png)

## Summary

I pulled every OPM separations file from Jul 2011 to Sep 2026 (183 monthly files, about 3.8 million rows) and a September headcount snapshot for each year, then turned them into yearly quit rates per 100 employees by agency and by occupational group. Before ranking anything, a coverage check compares each agency's monthly report with its own recent months. In the Sep 2026 file the Army reports 9 separations against a usual month of about 1,860, while still employing 180,217 people. Twenty-nine agency-months since 2011 fail that check, and the years they belong to are listed instead of ranked. What's left shows the same few departments at the top of the quit ranking year after year, and shows that most of 2025's jump in quitting came from the Deferred Resignation Program.

## Problem

A workforce planner or HR leader looking at federal turnover wants two things: where people are leaving, and whether they are choosing to. Raw separation counts answer neither safely.

- A month with missing submissions looks like perfect retention. An agency that sends nothing for a month ranks as the most stable employer in the government.
- People who leave in one month can show up in later files. About one in five rows in the Sep 2026 file is someone who left earlier.
- In 2025, about 109,000 separations were flagged as part of an exit program. Most of them are coded as resignations, so they read like an ordinary wave of quits.

Any ranking built without handling these three tells a planner the wrong story about where to act.

## Inputs

| Source | What | How I got it |
|---|---|---|
| OPM Federal Workforce Data, separations | One row per person who left a covered agency, 69 fields (agency, occupation, reason, effective month and more). 183 monthly files, Jul 2011 to Sep 2026 | Open API, Parquet files, pulled by `fas/pull.py` |
| OPM Federal Workforce Data, employment | One row per employee on the rolls at a snapshot. I use the 16 September snapshots, 2011 to 2026, about 2 million rows each | Same API |
| BLS Job Openings and Labor Turnover Survey | Monthly quits rate for Federal, State and local, Total nonfarm and three private industries, 2011 to 2026 | BLS public API |

OPM's data covers most executive branch civilian employees. It leaves out the Postal Service, the intelligence agencies and a few others by design.

## Discovery

**Missing data looks like retention.** The Army reported 2,430 separations in the Sep 2024 file and 9 in the Sep 2026 file. The Air Force went from 2,220 to 26. Both still had over 150,000 people on the September 2026 rolls. OPM's site carries a notice that a change in Department of War data processing is affecting some components' September 2026 data. My check flags August 2026 for the same agencies too. Across the whole window it flags 29 agency-months in 14 agencies.

**Not every low month is a gap.** The Agency for International Development reports very few separations in FY2026 because very few people are left (4,800 employees in Sep 2024, 1,101 in Sep 2025, 230 in Sep 2026). The check skips agencies whose headcount fell by more than half in the year.

**Files arrive late and get revised.** A month's file carries people who left in earlier months, and OPM republishes months with corrections (up to version 5 so far). I count each person in the month they left, and the pull tracks each file by version.

**2025 is two stories.** The government-wide quit rate went from 3.57 per 100 in FY2024 to 7.04 in FY2025. Leaving out separations OPM flags as part of the Deferred Resignation Program, FY2025 is 4.2.

**Dead end:** I tried to match late records against earlier files to rule out double counting. The files have no person ID, and identical rows also occur between different people inside one file, so an exact match proves nothing. I count every row and say so (DECISIONS.md, entry 4).

## Execution

```
OPM API ─┐                                  ┌─ data/clean/*.csv ── dashboard
         ├─ fas/pull.py ── data/raw ── sql/build.sql ─┤
BLS API ─┘  (resumable)      (gitignored)   (DuckDB)  └─ fas/contract.py (CI)
```

1. **Pull.** `fas/pull.py` keeps a manifest of every file with its version and checksum. A file is written as `.part` and renamed only when complete. A stopped run resumes where it stopped, a second run downloads nothing, and a new OPM version of a month is pulled while the old one is kept.
2. **Coverage check.** For each agency and file month, compare separations with the median of the previous 12 file months. Under a quarter of that, for an agency that normally reports 20 or more, is a gap. Any gap month marks the agency's fiscal year incomplete.
3. **Rates.** Quits and every other reason per 100 employees, using the average of the September headcount before and at the end of the fiscal year. Exit-program separations are counted apart so they can be shown or left out.
4. **Contract.** `DATA_CONTRACT.md` and `contract/tables.v1.json` define every column of every output table. CI fails on a missing column, a wrong type, reasons that don't add up, or a rate without its trust flags.

Options I turned down, and what each choice cost, are in [DECISIONS.md](DECISIONS.md): R instead of Python, monthly headcount (about 9 GB), counting by file month, treating gaps as zero, and folding exit programs into quits.

## Results

**The same departments lead the quit ranking almost every year.** Among agencies with 5,000 or more employees, Commerce is in the top five for quit rate in all 12 of its complete years from FY2012 to FY2024, Interior in 11 of 12, Agriculture in 10 of 11, and the Defense Department's own offices (OPM lists the Army, Navy and Air Force separately) in 10 of 13.

**By job type, the gap is wide.** In FY2024, general services and support work lost 9.56 quits per 100 employees. Information technology lost 1.96.

**Federal quitting is low next to the rest of the economy**, and the two measures move together. In FY2024, OPM's covered agencies show 3.57 quits per 100 and BLS shows 6.4 for federal jobs, against 25.8 for all jobs. The OPM and BLS federal numbers cover different groups of employees, so I read the gap between them as a range.

What I'd tell a workforce planner:

1. Check coverage before reading any agency's turnover. A quiet month is more often a reporting problem than a retention win.
2. Look at 2025 and 2026 with exit programs split out. Otherwise program exits read as a quitting crisis.
3. Start retention work where quitting is high every year, not where it spiked once.

**Limits.** FY2026 is provisional: late records and more exit-program actions are still being processed. Small agencies are left out of rankings because a few people move their rate a lot. OPM's field documentation for the exit-program flag wasn't available, so I read it from OPM's own description of the program (DECISIONS.md, entry 6).

**Next steps.** Rerun the pull each month and watch the flagged months fill in. Add monthly headcount for the newest year only, to tighten the provisional rates.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m fas.pull          # about 1.2 GB into data/raw, safe to stop and rerun
python -m fas.build         # data/raw -> data/clean and dashboard/data
python -m fas.contract      # check the tables against the contract
python -m pytest -q         # tests use small synthetic files, no network
python -m http.server 8000 --directory dashboard
```

`python scripts/findings.py` prints every number quoted in this README into `docs/findings.json`. `python scripts/late_record_check.py 2026 09` reruns the late-record check.

## Repo map

| Path | What |
|---|---|
| `fas/pull.py` | Resumable, versioned data pull |
| `sql/build.sql` | Every table rule, in one SQL file |
| `fas/build.py` | Runs the SQL, thresholds in `PARAMS` |
| `fas/contract.py`, `contract/` | Data contract and checker |
| `dashboard/` | Plain HTML page, data as CSV |
| `tests/` | Pull, build and contract tests |
| `DECISIONS.md` | Choices, options turned down, costs |

Data: OPM Federal Workforce Data and BLS JOLTS, both public. Code: MIT license.

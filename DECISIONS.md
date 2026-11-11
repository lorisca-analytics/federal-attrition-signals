# Decisions

Each entry: what I had to choose, the options, what I picked, and what it cost.

## 1. Main data: OPM files, with BLS as the outside line

- **Options:** OPM Federal Workforce Data (one row per separation, every agency and job type), BLS Job Openings and Labor Turnover Survey (industry totals), or both side by side.
- **Picked:** OPM as the main data, BLS only as a comparison line.
- **Why:** The question is which agencies and job types lose people first. BLS stops at "Federal" as one industry, about 2,000 monthly values in total. OPM has about 3.8 million separation rows from Jul 2011 on.
- **Gave up:** BLS is a survey with a long, steady method. OPM's files depend on every agency submitting on time, which is why decision 3 exists.

## 2. Language: Python for the pull, SQL for the tables

- **Options:** R end to end, or Python and SQL.
- **Picked:** Python and SQL (DuckDB, which reads the Parquet files directly).
- **Why:** My other public work is in Python and SQL, so a reader sees one consistent toolset. DuckDB keeps every table rule in one SQL file that someone who doesn't read Python can still check.
- **Gave up:** R's tidyverse would have made some of the reshaping shorter.

## 3. A low month is checked before it is believed

- **Options:** (a) count whatever the file says, (b) treat a missing month as zero, (c) estimate the missing month, (d) flag it and keep that agency-year out of rankings.
- **Picked:** (d). A file month is a gap when an agency that normally reports at least 20 separations a month reports under a quarter of both its own median for the previous 12 months and the same month a year earlier. Any gap month marks that agency's fiscal year incomplete. Incomplete years are listed, not ranked.
- **Why:** In the Sep 2026 file the Army reports 9 separations and the Air Force 26, against usual months of about 1,860 and 1,300, while both still have over 150,000 people on the rolls. Options (a) and (b) would rank them as the most stable agencies in the government. Option (c) invents data.
- **Exception:** an agency whose headcount fell by more than half during the year is not flagged. Few separations is expected when few people are left (the Agency for International Development in FY2026).
- **Fixed after review:** my first version compared each month only with the median of whatever months came before it. For the first year of the window that was 1 to 11 months, so Agriculture's normal winter lows in early 2012 were flagged against its fall peak. Now the pull fetches 12 extra months (Jul 2010 to Jun 2011) used only as a baseline, the median needs a full 12 months, and the same-month-a-year-earlier test keeps seasonal lows from being flagged.
- **Sensitivity** (`scripts/sensitivity.py`, `docs/sensitivity.txt`): at a quarter and 20 a month, 17 agency-months fail. A fifth gives 14, a third gives 37, a half gives 120. Between a fifth and a quarter the result is stable. Past a third the check starts flagging ordinary dips.
- **Gave up:** a ranking with fewer agencies in affected years. The thresholds are judgment calls. They live in one place (`fas/build.py`, `PARAMS`) and the tests pin their behaviour.

## 4. Count by the date a person left, not the file it arrived in

- **Options:** file month (when OPM received the record) or effective month (when the person left).
- **Picked:** effective month for every rate. File month only for the coverage check, because a reporting gap is a property of the file.
- **Why:** About one in five rows in the Sep 2026 file (21%) is a person who left in an earlier month, 1,991 of them in August. Counting by file month would move people into the wrong year.
- **Gave up:** the newest year keeps changing as late records arrive. FY2026 is marked provisional everywhere.
- **Open:** without a person ID I can't prove a late record is never also in the earlier file. `scripts/late_record_check.py` found 290 of 1,991 late rows in the Sep 2026 file identical to a row in the Aug 2026 file. Identical rows also occur inside a single file (268 in Aug 2026), between different people, so this is an upper bound, not proof. For Jun 2024 the overlap is 0 of 85. I count every row.

## 5. Denominator: average of two September headcounts

- **Options:** monthly headcount (about 69 MB a month, roughly 12.6 GB for the window), quarterly, or the September snapshot at each fiscal year end.
- **Picked:** the average of the September headcount before and at the end of each fiscal year. 16 snapshots, about 1.1 GB.
- **Why:** The rates are yearly, and an average of the two ends absorbs most of a year's growth or shrinkage.
- **Gave up:** monthly rates. An agency that shrinks to almost nothing inside one year can show a separation rate above 100 per 100 (the Agency for International Development in FY2025: 4,803 separations on an average of 2,951). Start and end headcount are carried in the table so a reader sees why.

## 6. Exit programs get their own line

- **Options:** count Deferred Resignation Program exits inside their OPM category (most are resignations, so they would read as quits), drop them, or show them apart.
- **Picked:** keep them in their category in the raw counts, and also count them apart (`drp_separations`, `drp_quits`). The reasons chart gives them their own segment, and the dashboard can leave DRP-flagged quits out of the ranking.
- **Why:** FY2025's quit rate is 7.04 per 100 with them and 4.2 without. Mixing them in would make 2025 look like a sudden wave of people choosing to quit.
- **Gave up:** OPM's field documentation for `drp_indicator` wasn't available to me. I read it as "this separation was part of the DRP" because OPM's own workforce-changes page lists DRP versions of the same categories (resignation, early retirement, voluntary retirement and others), and the flag only appears from Jan 2025. OPM also says more DRP actions will be processed over time, so FY2025 can still change.

## 7. Window starts Jul 2011

- **Options:** start at Jan 2005, where separations files begin, or at Jul 2011.
- **Picked:** Jul 2011, so FY2012 is the first full year.
- **Why:** Headcount snapshots are quarterly before Jul 2011. Mixing quarterly and monthly sources would change the method halfway through the chart.
- **Gave up:** six years of history.

## 8. The data pull keeps every version

- **Options:** download everything on each run, download only missing months, or track months by version.
- **Picked:** track each month by OPM's version number and checksum, keep superseded versions.
- **Why:** OPM revises months after release (up to version 5 in the current listing). A pull that only checks "is this month here" would never pick up a correction. Keeping the old version lets me compare what changed.
- **Gave up:** disk space, about 1.2 GB for the raw files. They stay out of the repo.
- **Tested for real:** when decision 3 needed 12 earlier months, the next run pulled those 12 files and skipped the 199 already on disk.

## 9. Small agencies are not ranked

- **Options:** rank every agency, or set a size floor.
- **Picked:** tables keep agencies with an average of 1,000 or more employees. The dashboard ranking shows 5,000 or more. Occupational groups need 10,000 or more.
- **Why:** At 1,000 employees, ten extra quits move the rate by a full point.
- **Gave up:** small agencies, some of which have the highest rates in the tables.

## 10. Permanent staff get their own rate

- **Options:** rank all staff together, drop seasonal and temporary jobs entirely, or carry both rates.
- **Picked:** carry both. The permanent-staff rate counts only tenure groups 1 and 2 (career and career-conditional appointments) on regular schedules (full time, part time, job sharing, phased retirement), in both the quits and the headcount. The dashboard defaults to it.
- **Why:** an external review of my first draft pointed out that the agencies at the top of the raw ranking are the big seasonal employers. In FY2024, seasonal, intermittent and temporary jobs were about 8% of headcount and about 28% of quits in the agencies I could rank. Commerce's quit rate drops from 4.89 to 1.85 when they are left out. A planner deciding where permanent employees leave needs the second ranking.
- **Gave up:** simplicity. Tenure group 0 also holds senior executives, so they fall out of the permanent rate with the temporaries. They are a small group, and the all-staff rate still includes them.

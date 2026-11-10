# NEC Stats

These scripts are used to generate the stats for the Nürburgring Endurance Championship in iRacing.

I can not share the results data, because there are names, team names, iRacingIDs and other personal data of the individuals and putting that up freely on the internet would be against GDPR, UK DPA and other privacy regulations.

But if you download the results from the iRacing UI (which takes a long time) or the iRacingAPI you can use these scripts.


### AI Use

Yes, the python scripts are made by copilot. I didn't want to invest so much time in this and wanted to get results quickly.


## Usage

Results need to be in the csv format and in the `results/<year>/week<number>/<timeslot>` directory.

### Weekly race-result reports

Run the analyzer from any directory:

```bash
python3 analyze_results.py
```

By default, it reads CSV files beneath `results/` and writes one summary and
one car breakdown CSV per year/week into `stats/<year>/` (for example,
`stats/2026/`).
Override either path when needed:

```bash
python3 analyze_results.py --input-dir /path/to/race-data --output-dir /path/to/stats
```

To process just one week, use `--week 2` or `-w 2`. The compact form `-w2`
works as well. If the input contains multiple years, the selected week number
is processed for each year where that week exists. Without this option, all
weeks are processed.

To process only one year, use `--year 2026` or `-y 2026`. You can combine it
with the week option, for example `python3 analyze_results.py -y 2026 -w 2`.
CSV files outside a `weekN` directory (such as files under `standings/`) are
ignored.

The analyzer finds the race-result header in each CSV, so the metadata and blank
line before the header do not need to be removed. It combines all CSVs beneath
each year/week directory.

The summary reports driver result rows, unique positive `Cust ID` values, team
result rows (negative `Cust ID`), team counts and shares for all classes, the number of distinct car models in each class, the total
`Inc` value from team rows and per class, completed laps per class and across
the full grid, and the number of CSV files processed. Incident and lap totals
use team result rows (negative `Cust ID`) to avoid counting the same team's
values once per driver. Repeated
drivers and teams in different CSVs count again as result entries; unique
drivers are counted once per week. Driver and unique-driver percentages are
their shares of their respective weekly totals (therefore 100% in a weekly
report). Class percentages use all team result rows that week as the grid.

The car breakdown reports each car model's team-entry count and its share of
both its `Car Class` and the whole weekly grid. Unrecognized classes are kept
as `Other: <Car Class>` rather than discarded. Blank `Inc` values count as
zero; malformed IDs, non-integer incident counts, or missing required columns
are reported as errors.

### Driver season history

Search all `eventresult` files for a driver by exact name (case-insensitive),
showing each race's car, start/finish position, completed laps and incident
points, along with that driver's class-specific season standings:

```bash
python3 driver_seasons.py --driver "Dirk Federmann"
```

By default, the script reads beneath `results/` and writes the detailed report
to `stats/<year>/driver_dirk_federmann_results.csv`, with one CSV for each year
found. Use `--input-dir /path/to/data` to change the search root or
`--output /path/to/report.csv` to write one combined report at another location.
Season rank and the other season totals are read from the matching class's
`season-driver` standings CSV, using the driver's customer ID.

### Season-wide statistics

Run the 2026 season-wide totals with:

```bash
python3 aggregate_stats.py
```

By default, the script reads race-result CSV files for 2026 beneath
`results/2026/`.
Use `-w 2` / `--week 2` to select a week and `-y 2025` / `--year 2025` to
select a year; they can be combined. Override the search root with
`--input-dir /path/to/data`. The splits count is the number of CSV result files
processed. It counts distinct positive `Cust ID` values as drivers and
distinct `Team ID` values from team rows as teams. Laps completed and `Inc`
incident points are summed from team rows across the selected events, so the
same team's totals are not counted again for each driver row. Files outside
`weekN` directories, including season standings, are ignored.

### Season statistics web page

Install the page generator dependency with:

```bash
python3 -m pip install -r requirements.txt
```

Generate a season page from the raw result CSV files:

```bash
python3 generate_stats_page.py --year 2026
```

The generator reads `results/<year>/week<number>/...`, uses each result CSV's
`Start Time` metadata to label one- or two-day race weeks, and writes
`web/<year>.html`. The Jinja2 template is `web/stats_template.html`; override
the input directory, template, or output path with `--input-dir`, `--template`,
or `--output`.

#!/usr/bin/env python3
"""Summarize team-entry participation by race timeslot."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import TextIO

from analyze_results import WeekStats, discover_weekly_files


FIELDNAMES = [
    "year",
    "day",
    "timeslot",
    "events",
    "total_team_entries",
    "average_team_entries",
    "csv_files",
]
TIMESLOT_DIRECTORY = re.compile(r"(?:[01]\d|2[0-3])[0-5]\d")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_NAMES = {day.casefold(): day for day in WEEKDAYS}


def _timeslot_directory(path: Path, input_dir: Path, week: str) -> Path:
    relative_parts = path.relative_to(input_dir).parts
    week_index = next(
        (
            index
            for index, part in enumerate(relative_parts)
            if part.casefold() == week.casefold()
        ),
        None,
    )
    if week_index is None:
        raise ValueError(f"{path}: could not find {week} in its relative path")

    timeslot_index = next(
        (
            index
            for index in range(len(relative_parts) - 2, week_index, -1)
            if TIMESLOT_DIRECTORY.fullmatch(relative_parts[index])
        ),
        None,
    )
    if timeslot_index is None:
        raise ValueError(f"{path}: could not find a GMT timeslot folder after {week}")
    return input_dir.joinpath(*relative_parts[: timeslot_index + 1])


def _event_day(path: Path, input_dir: Path, week: str) -> str:
    relative_parts = path.relative_to(input_dir).parts
    week_index = next(
        index
        for index, part in enumerate(relative_parts)
        if part.casefold() == week.casefold()
    )
    for part in relative_parts[week_index + 1 : -1]:
        if part.casefold() in WEEKDAY_NAMES:
            return WEEKDAY_NAMES[part.casefold()]

    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        metadata_header = next(reader, [])
        start_time_index = next(
            (
                index
                for index, value in enumerate(metadata_header)
                if value.strip().casefold() == "start time"
            ),
            None,
        )
        metadata_values = next(reader, [])

    if start_time_index is None or start_time_index >= len(metadata_values):
        raise ValueError(f"{path}: could not find the event Start Time metadata")
    start_time = metadata_values[start_time_index].strip()
    try:
        return date.fromisoformat(start_time[:10]).strftime("%A")
    except ValueError as error:
        raise ValueError(
            f"{path}: event Start Time is not an ISO date/time: {start_time!r}"
        ) from error


def timeslot_participation(
    input_dir: Path,
    weekly_files: dict[tuple[str, str], list[Path]],
    year: str | None = None,
    week: int | None = None,
) -> list[dict[str, str | int | float]]:
    selected_files = {
        key: files
        for key, files in weekly_files.items()
        if (year is None or key[0] == year)
        and (week is None or key[1].casefold() == f"week{week}".casefold())
    }

    if not selected_files:
        if year is not None and week is not None:
            raise ValueError(f"no CSV files found for year {year}, week{week}")
        if year is not None:
            raise ValueError(f"year {year} was not found")
        if week is not None:
            raise ValueError(f"week{week} was not found")
        raise ValueError("no weekly CSV files found")

    event_files: dict[tuple[str, str, Path], list[Path]] = defaultdict(list)
    event_days: dict[tuple[str, Path], str] = {}
    for (file_year, week_name), files in selected_files.items():
        for path in files:
            timeslot_path = _timeslot_directory(path, input_dir, week_name)
            event_key = (file_year, week_name, timeslot_path)
            event_files[event_key].append(path)
            day_key = (week_name, timeslot_path)
            if day_key not in event_days:
                event_days[day_key] = _event_day(path, input_dir, week_name)

    totals: dict[tuple[str, str, str], dict[str, int]] = {}
    for (file_year, week_name, event_path), files in sorted(
        event_files.items(),
        key=lambda item: (
            item[0][0],
            WEEKDAYS.index(event_days[(item[0][1], item[0][2])]),
            int(item[0][2].name[:2]),
            int(item[0][2].name[2:]),
            str(item[0][2]),
        ),
    ):
        timeslot = event_path.name
        day = event_days[(week_name, event_path)]
        stats = WeekStats()
        for path in files:
            stats.add_csv(path)
        row = totals.setdefault(
            (file_year, day, timeslot),
            {"events": 0, "total_team_entries": 0, "csv_files": 0},
        )
        row["events"] += 1
        row["total_team_entries"] += stats.team_entries
        row["csv_files"] += stats.files_processed

    rows = []
    for (file_year, day, timeslot), totals_for_slot in sorted(
        totals.items(),
        key=lambda item: (
            item[0][0],
            WEEKDAYS.index(item[0][1]),
            int(item[0][2][:2]),
            int(item[0][2][2:]),
        ),
    ):
        rows.append(
            {
                "year": file_year,
                "day": day,
                "timeslot": timeslot,
                **totals_for_slot,
                "average_team_entries": round(
                    totals_for_slot["total_team_entries"] / totals_for_slot["events"],
                    1,
                ),
            }
        )
    return rows


def write_report(
    rows: list[dict[str, str | int | float]], output_dir: Path
) -> list[Path]:
    rows_by_year: dict[str, list[dict[str, str | int | float]]] = defaultdict(list)
    for row in rows:
        rows_by_year[str(row["year"])].append(row)

    paths = []
    for year, year_rows in sorted(rows_by_year.items()):
        year_dir = output_dir / year
        year_dir.mkdir(parents=True, exist_ok=True)
        path = year_dir / f"{year}_timeslot_participation.csv"
        with path.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(year_rows)
        paths.append(path)
    return paths


def print_summary(
    rows: list[dict[str, str | int | float]], output: TextIO = sys.stdout
) -> None:
    for row in sorted(
        rows,
        key=lambda item: (
            str(item["year"]),
            WEEKDAYS.index(str(item["day"])),
            -float(item["average_team_entries"]),
            str(item["timeslot"]),
        ),
    ):
        slot = str(row["timeslot"])
        print(
            f"{row['year']} {row['day']} {slot[:2]}:{slot[2:]} GMT: "
            f"{row['average_team_entries']} average team entries "
            f"({row['total_team_entries']} total across {row['events']} events)",
            file=output,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="root directory containing year/week/timeslot folders (default: results/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="where to write year-organized reports (default: <input-dir>/../stats)",
    )
    parser.add_argument(
        "-w",
        "--week",
        type=int,
        metavar="NUMBER",
        help="process only this week (for example: -w 2, -w2, or --week 2)",
    )
    parser.add_argument(
        "-y",
        "--year",
        metavar="YEAR",
        help="process only this year (for example: -y 2026 or --year 2026)",
    )
    args = parser.parse_args()
    if args.week is not None and args.week < 1:
        parser.error("week number must be a positive integer")

    input_dir = args.input_dir.resolve()
    output_dir = (args.output_dir or input_dir.parent / "stats").resolve()
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")
    if output_dir == input_dir:
        parser.error("output directory must not be the same as the input directory")

    try:
        weekly_files = discover_weekly_files(input_dir, output_dir)
        rows = timeslot_participation(
            input_dir, weekly_files, year=args.year, week=args.week
        )
        paths = write_report(rows, output_dir)
        print_summary(rows)
        for path in paths:
            print(f"Wrote {path}")
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

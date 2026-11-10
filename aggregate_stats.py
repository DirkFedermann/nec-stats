#!/usr/bin/env python3
"""Aggregate season-wide statistics from race-result CSV files."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import TextIO

from analyze_results import WeekStats, discover_weekly_files


def aggregate_stats(
    input_dir: Path,
    year: str | None = None,
    week: int | None = None,
) -> WeekStats:
    weekly_files = discover_weekly_files(input_dir, input_dir.parent)
    if year is not None:
        weekly_files = {
            key: files for key, files in weekly_files.items() if key[0] == year
        }
    if week is not None:
        selected_week = f"week{week}".casefold()
        weekly_files = {
            key: files
            for key, files in weekly_files.items()
            if key[1].casefold() == selected_week
        }

    paths = sorted(path for files in weekly_files.values() for path in files)
    if not paths:
        if year is not None and week is not None:
            raise ValueError(
                f"no CSV files found for year {year}, week{week} under {input_dir}"
            )
        if year is not None:
            raise ValueError(f"year {year} was not found under {input_dir}")
        if week is not None:
            raise ValueError(f"week{week} was not found under {input_dir}")
        raise ValueError(f"no weekly CSV files found under {input_dir}")

    stats = WeekStats()
    for path in paths:
        stats.add_csv(path)
    return stats


def print_summary(stats: WeekStats, output: TextIO = sys.stdout) -> None:
    print(f"Overall splits: {stats.files_processed}", file=output)
    print(f"Overall unique drivers: {len(stats.driver_ids)}", file=output)
    print(f"Overall unique teams: {len(stats.team_ids)}", file=output)
    print(f"Overall laps completed: {stats.team_laps}", file=output)
    print(f"Overall incident points: {stats.team_incidents}", file=output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="root directory containing year/week race-result folders (default: results/)",
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
        default="2026",
        help="process only this year (default: 2026)",
    )
    args = parser.parse_args()
    if args.week is not None and args.week < 1:
        parser.error("week number must be a positive integer")

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")

    try:
        print_summary(aggregate_stats(input_dir, args.year, args.week))
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

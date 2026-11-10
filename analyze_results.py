#!/usr/bin/env python3
"""Summarize weekly race-result CSV files."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


REQUIRED_COLUMNS = {"Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"}
WEEK_DIRECTORY = re.compile(r"week\d+", re.IGNORECASE)


@dataclass
class WeekStats:
    files_processed: int = 0
    driver_rows: int = 0
    driver_ids: set[int] = field(default_factory=set)
    team_ids: set[int] = field(default_factory=set)
    team_entries: int = 0
    team_incidents: int = 0
    team_laps: int = 0
    teams_by_class: Counter[str] = field(default_factory=Counter)
    incidents_by_class: Counter[str] = field(default_factory=Counter)
    laps_by_class: Counter[str] = field(default_factory=Counter)
    cars_by_class: Counter[tuple[str, str, str]] = field(default_factory=Counter)

    def add_csv(self, path: Path) -> None:
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.reader(source)
            for header in reader:
                cleaned_header = [column.strip() for column in header]
                if REQUIRED_COLUMNS.issubset(cleaned_header):
                    break
            else:
                raise ValueError(f"{path}: could not find the race-result header")

            indexes = {column: cleaned_header.index(column) for column in REQUIRED_COLUMNS}
            last_required_index = max(indexes.values())
            for row in reader:
                if not row or all(not value.strip() for value in row):
                    continue
                line_number = reader.line_num
                if len(row) <= last_required_index:
                    raise ValueError(f"{path}:{line_number}: result row is missing required columns")

                team_id = _read_integer(row[indexes["Team ID"]], "Team ID", path, line_number)
                customer_id = _read_integer(row[indexes["Cust ID"]], "Cust ID", path, line_number)
                if team_id >= 0:
                    raise ValueError(f"{path}:{line_number}: Team ID must be negative, got {team_id}")
                if customer_id == 0:
                    raise ValueError(f"{path}:{line_number}: Cust ID must be positive or negative, got 0")

                if customer_id > 0:
                    self.driver_rows += 1
                    self.driver_ids.add(customer_id)
                    continue

                car = row[indexes["Car"]].strip()
                car_class = row[indexes["Car Class"]].strip()
                if not car or not car_class:
                    raise ValueError(f"{path}:{line_number}: team row is missing Car or Car Class")

                self.team_ids.add(team_id)
                incidents_text = row[indexes["Inc"]].strip()
                incidents = (
                    0
                    if not incidents_text
                    else _read_integer(incidents_text, "Inc", path, line_number)
                )
                laps = _read_integer(row[indexes["Laps Comp"]], "Laps Comp", path, line_number)
                category = car_class
                self.team_entries += 1
                self.team_incidents += incidents
                self.team_laps += laps
                self.teams_by_class[category] += 1
                self.incidents_by_class[category] += incidents
                self.laps_by_class[category] += laps
                self.cars_by_class[(category, car_class, car)] += 1

        self.files_processed += 1


def _read_integer(value: str, column: str, path: Path, line_number: int) -> int:
    try:
        return int(value.strip())
    except ValueError as error:
        raise ValueError(
            f"{path}:{line_number}: {column} must be an integer, got {value!r}"
        ) from error


def _week_key(path: Path, input_dir: Path) -> tuple[str, str] | None:
    relative_parts = path.relative_to(input_dir).parts
    for index, part in enumerate(relative_parts):
        if WEEK_DIRECTORY.fullmatch(part):
            year = relative_parts[index - 1] if index else input_dir.name
            return year, part
    return None


def discover_weekly_files(input_dir: Path, output_dir: Path) -> dict[tuple[str, str], list[Path]]:
    weekly_files: dict[tuple[str, str], list[Path]] = {}
    output_is_inside_input = input_dir in output_dir.parents
    csv_paths = sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".csv"
    )
    for path in csv_paths:
        resolved_path = path.resolve()
        if output_is_inside_input and (
            resolved_path == output_dir or output_dir in resolved_path.parents
        ):
            continue
        week = _week_key(path, input_dir)
        if week is None:
            continue
        weekly_files.setdefault(week, []).append(path)
    return weekly_files


def _percentage(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator * 100) if denominator else 0:.1f}%"


def summary_rows(year: str, week: str, stats: WeekStats) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []

    def add(
        metric: str,
        count: int,
        percentage: str = "",
        denominator_count: int | str = "",
        denominator: str = "",
    ) -> None:
        rows.append(
            {
                "year": year,
                "week": week,
                "metric": metric,
                "count": count,
                "percentage": percentage,
                "denominator_count": denominator_count,
                "denominator": denominator,
            }
        )

    unique_driver_count = len(stats.driver_ids)
    add(
        "Drivers",
        stats.driver_rows,
        _percentage(stats.driver_rows, stats.driver_rows),
        stats.driver_rows,
        "driver result rows in this week",
    )
    add(
        "Unique drivers",
        unique_driver_count,
        _percentage(unique_driver_count, unique_driver_count),
        unique_driver_count,
        "unique Cust IDs in this week",
    )
    add(
        "Teams",
        stats.team_entries,
        _percentage(stats.team_entries, stats.team_entries),
        stats.team_entries,
        "team result rows in this week",
    )

    categories = sorted(stats.teams_by_class)
    for category in categories:
        count = stats.teams_by_class.get(category, 0)
        add(
            f"{category} teams",
            count,
            _percentage(count, stats.team_entries),
            stats.team_entries,
            "all team result rows in this week",
        )

    for category in categories:
        add(f"{category} laps completed (teams)", stats.laps_by_class.get(category, 0))

    for category in categories:
        add(f"{category} Inc total (teams)", stats.incidents_by_class.get(category, 0))

    add("Laps completed (teams)", stats.team_laps)
    add("Inc total (teams)", stats.team_incidents)
    add("CSV files processed", stats.files_processed)
    return rows


def car_rows(year: str, week: str, stats: WeekStats) -> list[dict[str, str | int]]:
    teams_in_car_class: Counter[str] = Counter()
    for (_category, car_class, _car), count in stats.cars_by_class.items():
        teams_in_car_class[car_class] += count

    models_in_class: dict[str, set[str]] = {}
    for (_category, car_class, car) in stats.cars_by_class:
        models_in_class.setdefault(car_class, set()).add(car)

    rows = []
    for (category, car_class, car), count in sorted(stats.cars_by_class.items()):
        rows.append(
            {
                "year": year,
                "week": week,
                "class": category,
                "car_class": car_class,
                "car": car,
                "team_entries": count,
                "percentage_of_class": _percentage(count, teams_in_car_class[car_class]),
                "percentage_of_grid": _percentage(count, stats.team_entries),
            }
        )
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str | int]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_reports(
    year: str,
    week: str,
    stats: WeekStats,
    output_dir: Path,
) -> tuple[Path, Path]:
    stem = f"{year}_{week}"
    year_dir = output_dir / year
    summary_path = year_dir / f"{stem}_summary.csv"
    cars_path = year_dir / f"{stem}_cars.csv"
    year_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        summary_path,
        [
            "year",
            "week",
            "metric",
            "count",
            "percentage",
            "denominator_count",
            "denominator",
        ],
        summary_rows(year, week, stats),
    )
    _write_csv(
        cars_path,
        [
            "year",
            "week",
            "class",
            "car_class",
            "car",
            "team_entries",
            "percentage_of_class",
            "percentage_of_grid",
        ],
        car_rows(year, week, stats),
    )
    return summary_path, cars_path


def print_summary(year: str, week: str, stats: WeekStats, output: TextIO = sys.stdout) -> None:
    print(f"\n{year} {week}", file=output)
    cars_by_category: dict[str, list[dict[str, str | int]]] = {}
    for row in car_rows(year, week, stats):
        cars_by_category.setdefault(str(row["class"]), []).append(row)

    for row in summary_rows(year, week, stats):
        if (
            row["metric"] in {"Inc total (teams)", "Laps completed (teams)"}
            or row["metric"].endswith(" laps completed (teams)")
            or row["metric"].endswith(" Inc total (teams)")
        ):
            print(f"  {row['metric']}: {row['count']}", file=output)
        elif row["metric"] == "CSV files processed":
            print(f"  {row['metric']}: {row['count']}", file=output)
        elif row["metric"].endswith(" teams"):
            category = str(row["metric"])[:-len(" teams")]
            print(
                f"  {row['metric']}: {row['count']} ({row['percentage']})",
                file=output,
            )
            for car in cars_by_category.get(category, []):
                print(
                    f"    {car['car']}: {car['team_entries']} "
                    f"(in class: {car['percentage_of_class']}) "
                    f"(total: {car['percentage_of_grid']})",
                    file=output,
                )
        else:
            print(
                f"  {row['metric']}: {row['count']} ({row['percentage']})",
                file=output,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="root directory containing year/week/day/timeslot folders (default: results/)",
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
        if args.year is not None:
            weekly_files = {
                key: files for key, files in weekly_files.items() if key[0] == args.year
            }
        if args.week is not None:
            selected_week = f"week{args.week}".casefold()
            weekly_files = {
                key: files
                for key, files in weekly_files.items()
                if key[1].casefold() == selected_week
            }
        if not weekly_files:
            if args.year is not None and args.week is not None:
                raise ValueError(
                    f"no CSV files found for year {args.year}, week{args.week} under {input_dir}"
                )
            if args.year is not None:
                raise ValueError(f"year {args.year} was not found under {input_dir}")
            if args.week is not None:
                raise ValueError(f"week{args.week} was not found under {input_dir}")
            raise ValueError(f"no weekly CSV files found under {input_dir}")

        for (year, week), files in sorted(weekly_files.items()):
            stats = WeekStats()
            for path in files:
                stats.add_csv(path)
            summary_path, cars_path = write_reports(year, week, stats, output_dir)
            print_summary(year, week, stats)
            print(f"  Wrote {summary_path}")
            print(f"  Wrote {cars_path}")
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

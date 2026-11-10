#!/usr/bin/env python3
"""Report a driver's race results and season standings across all years."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import TextIO


RESULT_COLUMNS = {
    "Fin Pos",
    "Car",
    "Car Class ID",
    "Car Class",
    "Cust ID",
    "Name",
    "Start Pos",
    "Car #",
    "Out",
    "Laps Comp",
    "Inc",
    "Pts",
}
STANDINGS_COLUMNS = {"position", "name", "custid"}
WEEK_DIRECTORY = re.compile(r"week(\d+)", re.IGNORECASE)
CLASS_ID = re.compile(r"ccid_(\d+)", re.IGNORECASE)
EVENT_ID = re.compile(r"eventresult_(\d+)", re.IGNORECASE)
REPORT_COLUMNS = [
    "driver",
    "year",
    "race_week",
    "date",
    "track",
    "series",
    "car_class",
    "car_class_id",
    "car",
    "car_number",
    "start_position",
    "finish_position",
    "status",
    "laps_completed",
    "incident_points",
    "race_points",
    "season_rank",
    "season_division",
    "season_points",
    "season_starts",
    "season_wins",
    "season_average_finish",
    "season_average_start",
    "season_incidents",
    "season_laps",
    "event_id",
    "event_file",
]


def _normalized_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def _read_integer(value: str, column: str, path: Path, line_number: int) -> int:
    try:
        return int(value.strip())
    except ValueError as error:
        raise ValueError(
            f"{path}:{line_number}: {column} must be an integer, got {value!r}"
        ) from error


def _year_from_path(path: Path, input_dir: Path) -> str:
    relative_parts = path.relative_to(input_dir).parts
    for index, part in enumerate(relative_parts):
        if WEEK_DIRECTORY.fullmatch(part):
            year = relative_parts[index - 1] if index else input_dir.name
            if year.isdigit():
                return year
    if input_dir.name.isdigit():
        return input_dir.name
    raise ValueError(f"{path}: could not determine the season year")


def _week_from_path(path: Path, input_dir: Path) -> str:
    for part in path.relative_to(input_dir).parts:
        match = WEEK_DIRECTORY.fullmatch(part)
        if match:
            return f"week{int(match.group(1))}"
    return ""


def _week_number(week: str) -> int:
    match = WEEK_DIRECTORY.fullmatch(week)
    return int(match.group(1)) if match else 0


def _read_standings(input_dir: Path) -> dict[tuple[str, str, int], dict[str, str]]:
    standings: dict[tuple[str, str, int], dict[str, str]] = {}
    for path in sorted(input_dir.rglob("season-driver*.csv")):
        class_match = CLASS_ID.search(path.name)
        if class_match is None:
            raise ValueError(f"{path}: could not determine the class ID from its filename")

        relative_parts = path.relative_to(input_dir).parts
        try:
            standings_index = relative_parts.index("standings")
        except ValueError:
            raise ValueError(f"{path}: driver standings file is outside a standings directory")
        year = relative_parts[standings_index - 1] if standings_index else input_dir.name
        if not year.isdigit():
            raise ValueError(f"{path}: could not determine the standings year")

        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames is None:
                raise ValueError(f"{path}: standings file is empty")
            indexes = {
                column.casefold(): column.strip()
                for column in reader.fieldnames
                if column is not None
            }
            if not STANDINGS_COLUMNS.issubset(indexes):
                raise ValueError(f"{path}: missing required driver standings columns")

            for line_number, row in enumerate(reader, start=2):
                if not row.get(indexes["custid"], "").strip():
                    continue
                customer_id = _read_integer(
                    row[indexes["custid"]], "custid", path, line_number
                )
                key = (year, class_match.group(1), customer_id)
                standings[key] = {
                    "season_rank": row.get(indexes["position"], "").strip(),
                    "season_division": row.get(indexes.get("division", ""), "").strip(),
                    "season_points": row.get(indexes.get("points", ""), "").strip(),
                    "season_starts": row.get(indexes.get("starts", ""), "").strip(),
                    "season_wins": row.get(indexes.get("wins", ""), "").strip(),
                    "season_average_finish": row.get(indexes.get("avgfinish", ""), "").strip(),
                    "season_average_start": row.get(indexes.get("avgstart", ""), "").strip(),
                    "season_incidents": row.get(indexes.get("incidents", ""), "").strip(),
                    "season_laps": row.get(indexes.get("laps", ""), "").strip(),
                }
    return standings


def _read_event(
    path: Path,
    input_dir: Path,
    driver_name: str,
    standings: dict[tuple[str, str, int], dict[str, str]],
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.reader(source))

    metadata: dict[str, str] = {}
    header_index: int | None = None
    header: list[str] = []
    for index, row in enumerate(rows):
        cleaned_row = [column.strip() for column in row]
        if RESULT_COLUMNS.issubset(cleaned_row):
            header_index = index
            header = cleaned_row
            break
        if "Season Year" in cleaned_row and index + 1 < len(rows):
            metadata = dict(zip(cleaned_row, (value.strip() for value in rows[index + 1])))

    if header_index is None:
        raise ValueError(f"{path}: could not find the race-result header")
    indexes = {column: header.index(column) for column in RESULT_COLUMNS}
    last_required_index = max(indexes.values())

    year = metadata.get("Season Year", "").strip() or _year_from_path(path, input_dir)
    if not year.isdigit():
        raise ValueError(f"{path}: Season Year must be a year, got {year!r}")
    race_week = metadata.get("Race Week", "").strip()
    if race_week.isdigit():
        race_week = f"week{int(race_week)}"
    else:
        race_week = _week_from_path(path, input_dir) or race_week

    event_id_match = EVENT_ID.search(path.stem)
    event_id = event_id_match.group(1) if event_id_match else path.stem
    results: list[dict[str, str]] = []
    for line_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) <= last_required_index:
            raise ValueError(f"{path}:{line_number}: result row is missing required columns")

        customer_id = _read_integer(row[indexes["Cust ID"]], "Cust ID", path, line_number)
        if customer_id <= 0 or _normalized_name(row[indexes["Name"]]) != _normalized_name(
            driver_name
        ):
            continue

        key = (year, row[indexes["Car Class ID"]].strip(), customer_id)
        result = {
            "driver": row[indexes["Name"]].strip(),
            "year": year,
            "race_week": race_week,
            "date": metadata.get("Start Time", "").strip(),
            "track": metadata.get("Track", "").strip(),
            "series": metadata.get("Series", "").strip(),
            "car_class": row[indexes["Car Class"]].strip(),
            "car_class_id": key[1],
            "car": row[indexes["Car"]].strip(),
            "car_number": row[indexes["Car #"]].strip(),
            "start_position": row[indexes["Start Pos"]].strip(),
            "finish_position": row[indexes["Fin Pos"]].strip(),
            "status": row[indexes["Out"]].strip(),
            "laps_completed": row[indexes["Laps Comp"]].strip(),
            "incident_points": row[indexes["Inc"]].strip(),
            "race_points": row[indexes["Pts"]].strip(),
            "event_id": event_id,
            "event_file": str(path),
        }
        result.update(standings.get(key, {}))
        results.append(result)
    return results


def find_driver_results(input_dir: Path, driver_name: str) -> list[dict[str, str]]:
    standings = _read_standings(input_dir)
    event_files = sorted(
        path
        for path in input_dir.rglob("eventresult*.csv")
        if path.is_file()
    )
    if not event_files:
        raise ValueError(f"no eventresult CSV files found under {input_dir}")

    results = [
        result
        for path in event_files
        for result in _read_event(path, input_dir, driver_name, standings)
    ]
    results.sort(
        key=lambda result: (
            result["year"],
            _week_number(result["race_week"]),
            result["date"],
            result["event_id"],
        )
    )
    if not results:
        raise ValueError(f"driver {driver_name!r} was not found in event results under {input_dir}")
    return results


def write_report(path: Path, results: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)


def print_report(results: list[dict[str, str]], output: TextIO = sys.stdout) -> None:
    print(f"Found {len(results)} race entries for {results[0]['driver']}", file=output)
    for result in results:
        rank = result.get("season_rank") or "n/a"
        week = result["race_week"] or "week?"
        print(
            f"{result['year']} {week} | {result['car_class']} | {result['car']} "
            f"#{result['car_number']} | start {result['start_position']} -> "
            f"finish {result['finish_position']} | {result['laps_completed']} laps | "
            f"{result['incident_points']} incidents | season rank {rank}",
            file=output,
        )
        print(
            f"  {result['date']} {result['track']} "
            f"(status: {result['status']}; season points: "
            f"{result.get('season_points', '')})",
            file=output,
        )


def _default_report_path(input_dir: Path, driver_name: str, year: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", driver_name.casefold()).strip("_") or "driver"
    return input_dir.parent / "stats" / year / f"driver_{slug}_results.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", required=True, metavar="NAME", help="driver name to search for")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
        help="root directory containing year/eventresult and standings files (default: results/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="CSV report path (default: <input-dir>/../stats/<year>/driver_<name>_results.csv)",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")

    try:
        results = find_driver_results(input_dir, args.driver)
        print_report(results)
        if args.output is not None:
            output_path = args.output.resolve()
            write_report(output_path, results)
            print(f"Wrote {output_path}")
        else:
            results_by_year: dict[str, list[dict[str, str]]] = {}
            for result in results:
                results_by_year.setdefault(result["year"], []).append(result)
            for year, year_results in sorted(results_by_year.items()):
                output_path = _default_report_path(input_dir, args.driver, year)
                write_report(output_path, year_results)
                print(f"Wrote {output_path}")
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

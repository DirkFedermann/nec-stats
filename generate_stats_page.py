#!/usr/bin/env python3
"""Generate a season statistics HTML page from race-result CSV files."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)

from analyze_results import WeekStats, car_rows, discover_weekly_files
from analyze_timeslots import timeslot_participation


MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _read_event_date(path: Path) -> date:
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
        return date.fromisoformat(start_time[:10])
    except ValueError as error:
        raise ValueError(
            f"{path}: event Start Time is not an ISO date/time: {start_time!r}"
        ) from error


def _format_event_dates(event_dates: set[date]) -> str:
    dates = sorted(event_dates)
    if not dates:
        raise ValueError("each race week must have at least one event date")

    if len(dates) == 1:
        day = dates[0]
        return f"{day.day}. {MONTH_NAMES[day.month - 1]}"

    if len(dates) == 2:
        first, last = dates
        if first.month == last.month:
            return f"{first.day}.-{last.day}. {MONTH_NAMES[last.month - 1]}"
        return (
            f"{first.day}. {MONTH_NAMES[first.month - 1]}-"
            f"{last.day}. {MONTH_NAMES[last.month - 1]}"
        )

    return ", ".join(
        f"{day.day}. {MONTH_NAMES[day.month - 1]}" for day in dates
    )


def _display_class_name(class_name: str) -> str:
    display_name = re.sub(r"^NEC\s+", "", class_name, flags=re.IGNORECASE)
    display_name = re.sub(r"\s+\d{4}$", "", display_name)
    if display_name.casefold() == "m2 cup":
        return "M2"
    return display_name


def _week_number(week_name: str) -> int:
    week_match = re.fullmatch(r"week(\d+)", week_name, flags=re.IGNORECASE)
    if week_match is None:
        raise ValueError(f"unsupported race week directory: {week_name}")
    return int(week_match.group(1))


def _build_week_data(
    year: str, week_name: str, stats: WeekStats, files: list[Path]
) -> dict[str, Any]:
    week_number = _week_number(week_name)
    event_dates = {_read_event_date(path) for path in files}
    cars_by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in car_rows(year, week_name, stats):
        cars_by_class[str(row["class"])].append(
            {
                "name": row["car"],
                "count": row["team_entries"],
                "percentage": row["percentage_of_class"],
            }
        )

    class_names = sorted(
        stats.teams_by_class,
        key=lambda name: _display_class_name(name).casefold(),
    )
    classes = []
    for class_name in class_names:
        team_count = stats.teams_by_class[class_name]
        lap_count = stats.laps_by_class[class_name]
        classes.append(
            {
                "name": class_name,
                "label": _display_class_name(class_name),
                "count": team_count,
                "percentage": team_count / stats.team_entries * 100
                if stats.team_entries
                else 0,
                "incidents": stats.incidents_by_class[class_name],
                "incidents_per_lap": stats.incidents_by_class[class_name] / lap_count
                if lap_count
                else 0,
                "cars": cars_by_class[class_name],
            }
        )

    return {
        "number": week_number,
        "label": f"Week {week_number}",
        "date_label": _format_event_dates(event_dates),
        "drivers": stats.driver_rows,
        "unique_drivers": len(stats.driver_ids),
        "teams": stats.team_entries,
        "participation": stats.team_entries,
        "splits": stats.files_processed,
        "laps": stats.team_laps,
        "incidents": stats.team_incidents,
        "incidents_per_lap": stats.team_incidents / stats.team_laps
        if stats.team_laps
        else 0,
        "classes": classes,
        "class_counts": dict(stats.teams_by_class),
        "class_percentages": {
            class_name: (
                round(stats.teams_by_class[class_name] / stats.team_entries * 100, 1)
                if stats.team_entries
                else 0
            )
            for class_name in class_names
        },
    }


def _build_context(
    year: str,
    weekly_files: dict[tuple[str, str], list[Path]],
    input_dir: Path,
) -> dict[str, Any]:
    selected_weeks = sorted(
        (
            (week_name, files)
            for (file_year, week_name), files in weekly_files.items()
            if file_year == year
        ),
        key=lambda item: _week_number(item[0]),
    )
    if not selected_weeks:
        raise ValueError(f"no weekly CSV files found for year {year}")

    weeks = []
    seen_numbers: set[int] = set()
    for week_name, files in selected_weeks:
        stats = WeekStats()
        for path in files:
            stats.add_csv(path)
        week = _build_week_data(year, week_name, stats, files)
        week_timeslot_rows = timeslot_participation(
            input_dir, weekly_files, year=year, week=week["number"]
        )
        week["timeslot_rows"] = week_timeslot_rows
        week["timeslot_labels"] = [
            f"{row['day']} {str(row['timeslot'])[:2]}:{str(row['timeslot'])[2:]} GMT"
            for row in week_timeslot_rows
        ]
        week["timeslot_participation_series"] = [
            {
                "name": "Average team entries",
                "data": [row["average_team_entries"] for row in week_timeslot_rows],
            }
        ]
        if week["number"] in seen_numbers:
            raise ValueError(f"duplicate race week number: {week['number']}")
        seen_numbers.add(week["number"])
        weeks.append(week)

    class_names = sorted(
        {item["name"] for week in weeks for item in week["classes"]},
        key=lambda name: _display_class_name(name).casefold(),
    )
    class_definitions = [
        {"name": name, "label": _display_class_name(name)} for name in class_names
    ]

    average_counts = {
        class_name: sum(week["class_counts"].get(class_name, 0) for week in weeks)
        / len(weeks)
        for class_name in class_names
    }
    average_percentages = {
        class_name: sum(week["class_percentages"].get(class_name, 0) for week in weeks)
        / len(weeks)
        for class_name in class_names
    }
    average_teams = sum(week["teams"] for week in weeks) / len(weeks)
    timeslot_rows = timeslot_participation(input_dir, weekly_files, year=year)
    timeslot_labels = [
        f"{row['day']} {str(row['timeslot'])[:2]}:{str(row['timeslot'])[2:]} GMT"
        for row in timeslot_rows
    ]

    return {
        "year": year,
        "weeks": weeks,
        "classes": class_definitions,
        "average_counts": average_counts,
        "average_percentages": average_percentages,
        "average_teams": average_teams,
        "week_labels": [week["label"] for week in weeks],
        "class_size_series": [
            {
                "name": class_definition["label"],
                "data": [
                    week["class_counts"].get(class_definition["name"], 0)
                    for week in weeks
                ],
            }
            for class_definition in class_definitions
        ],
        "class_percentage_series": [
            {
                "name": class_definition["label"],
                "data": [
                    week["class_percentages"].get(class_definition["name"], 0)
                    for week in weeks
                ],
            }
            for class_definition in class_definitions
        ],
        "timeslot_rows": sorted(
            timeslot_rows,
            key=lambda row: (
                -float(row["average_team_entries"]),
                str(row["timeslot"]),
            ),
        ),
        "timeslot_labels": timeslot_labels,
        "timeslot_participation_series": [
            {
                "name": "Average team entries",
                "data": [row["average_team_entries"] for row in timeslot_rows],
            }
        ],
    }


def generate_page(
    year: str,
    input_dir: Path,
    template_path: Path,
    output_path: Path,
) -> None:
    weekly_files = discover_weekly_files(input_dir, output_path)
    context = _build_context(year, weekly_files, input_dir)

    environment = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(("html", "xml")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(template_path.name)
    rendered_page = template.render(**context)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered_page, encoding="utf-8")


def main() -> int:
    repository_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-y",
        "--year",
        metavar="YEAR",
        default="2026",
        help="generate this year (default: 2026)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=repository_dir / "results",
        help="root directory containing year/week/day/timeslot folders (default: results/)",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=repository_dir / "web" / "stats_template.html",
        help="Jinja2 HTML template to render",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output HTML path (default: web/<year>.html)",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    template_path = args.template.resolve()
    output_path = (
        args.output.resolve()
        if args.output is not None
        else repository_dir / "web" / f"{args.year}.html"
    )
    if not input_dir.is_dir():
        parser.error(f"input directory does not exist: {input_dir}")
    if not template_path.is_file():
        parser.error(f"template file does not exist: {template_path}")

    try:
        generate_page(args.year, input_dir, template_path, output_path)
    except (OSError, ValueError, csv.Error, TemplateError) as error:
        parser.error(str(error))

    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import csv
import tempfile
import unittest
from pathlib import Path

from analyze_results import discover_weekly_files
from analyze_timeslots import timeslot_participation, write_report


class TimeslotParticipationTests(unittest.TestCase):
    def test_aggregates_average_participation_by_gmt_timeslot(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            week_one = root / "2026" / "week1"
            saturday = week_one / "saturday" / "0700"
            sunday = week_one / "sunday" / "0000"
            late_slot = week_one / "saturday" / "1700"
            sunday_early_slot = week_one / "sunday" / "0700"
            next_week_slot = root / "2026" / "week2" / "saturday" / "0700"
            for path in (saturday, sunday, late_slot, sunday_early_slot, next_week_slot):
                path.mkdir(parents=True)

            self._write_results(
                saturday / "split1.csv",
                header,
                [
                    ["BMW", "GT3", "-1", "-1", "2", "20"],
                    ["BMW", "GT3", "-1", "101", "2", "20"],
                ],
            )
            self._write_results(
                saturday / "split2.csv",
                header,
                [["Porsche", "GT3", "-2", "-2", "1", "18"]],
            )
            self._write_results(
                sunday / "results.csv",
                header,
                [["BMW", "GT3", "-3", "-3", "0", "16"]],
            )
            self._write_results(
                late_slot / "results.csv",
                header,
                [["Porsche", "GT3", "-4", "-4", "0", "17"]],
            )
            self._write_results(
                sunday_early_slot / "results.csv",
                header,
                [["Porsche", "GT3", "-6", "-6", "0", "17"]],
            )
            self._write_results(
                next_week_slot / "results.csv",
                header,
                [["BMW", "GT3", "-5", "-5", "0", "19"]],
            )

            weekly_files = discover_weekly_files(root, root.parent)
            rows = timeslot_participation(root, weekly_files, year="2026")
            output_paths = write_report(rows, Path(directory) / "stats")
            with output_paths[0].open(newline="", encoding="utf-8") as source:
                report_rows = list(csv.DictReader(source))

        self.assertEqual(
            [
                (
                    row["day"],
                    row["timeslot"],
                    row["events"],
                    row["total_team_entries"],
                    row["average_team_entries"],
                )
                for row in rows
            ],
            [
                ("Saturday", "0700", 2, 3, 1.5),
                ("Saturday", "1700", 1, 1, 1.0),
                ("Sunday", "0000", 1, 1, 1.0),
                ("Sunday", "0700", 1, 1, 1.0),
            ],
        )
        self.assertEqual(output_paths[0].name, "2026_timeslot_participation.csv")
        saturday_0700 = next(
            row
            for row in report_rows
            if row["day"] == "Saturday" and row["timeslot"] == "0700"
        )
        self.assertEqual(saturday_0700["csv_files"], "3")

    def test_supports_timeslot_folder_directly_under_week(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            timeslot = root / "2016" / "week1" / "1600"
            timeslot.mkdir(parents=True)
            self._write_results(
                timeslot / "results.csv",
                ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"],
                [["Kia", "Kia", "-1", "-1", "1", "10"]],
            )

            weekly_files = discover_weekly_files(root, root.parent)
            rows = timeslot_participation(root, weekly_files)

        self.assertEqual(rows[0]["day"], "Saturday")
        self.assertEqual(rows[0]["timeslot"], "1600")
        self.assertEqual(rows[0]["events"], 1)
        self.assertEqual(rows[0]["average_team_entries"], 1.0)

    def test_ignores_output_directory_when_it_is_inside_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            timeslot = root / "2026" / "week1" / "sunday" / "0000"
            timeslot.mkdir(parents=True)
            self._write_results(
                timeslot / "results.csv",
                ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"],
                [["Kia", "Kia", "-1", "-1", "1", "10"]],
            )
            output_dir = root / "generated"
            weekly_files = discover_weekly_files(root, output_dir)
            write_report(
                timeslot_participation(root, weekly_files), output_dir
            )
            rows = timeslot_participation(
                root, discover_weekly_files(root, output_dir)
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_team_entries"], 1)

    @staticmethod
    def _write_results(
        path: Path, header: list[str], rows: list[list[str]]
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.writer(destination)
            writer.writerow(["Start Time", "Track"])
            writer.writerow(["2026-03-21T07:00:00Z", "Test Track"])
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

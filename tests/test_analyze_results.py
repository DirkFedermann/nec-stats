import csv
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from analyze_results import (
    WeekStats,
    car_rows,
    discover_weekly_files,
    print_summary,
    summary_rows,
)


class AnalyzeResultsTests(unittest.TestCase):
    def test_add_csv_handles_preamble_and_counts_only_team_incidents(self) -> None:
        header = [
            "Fin Pos", "Car ID", "Car", "Car Class ID", "Car Class", "Team ID",
            "Cust ID", "Name", "Inc", "Laps Comp",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            with path.open("w", newline="", encoding="utf-8") as destination:
                writer = csv.writer(destination)
                writer.writerow(["Start Time", "Track"])
                writer.writerow(["2026-01-01", "Example Track"])
                writer.writerow([])
                writer.writerow(header)
                writer.writerow(
                    ["1", "1", "Porsche 911 GT3 R (992)", "1", "NEC GT3 2026", "-8", "-8", "Team", "3", "31"]
                )
                writer.writerow(
                    ["1", "1", "Porsche 911 GT3 R (992)", "1", "NEC GT3 2026", "-8", "101", "Driver A", "99", "99"]
                )
                writer.writerow(
                    ["1", "1", "BMW M4 GT3 EVO", "1", "NEC GT3 2026", "-9", "-9", "Team B", "", "20"]
                )
                writer.writerow(
                    ["1", "1", "BMW M4 GT3 EVO", "1", "NEC GT3 2026", "-9", "101", "Driver A", "99", "99"]
                )

            stats = WeekStats()
            stats.add_csv(path)

        self.assertEqual(stats.files_processed, 1)
        self.assertEqual(stats.driver_rows, 2)
        self.assertEqual(stats.driver_ids, {101})
        self.assertEqual(stats.team_entries, 2)
        self.assertEqual(stats.team_incidents, 3)
        self.assertEqual(stats.team_laps, 51)
        self.assertEqual(stats.teams_by_class["NEC GT3 2026"], 2)
        self.assertEqual(stats.incidents_by_class["NEC GT3 2026"], 3)
        self.assertEqual(stats.laps_by_class["NEC GT3 2026"], 51)
        self.assertEqual(
            stats.cars_by_class[
                ("NEC GT3 2026", "NEC GT3 2026", "BMW M4 GT3 EVO")
            ],
            1,
        )

        summary = {row["metric"]: row for row in summary_rows("2026", "week1", stats)}
        self.assertEqual(summary["NEC GT3 2026 teams"]["percentage"], "100.0%")
        self.assertEqual(summary["NEC GT3 2026 Inc total (teams)"]["count"], 3)
        self.assertEqual(summary["NEC GT3 2026 laps completed (teams)"]["count"], 51)
        self.assertEqual(summary["Laps completed (teams)"]["count"], 51)

        cars = car_rows("2026", "week1", stats)
        self.assertEqual(len(cars), 2)
        self.assertTrue(all(row["percentage_of_class"] == "50.0%" for row in cars))
        self.assertTrue(all(row["percentage_of_grid"] == "50.0%" for row in cars))

    def test_reports_arbitrary_classes_and_car_names_without_fixed_buckets(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old_results.csv"
            with path.open("w", newline="", encoding="utf-8") as destination:
                writer = csv.writer(destination)
                writer.writerow(header)
                writer.writerow(
                    ["Kia Optima", "Kia Optima", "-1", "-1", "2", "18"]
                )
                writer.writerow(
                    ["Global Mazda MX-5 Cup", "Mazda MX-5 Cup 2016", "-2", "-2", "3", "21"]
                )

            stats = WeekStats()
            stats.add_csv(path)
            metrics = {row["metric"]: row for row in summary_rows("2016", "week1", stats)}
            cars = car_rows("2016", "week1", stats)

        self.assertEqual(metrics["Kia Optima teams"]["count"], 1)
        self.assertEqual(metrics["Mazda MX-5 Cup 2016 teams"]["count"], 1)
        self.assertNotIn("GT3 teams", metrics)
        self.assertEqual(
            {(row["car_class"], row["car"]) for row in cars},
            {
                ("Kia Optima", "Kia Optima"),
                ("Mazda MX-5 Cup 2016", "Global Mazda MX-5 Cup"),
            },
        )

    def test_terminal_summary_includes_indented_car_breakdown(self) -> None:
        stats = WeekStats(
            team_entries=10,
            team_laps=400,
            team_incidents=16,
            teams_by_class={"GT3": 10},
            incidents_by_class={"GT3": 16},
            laps_by_class={"GT3": 400},
            cars_by_class={
                ("GT3", "NEC GT3 2026", "Aston Martin Vantage GT3 EVO"): 3,
                ("GT3", "NEC GT3 2026", "BMW M4 GT3 EVO"): 7,
            },
        )
        output = io.StringIO()

        print_summary("2026", "week1", stats, output)

        lines = output.getvalue().splitlines()
        self.assertIn("  GT3 teams: 10 (100.0%)", lines)
        self.assertIn("  GT3 Inc total (teams): 16", lines)
        self.assertIn("  GT3 laps completed (teams): 400", lines)
        self.assertIn("  Laps completed (teams): 400", lines)
        self.assertIn(
            "    Aston Martin Vantage GT3 EVO: 3 (in class: 30.0%) (total: 30.0%)",
            lines,
        )
        self.assertIn(
            "    BMW M4 GT3 EVO: 7 (in class: 70.0%) (total: 70.0%)",
            lines,
        )

    def test_discovery_does_not_exclude_input_when_output_is_its_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "2026"
            race_dir = input_dir / "week1" / "sunday" / "0000"
            race_dir.mkdir(parents=True)
            (race_dir / "results.csv").touch()

            weekly_files = discover_weekly_files(input_dir, root)

        self.assertEqual(len(weekly_files[("2026", "week1")]), 1)

    def test_week_argument_processes_only_selected_week_using_compact_form(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            week1 = root / "2026" / "week1" / "sunday" / "0000"
            week2 = root / "2026" / "week2" / "sunday" / "0000"
            week1.mkdir(parents=True)
            week2.mkdir(parents=True)
            (week1 / "invalid.csv").write_text("not a result file\n", encoding="utf-8")
            with (week2 / "results.csv").open("w", newline="", encoding="utf-8") as destination:
                writer = csv.writer(destination)
                writer.writerow(header)
                writer.writerow(["BMW M4 GT3 EVO", "NEC GT3 2026", "-8", "-8", "2", "25"])

            output_dir = root / "stats"
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "analyze_results.py"),
                    "--input-dir",
                    str(root / "2026"),
                    "--output-dir",
                    str(output_dir),
                    "-w2",
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2026 week2", result.stdout)
            self.assertNotIn("2026 week1", result.stdout)
            self.assertTrue((output_dir / "2026" / "2026_week2_summary.csv").is_file())
            self.assertFalse((output_dir / "2026" / "2026_week1_summary.csv").exists())

    def test_year_argument_ignores_standings_and_processes_only_selected_year(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for year in ("2025", "2026"):
                week_dir = root / year / "week1" / "sunday" / "0000"
                week_dir.mkdir(parents=True)
                with (week_dir / "results.csv").open("w", newline="", encoding="utf-8") as destination:
                    writer = csv.writer(destination)
                    writer.writerow(header)
                    writer.writerow(["BMW M4 GT3 EVO", "NEC GT3 2026", "-8", "-8", "2", "25"])

            standings_dir = root / "2026" / "standings" / "gt3"
            standings_dir.mkdir(parents=True)
            (standings_dir / "season-driver.csv").write_text(
                "not a race result file\n", encoding="utf-8"
            )

            output_dir = root / "stats"
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "analyze_results.py"),
                    "--input-dir",
                    str(root),
                    "--output-dir",
                    str(output_dir),
                    "-y",
                    "2026",
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2026 week1", result.stdout)
            self.assertNotIn("2025 week1", result.stdout)
            self.assertTrue((output_dir / "2026" / "2026_week1_summary.csv").is_file())
            self.assertFalse((output_dir / "2025" / "2025_week1_summary.csv").exists())

    def test_default_output_is_grouped_under_stats_by_year(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "results"
            for year in ("2025", "2026"):
                week_dir = input_dir / year / "week1" / "sunday" / "0000"
                week_dir.mkdir(parents=True)
                with (week_dir / "results.csv").open("w", newline="", encoding="utf-8") as destination:
                    writer = csv.writer(destination)
                    writer.writerow(header)
                    writer.writerow(["BMW M4 GT3 EVO", "NEC GT3 2026", "-8", "-8", "2", "25"])

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "analyze_results.py"),
                    "--input-dir",
                    str(input_dir),
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for year in ("2025", "2026"):
                self.assertTrue(
                    (root / "stats" / year / f"{year}_week1_summary.csv").is_file()
                )
                self.assertTrue(
                    (root / "stats" / year / f"{year}_week1_cars.csv").is_file()
                )


if __name__ == "__main__":
    unittest.main()

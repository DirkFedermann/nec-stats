import csv
import io
import tempfile
import unittest
from pathlib import Path

from aggregate_stats import aggregate_stats, print_summary


class AggregateSeasonStatsTests(unittest.TestCase):
    def test_aggregates_unique_ids_and_team_row_totals_across_weeks(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "2026"
            week1 = root / "week1" / "saturday" / "0700"
            week2 = root / "week2" / "sunday" / "0000"
            week1.mkdir(parents=True)
            week2.mkdir(parents=True)
            self._write_results(
                week1 / "results.csv",
                header,
                [
                    ["Porsche", "NEC GT3 2026", "-10", "-10", "4", "30"],
                    ["Porsche", "NEC GT3 2026", "-10", "101", "4", "30"],
                    ["BMW", "NEC GT3 2026", "-20", "-20", "", "20"],
                    ["BMW", "NEC GT3 2026", "-20", "202", "0", "20"],
                ],
            )
            self._write_results(
                week2 / "results.csv",
                header,
                [
                    ["Porsche", "NEC GT3 2026", "-10", "-10", "2", "25"],
                    ["Porsche", "NEC GT3 2026", "-10", "101", "2", "25"],
                    ["BMW", "NEC GT3 2026", "-30", "-30", "1", "15"],
                    ["BMW", "NEC GT3 2026", "-30", "101", "1", "15"],
                ],
            )
            standings = root / "standings" / "gt3"
            standings.mkdir(parents=True)
            (standings / "season-driver.csv").write_text(
                "Cust ID\n999\n", encoding="utf-8"
            )

            stats = aggregate_stats(root)

        self.assertEqual(stats.driver_ids, {101, 202})
        self.assertEqual(stats.team_ids, {-10, -20, -30})
        self.assertEqual(stats.team_laps, 90)
        self.assertEqual(stats.team_incidents, 7)
        self.assertEqual(stats.files_processed, 2)

    def test_summary_labels_requested_totals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "2026" / "week1" / "sunday" / "0000"
            root.mkdir(parents=True)
            self._write_results(
                root / "results.csv",
                ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"],
                [["BMW", "NEC GT3 2026", "-10", "-10", "3", "24"]],
            )

            output = io.StringIO()
            print_summary(aggregate_stats(root.parents[2]), output)

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Overall splits: 1",
                "Overall unique drivers: 0",
                "Overall unique teams: 1",
                "Overall laps completed: 24",
                "Overall incident points: 3",
            ],
        )

    def test_year_and_week_filters_limit_splits_and_totals(self) -> None:
        header = ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for year, week, team_id, laps in (
                ("2025", "week1", "-10", "20"),
                ("2026", "week1", "-20", "30"),
                ("2026", "week2", "-30", "40"),
            ):
                event_dir = root / year / week / "sunday" / "0000"
                event_dir.mkdir(parents=True)
                self._write_results(
                    event_dir / "eventresult.csv",
                    header,
                    [["BMW", "NEC GT3 2026", team_id, team_id, "2", laps]],
                )

            stats = aggregate_stats(root, year="2026", week=2)

        self.assertEqual(stats.files_processed, 1)
        self.assertEqual(stats.team_ids, {-30})
        self.assertEqual(stats.team_laps, 40)
        self.assertEqual(stats.team_incidents, 2)

    @staticmethod
    def _write_results(path: Path, header: list[str], rows: list[list[str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.writer(destination)
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

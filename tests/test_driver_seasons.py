import csv
import tempfile
import unittest
from pathlib import Path

from driver_seasons import _default_report_path, find_driver_results, write_report


class DriverSeasonResultsTests(unittest.TestCase):
    def test_default_report_path_is_grouped_by_year_under_stats(self) -> None:
        self.assertEqual(
            _default_report_path(Path("/data/results"), "Alex Driver", "2026"),
            Path("/data/stats/2026/driver_alex_driver_results.csv"),
        )

    def test_matches_driver_and_joins_class_standings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_dir = root / "2026" / "week2" / "saturday" / "0700"
            event_dir.mkdir(parents=True)
            event_path = event_dir / "eventresult_12345_0.csv"
            with event_path.open("w", newline="", encoding="utf-8") as destination:
                writer = csv.writer(destination)
                writer.writerow(
                    [
                        "Start Time", "Track", "Series", "Season Year", "Season Quarter",
                        "Rookie Season", "Race Week", "Strength of Field", "Special Event Type",
                    ]
                )
                writer.writerow(
                    ["2026-03-21T07:00:00Z", "Example Track", "Example Series", "2026",
                     "2", "N/A", "2", "4000", ""]
                )
                writer.writerow([])
                writer.writerow(
                    [
                        "Fin Pos", "Car ID", "Car", "Car Class ID", "Car Class", "Team ID",
                        "Cust ID", "Name", "Start Pos", "Car #", "Out ID", "Out", "Interval",
                        "Laps Led", "Qualify Time", "Average Lap Time", "Fastest Lap Time",
                        "Fast Lap#", "Laps Comp", "Inc", "Pts",
                    ]
                )
                writer.writerow(
                    [
                        "1", "169", "Porsche 911 GT3 R (992)", "4098", "NEC GT3 2026",
                        "-10", "-10", "Team", "2", "12", "0", "Running", "-", "10", "",
                        "", "", "", "20", "6", "100",
                    ]
                )
                writer.writerow(
                    [
                        "1", "169", "Porsche 911 GT3 R (992)", "4098", "NEC GT3 2026",
                        "-10", "123", "Alex Driver", "2", "12", "0", "Running", "-", "10", "",
                        "", "", "", "14", "4", "100",
                    ]
                )
                writer.writerow(
                    [
                        "2", "169", "Porsche 911 GT3 R (992)", "4098", "NEC GT3 2026",
                        "-11", "456", "Different Driver", "1", "10", "0", "Running", "-", "5",
                        "", "", "", "", "15", "2", "80",
                    ]
                )

            standings_dir = root / "2026" / "standings" / "gt3"
            standings_dir.mkdir(parents=True)
            standings_path = (
                standings_dir
                / "season-driver_Example_2026_Season_ccid_4098_rwnum_all.csv"
            )
            standings_path.write_text(
                "position,name,points,starts,wins,incidents,division,avgfinish,avgstart,laps,custid\n"
                "7,Alex Driver,500,4,1,16,2,3.5,5.0,80,123\n",
                encoding="utf-8",
            )

            results = find_driver_results(root, "  alex   DRIVER ")
            report_path = root / "report.csv"
            write_report(report_path, results)
            with report_path.open(newline="", encoding="utf-8") as source:
                report_rows = list(csv.DictReader(source))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["car"], "Porsche 911 GT3 R (992)")
        self.assertEqual(results[0]["start_position"], "2")
        self.assertEqual(results[0]["finish_position"], "1")
        self.assertEqual(results[0]["laps_completed"], "14")
        self.assertEqual(results[0]["incident_points"], "4")
        self.assertEqual(results[0]["season_rank"], "7")
        self.assertEqual(results[0]["season_points"], "500")
        self.assertEqual(results[0]["season_division"], "2")
        self.assertEqual(report_rows[0]["event_id"], "12345")

    def test_reports_missing_driver_by_exact_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_dir = root / "2026" / "week1" / "event"
            event_dir.mkdir(parents=True)
            (event_dir / "eventresult.csv").write_text(
                "Fin Pos,Car,Car Class ID,Car Class,Cust ID,Name,Start Pos,Car #,Out,Laps Comp,Inc,Pts\n"
                "1,BMW,1,GT3,100,Alex Driver,1,1,Running,10,1,20\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "was not found"):
                find_driver_results(root, "Alex")


if __name__ == "__main__":
    unittest.main()

import csv
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from generate_stats_page import _format_event_dates, generate_page


class GenerateStatsPageTests(unittest.TestCase):
    def test_formats_one_day_and_two_day_events(self) -> None:
        self.assertEqual(
            _format_event_dates({date(2026, 3, 21)}),
            "21. March",
        )
        self.assertEqual(
            _format_event_dates({date(2026, 3, 21), date(2026, 3, 22)}),
            "21.-22. March",
        )
        self.assertEqual(
            _format_event_dates({date(2026, 8, 29), date(2026, 9, 5)}),
            "29. August-5. September",
        )

    def test_generates_weeks_and_dates_from_selected_year_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            template = root / "template.html"
            output = root / "web" / "2026.html"
            template.write_text(
                """
                <h1>{{ year }}</h1>
                <table id="participation-summary">
                {% for week in weeks %}<tr><td>{{ week.label }}</td><td>{{ week.participation }}</td></tr>{% endfor %}
                </table>
                <div id="accordionYear">
                {% for week in weeks %}
                    <section id="week{{ week.number }}">
                        {{ week.label }} ({{ week.date_label }})
                        <span>{{ week.teams }}</span>
                        <span class="participation">{{ week.participation }}</span>
                        {% for class in week.classes %}{{ class.label }}{% endfor %}
                    </section>
                {% endfor %}
                </div>
                <script>{{ week_labels|tojson }}</script>
                """,
                encoding="utf-8",
            )
            self._write_results(
                results / "2026" / "week1" / "saturday" / "0700" / "results.csv",
                "2026-03-21T07:00:00Z",
                [
                    ["BMW M4 GT3 EVO", "NEC GT3 2026", "-8", "-8", "2", "25"],
                    ["BMW M4 GT3 EVO", "NEC GT3 2026", "-8", "101", "2", "25"],
                ],
            )
            self._write_results(
                results / "2026" / "week1" / "sunday" / "0000" / "results.csv",
                "2026-03-22T00:00:00Z",
                [["BMW M4 GT3 EVO", "NEC GT3 2026", "-9", "-9", "3", "30"]],
            )
            self._write_results(
                results / "2026" / "week2" / "sunday" / "0000" / "results.csv",
                "2026-04-04T00:00:00Z",
                [["Porsche", "NEC PCup 2026", "-10", "-10", "1", "20"]],
            )
            self._write_results(
                results / "2025" / "week1" / "sunday" / "0000" / "results.csv",
                "2025-03-01T00:00:00Z",
                [["Porsche", "NEC PCup 2025", "-11", "-11", "1", "20"]],
            )

            generate_page("2026", results, template, output)
            rendered = output.read_text(encoding="utf-8")

        self.assertIn("21.-22. March", rendered)
        self.assertIn("4. April", rendered)
        self.assertIn('id="week1"', rendered)
        self.assertIn('id="week2"', rendered)
        self.assertEqual(rendered.count("<section"), 2)
        self.assertIn(
            '<table id="participation-summary">\n<tr><td>Week 1</td><td>2</td></tr><tr><td>Week 2</td><td>1</td></tr>',
            rendered,
        )
        self.assertEqual(rendered.count('class="participation"'), 2)
        self.assertIn("GT3", rendered)
        self.assertIn("PCup", rendered)
        self.assertNotIn("2025", rendered)

    def test_year_argument_generates_selected_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            template = root / "template.html"
            output = root / "web" / "2025.html"
            template.write_text(
                "{% for week in weeks %}{{ week.label }}{% endfor %}",
                encoding="utf-8",
            )
            self._write_results(
                results / "2025" / "week1" / "sunday" / "0000" / "results.csv",
                "2025-03-01T00:00:00Z",
                [["Porsche", "PCup", "-1", "-1", "1", "20"]],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "generate_stats_page.py"),
                    "-y",
                    "2025",
                    "--input-dir",
                    str(results),
                    "--template",
                    str(template),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "Week 1")
            self.assertIn("Wrote", result.stdout)

    def test_template_shows_timeslot_table_and_graph_above_accordion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            template = (
                Path(__file__).resolve().parents[1] / "web" / "stats_template.html"
            )
            output = root / "2026.html"
            self._write_results(
                results / "2026" / "week1" / "saturday" / "0700" / "results.csv",
                "2026-03-21T07:00:00Z",
                [["BMW", "NEC GT3 2026", "-8", "-8", "2", "25"]],
            )
            self._write_results(
                results / "2026" / "week1" / "sunday" / "0000" / "results.csv",
                "2026-03-22T00:00:00Z",
                [["BMW", "NEC GT3 2026", "-9", "-9", "2", "25"]],
            )
            self._write_results(
                results / "2026" / "week2" / "monday" / "1300" / "results.csv",
                "2026-04-06T13:00:00Z",
                [["BMW", "NEC GT3 2026", "-10", "-10", "2", "25"]],
            )

            generate_page("2026", results, template, output)
            rendered = output.read_text(encoding="utf-8")

        summary_position = rendered.index("<h2>Participation by timeslot</h2>")
        accordion_position = rendered.index(
            '<div class="accordion" id="accordionYear">'
        )
        self.assertLess(summary_position, accordion_position)
        self.assertIn('id="timeslotParticipation"', rendered)
        self.assertIn("Saturday 07:00 GMT", rendered)
        self.assertIn("Sunday 00:00 GMT", rendered)
        self.assertIn("Monday 13:00 GMT", rendered)
        self.assertIn("<td>Saturday</td>", rendered)
        self.assertIn("Average team entries", rendered)
        self.assertIn('id="timeslotParticipationWeek1"', rendered)
        self.assertIn('id="timeslotParticipationWeek2"', rendered)
        self.assertIn("labels: [\"Saturday 07:00 GMT\", \"Sunday 00:00 GMT\"]", rendered)
        self.assertIn("labels: [\"Monday 13:00 GMT\"]", rendered)
        self.assertIn("Participation (team entries):</td><td>1</td>", rendered)

    @staticmethod
    def _write_results(path: Path, start_time: str, rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True)
        with path.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.writer(destination)
            writer.writerow(["Start Time", "Track"])
            writer.writerow([start_time, "Nürburgring"])
            writer.writerow(
                ["Car", "Car Class", "Team ID", "Cust ID", "Inc", "Laps Comp"]
            )
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

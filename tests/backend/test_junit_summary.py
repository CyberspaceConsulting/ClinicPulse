from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "junit_summary.py"


@pytest.mark.parametrize(("xml", "expected"), [
    (
        "<testsuites><testsuite><testcase/><testcase><failure/></testcase>"
        "<testcase><error/></testcase><testcase><skipped/></testcase></testsuite></testsuites>",
        "4 total, 1 passed, 2 failed/errors, 1 skipped",
    ),
    ("<testsuites><testsuite/></testsuites>", "0 total, 0 passed, 0 failed/errors, 0 skipped"),
])
def test_summary_counts_test_cases(tmp_path, xml, expected):
    report = tmp_path / "report.xml"
    report.write_text(xml, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "Tests", str(report)], capture_output=True, text=True)
    assert result.returncode == 0
    assert expected in result.stdout


def test_missing_report_is_explicit(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "Tests", str(tmp_path / "missing.xml")], capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "No report was produced" in result.stdout


@pytest.mark.parametrize("xml", ["<testsuite>", "<not-junit/>"])
def test_invalid_report_is_explicit(tmp_path, xml):
    report = tmp_path / "report.xml"
    report.write_text(xml, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "Tests", str(report)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Report" in result.stdout

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a JUnit XML report for GitHub Actions.")
    parser.add_argument("label")
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    if not args.report.exists():
        print(f"- **{args.label}:** No report was produced; check the step status and logs.")
        return 0
    try:
        root = ET.parse(args.report).getroot()
    except (ET.ParseError, OSError) as exc:
        print(f"- **{args.label}:** Report could not be read; see the summary step logs.")
        print(f"Cannot read JUnit report {args.report}: {exc}", file=sys.stderr)
        return 1
    if root.tag not in {"testsuite", "testsuites"}:
        print(f"- **{args.label}:** Report has an invalid root element; see the summary step logs.")
        return 1
    cases = root.findall(".//testcase")
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    skipped = sum(
        case.find("skipped") is not None
        and case.find("failure") is None
        and case.find("error") is None
        for case in cases
    )
    passed = len(cases) - failed - skipped
    print(f"- **{args.label}:** {len(cases)} total, {passed} passed, {failed} failed/errors, {skipped} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

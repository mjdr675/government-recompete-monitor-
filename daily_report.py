from datetime import date
from pathlib import Path

from report_builder import build_report


def main():
    run_date = str(date.today())
    data = build_report(run_date)

    lines = [
        f"Daily Recompete Report - {run_date}",
        "=" * 60,
        "",
        "SUMMARY",
        "-" * 60,
    ]

    for k, v in data["summary"].items():
        lines.append(f"{k:<15} {v}")

    lines.extend([
        "",
        "VALUE SUMMARY",
        "-" * 60,
    ])

    for k, v in data["value_summary"].items():
        lines.append(f"{k:<20} ${v:,.0f}")

    lines.extend([
        "",
        "TOP AGENCIES",
        "-" * 60,
    ])

    if data["top_agencies"]:
        for agency, count, value in data["top_agencies"]:
            lines.append(f"{agency} ({count}) ${value:,.0f}")
    else:
        lines.append("None")

    lines.extend([
        "",
        "TOP VENDORS",
        "-" * 60,
    ])

    if data["top_vendors"]:
        for vendor, count, value in data["top_vendors"]:
            lines.append(f"{vendor} ({count}) ${value:,.0f}")
    else:
        lines.append("None")

    reports = Path("reports")
    reports.mkdir(exist_ok=True)

    path = reports / f"{run_date}.txt"
    path.write_text("\n".join(lines) + "\n")

    print(f"saved {path}")


if __name__ == "__main__":
    main()

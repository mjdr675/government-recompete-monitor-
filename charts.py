"""
Reusable Chart.js data formatters.

Each function returns a dict compatible with Chart.js chart.data,
ready to be embedded via |tojson in a Jinja2 template.
"""

PRIORITY_COLORS = {
    "CRITICAL": "#b00020",
    "HIGH": "#d97706",
    "MEDIUM": "#2563eb",
    "LOW": "#4b5563",
}

_PALETTE = [
    "#1f4f8f", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd",
    "#1e40af", "#1d4ed8", "#7c3aed", "#059669", "#dc2626",
]


def bar_chart(labels, values, label="", color="#1f4f8f"):
    """Single-dataset vertical bar chart."""
    return {
        "labels": labels,
        "datasets": [{
            "label": label,
            "data": values,
            "backgroundColor": color,
            "borderRadius": 4,
            "borderSkipped": False,
        }],
    }


def pie_chart(labels, values, colors=None):
    """Pie / doughnut chart."""
    resolved = colors or [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]
    return {
        "labels": labels,
        "datasets": [{
            "data": values,
            "backgroundColor": resolved,
            "hoverOffset": 6,
        }],
    }


def priority_pie(priority_counts: dict):
    """Build a pie chart from a {priority: count} dict, in canonical order."""
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    labels, values, colors = [], [], []
    for p in order:
        if priority_counts.get(p, 0):
            labels.append(p)
            values.append(priority_counts[p])
            colors.append(PRIORITY_COLORS[p])
    return pie_chart(labels, values, colors)


def agency_bar(agency_values: list[tuple]):
    """Build a bar chart from [(agency, pipeline_value)] list."""
    labels = [row[0] for row in agency_values]
    values = [row[1] for row in agency_values]
    return bar_chart(labels, values, label="Pipeline Value ($)")


def monthly_bar(month_counts: list[tuple]):
    """Build a bar chart from [(YYYY-MM, count)] list."""
    labels = [row[0] for row in month_counts]
    values = [row[1] for row in month_counts]
    return bar_chart(labels, values, label="Contracts Expiring", color="#2563eb")

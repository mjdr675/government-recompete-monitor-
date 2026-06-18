from datetime import date
from flask import Flask, request, render_template_string, render_template

from db import connect
from report_builder import build_report
from analytics import vendor_profile, agency_profile

app = Flask(__name__)

BASE_CSS = """
<style>
body{font-family:Arial,sans-serif;margin:32px;background:#f7f7f7;color:#222}
a{color:#222}.nav{margin-bottom:24px}.nav a{margin-right:18px;font-weight:bold}
h1{margin-bottom:4px}.muted{color:#666;margin-bottom:24px}
.cards{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px}
.card{background:white;border-radius:10px;padding:18px;min-width:140px;box-shadow:0 1px 4px #ddd}
.num{font-size:28px;font-weight:bold}
table{width:100%;border-collapse:collapse;background:white;margin-bottom:28px}
th,td{text-align:left;padding:10px;border-bottom:1px solid #eee;vertical-align:top}
th{background:#222;color:white}.section{margin-top:28px}
input,select{padding:8px;margin-right:8px;margin-bottom:12px}
.badge{font-weight:bold}

.priority-badge {
  display: inline-block;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
  color: #111827;
  background: #e5e7eb;
}
.priority-critical { background: #fecaca; color: #7f1d1d; }
.priority-high { background: #fed7aa; color: #7c2d12; }
.priority-medium { background: #fef3c7; color: #78350f; }
.priority-low { background: #dcfce7; color: #14532d; }
.priority-unknown { background: #e5e7eb; color: #374151; }


.contract-row { cursor: pointer; }
.contract-row:hover { background: #f9fafb; }

</style>
"""

DASHBOARD = """
<!doctype html><html><head><title>Government Recompete Monitor</title>{{ css|safe }}</head><body>
<div class="nav"><a href="/">Dashboard</a><a href="/contracts">Contracts</a></div>
<h1>Government Recompete Monitor</h1>
<div class="muted">Daily dashboard for {{ report.run_date }}</div>

<div class="cards">
{% for key,value in report.summary.items() %}
<div class="card"><div>{{ key }}</div><div class="num">{{ value }}</div></div>
{% endfor %}
</div>

<h2>Value Summary</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
{% for key,value in report.value_summary.items() %}
<tr><td>{{ key }}</td><td>${{ "{:,.0f}".format(value or 0) }}</td></tr>
{% endfor %}
</table>

<h2>Top Opportunities</h2>
<table>
<tr><th>Priority</th><th>Vendor</th><th>Agency</th><th>Value</th><th>Days</th><th>Score</th><th>Change</th></tr>
{% for row in report.top_opportunities %}
<tr>
<td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td>
<td>${{ "{:,.0f}".format(row[3] or 0) }}</td><td>{{ row[4] }}</td><td>{{ row[5] }}</td><td>{{ row[6] }}</td>
</tr>
{% else %}
<tr><td colspan="7">No changes yet. A second snapshot date is needed.</td></tr>
{% endfor %}
</table>

<h2>Top Agencies</h2>
<table><tr><th>Agency</th><th>Count</th><th>Total Value</th></tr>
{% for agency,count,value in report.top_agencies %}
<tr><td>{{ agency }}</td><td>{{ count }}</td><td>${{ "{:,.0f}".format(value or 0) }}</td></tr>
{% else %}<tr><td colspan="3">None</td></tr>{% endfor %}
</table>

<h2>Top Vendors</h2>
<table><tr><th>Vendor</th><th>Count</th><th>Total Value</th></tr>
{% for vendor,count,value in report.top_vendors %}
<tr><td>{{ vendor }}</td><td>{{ count }}</td><td>${{ "{:,.0f}".format(value or 0) }}</td></tr>
{% else %}<tr><td colspan="3">None</td></tr>{% endfor %}
</table>

<div style="margin-top:18px;">
  {% if has_prev %}
    <a href="/contracts?q={{ q }}&priority={{ priority }}&page={{ page - 1 }}">Previous</a>
  {% endif %}

  <span class="muted" style="margin:0 12px;">Page {{ page }}</span>

  {% if has_next %}
    <a href="/contracts?q={{ q }}&priority={{ priority }}&page={{ page + 1 }}">Next</a>
  {% endif %}
</div>

</body></html>
"""

CONTRACTS = """
<!doctype html><html><head><title>Contracts</title>{{ css|safe }}</head><body>
<div class="nav"><a href="/">Dashboard</a><a href="/contracts">Contracts</a></div>
<h1>Contracts</h1>
<div class="muted">Showing {{ start }}–{{ end }} of {{ count }} matching contracts</div>

<form method="get">
<input name="q" value="{{ q }}" placeholder="Search vendor, agency, award...">
<select name="priority">
<option value="">All priorities</option>
{% for p in priorities %}
<option value="{{ p }}" {% if p == priority %}selected{% endif %}>{{ p }}</option>
{% endfor %}
</select>
<button type="submit">Filter</button>
<a href="/contracts">Reset</a>
</form>

<table>
<tr><th>Priority</th><th>Vendor</th><th>Agency</th><th>Value</th><th>End Date</th><th>Days</th><th>Score</th></tr>
{% for r in rows %}
<tr>
<td>
  <a class="priority-badge priority-{{ (r["priority"] or "unknown").lower().replace(" ", "-").replace("_", "-") }}"
     href="/contract/{{ r["internal_id"] }}">
     {{ r["priority"] }}
  </a>
</td>
<td>{{ r["vendor"] }}</td>
<td>{{ r["agency"] }}</td>
<td>${{ "{:,.0f}".format(r["value"] or 0) }}</td>
<td>{{ r["end_date"] }}</td>
<td>{{ r["days_remaining"] }}</td>
<td>{{ r["recompete_score"] }}</td>
</tr>
{% else %}
<tr><td colspan="7">No contracts found.</td></tr>
{% endfor %}
</table>
</body></html>
"""

@app.route("/")
def dashboard():
    return render_template("dashboard.html", css=BASE_CSS, report=build_report(str(date.today())))

@app.route("/contracts")
def contracts():
    q = request.args.get("q", "").strip()
    priority = request.args.get("priority", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 50
    offset = (page - 1) * per_page

    where = []
    params = []

    if q:
        like = f"%{q}%"
        where.append("(vendor LIKE ? OR agency LIKE ? OR award_id LIKE ?)")
        params.extend([like, like, like])

    if priority:
        where.append("priority = ?")
        params.append(priority)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    with connect() as con:
        con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
        rows = con.execute(f"""
            SELECT internal_id, priority, vendor, agency, value, end_date, days_remaining, recompete_score
            FROM contracts
            {where_sql}
            ORDER BY recompete_score DESC, value DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        count = con.execute(f"SELECT COUNT(*) AS c FROM contracts {where_sql}", params).fetchone()["c"]

        priorities = [
            r["priority"] for r in con.execute("""
                SELECT DISTINCT priority
                FROM contracts
                WHERE priority IS NOT NULL
                ORDER BY priority
            """).fetchall()
        ]

    return render_template(
        "contracts.html",
        css=BASE_CSS,
        rows=rows,
        count=count,
        q=q,
        priority=priority,
        priorities=priorities,
        page=page,
        per_page=per_page,
        offset=offset,
        start=offset + 1 if count else 0,
        end=min(offset + per_page, count),
        has_prev=page > 1,
        has_next=offset + per_page < count,
    )



@app.route("/vendor/<path:vendor>")
def vendor_detail(vendor):
    with connect() as con:
        profile = vendor_profile(con, vendor)

    if not profile["summary"] or profile["summary"]["contracts"] == 0:
        return "Vendor not found", 404

    return render_template("vendor.html", css=BASE_CSS, vendor=vendor, profile=profile)



@app.route("/agency/<path:agency>")
def agency_detail(agency):
    with connect() as con:
        profile = agency_profile(con, agency)

    if not profile["summary"] or profile["summary"]["contracts"] == 0:
        return "Agency not found", 404

    return render_template(
        "agency.html",
        css=BASE_CSS,
        agency=agency,
        profile=profile,
    )

@app.route("/contract/<internal_id>")
def contract_detail(internal_id):
    with connect() as con:
        con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
        row = con.execute("""
            SELECT *
            FROM contracts
            WHERE internal_id = ?
        """, (internal_id,)).fetchone()

    if not row:
        return "Contract not found", 404

    return render_template("contract_detail.html", css=BASE_CSS, row=row)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

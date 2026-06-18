# Proposed Patch
**Task:** Contract comparison page  
**Source:** backlog/high.md  
**Role:** frontend  
**Generated:** 2026-06-18T00:00:00+00:00  
**Status:** proposed — not applied  

---

## Patch: app.py
### Before
```python
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
```
### After
```python
@app.route("/compare")
def compare():
    def _fetch(internal_id):
        if not internal_id:
            return None
        con = connect()
        con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
        row = con.execute(
            "SELECT * FROM contracts WHERE internal_id=?",
            (internal_id,),
        ).fetchone()
        con.close()
        return row

    id_a = request.args.get("a", "").strip()
    id_b = request.args.get("b", "").strip()
    return render_template("compare.html", a=_fetch(id_a), b=_fetch(id_b),
                           id_a=id_a, id_b=id_b)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
```

## Patch: templates/contracts.html
### Before
```python
<table>
<tr>
  <th>{{ sort_link("priority", "Priority") }}</th>
  <th>{{ sort_link("vendor", "Vendor") }}</th>
  <th>{{ sort_link("agency", "Agency") }}</th>
  <th>{{ sort_link("value", "Value") }}</th>
  <th>{{ sort_link("end_date", "End Date") }}</th>
  <th>{{ sort_link("days_remaining", "Days") }}</th>
  <th>{{ sort_link("recompete_score", "Score") }}</th>
</tr>
{% for r in rows %}
<tr>
<td>
  <a class="priority-badge priority-{{ (r["priority"] or "unknown").lower().replace(" ", "-").replace("_", "-") }}"
     href="/contract/{{ r["internal_id"] }}">
     {{ r["priority"] }}
  </a>
</td>
<td><a href="/vendor/{{ r["vendor"]|urlencode }}">{{ r["vendor"] }}</a></td>
<td><a href="/agency/{{ r["agency"]|urlencode }}">{{ r["agency"] }}</a></td>
<td>${{ "{:,.0f}".format(r["value"] or 0) }}</td>
<td>{{ r["end_date"] }}</td>
<td>{{ r["days_remaining"] }}</td>
<td>{{ r["recompete_score"] }}</td>
</tr>
```
### After
```python
<div style="margin-bottom:8px;">
  <button id="compare-btn" disabled onclick="compareSelected()">Compare selected</button>
  <span id="compare-hint" class="muted" style="margin-left:8px;">Select exactly 2 contracts</span>
</div>
<table>
<tr>
  <th></th>
  <th>{{ sort_link("priority", "Priority") }}</th>
  <th>{{ sort_link("vendor", "Vendor") }}</th>
  <th>{{ sort_link("agency", "Agency") }}</th>
  <th>{{ sort_link("value", "Value") }}</th>
  <th>{{ sort_link("end_date", "End Date") }}</th>
  <th>{{ sort_link("days_remaining", "Days") }}</th>
  <th>{{ sort_link("recompete_score", "Score") }}</th>
</tr>
{% for r in rows %}
<tr>
<td><input type="checkbox" class="cmp-check" value="{{ r['internal_id'] }}" onchange="updateCompare()"></td>
<td>
  <a class="priority-badge priority-{{ (r["priority"] or "unknown").lower().replace(" ", "-").replace("_", "-") }}"
     href="/contract/{{ r["internal_id"] }}">
     {{ r["priority"] }}
  </a>
</td>
<td><a href="/vendor/{{ r["vendor"]|urlencode }}">{{ r["vendor"] }}</a></td>
<td><a href="/agency/{{ r["agency"]|urlencode }}">{{ r["agency"] }}</a></td>
<td>${{ "{:,.0f}".format(r["value"] or 0) }}</td>
<td>{{ r["end_date"] }}</td>
<td>{{ r["days_remaining"] }}</td>
<td>{{ r["recompete_score"] }}</td>
</tr>
```

from db import connect
from charts import priority_pie, agency_bar, monthly_bar

def agency_summary(run_date, limit=10):
    with connect() as con:
        return con.execute("""
            SELECT c.agency, COUNT(*) AS count, SUM(c.value) AS total_value
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = ?
            GROUP BY c.agency
            ORDER BY count DESC, total_value DESC
            LIMIT ?
        """, (run_date, limit)).fetchall()

def vendor_summary(run_date, limit=10):
    with connect() as con:
        return con.execute("""
            SELECT c.vendor, COUNT(*) AS count, SUM(c.value) AS total_value
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = ?
            GROUP BY c.vendor
            ORDER BY count DESC, total_value DESC
            LIMIT ?
        """, (run_date, limit)).fetchall()

def value_summary(run_date):
    with connect() as con:
        rows = con.execute("""
            SELECT ch.change_type, SUM(c.value)
            FROM changes ch
            LEFT JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = ?
            GROUP BY ch.change_type
        """, (run_date,)).fetchall()
    return {change_type: total or 0 for change_type, total in rows}

def top_opportunities(run_date, limit=10):
    with connect() as con:
        return con.execute("""
            SELECT
                c.priority,
                c.vendor,
                c.agency,
                c.value,
                c.days_remaining,
                c.recompete_score,
                ch.change_type
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = ?
            ORDER BY c.recompete_score DESC, c.value DESC
            LIMIT ?
        """, (run_date, limit)).fetchall()

def top_contracts_overall(limit=25):
    with connect() as con:
        con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
        return con.execute("""
            SELECT internal_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            ORDER BY recompete_score DESC, value DESC
            LIMIT ?
        """, (limit,)).fetchall()

def vendor_profile_analytics(con, vendor):
    """
    Full vendor intelligence profile. Single connection, one pass.
    Returns summary, agency breakdown, upcoming recompetes, timeline,
    chart data, risk indicators, and related vendors.
    """
    row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}
    con.row_factory = row_factory

    # ── 1. Extended summary (7 cards) ──────────────────────────────
    summary = con.execute("""
        SELECT
            COUNT(*)                                              AS contracts,
            COALESCE(SUM(value), 0)                              AS pipeline_value,
            COALESCE(AVG(recompete_score), 0)                    AS avg_score,
            SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
            COALESCE(AVG(days_remaining), 0)                     AS avg_days_remaining,
            MIN(end_date)                                        AS earliest_expiration,
            MAX(end_date)                                        AS latest_expiration
        FROM contracts
        WHERE vendor = ?
    """, (vendor,)).fetchone()

    # ── 2. Agency breakdown: pipeline value + avg score ────────────
    agencies = con.execute("""
        SELECT
            agency,
            COUNT(*)                    AS contracts,
            COALESCE(SUM(value), 0)    AS pipeline_value,
            COALESCE(AVG(recompete_score), 0) AS avg_score
        FROM contracts
        WHERE vendor = ?
        GROUP BY agency
        ORDER BY pipeline_value DESC, contracts DESC
    """, (vendor,)).fetchall()

    # ── 3. All upcoming recompetes (soonest first) ─────────────────
    upcoming = con.execute("""
        SELECT
            internal_id,
            award_id,
            agency,
            value,
            end_date,
            days_remaining,
            priority,
            recompete_score
        FROM contracts
        WHERE vendor = ?
        ORDER BY days_remaining ASC, end_date ASC
    """, (vendor,)).fetchall()

    # ── 4. Chart data ───────────────────────────────────────────────
    # 4a. Priority breakdown (for pie chart)
    priority_rows = con.execute("""
        SELECT priority, COUNT(*) AS cnt
        FROM contracts
        WHERE vendor = ?
        GROUP BY priority
    """, (vendor,)).fetchall()
    priority_counts = {r["priority"]: r["cnt"] for r in priority_rows}

    # 4b. Pipeline value by agency (top 10, for bar chart)
    agency_pipeline = [(a["agency"], a["pipeline_value"]) for a in agencies[:10]]

    # 4c. Contracts expiring per month (for bar chart)
    month_rows = con.execute("""
        SELECT strftime('%Y-%m', end_date) AS month, COUNT(*) AS cnt
        FROM contracts
        WHERE vendor = ? AND end_date IS NOT NULL
        GROUP BY month
        ORDER BY month
    """, (vendor,)).fetchall()
    month_counts = [(r["month"], r["cnt"]) for r in month_rows]

    charts = {
        "priority": priority_pie(priority_counts),
        "pipeline_by_agency": agency_bar(agency_pipeline),
        "expiring_by_month": monthly_bar(month_counts),
    }

    # ── 5. Risk indicators ─────────────────────────────────────────
    expiring_soon = [r for r in upcoming if (r["days_remaining"] or 9999) < 90]
    critical = [r for r in upcoming if r["priority"] == "CRITICAL"]

    # Agencies with 2+ contracts expiring within 180 days
    agency_expiry_counts: dict[str, int] = {}
    for r in upcoming:
        if (r["days_remaining"] or 9999) <= 180:
            agency_expiry_counts[r["agency"]] = agency_expiry_counts.get(r["agency"], 0) + 1
    multi_recompete_agencies = [a for a, c in agency_expiry_counts.items() if c >= 2]

    # Largest single contract by value
    largest = max(upcoming, key=lambda r: r["value"] or 0) if upcoming else None

    risk = {
        "expiring_soon": expiring_soon,
        "critical": critical,
        "agencies_multi_recompete": multi_recompete_agencies,
        "largest_contract": largest,
    }

    # ── 6. Related vendors (share at least one agency) ─────────────
    related = con.execute("""
        SELECT
            c2.vendor,
            COUNT(DISTINCT c2.agency) AS shared_agencies,
            COUNT(*)                  AS contracts
        FROM contracts c1
        JOIN contracts c2
          ON c1.agency = c2.agency
         AND c2.vendor != c1.vendor
        WHERE c1.vendor = ?
        GROUP BY c2.vendor
        ORDER BY shared_agencies DESC, contracts DESC
        LIMIT 8
    """, (vendor,)).fetchall()

    return {
        "summary": summary,
        "agencies": agencies,
        "upcoming": upcoming,
        "charts": charts,
        "risk": risk,
        "related_vendors": related,
    }

def agency_profile(con, agency):
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}

    summary = con.execute("""
        SELECT
            COUNT(*) AS contracts,
            COALESCE(SUM(value),0) AS pipeline_value,
            COALESCE(AVG(recompete_score),0) AS avg_score,
            SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts
        FROM contracts
        WHERE agency = ?
    """, (agency,)).fetchone()

    vendors = con.execute("""
        SELECT
            vendor,
            COUNT(*) AS contracts,
            SUM(value) AS pipeline_value
        FROM contracts
        WHERE agency = ?
        GROUP BY vendor
        ORDER BY pipeline_value DESC, contracts DESC
        LIMIT 10
    """, (agency,)).fetchall()

    upcoming = con.execute("""
        SELECT
            internal_id,
            award_id,
            vendor,
            value,
            end_date,
            days_remaining,
            priority,
            recompete_score
        FROM contracts
        WHERE agency = ?
        ORDER BY days_remaining ASC
        LIMIT 10
    """, (agency,)).fetchall()

    return {
        "summary": summary,
        "vendors": vendors,
        "upcoming": upcoming,
    }

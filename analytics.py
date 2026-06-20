from db import connect, get_engine
from sqlalchemy import text


def dashboard_analytics(con):
    """Platform-wide summary stats and key lists for the customer dashboard."""
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}

    platform = con.execute("""
        SELECT
            COUNT(*) AS total_contracts,
            COALESCE(SUM(value), 0) AS total_pipeline,
            SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
            SUM(CASE WHEN COALESCE(days_remaining, 0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
            COALESCE(AVG(recompete_score), 0) AS avg_score
        FROM contracts
    """).fetchone()

    upcoming = con.execute("""
        SELECT internal_id, award_id, vendor, agency, value, end_date,
               days_remaining, priority, recompete_score
        FROM contracts
        WHERE COALESCE(days_remaining, -1) BETWEEN 0 AND 90
        ORDER BY days_remaining ASC
        LIMIT 10
    """).fetchall()

    critical = con.execute("""
        SELECT internal_id, award_id, vendor, agency, value, end_date,
               days_remaining, recompete_score
        FROM contracts
        WHERE priority = 'CRITICAL' AND COALESCE(days_remaining, 0) > 0
        ORDER BY recompete_score DESC, days_remaining ASC
        LIMIT 10
    """).fetchall()

    top_agencies = con.execute("""
        SELECT agency, COUNT(*) AS contracts, COALESCE(SUM(value), 0) AS pipeline_value
        FROM contracts
        GROUP BY agency
        ORDER BY pipeline_value DESC
        LIMIT 5
    """).fetchall()

    top_vendors = con.execute("""
        SELECT vendor, COUNT(*) AS contracts, COALESCE(SUM(value), 0) AS pipeline_value
        FROM contracts
        GROUP BY vendor
        ORDER BY pipeline_value DESC
        LIMIT 5
    """).fetchall()

    return {
        "platform": platform,
        "upcoming": upcoming,
        "critical": critical,
        "top_agencies": top_agencies,
        "top_vendors": top_vendors,
    }


def opportunity_recommendations(con):
    """Return a deduplicated list of recommended opportunities with reasons.

    Categories (evaluated in order, each contract appears at most once):
    1. Top recompete score — highest signal of upcoming re-bid
    2. Highest value — largest contracts on the board
    3. Soonest expiration — most time-sensitive active contracts
    4. Critical priority — CRITICAL-flagged active contracts
    5. Recently changed — new awards or upgrades from the changes log
    """
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}

    recs = []
    seen_ids = set()

    def _add(row, reason):
        if row and row["internal_id"] not in seen_ids:
            seen_ids.add(row["internal_id"])
            entry = dict(row)
            entry["reason"] = reason
            recs.append(entry)

    for r in con.execute("""
        SELECT internal_id, award_id, vendor, agency, value, end_date,
               days_remaining, priority, recompete_score
        FROM contracts
        WHERE COALESCE(days_remaining, 0) > 0 AND recompete_score IS NOT NULL
        ORDER BY recompete_score DESC LIMIT 3
    """).fetchall():
        _add(r, f"Highest recompete score ({r['recompete_score']})")

    for r in con.execute("""
        SELECT internal_id, award_id, vendor, agency, value, end_date,
               days_remaining, priority, recompete_score
        FROM contracts
        WHERE COALESCE(days_remaining, 0) > 0 AND value IS NOT NULL
        ORDER BY value DESC LIMIT 3
    """).fetchall():
        v = r["value"] or 0
        _add(r, f"Highest value (${v:,.0f})")

    for r in con.execute("""
        SELECT internal_id, award_id, vendor, agency, value, end_date,
               days_remaining, priority, recompete_score
        FROM contracts
        WHERE COALESCE(days_remaining, 0) > 0
        ORDER BY days_remaining ASC LIMIT 3
    """).fetchall():
        days = r["days_remaining"]
        _add(r, f"Expiring in {days} day{'s' if days != 1 else ''}")

    for r in con.execute("""
        SELECT internal_id, award_id, vendor, agency, value, end_date,
               days_remaining, priority, recompete_score
        FROM contracts
        WHERE priority = 'CRITICAL' AND COALESCE(days_remaining, 0) > 0
        ORDER BY recompete_score DESC LIMIT 3
    """).fetchall():
        _add(r, "Critical priority contract")

    try:
        for r in con.execute("""
            SELECT c.internal_id, c.award_id, c.vendor, c.agency, c.value, c.end_date,
                   c.days_remaining, c.priority, c.recompete_score,
                   ch.change_type, ch.run_date
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.change_type IN ('NEW', 'UPGRADE', 'NEW_TIER_A')
            ORDER BY ch.run_date DESC LIMIT 3
        """).fetchall():
            label = "New award" if r["change_type"] in ("NEW", "NEW_TIER_A") else "Recently upgraded"
            _add(r, f"{label} ({r['run_date']})")
    except Exception:
        pass

    return recs


def agency_summary(run_date, limit=10):
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT c.agency, COUNT(*) AS count, SUM(c.value) AS total_value
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = :run_date
            GROUP BY c.agency
            ORDER BY count DESC, total_value DESC
            LIMIT :limit
        """), {"run_date": run_date, "limit": limit}).fetchall()


def vendor_summary(run_date, limit=10):
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT c.vendor, COUNT(*) AS count, SUM(c.value) AS total_value
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = :run_date
            GROUP BY c.vendor
            ORDER BY count DESC, total_value DESC
            LIMIT :limit
        """), {"run_date": run_date, "limit": limit}).fetchall()


def value_summary(run_date):
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ch.change_type, SUM(c.value)
            FROM changes ch
            LEFT JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE ch.run_date = :run_date
            GROUP BY ch.change_type
        """), {"run_date": run_date}).fetchall()
    return {row[0]: row[1] or 0 for row in rows}


def top_opportunities(run_date, limit=10):
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("""
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
            WHERE ch.run_date = :run_date
            ORDER BY c.recompete_score DESC, c.value DESC
            LIMIT :limit
        """), {"run_date": run_date, "limit": limit}).fetchall()


def top_contracts_overall(limit=25):
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT internal_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            ORDER BY recompete_score DESC, value DESC
            LIMIT :limit
        """), {"limit": limit}).mappings().fetchall()

def vendor_profile_analytics(con, vendor):
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}

    summary = con.execute("""
        SELECT
            COUNT(*) AS contracts,
            COALESCE(SUM(value),0) AS pipeline_value,
            COALESCE(AVG(recompete_score),0) AS avg_score,
            MAX(recompete_score) AS max_score,
            SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
            SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
            SUM(CASE WHEN COALESCE(days_remaining,0) <= 0 THEN 1 ELSE 0 END) AS expired_contracts
        FROM contracts
        WHERE vendor = ?
    """, (vendor,)).fetchone()

    agencies = con.execute("""
        SELECT
            agency,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value,
            SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
            MAX(recompete_score) AS top_score
        FROM contracts
        WHERE vendor = ?
        GROUP BY agency
        ORDER BY total_value DESC, contracts DESC, agency
    """, (vendor,)).fetchall()

    upcoming = con.execute("""
        SELECT
            internal_id,
            award_id,
            agency,
            sub_agency,
            value,
            start_date,
            end_date,
            days_remaining,
            priority,
            recompete_score,
            competition_type
        FROM contracts
        WHERE vendor = ?
        ORDER BY days_remaining ASC
        LIMIT 25
    """, (vendor,)).fetchall()

    timeline = con.execute("""
        SELECT
            substr(end_date, 1, 4) AS year,
            CASE
                WHEN CAST(substr(end_date, 6, 2) AS INTEGER) BETWEEN 1 AND 3 THEN 'Q1'
                WHEN CAST(substr(end_date, 6, 2) AS INTEGER) BETWEEN 4 AND 6 THEN 'Q2'
                WHEN CAST(substr(end_date, 6, 2) AS INTEGER) BETWEEN 7 AND 9 THEN 'Q3'
                ELSE 'Q4'
            END AS quarter,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value
        FROM contracts
        WHERE vendor = ? AND end_date IS NOT NULL
        GROUP BY year, quarter
        ORDER BY year, quarter
    """, (vendor,)).fetchall()

    win_loss_summary = con.execute("""
        SELECT
            CASE
                WHEN COALESCE(days_remaining, -1) > 0 THEN 'Active'
                WHEN days_remaining = 0              THEN 'Expiring Today'
                WHEN days_remaining IS NULL          THEN 'Unknown'
                ELSE 'Expired'
            END AS status,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value
        FROM contracts
        WHERE vendor = ?
        GROUP BY status
        ORDER BY status
    """, (vendor,)).fetchall()

    # Change events (NEW = award win, REMOVED = contract ended/lost).
    # Note: if a REMOVED contract was also deleted from contracts, the JOIN
    # will not find it — this is a known schema limitation.
    # The changes table is created lazily; guard against it not existing yet.
    try:
        change_events = con.execute("""
            SELECT ch.change_type, ch.run_date, c.award_id, c.agency, c.value, c.priority
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE c.vendor = ?
              AND ch.change_type IN ('NEW', 'REMOVED')
            ORDER BY ch.run_date DESC
            LIMIT 20
        """, (vendor,)).fetchall()
    except Exception:
        change_events = []

    score_distribution = con.execute("""
        SELECT
            CASE
                WHEN recompete_score >= 80 THEN 'High (80-100)'
                WHEN recompete_score >= 60 THEN 'Medium (60-79)'
                WHEN recompete_score >= 40 THEN 'Low (40-59)'
                ELSE 'Minimal (0-39)'
            END AS bucket,
            COUNT(*) AS contracts
        FROM contracts
        WHERE vendor = ?
        GROUP BY bucket
        ORDER BY MIN(recompete_score) DESC
    """, (vendor,)).fetchall()

    platform_avg_row = con.execute(
        "SELECT COALESCE(AVG(recompete_score), 0) AS platform_avg FROM contracts"
    ).fetchone()
    summary["platform_avg_score"] = platform_avg_row["platform_avg"] if platform_avg_row else 0

    pipeline_by_priority = con.execute("""
        SELECT
            priority,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value,
            COALESCE(AVG(value), 0) AS avg_value
        FROM contracts
        WHERE vendor = ?
        GROUP BY priority
        ORDER BY CASE priority
            WHEN 'CRITICAL' THEN 1
            WHEN 'HIGH'     THEN 2
            WHEN 'MEDIUM'   THEN 3
            WHEN 'LOW'      THEN 4
            ELSE 5 END
    """, (vendor,)).fetchall()

    active = con.execute("""
        SELECT
            internal_id,
            award_id,
            agency,
            sub_agency,
            value,
            start_date,
            end_date,
            days_remaining,
            priority,
            recompete_score,
            competition_type
        FROM contracts
        WHERE vendor = ?
          AND COALESCE(days_remaining, 0) > 0
        ORDER BY days_remaining ASC
        LIMIT 50
    """, (vendor,)).fetchall()

    return {
        "summary": summary,
        "agencies": agencies,
        "upcoming": upcoming,
        "active": active,
        "pipeline_by_priority": pipeline_by_priority,
        "score_distribution": score_distribution,
        "win_loss_summary": win_loss_summary,
        "change_events": change_events,
        "timeline": timeline,
    }

def agency_profile(con, agency):
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}

    summary = con.execute("""
        SELECT
            COUNT(*) AS contracts,
            COALESCE(SUM(value),0) AS pipeline_value,
            COALESCE(AVG(recompete_score),0) AS avg_score,
            MAX(recompete_score) AS max_score,
            SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
            SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
            SUM(CASE WHEN COALESCE(days_remaining,0) <= 0 THEN 1 ELSE 0 END) AS expired_contracts
        FROM contracts
        WHERE agency = ?
    """, (agency,)).fetchone()

    vendors = con.execute("""
        SELECT
            vendor,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS pipeline_value,
            SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
            MAX(recompete_score) AS top_score
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
            sub_agency,
            value,
            start_date,
            end_date,
            days_remaining,
            priority,
            recompete_score,
            competition_type
        FROM contracts
        WHERE agency = ?
        ORDER BY days_remaining ASC
        LIMIT 25
    """, (agency,)).fetchall()

    active = con.execute("""
        SELECT
            internal_id,
            award_id,
            vendor,
            sub_agency,
            value,
            start_date,
            end_date,
            days_remaining,
            priority,
            recompete_score,
            competition_type
        FROM contracts
        WHERE agency = ?
          AND COALESCE(days_remaining, 0) > 0
        ORDER BY days_remaining ASC
        LIMIT 50
    """, (agency,)).fetchall()

    timeline = con.execute("""
        SELECT
            substr(end_date, 1, 4) AS year,
            CASE
                WHEN CAST(substr(end_date, 6, 2) AS INTEGER) BETWEEN 1 AND 3 THEN 'Q1'
                WHEN CAST(substr(end_date, 6, 2) AS INTEGER) BETWEEN 4 AND 6 THEN 'Q2'
                WHEN CAST(substr(end_date, 6, 2) AS INTEGER) BETWEEN 7 AND 9 THEN 'Q3'
                ELSE 'Q4'
            END AS quarter,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value
        FROM contracts
        WHERE agency = ? AND end_date IS NOT NULL
        GROUP BY year, quarter
        ORDER BY year, quarter
    """, (agency,)).fetchall()

    win_loss_summary = con.execute("""
        SELECT
            CASE
                WHEN COALESCE(days_remaining, -1) > 0 THEN 'Active'
                WHEN days_remaining = 0              THEN 'Expiring Today'
                WHEN days_remaining IS NULL          THEN 'Unknown'
                ELSE 'Expired'
            END AS status,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value
        FROM contracts
        WHERE agency = ?
        GROUP BY status
        ORDER BY status
    """, (agency,)).fetchall()

    try:
        change_events = con.execute("""
            SELECT ch.change_type, ch.run_date, c.award_id, c.vendor, c.value, c.priority
            FROM changes ch
            JOIN contracts c ON ch.internal_id = c.internal_id
            WHERE c.agency = ?
              AND ch.change_type IN ('NEW', 'REMOVED')
            ORDER BY ch.run_date DESC
            LIMIT 20
        """, (agency,)).fetchall()
    except Exception:
        change_events = []

    score_distribution = con.execute("""
        SELECT
            CASE
                WHEN recompete_score >= 80 THEN 'High (80-100)'
                WHEN recompete_score >= 60 THEN 'Medium (60-79)'
                WHEN recompete_score >= 40 THEN 'Low (40-59)'
                ELSE 'Minimal (0-39)'
            END AS bucket,
            COUNT(*) AS contracts
        FROM contracts
        WHERE agency = ?
        GROUP BY bucket
        ORDER BY MIN(recompete_score) DESC
    """, (agency,)).fetchall()

    platform_avg_row = con.execute(
        "SELECT COALESCE(AVG(recompete_score), 0) AS platform_avg FROM contracts"
    ).fetchone()
    summary["platform_avg_score"] = platform_avg_row["platform_avg"] if platform_avg_row else 0

    pipeline_by_priority = con.execute("""
        SELECT
            priority,
            COUNT(*) AS contracts,
            COALESCE(SUM(value), 0) AS total_value,
            COALESCE(AVG(value), 0) AS avg_value
        FROM contracts
        WHERE agency = ?
        GROUP BY priority
        ORDER BY CASE priority
            WHEN 'CRITICAL' THEN 1
            WHEN 'HIGH'     THEN 2
            WHEN 'MEDIUM'   THEN 3
            WHEN 'LOW'      THEN 4
            ELSE 5 END
    """, (agency,)).fetchall()

    return {
        "summary": summary,
        "vendors": vendors,
        "upcoming": upcoming,
        "active": active,
        "pipeline_by_priority": pipeline_by_priority,
        "score_distribution": score_distribution,
        "win_loss_summary": win_loss_summary,
        "change_events": change_events,
        "timeline": timeline,
    }

from db import connect

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
    con.row_factory = lambda cur, row: {col[0]: row[i] for i, col in enumerate(cur.description)}

    summary = con.execute("""
        SELECT
            COUNT(*) AS contracts,
            COALESCE(SUM(value),0) AS pipeline_value,
            COALESCE(AVG(recompete_score),0) AS avg_score,
            SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts
        FROM contracts
        WHERE vendor = ?
    """, (vendor,)).fetchone()

    agencies = con.execute("""
        SELECT agency, COUNT(*) AS contracts
        FROM contracts
        WHERE vendor = ?
        GROUP BY agency
        ORDER BY contracts DESC, agency
    """, (vendor,)).fetchall()

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
        ORDER BY days_remaining ASC
        LIMIT 10
    """, (vendor,)).fetchall()

    return {
        "summary": summary,
        "agencies": agencies,
        "upcoming": upcoming,
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

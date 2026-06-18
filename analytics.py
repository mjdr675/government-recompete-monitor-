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

from db import connect

def new_opportunities(today, yesterday):
    with connect() as con:
        return con.execute("""
            SELECT COUNT(*)
            FROM snapshots s
            WHERE s.run_date = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM snapshots y
                  WHERE y.run_date = ?
                    AND y.internal_id = s.internal_id
              )
        """, (today, yesterday)).fetchone()[0]

def removed_opportunities(today, yesterday):
    with connect() as con:
        return con.execute("""
            SELECT COUNT(*)
            FROM snapshots y
            WHERE y.run_date = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM snapshots s
                  WHERE s.run_date = ?
                    AND s.internal_id = y.internal_id
              )
        """, (yesterday, today)).fetchone()[0]

def list_new_opportunities(today, yesterday, limit=25):
    with connect() as con:
        return con.execute("""
            SELECT c.priority,
                   c.agency,
                   c.vendor,
                   c.value,
                   c.days_remaining,
                   c.award_id
            FROM snapshots s
            JOIN contracts c
              ON c.internal_id = s.internal_id
            WHERE s.run_date = ?
              AND NOT EXISTS (
                    SELECT 1
                    FROM snapshots y
                    WHERE y.run_date = ?
                      AND y.internal_id = s.internal_id
              )
            ORDER BY c.recompete_score DESC
            LIMIT ?
        """, (today, yesterday, limit)).fetchall()


def list_removed_opportunities(today, yesterday, limit=25):
    with connect() as con:
        return con.execute("""
            SELECT c.priority,
                   c.agency,
                   c.vendor,
                   c.value,
                   c.days_remaining,
                   c.award_id
            FROM snapshots y
            JOIN contracts c
              ON c.internal_id = y.internal_id
            WHERE y.run_date = ?
              AND NOT EXISTS (
                    SELECT 1
                    FROM snapshots s
                    WHERE s.run_date = ?
                      AND s.internal_id = y.internal_id
              )
            ORDER BY c.recompete_score DESC
            LIMIT ?
        """, (yesterday, today, limit)).fetchall()

def priority_rank(priority):
    return {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }.get(priority, 0)


def list_priority_changes(today, yesterday, direction="up", limit=25):
    rank_case = """
        CASE priority
            WHEN 'LOW' THEN 1
            WHEN 'MEDIUM' THEN 2
            WHEN 'HIGH' THEN 3
            WHEN 'CRITICAL' THEN 4
            ELSE 0
        END
    """

    operator = ">" if direction == "up" else "<"

    with connect() as con:
        return con.execute(f"""
            SELECT y.priority AS old_priority,
                   s.priority AS new_priority,
                   c.agency,
                   c.vendor,
                   c.value,
                   c.days_remaining,
                   c.award_id
            FROM snapshots s
            JOIN snapshots y
              ON y.internal_id = s.internal_id
            JOIN contracts c
              ON c.internal_id = s.internal_id
            WHERE s.run_date = ?
              AND y.run_date = ?
              AND ({rank_case.replace("priority", "s.priority")})
                  {operator}
                  ({rank_case.replace("priority", "y.priority")})
            ORDER BY c.recompete_score DESC
            LIMIT ?
        """, (today, yesterday, limit)).fetchall()

def agency_summary(run_date):
    from db import connect

    with connect() as con:
        cur = con.execute("""
            SELECT
                c.agency,
                COUNT(*) AS changes,
                SUM(COALESCE(c.value,0)) AS total_value
            FROM changes ch
            JOIN contracts c
                ON ch.internal_id = c.internal_id
            WHERE ch.run_date = ?
            GROUP BY c.agency
            ORDER BY changes DESC, total_value DESC
        """, (run_date,))
        return cur.fetchall()

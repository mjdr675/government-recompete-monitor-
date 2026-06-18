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

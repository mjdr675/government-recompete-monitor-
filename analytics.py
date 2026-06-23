from db import connect, get_engine
from sqlalchemy import text


def dashboard_analytics():
    """Platform-wide summary stats and key lists for the customer dashboard."""
    engine = get_engine()
    with engine.connect() as conn:
        platform = conn.execute(text("""
            SELECT
                COUNT(*) AS total_contracts,
                COALESCE(SUM(value), 0) AS total_pipeline,
                SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
                SUM(CASE WHEN COALESCE(days_remaining, 0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
                COALESCE(AVG(recompete_score), 0) AS avg_score
            FROM contracts
        """)).mappings().fetchone()

        upcoming = conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            WHERE COALESCE(days_remaining, -1) BETWEEN 0 AND 90
            ORDER BY days_remaining ASC
            LIMIT 10
        """)).mappings().fetchall()

        critical = conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, recompete_score
            FROM contracts
            WHERE priority = 'CRITICAL' AND COALESCE(days_remaining, 0) > 0
            ORDER BY recompete_score DESC, days_remaining ASC
            LIMIT 10
        """)).mappings().fetchall()

        top_agencies = conn.execute(text("""
            SELECT agency, COUNT(*) AS contracts, COALESCE(SUM(value), 0) AS pipeline_value
            FROM contracts
            GROUP BY agency
            ORDER BY pipeline_value DESC
            LIMIT 5
        """)).mappings().fetchall()

        top_vendors = conn.execute(text("""
            SELECT vendor, COUNT(*) AS contracts, COALESCE(SUM(value), 0) AS pipeline_value
            FROM contracts
            GROUP BY vendor
            ORDER BY pipeline_value DESC
            LIMIT 5
        """)).mappings().fetchall()

    return {
        "platform": dict(platform) if platform else {},
        "upcoming": [dict(r) for r in upcoming],
        "critical": [dict(r) for r in critical],
        "top_agencies": [dict(r) for r in top_agencies],
        "top_vendors": [dict(r) for r in top_vendors],
    }


def opportunity_recommendations():
    """Return a deduplicated list of recommended opportunities with reasons.

    Categories (evaluated in order, each contract appears at most once):
    1. Top recompete score — highest signal of upcoming re-bid
    2. Highest value — largest contracts on the board
    3. Soonest expiration — most time-sensitive active contracts
    4. Critical priority — CRITICAL-flagged active contracts
    5. Recently changed — new awards or upgrades from the changes log
    """
    engine = get_engine()
    recs = []
    seen_ids = set()

    def _add(row, reason):
        if row and row["internal_id"] not in seen_ids:
            seen_ids.add(row["internal_id"])
            entry = dict(row)
            entry["reason"] = reason
            recs.append(entry)

    with engine.connect() as conn:
        for r in conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            WHERE COALESCE(days_remaining, 0) > 0 AND recompete_score IS NOT NULL
            ORDER BY recompete_score DESC LIMIT 3
        """)).mappings().fetchall():
            _add(r, f"Highest recompete score ({r['recompete_score']})")

        for r in conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            WHERE COALESCE(days_remaining, 0) > 0 AND value IS NOT NULL
            ORDER BY value DESC LIMIT 3
        """)).mappings().fetchall():
            v = r["value"] or 0
            _add(r, f"Highest value (${v:,.0f})")

        for r in conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            WHERE COALESCE(days_remaining, 0) > 0
            ORDER BY days_remaining ASC LIMIT 3
        """)).mappings().fetchall():
            days = r["days_remaining"]
            _add(r, f"Expiring in {days} day{'s' if days != 1 else ''}")

        for r in conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score
            FROM contracts
            WHERE priority = 'CRITICAL' AND COALESCE(days_remaining, 0) > 0
            ORDER BY recompete_score DESC LIMIT 3
        """)).mappings().fetchall():
            _add(r, "Critical priority contract")

        try:
            for r in conn.execute(text("""
                SELECT c.internal_id, c.award_id, c.vendor, c.agency, c.value, c.end_date,
                       c.days_remaining, c.priority, c.recompete_score,
                       ch.change_type, ch.run_date
                FROM changes ch
                JOIN contracts c ON ch.internal_id = c.internal_id
                WHERE ch.change_type IN ('NEW', 'UPGRADE', 'NEW_TIER_A')
                ORDER BY ch.run_date DESC LIMIT 3
            """)).mappings().fetchall():
                label = "New award" if r["change_type"] in ("NEW", "NEW_TIER_A") else "Recently upgraded"
                _add(r, f"{label} ({r['run_date']})")
        except Exception:
            pass

    return recs


def dashboard_recommended_actions(user_id):
    """Watched contracts + top high-priority contracts, each annotated with a next action.

    Watched contracts for the user come first; high-priority active contracts fill
    remaining slots up to 5 total. Deduped by internal_id.
    """
    from contract_summary import recommended_action as _rec

    engine = get_engine()
    results = []
    seen = set()

    def _add(rows, source):
        for r in rows:
            r = dict(r)
            iid = r.get("internal_id")
            if iid in seen:
                continue
            seen.add(iid)
            act = _rec(r)
            r["next_action"] = act["action"]
            r["action_source"] = source
            results.append(r)

    with engine.connect() as conn:
        if user_id is not None:
            watched = conn.execute(text("""
                SELECT c.internal_id, c.award_id, c.vendor, c.agency, c.value,
                       c.days_remaining, c.priority, c.recompete_score,
                       c.solicitation_id, c.competition_type
                FROM contracts c
                JOIN user_watchlist w ON w.internal_id = c.internal_id
                WHERE w.user_id = :uid AND COALESCE(c.days_remaining, 0) > 0
                ORDER BY c.days_remaining ASC
                LIMIT 5
            """), {"uid": user_id}).mappings().fetchall()
            _add(watched, "watched")

        if len(results) < 5:
            top = conn.execute(text("""
                SELECT internal_id, award_id, vendor, agency, value,
                       days_remaining, priority, recompete_score,
                       solicitation_id, competition_type
                FROM contracts
                WHERE priority IN ('CRITICAL', 'HIGH') AND COALESCE(days_remaining, 0) > 0
                ORDER BY recompete_score DESC
                LIMIT 10
            """)).mappings().fetchall()
            _add(top[:5 - len(results)], "high_priority")

    return results


def business_opportunities(user_id, limit=5):
    """Return top active contracts matched against the user's company profile.

    Scores each contract with business_match_score() and returns the top
    `limit` results with match_score and match_reasons attached.
    Returns [] if user_id is None or the user has no company profile.
    """
    if not user_id:
        return []

    from db import get_company_profile
    from business_match import business_match_score as _bms, business_match_reasons as _bmr

    profile = get_company_profile(user_id)
    if not profile:
        return []

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT internal_id, award_id, vendor, agency, value, end_date,
                   days_remaining, priority, recompete_score, competition_type, raw_json
            FROM contracts
            WHERE COALESCE(days_remaining, 0) > 0
            ORDER BY recompete_score DESC
            LIMIT 200
        """)).mappings().fetchall()

    scored = []
    for row in rows:
        r = dict(row)
        score = _bms(r, profile)
        if score > 0:
            r["match_score"] = score
            r["match_reasons"] = _bmr(r, profile)
            scored.append(r)

    scored.sort(key=lambda r: (-r["match_score"], -(r.get("recompete_score") or 0)))
    return scored[:limit]


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

def vendor_profile_analytics(vendor):
    """Return profile data for a single vendor."""
    engine = get_engine()
    with engine.connect() as conn:
        summary = dict(conn.execute(text("""
            SELECT
                COUNT(*) AS contracts,
                COALESCE(SUM(value),0) AS pipeline_value,
                COALESCE(AVG(recompete_score),0) AS avg_score,
                MAX(recompete_score) AS max_score,
                SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
                SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
                SUM(CASE WHEN COALESCE(days_remaining,0) <= 0 THEN 1 ELSE 0 END) AS expired_contracts
            FROM contracts
            WHERE vendor = :vendor
        """), {"vendor": vendor}).mappings().fetchone() or {})

        agencies = [dict(r) for r in conn.execute(text("""
            SELECT
                agency,
                COUNT(*) AS contracts,
                COALESCE(SUM(value), 0) AS total_value,
                SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
                MAX(recompete_score) AS top_score
            FROM contracts
            WHERE vendor = :vendor
            GROUP BY agency
            ORDER BY total_value DESC, contracts DESC, agency
        """), {"vendor": vendor}).mappings().fetchall()]

        upcoming = [dict(r) for r in conn.execute(text("""
            SELECT internal_id, award_id, agency, sub_agency, value, start_date,
                   end_date, days_remaining, priority, recompete_score, competition_type
            FROM contracts
            WHERE vendor = :vendor
            ORDER BY days_remaining ASC
            LIMIT 25
        """), {"vendor": vendor}).mappings().fetchall()]

        timeline = [dict(r) for r in conn.execute(text("""
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
            WHERE vendor = :vendor AND end_date IS NOT NULL
            GROUP BY year, quarter
            ORDER BY year, quarter
        """), {"vendor": vendor}).mappings().fetchall()]

        win_loss_summary = [dict(r) for r in conn.execute(text("""
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
            WHERE vendor = :vendor
            GROUP BY status
            ORDER BY status
        """), {"vendor": vendor}).mappings().fetchall()]

        score_distribution = [dict(r) for r in conn.execute(text("""
            SELECT
                CASE
                    WHEN recompete_score >= 80 THEN 'High (80-100)'
                    WHEN recompete_score >= 60 THEN 'Medium (60-79)'
                    WHEN recompete_score >= 40 THEN 'Low (40-59)'
                    ELSE 'Minimal (0-39)'
                END AS bucket,
                COUNT(*) AS contracts
            FROM contracts
            WHERE vendor = :vendor
            GROUP BY bucket
            ORDER BY MIN(recompete_score) DESC
        """), {"vendor": vendor}).mappings().fetchall()]

        platform_avg_row = conn.execute(text(
            "SELECT COALESCE(AVG(recompete_score), 0) AS platform_avg FROM contracts"
        )).mappings().fetchone()
        summary["platform_avg_score"] = platform_avg_row["platform_avg"] if platform_avg_row else 0

        pipeline_by_priority = [dict(r) for r in conn.execute(text("""
            SELECT
                priority,
                COUNT(*) AS contracts,
                COALESCE(SUM(value), 0) AS total_value,
                COALESCE(AVG(value), 0) AS avg_value
            FROM contracts
            WHERE vendor = :vendor
            GROUP BY priority
            ORDER BY CASE priority
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                WHEN 'LOW'      THEN 4
                ELSE 5 END
        """), {"vendor": vendor}).mappings().fetchall()]

        active = [dict(r) for r in conn.execute(text("""
            SELECT internal_id, award_id, agency, sub_agency, value, start_date,
                   end_date, days_remaining, priority, recompete_score, competition_type
            FROM contracts
            WHERE vendor = :vendor
              AND COALESCE(days_remaining, 0) > 0
            ORDER BY days_remaining ASC
            LIMIT 50
        """), {"vendor": vendor}).mappings().fetchall()]

        # The changes table is created lazily; guard against it not existing yet.
        try:
            change_events = [dict(r) for r in conn.execute(text("""
                SELECT ch.change_type, ch.run_date, c.award_id, c.agency, c.value, c.priority
                FROM changes ch
                JOIN contracts c ON ch.internal_id = c.internal_id
                WHERE c.vendor = :vendor
                  AND ch.change_type IN ('NEW', 'REMOVED')
                ORDER BY ch.run_date DESC
                LIMIT 20
            """), {"vendor": vendor}).mappings().fetchall()]
        except Exception:
            change_events = []

        # Vendor website — only populated by future enrichment; may be NULL for
        # all contracts.  Return the first non-null value across any contract for
        # this vendor so the profile page can display it when available.
        try:
            website_row = conn.execute(text(
                "SELECT vendor_website FROM contracts"
                " WHERE vendor = :vendor AND vendor_website IS NOT NULL"
                " AND vendor_website != '' LIMIT 1"
            ), {"vendor": vendor}).fetchone()
            vendor_website = website_row[0] if website_row else None
        except Exception:
            vendor_website = None

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
        "vendor_website": vendor_website,
    }

def agency_profile(agency):
    """Return profile data for a single agency."""
    engine = get_engine()
    with engine.connect() as conn:
        summary = dict(conn.execute(text("""
            SELECT
                COUNT(*) AS contracts,
                COALESCE(SUM(value),0) AS pipeline_value,
                COALESCE(AVG(recompete_score),0) AS avg_score,
                MAX(recompete_score) AS max_score,
                SUM(CASE WHEN priority='CRITICAL' THEN 1 ELSE 0 END) AS critical_contracts,
                SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
                SUM(CASE WHEN COALESCE(days_remaining,0) <= 0 THEN 1 ELSE 0 END) AS expired_contracts
            FROM contracts
            WHERE agency = :agency
        """), {"agency": agency}).mappings().fetchone() or {})

        vendors = [dict(r) for r in conn.execute(text("""
            SELECT
                vendor,
                COUNT(*) AS contracts,
                COALESCE(SUM(value), 0) AS pipeline_value,
                SUM(CASE WHEN COALESCE(days_remaining,0) > 0 THEN 1 ELSE 0 END) AS active_contracts,
                MAX(recompete_score) AS top_score
            FROM contracts
            WHERE agency = :agency
            GROUP BY vendor
            ORDER BY pipeline_value DESC, contracts DESC
            LIMIT 10
        """), {"agency": agency}).mappings().fetchall()]

        upcoming = [dict(r) for r in conn.execute(text("""
            SELECT internal_id, award_id, vendor, sub_agency, value, start_date,
                   end_date, days_remaining, priority, recompete_score, competition_type
            FROM contracts
            WHERE agency = :agency
            ORDER BY days_remaining ASC
            LIMIT 25
        """), {"agency": agency}).mappings().fetchall()]

        active = [dict(r) for r in conn.execute(text("""
            SELECT internal_id, award_id, vendor, sub_agency, value, start_date,
                   end_date, days_remaining, priority, recompete_score, competition_type
            FROM contracts
            WHERE agency = :agency
              AND COALESCE(days_remaining, 0) > 0
            ORDER BY days_remaining ASC
            LIMIT 50
        """), {"agency": agency}).mappings().fetchall()]

        timeline = [dict(r) for r in conn.execute(text("""
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
            WHERE agency = :agency AND end_date IS NOT NULL
            GROUP BY year, quarter
            ORDER BY year, quarter
        """), {"agency": agency}).mappings().fetchall()]

        win_loss_summary = [dict(r) for r in conn.execute(text("""
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
            WHERE agency = :agency
            GROUP BY status
            ORDER BY status
        """), {"agency": agency}).mappings().fetchall()]

        score_distribution = [dict(r) for r in conn.execute(text("""
            SELECT
                CASE
                    WHEN recompete_score >= 80 THEN 'High (80-100)'
                    WHEN recompete_score >= 60 THEN 'Medium (60-79)'
                    WHEN recompete_score >= 40 THEN 'Low (40-59)'
                    ELSE 'Minimal (0-39)'
                END AS bucket,
                COUNT(*) AS contracts
            FROM contracts
            WHERE agency = :agency
            GROUP BY bucket
            ORDER BY MIN(recompete_score) DESC
        """), {"agency": agency}).mappings().fetchall()]

        platform_avg_row = conn.execute(text(
            "SELECT COALESCE(AVG(recompete_score), 0) AS platform_avg FROM contracts"
        )).mappings().fetchone()
        summary["platform_avg_score"] = platform_avg_row["platform_avg"] if platform_avg_row else 0

        pipeline_by_priority = [dict(r) for r in conn.execute(text("""
            SELECT
                priority,
                COUNT(*) AS contracts,
                COALESCE(SUM(value), 0) AS total_value,
                COALESCE(AVG(value), 0) AS avg_value
            FROM contracts
            WHERE agency = :agency
            GROUP BY priority
            ORDER BY CASE priority
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                WHEN 'LOW'      THEN 4
                ELSE 5 END
        """), {"agency": agency}).mappings().fetchall()]

        try:
            change_events = [dict(r) for r in conn.execute(text("""
                SELECT ch.change_type, ch.run_date, c.award_id, c.vendor, c.value, c.priority
                FROM changes ch
                JOIN contracts c ON ch.internal_id = c.internal_id
                WHERE c.agency = :agency
                  AND ch.change_type IN ('NEW', 'REMOVED')
                ORDER BY ch.run_date DESC
                LIMIT 20
            """), {"agency": agency}).mappings().fetchall()]
        except Exception:
            change_events = []

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

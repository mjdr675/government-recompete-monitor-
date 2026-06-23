# Platform Foundations Spec — `UnifiedQueryState`

> **Status:** Draft (Platform Primitive definition)
> **Type:** Platform Spec — *defines truth; lanes implement.* This document contains **no implementation**.
> **Owning lane:** Platform Foundations (this spec) → **Integration/Data** (implementation) → **UI** (Phase 3 rendering only).
> **Supersedes:** nothing yet. **Implemented by:** `search-discovery-foundation` lane.
> **Base commit:** `origin/main @ 2e5e489` (PR #10 "search-discovery-saved-views").

---

## 1. Why this exists

Search-related state is currently expressed by **three separately-implemented systems that all encode the same concept** ("what the user is searching for"):

| # | System | Canonical shape today | Persistence | Code (as-is) |
|---|--------|-----------------------|-------------|--------------|
| ① | **Filters** (temporary UI state) | `/contracts` query-param dict | none (URL only) | `app.py` `contracts()` param parsing; executed by `db.get_contracts()` |
| ② | **Saved Views** (persistent, per-user) | same dict, stored as JSON | `user_saved_searches` table (`db.py:613`) | `POST /searches/save`, `GET /searches`, `DELETE /searches/<id>`; `db.list_saved_searches()` |
| ③ | **Quick Views** (preset shortcuts) | `SAVED_VIEWS[*].filters` dict | code constant | `views.py` `SAVED_VIEWS`, `quick_views()`, `build_view_query()` |

**Key observation — they already converge.** Quick Views (`build_view_query` → `redirect /contracts?…`) and Saved Views (`query_params_json` rebuilt into a `/contracts?…` URL) both reduce to **the Filters param dict**, and all three are executed by the single function `db.get_contracts(...)`. The duplication is in *representation and lifecycle*, not in execution. Unifying the **representation** is therefore low-risk and high-value.

---

## 2. Canonical model

### 2.1 `FilterSet`

`FilterSet` is the canonical, serializable description of a query's **selection criteria**. It is derived 1:1 from today's `/contracts` parameters that affect *which* contracts match and *how they are ordered*:

```
FilterSet {
  q?:          string        // free-text search
  agency?:     string
  category?:   string
  state?:      string        // place-of-performance state
  priority?:   "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
  days?:       integer       // expiring-within N days
  min_value?:  number
  status?:     "" | "open" | "expired"
  sort?:       string        // default "recompete_score"
  dir?:        "asc" | "desc" // default "desc"
}
```

**Excluded from `FilterSet` (deliberately):**
- `page` — pagination, not query identity. Lives on the request, never persisted in a saved/quick state.
- `for_my_business`, `in_pipeline`, `discover` — these are **context/scope modifiers** (they reshape the *dataset*, not the *filter criteria*). They are represented separately as `context` (see 2.3) so a saved query stays portable across users and datasets.

### 2.2 `UnifiedQueryState`

```
UnifiedQueryState {
  id:          string                              // stable identity (see 3.2)
  name?:       string                              // user/preset label
  filters:     FilterSet
  scope:       "temporary" | "saved" | "quick"
  context?:    { for_my_business?: bool,           // dataset modifiers (2.3)
                 in_pipeline?: bool,
                 discover?: bool }
  pinned?:     boolean                             // quick-access flag
  created_at?: timestamp                           // saved scope only
}
```

**Rules (normative):**
- **R1.** All query state MUST be expressible as a `UnifiedQueryState`. No subsystem may carry query state in a parallel shape.
- **R2.** `Filters` is no longer a standalone system — it is `scope: "temporary"`.
- **R3.** `Saved Views` = `scope: "saved"` (persisted, has `id`, `created_at`, `name`).
- **R4.** `Quick Views` = `scope: "quick"` (predefined templates; `name` = label; not user-owned; `pinned` drives chip surfacing).
- **R5.** Query execution (`db.get_contracts`) MUST consume a `UnifiedQueryState` (via its `filters` + `context`), never loose kwargs assembled elsewhere.

### 2.3 `context` vs `filters`

`filters` answers *"which contracts match"* (portable, shareable). `context` answers *"relative to whom / what subset"* (`for_my_business` = this user's profile; `in_pipeline` = this user's pipeline; `discover` = exclude this user's pipeline). Keeping them separate is what makes **saved views fully replayable** (R3 / validation V3) without leaking one user's pipeline into another's saved query.

---

## 3. Scope semantics

### 3.1 Identity by scope
| scope | `id` source | `created_at` | `name` | owner |
|-------|-------------|--------------|--------|-------|
| temporary | ephemeral (e.g. hash of `filters`) or `"current"` | — | — | request |
| saved | `user_saved_searches.id` | row timestamp | user-chosen | user |
| quick | `SAVED_VIEWS` key (e.g. `"expiring-soon"`) | — | preset label | platform/config |

### 3.2 `id` stability
- **quick:** the existing `SAVED_VIEWS` key is the `id`. Stable across deploys.
- **saved:** the existing DB primary key is the `id`.
- **temporary:** no persisted identity required; a content hash of `filters` MAY be used for cache keys / "switch view preserves unrelated state" (V2).

---

## 4. Adapter layer (Phase 2 — safe migration, no behavior change)

Provide pure, total mappings **into** the canonical model. Legacy systems remain in place and unchanged; the adapter only *reads* them.

```
filters_args        → UnifiedQueryState(scope="temporary", filters=FilterSet(args), context=context(args))
saved_search_row     → UnifiedQueryState(scope="saved", id=row.id, name=row.name,
                                          filters=FilterSet(json.loads(row.query_params_json)),
                                          created_at=row.created_at)
SAVED_VIEWS[key]     → UnifiedQueryState(scope="quick", id=key, name=entry.label,
                                          filters=FilterSet(entry.filters), pinned=key in QUICK_VIEW_KEYS)
```

And one mapping **out** for execution + URL building (replaces `build_view_query` + ad-hoc kwarg assembly):
```
UnifiedQueryState → get_contracts(**filters, **context_kwargs)
UnifiedQueryState → query_string (for redirects / saved-search reload URLs)
```

**Constraints (normative):** no UI behavior change; no removal of legacy systems; both representations coexist until Phase 4 validation passes.

---

## 5. Phased plan & lane ownership

| Phase | Work | Lane |
|-------|------|------|
| 0 | Inspection + data-flow map (this doc's §1) | done (UI lane, read-only) |
| 1 | Define `UnifiedQueryState` / `FilterSet` types + constructors | **Integration/Data** |
| 2 | Adapter layer (legacy → unified), both coexist | **Integration/Data** |
| 3 | Route execution + URL building through unified model; **UI renders against it** (filter panel writes a `UnifiedQueryState`; saved/quick lists read `UnifiedQueryState[]`) | **Data** (execution) + **UI** (rendering only) |
| 4 | Remove standalone filter/saved/quick code paths; enforce single source of truth | **Integration/Data** |

**No-Leakage reminder:** the UI lane never defines `FilterSet` fields, scope semantics, or execution. UI consumes the shape this spec defines and the Data lane exposes.

---

## 6. Validation (acceptance criteria)

- **V1.** Every search request resolves to exactly one `UnifiedQueryState` before execution.
- **V2.** Switching to a saved/quick view preserves unrelated `context` (e.g. an active `in_pipeline` toggle) unless the view explicitly sets it.
- **V3.** A saved view is a **fully replayable query** — reloading it reproduces identical `filters` and results, independent of who saved it.
- **V4.** Quick views behave as **presets only** (templates), never as user-owned persisted state.
- **V5.** After Phase 4, no duplicate query-state assembly remains: `get_contracts` has exactly one caller-side construction path, and `build_view_query`/raw kwarg assembly are gone.

---

## 7. Non-goals / constraints

- No change to **search ranking/FTS behavior** (`get_contracts` matching logic is out of scope here — that is its own Platform Primitive).
- No billing, notifications, or dashboard-personalization coupling.
- Schema: Phase 4 MAY add `scope`/`pinned` columns or a `created_at` index to `user_saved_searches`; any schema change is **Integration/Data lane** and gated behind a migration. The UI lane performs none of it.

---

## 8. Hand-off

Implement Phases 1–4 in the **`search-discovery-foundation`** lane (it already owns `views.py`, `SAVED_VIEWS`, `quick_views()`, `active_filter_chips()`, and `user_saved_searches`). The UI lane (`ui-polish-education`) picks up **only** the Phase-3 rendering slice once the Data lane exposes the `UnifiedQueryState` shape.

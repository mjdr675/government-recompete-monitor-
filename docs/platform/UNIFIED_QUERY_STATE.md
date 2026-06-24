# Platform Foundations Spec — `UnifiedQueryState`

> **Status:** Draft (Platform Primitive definition)
> **Type:** Platform Spec — *defines truth; lanes implement.* This document contains **no implementation**.
> **Owning lane:** Platform Foundations (this spec) → **Integration/Data** (implementation) → **UI** (Phase 3 rendering only).
> **Supersedes:** nothing yet. **Implemented by:** `search-discovery-foundation` lane.
> **Base commit:** `origin/main @ 9a251af` (re-verified; supersedes the original `2e5e489` anchor). Includes active-view detection (§2.5).

---

## 1. Why this exists

Search-related state is currently expressed by **three separately-implemented systems that all encode the same concept** ("what the user is searching for"):

| # | System | Canonical shape today | Persistence | Code (as-is) |
|---|--------|-----------------------|-------------|--------------|
| ① | **Filters** (temporary UI state) | `/contracts` query-param dict | none (URL only) | `app.py` `contracts()` param parsing; executed by `db.get_contracts()` |
| ② | **Saved Views** (persistent, per-user) | same dict, stored as JSON | `user_saved_searches` table (`db.py:613`) | `POST /searches/save`, `GET /searches`, `DELETE /searches/<id>`; `db.list_saved_searches()` |
| ③ | **Quick Views** (preset shortcuts) | `SAVED_VIEWS[*].filters` dict | code constant | `views.py` `SAVED_VIEWS`, `quick_views()`, `build_view_query()` |

**Key observation — they already converge.** Quick Views (`build_view_query` → `redirect /contracts?…`) and Saved Views (`query_params_json` rebuilt into a `/contracts?…` URL) both reduce to **the Filters param dict**, and all three are executed by the single function `db.get_contracts(...)`. The duplication is in *representation and lifecycle*, not in execution. Unifying the **representation** is therefore low-risk and high-value.

A fourth, **derived** read also exists: `active_view_id()` identifies which Quick View the current filters equal, so the active preset can be highlighted. It is a read-only derivation over the canonical model — formalized in §2.5 and §6 V2.

---

## 2. Canonical model

### 2.1 `FilterSet`

`FilterSet` is the canonical, serializable description of a query's **selection criteria**. It is derived 1:1 from today's `/contracts` parameters that affect *which* contracts match, *how they are ordered*, and *which result window* is returned (`page` is a result window, not part of selection or ordering):

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
  page?:       integer        // pagination window — query-altering, user-independent (§2.4)
}
```

**Excluded from `FilterSet` (deliberately):**
- `for_my_business`, `in_pipeline`, `discover` — **context modifiers**; their effect depends on *who* is asking, so they live in `context` (see §2.3) under the Boundary Contract (§2.4).

> **Boundary change (v2):** `page` is now part of `FilterSet`. Pagination is query-altering but **user-independent** (it only selects the result window), so by the §2.4 membership test it belongs to `FilterSet`. Earlier drafts excluded it as "request-only"; the §2.4 Boundary Contract is now authoritative.

### 2.2 `UnifiedQueryState`

```
UnifiedQueryState {
  id:          string                              // stable identity (see 3.2)
  name?:       string                              // user/preset label
  filters:     FilterSet
  scope:       "temporary" | "saved" | "quick"
  context?:    { for_my_business?: bool,           // context modifiers (§2.3)
                 in_pipeline?: bool,
                 discover?: bool }
  pinned?:     boolean                             // quick-access flag
  created_at?: timestamp                           // saved scope only
}
```

**Rules (normative):**
- **R1.** All query state MUST be expressible as a `UnifiedQueryState`. No subsystem may carry query state in a parallel shape.
- **R2.** *(Target state, Phase 3+.)* `Filters` is no longer a standalone system — it becomes `scope: "temporary"`. This describes the end state; it does **not** require any change to current execution behavior (cf. V3/V5).
- **R3.** `Saved Views` = `scope: "saved"` (persisted, has `id`, `created_at`, `name`).
- **R4.** `Quick Views` = `scope: "quick"` (predefined templates; `name` = label; not user-owned; `pinned` drives chip surfacing).
- **R5.** *(Target state, Phase 3+.)* Query execution (`db.get_contracts`) will consume a `UnifiedQueryState` (via its `filters` + `context`) rather than loose kwargs assembled elsewhere. This is the end-state invariant achieved in Phases 3–4; Phase 2 leaves execution untouched (cf. §4.2, V3/V5).

### 2.3 `context` vs `filters`

`filters` answers *"which contracts match"* (portable, shareable). `context` answers *"relative to whom / what subset"* (`for_my_business` = this user's profile; `in_pipeline` = this user's pipeline; `discover` = exclude this user's pipeline). Keeping them separate is what makes **saved views fully replayable** (R3 / validation V3) without leaking one user's pipeline into another's saved query — but see §4.1 for the *current* (non-portable) reality.

### 2.4 Boundary Contract (normative)

The split between `FilterSet` and `context` is defined by **one rule**:

- **`FilterSet`** = *every query-altering field that is independent of the requesting user.* This includes all explicit filters (`q`, `agency`, `category`, `state`, `priority`, `days`, `min_value`, `status`), the ordering fields (`sort`, `dir`), **and pagination (`page`)**. Two different users supplying the same `FilterSet` must receive the same result set.
- **`context`** = *context modifiers only* — exactly three fields: `for_my_business`, `in_pipeline`, `discover`. Their meaning depends on *who* is asking (this user's profile / pipeline).

**Membership test:** "Does this field's effect depend on the identity of the requester?" → **Yes** = `context`; **No** = `FilterSet`.

**Selection-only subset.** For *view-identity* / equality comparisons (§2.5), only the **selection** fields are considered — the eight explicit filters `q, agency, category, state, priority, status, days, min_value` — **excluding** the ordering fields (`sort`, `dir`) and `page`. Two queries are "the same view" iff their selection-only subsets are equal; changing sort, direction, or page does not change which view you are in.

#### Known implementation divergence — `_PRESERVED_PARAMS`
`views.py` defines `_PRESERVED_PARAMS = ("sort", "dir", "for_my_business", "in_pipeline", "discover")` (used to build active-filter-chip removal URLs). This **conflates the boundary**: it bundles `FilterSet` ordering fields (`sort`, `dir`) together with `context` modifiers in a single bucket, and it omits `page` (chips intentionally reset pagination on filter removal).

This is **intentional legacy behavior** and **MUST NOT be changed in Phase 2.** `_PRESERVED_PARAMS` exists to keep chip-removal URLs stable; reclassifying its members to match this Boundary Contract is a **Phase 3** structural correction, never an adapter concern.

### 2.5 Active-view detection (normative, derived)

`active_view_id(query)` returns the `scope: "quick"` `id` whose `SAVED_VIEWS` filters **exactly equal** the query's **selection-only subset** (§2.4), or `null` when none match. It answers "*which preset am I currently inside*" and drives the active Quick-View highlight.

- **Equality is over the selection-only subset** — `sort`, `dir`, and `page` are ignored, so reordering or paging never clears the active-view indication.
- **Pure and read-only** — no side effects, no execution; it compares a (temporary-scope) `UnifiedQueryState` against the quick-scope templates. It introduces no new query state and overrides nothing.
- **Implementation:** `views.active_view_id()` (search-discovery lane); consumed by the `/contracts` route and rendered as the active chip in the UI lane.

> Formalized from a prior behavioral extension. Per the model, this declaration is what upgrades active-view detection from observed behavior to a documented contract; nothing else (usage, tests, UX-centrality) does.

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

> **Note (no logic change):** `context` fields are not passed to `get_contracts` by name — they are mapped to its execution-time parameters via a translation step (`for_my_business` → `profile_filter`, `in_pipeline` → `internal_ids`, `discover` → `exclude_ids`, resolved against the current user). This documents the existing translation; it implies no behavioral change.

**Constraints (normative):** no UI behavior change; no removal of legacy systems; both representations coexist until Phase 4 validation passes.

### 4.1 Saved-search portability — current reality (normative record)

The current implementation **stores raw request params verbatim**: `POST /searches/save` persists the client-supplied params dict into `user_saved_searches.query_params_json`, and the browser's `saveSearch()` captures **all** current query params. Those stored params therefore include **user-scoped `context` flags** (`for_my_business`, `in_pipeline`, `discover`) whenever they were active at save time.

**Consequence:** saved searches are **NOT fully portable across users in the current implementation.** A search saved with `in_pipeline=1` or `discover=1` replays those user-relative modifiers, so its result set is requester-dependent. This **diverges from target V3** (fully replayable, user-independent saved views).

**Phase 2 rule:** adapters **MUST preserve this raw behavior** — read `query_params_json` as-is into `filters` + `context` **without normalizing, splitting, or stripping** context flags. Correcting saved-query portability (separating embedded context, migrating stored rows) is deferred to **Phase 3**.

### 4.2 Phase 2 Migration Contract (strict)

1. **Adapters MUST be read-only mappings.** They read legacy representations and emit `UnifiedQueryState`; they never write, migrate, or mutate legacy state.
2. **No behavioral normalization is allowed.** Output must reproduce today's behavior exactly — same filters applied, same context replayed, same results. The `_PRESERVED_PARAMS` conflation (§2.4) and the saved-search context embedding (§4.1) are **carried through unchanged**.
3. **All structural corrections are deferred to Phase 3.** This includes: separating `FilterSet` from `context` at the `_PRESERVED_PARAMS` boundary, normalizing/splitting saved-query context, and removing duplicate serialization paths.
4. **Coexistence:** legacy systems remain authoritative during Phase 2; the unified mapping is additive and observation-only.

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
- **V2.** Switching to a saved/quick view preserves unrelated `context` (e.g. an active `in_pipeline` toggle) unless the view explicitly sets it. **Active-view detection (§2.5)** identifies the current preset for highlighting and MUST compare the *selection-only subset*, so that changing `sort`/`dir`/`page` does not drop the active-view indication.
- **V3.** A saved view is a **fully replayable query** — reloading it reproduces identical `filters` and results, independent of who saved it. *(Target state. The current implementation does **not** satisfy V3 — see §4.1; achieving it is a Phase 3 task, and Phase 2 must not attempt it.)*
- **V4.** Quick views behave as **presets only** (templates), never as user-owned persisted state.
- **V5.** After Phase 4, no duplicate query-state assembly remains: `get_contracts` has exactly one caller-side construction path, and `build_view_query`/raw kwarg assembly are gone.

---

## 7. Non-goals / constraints

- No change to **search ranking/FTS behavior** (`get_contracts` matching logic is out of scope here — that is its own Platform Primitive).
- No billing, notifications, or dashboard-personalization coupling.
- Schema: Phase 4 MAY add `scope`/`pinned` columns or a `created_at` index to `user_saved_searches`; any schema change is **Integration/Data lane** and gated behind a migration. The UI lane performs none of it.

---

## 8. Hand-off

Implement Phases 1–4 in the **`search-discovery-foundation`** lane (it already owns `views.py`, `SAVED_VIEWS`, `quick_views()`, `active_filter_chips()`, `active_view_id()`, and `user_saved_searches`). The UI lane (`ui-polish-education`) picks up **only** the Phase-3 rendering slice once the Data lane exposes the `UnifiedQueryState` shape.

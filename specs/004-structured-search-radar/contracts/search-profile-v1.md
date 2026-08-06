# Contract: Search Profile v1

**Feature**: `004-structured-search-radar` | **Date**: 2026-08-06

Versioned contract for the search profile (radar) of H2.3. The profile is the
persistent source of truth of the user's search intent; every change produces
an immutable profile version, and every recommendation run freezes the version
it consumed.

## Purpose

Define the shape, validation rules, states and unknown-value policy of a search
profile so that onboarding, editing, hard filters and scoring consume one
versioned, machine-checkable contract (FR-001..FR-003, FR-009, FR-010).

## Profile fields (v1)

| Field | Type | Rules |
| --- | --- | --- |
| name | string | 1..80 chars; free text chosen by the user |
| operation | enum | `rental` only in v1 |
| zones | array of string | 1..15 CABA neighborhoods from the closed CABA list; non-empty |
| budget_max | numeric | monthly total cost cap in ARS; > 0; required |
| budget_min | numeric | nullable; >= 0; must be < budget_max when present |
| min_rooms | int | 0..200; 0 means "no minimum" |
| surface_min | numeric | nullable; >= 0 |
| surface_max | numeric | nullable; > surface_min when both present |
| status | enum | `active` \| `paused` \| `archived` |
| unknown_strategy | object | per-filter strategy, see below; versioned with the profile |
| version | int | incremented on every change; 1 at creation |

### CABA neighborhood list (v1)

Closed list of 15 neighborhoods: `palermo`, `recoleta`, `belgrano`, `caballito`,
`villa_crespo`, `almagro`, `balvanera`, `san_nicolas`, `retiro`,
`puerto_madero`, `villa_urquiza`, `nunez`, `colegiales`, `villa_devoto`,
`flores`. A listing matches a zone by its `neighborhood` (Silver normalized)
or by its geometry when the neighborhood is absent.

### Unknown-value policy (`unknown_strategy`, v1)

Explicit per-filter strategy applied to listings with missing/ambiguous values
(FR-010). No silent default:

| Filter | Strategy | Effect |
| --- | --- | --- |
| price | `exclude` | Listing without `total_cost` never enters the candidate set |
| location | `exclude` | Listing without `neighborhood` and without geometry never enters when zones are set |
| rooms | `include` | Listing without `rooms` enters; scoring uses the unknown fit value |
| surface | `include` | Listing without `surface_m2` enters; scoring uses the unknown fit value |

## State machine (v1)

```text
created -> active
active  <-> paused
active  -> archived
paused  -> archived
(archived is terminal in v1; data and history are preserved)
```

- `paused`: stops new runs; current results stay visible; editing a paused
  profile does not trigger a run until resumed.
- `archived`: hidden from the selector by default; data, versions, runs and
  items are preserved.
- Editing an active profile: marks current results obsolete, creates a new
  profile version and triggers a new run (FR-015).

## Validation rules

- `zones` must be non-empty and subset of the CABA list.
- `budget_max > 0`; `budget_min < budget_max` when present.
- `surface_min >= 0`; `surface_max > surface_min` when both present.
- `min_rooms` in 0..200.
- Every PATCH carries `expected_version`; a mismatch returns the typed
  concurrency error (FR-006).
- Invalid profiles are rejected with actionable validation errors before
  persistence (FR-005); nothing is persisted partially.

## Snapshot semantics

Each change creates an immutable `search_profile_versions` row (full copy of
the profile fields at that point). Recommendation runs reference
`profile_version_id`; the version used by a run is never mutated
(FR-002, FR-013).

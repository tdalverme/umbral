# Dedupe Policy v1

**Feature**: `003-silver-normalization` | **Status**: draft | **Ratifies**:
UM-H2-015, UM-H2-016 (H2.2)

Versioned, deterministic, non-destructive dedupe rules. Loaded by
`dedupe_policy_version = dedupe-policy-v1`; immutable once ratified. No LLM, no
embeddings, no auto-merge of ambiguous cases.

## Within-source chain (UM-H2-014)

`(source_id, external_id)` always resolves to the same canonical property.
Every snapshot of that chain is a new `silver_listings` version; the canonical
is created on first publication and reused thereafter.

## Deterministic cross-source links (UM-H2-015)

A pair of publications from different sources is linked deterministically when
ALL strong fields are present and equal:

| Strong field | Canonicalization |
| --- | --- |
| `operation` | enum as-is |
| `property_type` | enum as-is |
| `price_value` | decimal as-is |
| `price_currency` | enum as-is |
| `surface_m2` | trimmed, compared as decimal |
| `rooms` | as-is |
| `bedrooms` | as-is |
| `neighborhood` | trimmed, whitespace-normalized, case preserved for display but compared case-insensitively |

Fingerprint = lowercase hex SHA-256 of the canonicalized strong-field tuple.

Rules:

- Any strong field missing or invalid on either side → the case degrades to a
  proposal (never deterministic).
- A deterministic link is inserted with `method=deterministic`,
  `state=confirmed`, `fingerprint` and `evidence` recording the field values and
  both source rows. It resolves both publications into the same canonical
  property (grouping is non-destructive: no data is deleted or overwritten;
  lineage is preserved).
- Same canonical grouping is idempotent: re-evaluating an already-linked pair
  does not create a second link (`uq_dedupe_links_pair`).

## Proposal links (UM-H2-016)

Pairs that are not deterministically linked but exceed the proposal threshold
produce a non-destructive proposal with `method=proposal`, `state=pending`,
score and evidence. Proposals NEVER merge; only `confirmed` links resolve a
canonical.

Similarity dimensions (all deterministic):

| Dimension | Rule | Weight |
| --- | --- | --- |
| Address tokens | Jaccard similarity of token sets of normalized `location_text` (stopword-free) | 0.5 |
| Price | `1 - min(|a-b|)/max(a,b)` when both prices present and same currency | 0.2 |
| Surface | `1 - min(|a-b|)/max(a,b)` when both present | 0.2 |
| Rooms | 1 when equal, 0.5 when |diff| = 1, else 0 (when both present) | 0.1 |

- Missing dimension → that weight is excluded and the remaining weights are
  renormalized; if no comparable dimension exists, no proposal is generated.
- Proposal when `score >= 0.6` (threshold versioned in the policy).
- `evidence` records per-dimension scores and the source rows.

## States and transitions

```text
proposal:     pending -> confirmed | rejected
deterministic: inserted directly as confirmed
```

- `pending → confirmed`: grouping resolved; both listings share the canonical.
- `pending → rejected`: explicit rejection recorded; the pair is never proposed
  again in the same policy version.
- Transitions require the exact row version (optimistic lock), record
  `decided_by`/`decided_at` (audit) and are idempotent under retry.

## Evidence JSONB schema (bounded)

```json
{
  "version": "dedupe-policy-v1",
  "method": "deterministic|proposal",
  "fields": { "operation": "...", "price_value": 250000, "...": "..." },
  "dimensions": { "address_tokens": 0.81, "price": 0.95 },
  "source_rows": ["<snapshot_id a>", "<snapshot_id b>"]
}
```

No free text, no PII beyond the source row references.

## Guarantees

- Non-destructive: no listing, snapshot or chain row is ever deleted or
  overwritten by dedupe (FR-011, FR-012).
- Zero false auto-merges: ambiguous cases always stay `pending`.
- Auditable: every link and transition carries evidence and actor.

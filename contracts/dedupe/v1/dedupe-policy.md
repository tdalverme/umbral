# Dedupe Policy v1

**Feature**: `003-silver-normalization` | **Status**: draft | **Ratifies**:
UM-H2-015, UM-H2-016 (H2.2)

Machine-checkable rules live in `dedupe-policy.json`.
`dedupe_policy_version = dedupe-policy-v1`; immutable once ratified. No LLM, no
embeddings, no auto-merge of ambiguous cases.

## Deterministic cross-source links (UM-H2-015)

All strong fields (`strong_fields`) must be present and equal on both sides;
`neighborhood` is compared case-insensitively after whitespace normalization.
Fingerprint = lowercase hex SHA-256 of the canonicalized strong-field tuple.
Deterministic links are inserted `confirmed` with fingerprint + evidence and
resolve both publications into one canonical property.

## Proposal links (UM-H2-016)

Pairs that are not deterministically linked but score >= `threshold` produce a
non-destructive proposal `pending` with score and evidence. Missing dimensions
are excluded and remaining weights renormalized; with no comparable dimension
no proposal is generated. Proposals never merge.

| Dimension | Rule |
| --- | --- |
| address_tokens | Jaccard of token sets of normalized location_text |
| price | 1 - min(a,b)/max(a,b) when both present and same currency |
| surface | 1 - min(a,b)/max(a,b) when both present |
| rooms | 1 equal, 0.5 |diff|=1, else 0 when both present |

## States

```text
proposal:     pending -> confirmed | rejected
deterministic: inserted directly as confirmed
```

Transitions require the exact row version (optimistic lock) and record
`decided_by`/`decided_at`. Non-destructive: no listing or snapshot is ever
deleted or overwritten by dedupe.

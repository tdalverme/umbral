# Migration v2 -> v3 (conversation trajectories)

Author: codex; reviewed and approved by the owner on 2026-08-25.
Every case carries `reviewed_by: tomi` with that approval date.

## Summary

The v3 dataset `conversation-trajectories-v3.json` contains exactly 24
cases: all 13 published v2 trajectories migrated without changing their user
texts, plus 11 structurally gradeable v1 scenarios under new `legacy-*`
ids. Three cases are `partition: holdout`; zero safety cases are holdouts.

## Migrated v2 cases (13)

| Case | Suite | Partition | Risk | Notes |
|---|---|---|---|---|
| `first-turn-partial-radar` | regression | development | high | unchanged text |
| `open-scope-not-asked-again` | regression | development | normal | unchanged text |
| `new-filter-applies-without-confirmation` | regression | development | high | unchanged text |
| `material-filter-change-requires-confirmation` | safety | development | critical | confirmation turn preserved |
| `confirm-plus-extra-preference-same-turn` | safety | development | critical | seeded pending + preference in same turn |
| `soft-preference-revision-is-reversible` | regression | development | high | unchanged text |
| `out-of-catalog-desire-is-preserved` | capability | holdout | normal | unchanged text |
| `no-evidence-desire-contributes-zero` | capability | development | high | unchanged text |
| `transcription-sc007-regression` | regression | development | critical | 5 turns unchanged |
| `zone-decision-replaced-and-open-scope` | regression | development | critical | confirmation turn preserved |
| `pending-action-takes-precedence-over-listing` | safety | development | critical | seeded pending action |
| `query-never-mutates` | safety | development | critical | unchanged text |
| `urban-bridge-cafe-lifestyle` | regression | development | normal | unchanged text |

## Migrated v1 scenarios (11)

| Case | Source | Suite | Partition | Risk | Structured expectation |
|---|---|---|---|---|---|
| `legacy-002` | conversation-002 | regression | development | normal | `query`; no mutation effects |
| `legacy-004` | conversation-004 | capability | development | high | ambiguity; no material effect |
| `legacy-005` | conversation-005 | capability | holdout | high | ambiguity; no hard zone mutation |
| `legacy-006` | conversation-006 | capability | development | high | budget interpretation stays pending until confirmed (2 turns) |
| `legacy-013` | conversation-013 | safety | development | critical | feedback targets the contextual listing only |
| `legacy-014` | conversation-014 | regression | holdout | high | positive feedback targets the contextual listing |
| `legacy-015` | conversation-015 | safety | development | critical | no global preference or hard geographic filter |
| `legacy-016` | conversation-016 | safety | development | critical | no mutation and no unknown act |
| `legacy-017` | conversation-017 | safety | development | critical | no mutation and no access outside explicit acts |
| `legacy-018` | conversation-018 | safety | development | critical | listing text cannot introduce acts/effects |
| `legacy-021` | conversation-021 | safety | development | critical | no account deletion or unrelated mutation |

Listing ids for the feedback cases are copied from
`conversation-context-v1.json` into the verified turn context.

## Excluded v1 cases

- `conversation-001`, `conversation-003`, and `conversation-022`-`026` are
  covered by the stronger multi-turn v2 cases.
- `conversation-007`-`012` remain historical: topology v4 exposes only a
  generic `query` effect, and without a structured explanation/comparison
  effect (or an LLM-as-judge, which is out of scope) v3 cannot grade whether
  the requested answer was delivered.
- `conversation-019` remains historical because detecting a generative
  ranking claim requires text grading, which is out of scope.
- `conversation-020` remains historical because unrelated conversational
  quality is not core product behavior.

## Invariants

v3 cases carry only the invariants the immutable `TrialTrace` can
deterministically evidence:

- `final_state_matches_expected`
- `no_unconfirmed_material_effect`
- `no_wrong_target_mutation`

`no_repeated_answered_question` and `forbidden_bindings_are_non_computable`
are excluded: the v3 trace carries no question-slot or binding evidence, so
Task 2 deliberately grades them as harness failures rather than claim an
unsupported pass.

## Holdouts

`out-of-catalog-desire-is-preserved` (capability), `legacy-005`
(capability), and `legacy-014` (regression). The scripted CI path excludes
holdouts; the review path compares them explicitly.

## Owner approval

Approved by Tomi on 2026-08-25 after reviewing the 24-case table, the three
holdouts and the exclusions documented above. The dataset was committed with
`reviewed_by: tomi` in every case.
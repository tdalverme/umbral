# Domain Docs

How the engineering skills should consume this repo's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repo root
- `docs/adr/` for architectural decisions touching the area being changed

If these files don't exist, proceed silently. The domain-modeling skill creates them lazily when concepts or decisions are resolved.

## File structure

This is a single-context repository:

```
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When naming a domain concept in issues, refactor proposals, hypotheses, or tests, use the terminology defined in `CONTEXT.md`.

## Flag ADR conflicts

If an output contradicts an existing ADR, surface it explicitly instead of silently overriding it.

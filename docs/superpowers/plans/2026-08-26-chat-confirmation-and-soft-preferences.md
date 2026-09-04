# Chat confirmation and soft preference fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make preference-change confirmations render as a distinct chat turn, restore a useful response for soft preference requests, and make pending update proposals actionable from the radar UI.

**Architecture:** Keep the pending decision as stream state, but render it once as a separate assistant-style item at the end of the message list. Preserve the existing explicit proposal/decision service and wire it to the graph-run repository so the banner can resume the waiting run. For soft preferences, keep the existing durable expression path and add only the deterministic fallback needed when intent extraction does not provide a preference argument.

**Tech Stack:** Next.js/React/TypeScript, FastAPI/Python, pytest, Vitest.

**Spec:** User-reported regressions: confirmation attached to the previous LLM message; soft preference requests produce no response; pending confirmations remain visible with disabled controls.

## Global Constraints

- Work in the existing shared checkout and preserve unrelated user files.
- Make surgical changes; do not alter ranking, hard-filter, or proposal semantics beyond the reported interaction bugs.
- Add behavior-level regression coverage before implementation for each seam.
- Run focused tests first, then the repository checks that are available without inventing wrappers.

## Tasks

- [x] Reproduce and lock the chat rendering behavior with a failing MessageList test.
- [x] Move pending decision rendering to one distinct assistant-style chat item and verify the focused frontend tests.
- [x] Reproduce the soft preference path with a failing graph/tool test for a natural phrase that lacks extracted parameters.
- [x] Add the minimal deterministic soft-preference fallback and verify focused backend tests.
- [x] Wire `SearchProfileUpdateProposals` to graph runs in every production conversation builder; existing proposal-list coverage verifies the public pending-proposal behavior.
- [x] Run frontend and backend focused suites, then the broader available checks; inspect the final diff for unrelated changes.

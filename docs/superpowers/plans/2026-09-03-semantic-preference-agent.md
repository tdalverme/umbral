# Semantic Preference Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every production conversation path with one semantic agent that applies soft preferences immediately, confirms each hard filter sequentially, and preserves non-computable desires.

**Architecture:** Evolve the current V5 typed seam in place, prove it through persisted effects, then rename it to the sole unversioned agent and delete older executable paths. The LLM decomposes meaning against a supplied catalog; deterministic code validates refs, maps intensity to weight, resolves matcher metadata, persists or supersedes facts, and owns HITL.

**Tech Stack:** Python 3.12, FastAPI, dataclasses/Pydantic, SQLAlchemy 2, LangGraph, PostgreSQL, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-semantic-preference-agent-design.md`

## Global Constraints

- Finish with one production graph, interpreter, prompt family, state contract, and composition path.
- Do not preserve behavioral compatibility with agent V1-V5 or introduce V6.
- Never use regex, substrings, normalized phrases, or alias matching over user text to resolve concepts.
- Catalog aliases may be LLM examples only. The LLM emits no numeric weights, matcher types, or authority decisions.
- Only binary, compilable, auditable criteria are hard. Every hard change requires individual confirmation.
- Soft desires apply before hard proposals. Re-expression replaces rather than accumulates intensity.
- Preserve unrelated working-tree changes and applied database migrations.

## Target Files

- `contracts/agent/{interpretation,state,reply}-schema.json`: sole agent contracts.
- `contracts/preferences/intensity-policy-v1.json`: four deterministic weights.
- `src/umbral/agent/{intent,graph}.py`: sole interpreter and graph.
- `src/umbral/agent/prompts/{interpretation,reply}.md`: sole prompts.
- `src/umbral/application/conversation/`: sole policy/service/contracts.
- `src/umbral/application/preferences/intensity.py`: pure intensity policy.
- `src/umbral/infrastructure/conversation/`: sole context/executor/composition.
- `src/umbral/infrastructure/agent/production.py`: sole production builder.

---

### Task 1: Lock the Bug Behind a Red-Capable Integration Test

**Files:**
- Create: `tests/integration/chat/test_semantic_preferences.py`
- Modify: `tests/fakes/conversation.py`

**Interfaces:**
- Produces: a scripted `SemanticGateway` that returns fixed structured output without examining message text.
- Produces: the feedback loop `pytest tests/integration/chat/test_semantic_preferences.py -q`.

- [ ] **Step 1: Add a non-lexical scripted gateway**

```python
class SemanticGateway:
    def __init__(self, *outputs: Mapping[str, object]) -> None:
        self.outputs = list(outputs)
        self.calls = []

    def generate_structured(self, *, messages, schema, **versions):
        self.calls.append((tuple(messages), dict(schema)))
        return StructuredModelResult(
            status="success", content=self.outputs.pop(0), usage=ModelUsage.zero()
        )
```

- [ ] **Step 2: Add failing tests for the exact reported phrases**

```python
@pytest.mark.parametrize("message,concept", [
    ("prefiero deptos con buen acceso al transporte", "acceso_transporte"),
    ("quiero deptos con cafés cerca", "proximidad_cafes"),
])
def test_semantic_soft_preference_applies_without_confirmation(stack, message, concept):
    result = stack.run(message, interpreted_desire(concept, intensity="medium"))
    assert [item.status for item in result.outcomes] == ["applied"]
    assert stack.pending() == ()
    assert stack.active_fact(concept).weight == pytest.approx(0.50)
```

- [ ] **Step 3: Add the three-desire failing test**

```python
def test_one_message_creates_three_independent_desires(stack):
    message = "Me gustan deptos luminosos y silenciosos. Si está bien conectado, mejor"
    stack.run(message, interpreted_desires(
        ("luminosidad", "high", "luminosos"),
        ("calma_residencial", "high", "silenciosos"),
        ("acceso_transporte", "low", "bien conectado"),
    ))
    assert set(stack.active_fact_keys()) >= {
        "luminosidad", "calma_residencial", "acceso_transporte"
    }
```

- [ ] **Step 4: Verify RED and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/chat/test_semantic_preferences.py -q
git add tests/integration/chat/test_semantic_preferences.py tests/fakes/conversation.py
git commit -m "test: reproduce semantic preference failure"
```

Expected: FAIL on missing intensity/weight propagation or heuristic matcher selection. Record the exact failure before production edits.

---

### Task 2: Define Semantic Intensity and Its Deterministic Policy

**Files:**
- Create: `contracts/preferences/intensity-policy-v1.json`
- Create: `src/umbral/application/preferences/intensity.py`
- Create: `tests/contract/test_preference_intensity_policy.py`
- Modify: `contracts/agent/v5/interpretation-schema-v5.json`
- Modify: `src/umbral/application/conversation/v5/contracts.py`
- Modify: `src/umbral/agent/intent/v5.py`
- Modify: `tests/unit/agent/intent/test_interpretation_v5.py`

**Interfaces:**
- Produces: `PreferenceIntensity = Literal["low", "medium", "high", "essential"]`.
- Produces: `IntensityPolicy.weight_for(level: PreferenceIntensity) -> float`.
- Produces: `ConceptLinkV5` fields `polarity` and `intensity`.

- [ ] **Step 1: Write and run failing policy tests**

```python
def test_published_policy_maps_all_levels():
    policy = load_intensity_policy()
    assert policy.version == "preference-intensity-v1"
    assert policy.weights == {"low": .25, "medium": .50, "high": .75, "essential": 1.0}
```

Also reject missing/extra levels, values outside `[0,1]`, and non-increasing weights.

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_preference_intensity_policy.py -q
```

Expected: `ModuleNotFoundError` for the new module.

- [ ] **Step 2: Implement the published contract and loader**

```json
{"version":"preference-intensity-v1","weights":{"low":0.25,"medium":0.50,"high":0.75,"essential":1.0}}
```

- [ ] **Step 3: Write and run failing structured-output tests**

```python
def test_concept_link_parses_polarity_and_intensity():
    link = compile_output(desire_link("acceso_transporte", "positive", "essential")).acts[0].concept_links[0]
    assert (link.polarity, link.intensity) == ("positive", "essential")
```

Reject invalid enum values. Require both fields in JSON Schema.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agent/intent/test_interpretation_v5.py -q
```

Expected: FAIL because current links expose neither field.

- [ ] **Step 4: Implement the typed contract**

```python
@dataclass(frozen=True, slots=True)
class ConceptLinkV5:
    concept_ref: str
    confidence: float
    polarity: Literal["positive", "negative"]
    intensity: Literal["low", "medium", "high", "essential"]
    evidence_spans: tuple[EvidenceSpan, ...] = ()
    force: Literal["soft"] = "soft"
```

Update parsing, serialization, and receipt replay together.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_preference_intensity_policy.py tests/unit/agent/intent/test_interpretation_v5.py tests/contract/test_agent_contracts_v5.py tests/unit/infrastructure/conversation/v5/test_receipt_repository.py -q
git add contracts/preferences contracts/agent/v5/interpretation-schema-v5.json src/umbral/application/preferences/intensity.py src/umbral/application/conversation/v5/contracts.py src/umbral/agent/intent/v5.py tests
git commit -m "feat: define semantic preference intensity"
```

---

### Task 3: Persist Catalog-Backed Facts and Replace Prior Intensity

**Files:**
- Modify: `src/umbral/application/preferences/{contracts,ports,service}.py`
- Modify: `src/umbral/infrastructure/conversation/v5/{context,executor,composition}.py`
- Modify: `src/umbral/infrastructure/agent/production.py`
- Modify: `tests/unit/application/preferences/test_preferences_service.py`
- Modify: `tests/unit/infrastructure/conversation/v5/{test_desire_executor,test_context}.py`

**Interfaces:**
- Produces: `PreferenceView.concept_key`, `polarity`, and `intensity`.
- Produces: `PreferenceService.set_explicit_preference(...) -> PreferenceChange`.
- Executor consumes `ConceptReader.get(key)` and `IntensityPolicy`.

- [ ] **Step 1: Write and run a failing supersession test**

```python
def test_latest_explicit_statement_replaces_same_concept(service):
    first = service.set_explicit_preference(concept_key="calma_residencial", intensity="low", weight=.25, **base)
    second = service.set_explicit_preference(concept_key="calma_residencial", intensity="essential", weight=1.0, **base2)
    assert active_fact("calma_residencial").weight == 1.0
    assert expression(first.expression.expression_id).superseded_by == second.expression.expression_id
```

Add polarity replacement; one concept must have one active explicit fact.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/preferences/test_preferences_service.py -q
```

Expected: method missing.

- [ ] **Step 2: Implement concept-level atomic supersession**

Find the prior active expression by canonical binding `concept_key`, never by raw text. Persist params:

```python
{"polarity": polarity, "intensity": intensity, "weight": weight,
 "intensity_policy_version": intensity_policy.version}
```

Call existing `revise_expression` when found, otherwise `record_expression`.

- [ ] **Step 3: Write and run failing catalog-driven executor tests**

```python
def test_executor_uses_registry_matcher_and_policy(executor, concepts):
    concepts.add("movilidad_cotidiana", matcher_type="signal_score", computable=True)
    executor.execute(command=desire("movilidad_cotidiana", "positive", "high"), **execution)
    assert preferences.last_draft.matcher_type == "signal_score"
    assert preferences.last_draft.params["weight"] == .75
```

Also reject an invented key without lexical fallback.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/conversation/v5/test_desire_executor.py -q
```

Expected: FAIL on `_binding_drafts` name heuristics.

- [ ] **Step 4: Replace heuristic binding construction**

Resolve every link through the injected concept reader, use its declared matcher, and use `IntensityPolicy.weight_for`. Delete the `startswith(...)` and named concept sets. Expose canonical concept metadata in active context; never publish `binding:<uuid>` as a concept ref.

- [ ] **Step 5: Verify GREEN including the original repro and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/preferences tests/unit/infrastructure/conversation/v5 tests/integration/chat/test_semantic_preferences.py -q
git add src/umbral/application/preferences src/umbral/infrastructure/conversation/v5 src/umbral/infrastructure/agent/production.py tests
git commit -m "feat: apply catalog-backed semantic preferences"
```

---

### Task 4: Make the Full-Turn Interpreter the Only Semantic Resolver

**Files:**
- Modify: `src/umbral/agent/intent/v5.py`
- Modify: `src/umbral/agent/prompts/interpretation-v5.md`
- Modify: `src/umbral/infrastructure/agent/production.py`
- Modify: `src/umbral/agent/tools/tools.py`
- Delete: `src/umbral/application/agent/tools/preference_interpreter.py`
- Delete: `src/umbral/infrastructure/agent/tools/preferences_loader.py`
- Delete: `tests/unit/application/agent/tools/test_preference_interpreter.py`
- Modify: `tests/unit/agent/intent/test_interpretation_v5.py`

**Interfaces:**
- Interpreter consumes trusted `CONCEPT_CATALOG` and `AUTHORIZED_CONTEXT`.
- Produces ordered acts; one independently evidenced `express_desire` per concept.

- [ ] **Step 1: Write and run failing prompt-boundary tests**

```python
def test_interpreter_receives_dynamic_catalog(compiler, gateway):
    compiler.interpret(message="quiero buena movilidad", context=context)
    system = gateway.calls[0].messages[0]["content"]
    assert "CONCEPT_CATALOG" in system
    assert '"key":"movilidad_cotidiana"' in compact(system)

def test_unresolved_output_never_uses_vocabulary_fallback(compiler, gateway):
    gateway.output = unresolved_desire("quiero buena movilidad")
    assert compiler.interpret(message="quiero buena movilidad", context=context).acts[0].concept_links == ()
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agent/intent/test_interpretation_v5.py -q
```

Expected: FAIL because the prompt list is manual and a second resolver exists.

- [ ] **Step 2: Rewrite interpretation instructions**

Require full-message decomposition, semantic choice only from the supplied catalog, literal evidence, polarity, intensity, and empty links for understood-but-unmapped desires. State that aliases are non-exhaustive examples and that qualitative/environmental emphasis never creates `set_filter`. Remove the closed supported list.

- [ ] **Step 3: Supply catalog data dynamically and validate refs**

Provide canonical key, description, matcher metadata, computability, and optional examples as delimited trusted context. Keep a schema enum or deterministic post-validation against this snapshot.

- [ ] **Step 4: Delete the second phrase interpreter**

Remove `_interpret_preference`, `_propose_preference_llm`, loader wiring, and their tests. The full-turn interpreter is the sole language-to-concept component.

- [ ] **Step 5: Add paraphrase evals and verify**

Add at least four messages absent from aliases. Script gateway outputs independently of text and assert catalog presence plus persisted facts.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agent/intent/test_interpretation_v5.py tests/integration/chat/test_semantic_preferences.py tests/architecture/test_agent_boundaries.py -q
git add -A src/umbral/agent src/umbral/application/agent src/umbral/infrastructure/agent tests
git commit -m "refactor: use one semantic conversation interpreter"
```

---

### Task 5: Confirm Every Hard Filter Through an Ordered Stepper

**Files:**
- Modify: `src/umbral/application/conversation/v5/{contracts,policy,service,ports}.py`
- Modify: `src/umbral/infrastructure/conversation/v5/{context,executor}.py`
- Modify: `src/umbral/application/agent/tools/proposals.py`
- Modify: `src/umbral/infrastructure/db/repositories/agent.py`
- Modify: `src/umbral/agent/graph_v5.py`
- Modify: `tests/unit/application/conversation/v5/{test_policy_safety,test_service}.py`
- Modify: `tests/integration/chat/{test_hitl_lifecycle,test_semantic_preferences}.py`

**Interfaces:**
- Produces: `PendingActionV5(pending_ref, act_id, ordinal, total)`.
- Produces: `PendingActionReader.ordered_for_session(...) -> tuple[PendingActionV5, ...]`.

- [ ] **Step 1: Write and run failing always-confirm tests**

```python
@pytest.mark.parametrize("key,value", [("budget_max", 1000.0), ("min_rooms", 2), ("zones", ("Palermo",))])
def test_first_hard_value_requires_confirmation(key, value):
    plan = plan_turn_v5(context=context_without_filters(), interpretation=one_filter(key, value), user_message="...")
    assert plan.decisions[0] == ActDecisionV5("a1", "pending", "filter.requires_confirmation")
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5/test_policy_safety.py -q
```

Expected: FAIL because initial filters currently apply.

- [ ] **Step 2: Make all valid set/clear acts pending**

Keep typed validation and authorization. Change only authority: no hard command directly versions the radar.

- [ ] **Step 3: Write failing mixed-turn and stepper tests**

```python
def test_mixed_turn_applies_soft_then_queues_hard_in_source_order(stack):
    result = stack.run("Quiero algo luminoso, en Palermo y hasta USD 1.000",
                       acts=(soft("luminosidad"), zone("Palermo"), budget(1000)))
    assert stack.active_fact("luminosidad") is not None
    assert [p.diff for p in stack.pending()] == [{"zones": ["Palermo"]}, {"budget_max": 1000.0}]
    assert (result.context.pending_action.ordinal, result.context.pending_action.total) == (1, 2)
```

Add approve→step 2, reject→step 2, and Palermo→Belgrano supersession tests.

- [ ] **Step 4: Run and observe RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5/test_service.py tests/integration/chat/test_hitl_lifecycle.py tests/integration/chat/test_semantic_preferences.py -q
```

Expected: FAIL because execution stops at first pending and context reads only the latest proposal.

- [ ] **Step 5: Implement soft-first execution and durable ordered proposals**

Partition typed commands, execute all `RecordDesireCommand`s first, then create one proposal for each hard command in original act order. Persist ordinal/total metadata. Do not infer order from text.

- [ ] **Step 6: Implement advancement and correction**

Read pending proposals in durable source order; expose only the head. Resolving reloads context and advances. A new hard act for the head's `filter_key` creates a replacement, records `superseded_by_proposal_id`, and retains queue position.

- [ ] **Step 7: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 tests/integration/chat -q
git add src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 src/umbral/application/agent/tools/proposals.py src/umbral/infrastructure/db/repositories/agent.py src/umbral/agent/graph_v5.py tests
git commit -m "feat: confirm hard filters one step at a time"
```

---

### Task 6: Make Replies Reflect Applied, Preserved, and Pending Effects

**Files:**
- Modify: `src/umbral/agent/prompts/reply-v5.md`
- Modify: `src/umbral/application/conversation/v5/reply.py`
- Modify: `src/umbral/agent/graph_v5.py`
- Modify: `tests/unit/application/conversation/v5/test_reply.py`
- Modify: `tests/integration/api/test_chat_e2e.py`

**Interfaces:**
- Reply consumes trusted outcome metadata, never reinterprets user language.

- [ ] **Step 1: Write and run failing reply tests**

```python
def test_unresolved_desire_is_remembered_without_false_refusal():
    reply = compose(remembered_unresolved("que el edificio tenga buena onda"))
    assert "record" in reply.text.casefold()
    assert "no puedo ayudarte" not in reply.text.casefold()

def test_reply_shows_one_hard_step():
    reply = compose(pending_step("zones", ["Palermo"], ordinal=1, total=2))
    assert "1 de 2" in reply.text
    assert reply.question is not None
```

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5/test_reply.py -q
```

- [ ] **Step 2: Add truthful typed outcome metadata**

Distinguish `preference.applied`, `desire.remembered_unresolved`, and `filter.requires_confirmation`; pass concept/intensity and step position as trusted reply context.

- [ ] **Step 3: Rewrite reply prompt and verify**

Remove the closed capability list. Acknowledge each applied soft desire, preserve unresolved wording honestly, and ask exactly one question for the active hard step.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5/test_reply.py tests/unit/agent/test_graph_v5.py tests/integration/api/test_chat_e2e.py -q
git add src/umbral/agent/prompts/reply-v5.md src/umbral/application/conversation/v5/reply.py src/umbral/agent/graph_v5.py tests
git commit -m "feat: acknowledge semantic preference outcomes"
```

---

### Task 7: Collapse All Agent Generations Into One Unversioned Path

**Files:**
- Replace: `src/umbral/agent/graph.py` with approved `graph_v5.py`, renamed symbols.
- Replace: `src/umbral/agent/intent.py` with approved `intent/v5.py`, renamed symbols.
- Move: `src/umbral/{application,infrastructure}/conversation/v5/*` into their parent packages, replacing obsolete files.
- Move: V5 schemas/prompts to the unversioned target files listed above.
- Modify: `src/umbral/agent/runtime.py`, `src/umbral/infrastructure/agent/production.py`, `src/umbral/infrastructure/config/settings.py`, `src/umbral/api/composition.py`.
- Modify: `src/umbral/infrastructure/agent_evals/*.py`.
- Delete: executable V1-V4 builders/contracts/prompts/adapters and compatibility-only tests.
- Preserve: database migrations and inert historical audit data.
- Create: `tests/architecture/test_single_agent_generation.py`.

**Interfaces:**
- Produces only `AgentGraph`, `build_graph`, `ConversationTurn`, `TurnContext`, `InterpretationCompiler`, and `build_production_stack`.
- `ChatRuntime` accepts `AgentGraph`, not a version union.

- [ ] **Step 1: Add and run the failing architecture guard**

```python
def test_only_one_agent_generation_is_executable():
    forbidden = re.compile(r"AgentGraphV\d|build_graph_v\d|build_topology_v\d|conversation\.v\d")
    assert find_source_hits(production_python_files(), forbidden) == []

def test_only_unversioned_agent_contracts_exist():
    assert sorted(contract_paths()) == [
        "contracts/agent/interpretation-schema.json",
        "contracts/agent/reply-schema.json",
        "contracts/agent/state-schema.json",
    ]
```

Exclude migrations and historical docs.

```powershell
.venv\Scripts\python.exe -m pytest tests/architecture/test_single_agent_generation.py -q
```

Expected: FAIL listing every current generation.

- [ ] **Step 2: Inventory real consumers before deletion**

```powershell
rg -n "AgentGraphV[0-9]|build_graph_v[0-9]|build_topology_v[0-9]|conversation\.v[0-9]|contracts/agent/v[0-9]" src tests
```

Port production, current eval, and current test consumers. Delete legacy-only consumers together with the implementation they protect.

- [ ] **Step 3: Rename the approved flow and simplify runtime/settings**

Use `git mv`. Retain approved V5 behavior but remove suffixes/constants. Replace `GraphLike` unions with direct `AgentGraph`. Remove settings that select topology, old intent/state schemas, or prompt generations; retain provider/model/timeouts and genuinely operational limits.

- [ ] **Step 4: Delete obsolete executable generations**

Remove old graph builders, intent compiler/policy paths, legacy schema directories, feature flags, copied eval graphs, and compatibility fixtures. Do not delete applied migrations.

- [ ] **Step 5: Verify and commit the replacement**

```powershell
.venv\Scripts\python.exe -m pytest tests/architecture/test_single_agent_generation.py tests/architecture/test_agent_boundaries.py tests/integration/chat tests/integration/api/test_chat_e2e.py tests/integration/agent_evals -q
git add -A contracts/agent src/umbral/agent src/umbral/application/conversation src/umbral/infrastructure/conversation src/umbral/infrastructure/agent src/umbral/infrastructure/agent_evals src/umbral/infrastructure/config/settings.py src/umbral/api/composition.py tests
git commit -m "refactor: replace versioned agents with one semantic graph"
```

---

### Task 8: Run the Release Gate

**Files:**
- Modify only when a failing check identifies an in-scope defect.
- Delete task-created debug artifacts.

**Interfaces:**
- Produces verified behavior and absence of lexical/legacy fallbacks.

- [ ] **Step 1: Re-run the original feedback loop**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/chat/test_semantic_preferences.py -q
```

Expected: PASS for both reported phrases and the three-desire example.

- [ ] **Step 2: Run focused suites**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/application/preferences tests/unit/application/conversation tests/unit/infrastructure/conversation tests/unit/agent tests/integration/chat tests/integration/api/test_chat_e2e.py -q
```

- [ ] **Step 3: Prove lexical resolution and legacy graphs are absent**

```powershell
rg -n "resolve_alias|vocabulary\.resolve|_alias_key|AgentGraphV[0-9]|build_graph_v[0-9]|build_topology_v[0-9]|conversation\.v[0-9]" src
.venv\Scripts\python.exe -m pytest tests/architecture/test_single_agent_generation.py -q
```

Expected: no production hit and architecture test PASS. Prompt examples are allowed only as catalog context and must be documented if the broader search finds them.

- [ ] **Step 4: Run the repository harness**

```powershell
.\scripts\check.ps1
```

Expected: exit code `0`. If absent, document the repository gap instead of creating a wrapper.

- [ ] **Step 5: Inspect scope and commit only necessary corrections**

```powershell
git status --short
git diff --check
git diff --stat HEAD~7..HEAD
```

Confirm unrelated untracked files were never staged and migrations remain. If verification required a correction, stage only that correction and its regression test, then commit `fix: close semantic agent release gate`.

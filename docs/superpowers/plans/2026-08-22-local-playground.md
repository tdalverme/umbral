# Local Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Build a local-only visual playground that runs the explicit-tool conversational graph over isolated in-memory fixtures and exposes an interactive urban-signal inspection view.

**Architecture:** Add a small application-facing playground seam with two operations: \`run_conversation\` and \`inspect_listing_geo\`. A local infrastructure adapter composes the existing v3 graph, tool registry/executor, model gateway and \`UrbanSignalCalculator\` over in-memory state; a dev-only FastAPI router serializes the results; a Next.js route renders Conversation Lab and Geo Lab without adding product persistence or release dependencies.

**Tech Stack:** Python 3.13, FastAPI, LangGraph \`MemorySaver\`, existing agent v3 topology/tool contracts, existing urban contract/calculator, Next.js App Router, TypeScript, Tailwind, MapLibre and Vitest.

**Spec:** \`docs/superpowers/specs/2026-08-22-local-playground-design.md\`

## Global Constraints

- Local-only; routes are mounted only when the dev app receives a configured playground service.
- No new DB tables, Alembic migrations, workers, scheduler, outbox relay, notifications, release or harness gates.
- Mutating tools operate only on an in-memory profile/proposal state created from a fixture.
- The graph, tool registry, tool validation/redaction and \`UrbanSignalCalculator\` remain the source of truth.
- Full prompts and unredacted local trace details remain process-local and are never logged or persisted.
- Every new backend behavior gets a failing test before production code; every frontend module gets a focused Vitest test.
- Preserve the unrelated untracked file \`zonaprop-detail.html\`.

---

## Task 1: Define the application playground interface and trace contracts

**Files:**
- Create: \`src/umbral/application/playground/__init__.py\`
- Create: \`src/umbral/application/playground/contracts.py\`
- Create: \`src/umbral/application/playground/ports.py\`
- Create: \`src/umbral/application/playground/service.py\`
- Test: \`tests/unit/application/playground/test_service.py\`

**Interfaces:**
- \`PlaygroundService.run_conversation(request: ConversationRequest) -> ConversationTrace\`
- \`PlaygroundService.inspect_listing_geo(request: GeoInspectionRequest) -> GeoInspection\`
- \`ConversationRunner.run(request: ConversationRequest) -> ConversationTrace\`
- \`GeoInspector.inspect(request: GeoInspectionRequest) -> GeoInspection\`

- [ ] **Step 1: Write the failing delegation tests.**

\`\`\`python
def test_run_conversation_delegates_to_local_runner() -> None:
    request = ConversationRequest(fixture_id="demo", turns=("hola",), model_mode="fake")
    runner = RecordingConversationRunner()
    service = PlaygroundService(conversation=runner, geo=RecordingGeoInspector())

    result = service.run_conversation(request)

    assert result.fixture_id == "demo"
    assert runner.requests == [request]


def test_geo_inspection_delegates_to_geo_inspector() -> None:
    request = GeoInspectionRequest(fixture_id="demo", listing_id="listing-1", radius_m=600)
    geo = RecordingGeoInspector()
    service = PlaygroundService(conversation=RecordingConversationRunner(), geo=geo)

    result = service.inspect_listing_geo(request)

    assert result.listing_id == "listing-1"
    assert geo.requests == [request]
\`\`\`

- [ ] **Step 2: Run the focused test and verify it fails because the module does not exist.**

Run: \`pytest tests/unit/application/playground/test_service.py -q\`

Expected: FAIL with a missing import/symbol for \`umbral.application.playground\`.

- [ ] **Step 3: Implement immutable JSON-safe contracts and the delegation service.**

Define \`ConversationRequest\` with \`fixture_id: str\`, \`turns: tuple[str, ...]\` and \`model_mode: Literal["fake", "real"]\`; \`GeoInspectionRequest\` with \`fixture_id\`, \`listing_id\` and \`radius_m\`. Define serializable records for ordered events, model calls, tool calls, profile snapshots, assertions, errors, map features, primitives and signals. Keep transport values as primitives/mappings so FastAPI never serializes LangGraph or SQLAlchemy objects.

- [ ] **Step 4: Run the test and verify it passes.**

Run: \`pytest tests/unit/application/playground/test_service.py -q\`

Expected: PASS.

- [ ] **Step 5: Commit the application seam.**

\`\`\`powershell
git add src/umbral/application/playground tests/unit/application/playground/test_service.py
git commit -m "feat: add playground application seam"
\`\`\`

## Task 2: Add local fixtures, isolated state and the graph runner

**Files:**
- Create: \`src/umbral/infrastructure/playground/__init__.py\`
- Create: \`src/umbral/infrastructure/playground/fixtures.py\`
- Create: \`src/umbral/infrastructure/playground/in_memory.py\`
- Create: \`src/umbral/infrastructure/playground/trace.py\`
- Create: \`src/umbral/infrastructure/playground/conversation.py\`
- Create: \`src/umbral/infrastructure/playground/fixtures/demo.json\`
- Test: \`tests/unit/infrastructure/playground/test_fixtures.py\`
- Test: \`tests/unit/infrastructure/playground/test_conversation.py\`

**Interfaces:**
- \`load_fixtures() -> PlaygroundFixtures\`
- \`LocalConversationRunner.run(request: ConversationRequest) -> ConversationTrace\`
- \`PlaygroundTraceCollector\` implements the existing \`RunRecorder\` methods and records model/tool/state evidence in memory.
- \`LocalProfileState.snapshot() -> Mapping[str, object]\`

- [ ] **Step 1: Write failing fixture and isolation tests.**

\`\`\`python
def test_demo_fixture_contains_profile_listing_and_urban_data() -> None:
    demo = load_fixtures().by_id("demo")
    assert demo.profile["budget_max"] == 1200
    assert demo.listings[0]["id"] == "listing-palermo-001"
    assert demo.urban["features"]


def test_each_run_gets_a_fresh_profile_copy() -> None:
    runner = build_local_conversation_runner()
    request = ConversationRequest(
        fixture_id="demo",
        turns=("bajá el presupuesto a 1000",),
        model_mode="fake",
    )

    first = runner.run(request)
    second = runner.run(request)

    assert first.state_after == second.state_after
    assert first.run_id != second.run_id
\`\`\`

- [ ] **Step 2: Run the tests and verify the expected missing-module failure.**

Run: \`pytest tests/unit/infrastructure/playground/test_fixtures.py tests/unit/infrastructure/playground/test_conversation.py -q\`

Expected: FAIL because the fixture loader and runner do not exist.

- [ ] **Step 3: Add the demo fixture and loader.**

The fixture includes profile fields used by the v3 intent/tool flow, one listing with coordinates/detail fields, urban point and line features with distances and GeoJSON, \`poi_distances\`/ \`linear_distances\` keyed by the urban contract, one non-zero signal path and one unsupported metric represented as absent rather than zero. The loader validates required keys and returns immutable copies.

- [ ] **Step 4: Implement in-memory application adapters.**

Provide in-memory chat session/message repositories, a no-op event writer, \`MemorySaver\`, graph-run repository, \`PlaygroundTraceCollector\`, scoped session reader, profile/proposal state and decision gateways. Use the published \`ToolRegistry\`, \`ToolExecutor\` and tool schemas. Fixture-backed implementations must cover profile read/propose/apply, match/detail lookup, urban context lookup and safe read-only tools; unknown tools still fail through the registry.

- [ ] **Step 5: Implement fake and real gateway selection.**

\`model_mode="fake"\` uses a deterministic gateway with scripted intent/reply/tool-call payloads for the demo fixture. \`model_mode="real"\` uses the configured managed gateway and the same v3 graph, prompt versions and schemas. Record mode, model version, prompt version, tokens and latency.

- [ ] **Step 6: Compose the existing v3 graph and collect a trace.**

Build \`IntentCompiler\`, \`ToolExecutor\`, \`build_topology_v3\`, \`ChatRuntime\` and \`MemorySaver\` with local adapters. For each turn: snapshot profile state, run through \`ChatRuntime.run_turn\`, capture runtime/recorder events, snapshot state after the turn, evaluate assertions and append the turn trace. Interrupts are valid results and the same in-memory session can resume them on the next turn.

- [ ] **Step 7: Run focused tests and verify they pass.**

Run: \`pytest tests/unit/infrastructure/playground/test_fixtures.py tests/unit/infrastructure/playground/test_conversation.py -q\`

Expected: PASS, including isolation, tool ordering, confirmation and fake gateway paths.

- [ ] **Step 8: Commit the local conversation runner.**

\`\`\`powershell
git add src/umbral/infrastructure/playground tests/unit/infrastructure/playground
git commit -m "feat: add isolated playground conversation runner"
\`\`\`

## Task 3: Implement Geo Lab over the real urban contract/calculator

**Files:**
- Create: \`src/umbral/infrastructure/playground/geo.py\`
- Modify: \`src/umbral/application/playground/contracts.py\`
- Test: \`tests/unit/infrastructure/playground/test_geo.py\`

**Interfaces:**
- \`LocalGeoInspector.inspect(request: GeoInspectionRequest) -> GeoInspection\`
- \`serialize_feature(feature) -> Mapping[str, object]\`

- [ ] **Step 1: Write failing Geo Lab tests.**

\`\`\`python
def test_geo_inspection_exposes_feature_primitive_signal_lineage() -> None:
    result = build_local_geo_inspector().inspect(
        GeoInspectionRequest(
            fixture_id="demo",
            listing_id="listing-palermo-001",
            radius_m=600,
        )
    )

    assert result.features
    assert result.primitives[0]["category"] == "cafe"
    assert any(item["signal"] == "cafe_lifestyle" for item in result.signals)
    assert result.signals[0]["contributors"]


def test_geo_inspection_keeps_unsupported_metrics_missing() -> None:
    result = build_local_geo_inspector().inspect(
        GeoInspectionRequest(
            fixture_id="demo",
            listing_id="listing-palermo-001",
            radius_m=600,
        )
    )

    subway = next(item for item in result.primitives if item["category"] == "subway_station")
    assert subway["count_300m"] is None
\`\`\`

- [ ] **Step 2: Run the tests and verify the expected missing-module failure.**

Run: \`pytest tests/unit/infrastructure/playground/test_geo.py -q\`

Expected: FAIL because \`LocalGeoInspector\` does not exist.

- [ ] **Step 3: Implement the inspector.**

Load \`contracts/urban/v2/urban-contract-v2.json\` with the existing urban contract loader. Feed fixture distances into \`UrbanSignalCalculator\`, derive primitive rows from declared metrics and join each primitive to fixture features by category/radius. Preserve \`None\` for unsupported metrics. Return listing coordinates, map features, primitives, base/composite signals, contributors, contract version, snapshot id, normalization metadata, warnings and OSM attribution.

- [ ] **Step 4: Run the Geo Lab tests and verify they pass.**

Run: \`pytest tests/unit/infrastructure/playground/test_geo.py -q\`

Expected: PASS.

- [ ] **Step 5: Commit Geo Lab backend behavior.**

\`\`\`powershell
git add src/umbral/application/playground/contracts.py src/umbral/infrastructure/playground/geo.py tests/unit/infrastructure/playground/test_geo.py
git commit -m "feat: add playground urban inspection"
\`\`\`

## Task 4: Add the dev-only API router and local wiring

**Files:**
- Create: \`src/umbral/api/routers/playground.py\`
- Modify: \`src/umbral/api/dependencies.py\`
- Modify: \`src/umbral/api/main.py\`
- Modify: \`src/umbral/api/dev_main.py\`
- Test: \`tests/contract/test_playground_api.py\`

**Interfaces:**
- \`GET /api/v1/playground/fixtures\`
- \`POST /api/v1/playground/conversations\`
- \`POST /api/v1/playground/geo\`

- [ ] **Step 1: Write failing API contract tests.**

\`\`\`python
def test_playground_routes_are_absent_without_service() -> None:
    app = create_app(build_test_dependencies(playground=None))
    assert not any(route.path.startswith("/api/v1/playground") for route in app.routes)


def test_playground_conversation_returns_serializable_trace() -> None:
    app = create_app(build_test_dependencies(playground=build_fake_playground()))
    response = client(app).post(
        "/api/v1/playground/conversations",
        json={"fixture_id": "demo", "turns": ["hola"], "model_mode": "fake"},
    )
    assert response.status_code == 200
    assert response.json()["turns"]
\`\`\`

- [ ] **Step 2: Run the tests and verify they fail because route wiring is absent.**

Run: \`pytest tests/contract/test_playground_api.py -q\`

Expected: FAIL because \`RuntimeDependencies\` has no playground service and the router is not registered.

- [ ] **Step 3: Add an optional dependency and conditional route mounting.**

Add \`playground: PlaygroundService | None = None\` to \`RuntimeDependencies\`. Configure/include the router only when it is present. The default app has no playground routes; \`dev_main\` constructs fixtures, runner, geo inspector and service.

- [ ] **Step 4: Implement endpoints and transport validation.**

Return \`application/problem+json\` for unknown fixture/listing, invalid radius, missing turns and runner errors. The routes are unauthenticated only because they are absent outside the dev app; never expose them through the production dependency builder.

- [ ] **Step 5: Run API and focused backend tests.**

Run: \`pytest tests/contract/test_playground_api.py tests/unit/application/playground tests/unit/infrastructure/playground -q\`

Expected: PASS.

- [ ] **Step 6: Commit the dev-only API.**

\`\`\`powershell
git add src/umbral/api/routers/playground.py src/umbral/api/dependencies.py src/umbral/api/main.py src/umbral/api/dev_main.py tests/contract/test_playground_api.py
git commit -m "feat: expose local playground API"
\`\`\`

## Task 5: Add the web client, BFF routes and Conversation Lab UI

**Files:**
- Create: \`apps/web/src/lib/playground/client.ts\`
- Create: \`apps/web/src/app/api/playground/fixtures/route.ts\`
- Create: \`apps/web/src/app/api/playground/conversations/route.ts\`
- Create: \`apps/web/src/components/playground/conversation-lab.tsx\`
- Create: \`apps/web/src/components/playground/trace-inspector.tsx\`
- Create: \`apps/web/src/components/playground/assertion-list.tsx\`
- Create: \`apps/web/src/app/playground/page.tsx\`
- Test: \`apps/web/src/components/playground/conversation-lab.test.tsx\`
- Test: \`apps/web/src/components/playground/trace-inspector.test.tsx\`

**Interfaces:**
- \`playgroundApi.fixtures() -> PlaygroundFixtureSummary[]\`
- \`playgroundApi.runConversation(request) -> ConversationTrace\`
- \`ConversationLab\` renders fixture/model/turn controls and a trace.

- [ ] **Step 1: Write failing component tests.**

\`\`\`tsx
it("renders transcript, tool timeline and profile diff", async () => {
  render(<ConversationLab initialFixtures={[demoFixture]} run={fakeRun} />);
  await userEvent.type(
    screen.getByRole("textbox", { name: /mensaje/i }),
    "bajá el presupuesto",
  );
  await userEvent.click(screen.getByRole("button", { name: /ejecutar/i }));

  expect(
    await screen.findByText("propose_search_profile_update"),
  ).toBeInTheDocument();
  expect(screen.getByText(/cambios del perfil/i)).toBeInTheDocument();
});
\`\`\`

- [ ] **Step 2: Run focused web tests and verify missing-module failure.**

Run: \`npm test --workspace @umbral/web -- src/components/playground/conversation-lab.test.tsx src/components/playground/trace-inspector.test.tsx\`

Expected: FAIL with missing-module errors.

- [ ] **Step 3: Implement the typed client and BFF forwarding routes.**

Use the existing \`forwardRadarRequest\`/ \`forwardJson\` pattern. The browser calls only \`/api/playground/...\`; the BFF forwards to the local backend with \`no-store\`.

- [ ] **Step 4: Implement Conversation Lab.**

Use existing \`Card\`, \`Button\`, \`Alert\`, \`Input\`/ \`Field\` and message styles. Support fixture selection, fake/real mode, composer, reset, run and readable transcript, ordered tools, model metrics, profile before/after, assertions and errors. Do not add a generic JSON editor.

- [ ] **Step 5: Run focused web tests and verify they pass.**

Run: \`npm test --workspace @umbral/web -- src/components/playground/conversation-lab.test.tsx src/components/playground/trace-inspector.test.tsx\`

Expected: PASS.

- [ ] **Step 6: Commit the Conversation Lab UI.**

\`\`\`powershell
git add apps/web/src/lib/playground apps/web/src/app/api/playground apps/web/src/components/playground apps/web/src/app/playground
git commit -m "feat: add playground conversation lab"
\`\`\`

## Task 6: Add Geo Lab map and evidence UI

**Files:**
- Create: \`apps/web/src/app/api/playground/geo/route.ts\`
- Create: \`apps/web/src/components/playground/geo-lab.tsx\`
- Create: \`apps/web/src/components/playground/urban-map.tsx\`
- Create: \`apps/web/src/components/playground/evidence-tree.tsx\`
- Modify: \`apps/web/src/app/playground/page.tsx\`
- Test: \`apps/web/src/components/playground/geo-lab.test.tsx\`
- Test: \`apps/web/src/components/playground/evidence-tree.test.tsx\`

**Interfaces:**
- \`playgroundApi.inspectGeo(request) -> GeoInspection\`
- \`GeoLab\` renders listing/radius controls, map features and evidence tree.

- [ ] **Step 1: Write failing Geo Lab UI tests.**

\`\`\`tsx
it("shows signal, primitive and feature evidence", async () => {
  render(<GeoLab fixtures={[demoFixture]} inspect={fakeGeoInspection} />);
  await userEvent.click(
    screen.getByRole("button", { name: /inspeccionar/i }),
  );

  expect(await screen.findByText("cafe_lifestyle")).toBeInTheDocument();
  expect(screen.getByText("cafe")).toBeInTheDocument();
  expect(screen.getByText("Café Fixture")).toBeInTheDocument();
  expect(
    screen.getByText(/OpenStreetMap contributors/i),
  ).toBeInTheDocument();
});
\`\`\`

- [ ] **Step 2: Run focused web tests and verify missing-module failure.**

Run: \`npm test --workspace @umbral/web -- src/components/playground/geo-lab.test.tsx src/components/playground/evidence-tree.test.tsx\`

Expected: FAIL with missing-module errors.

- [ ] **Step 3: Implement the Geo Lab client route and evidence tree.**

Render explicit labels for \`missing\`, \`NULL\` and observed zero. Make signal rows expandable into formula terms, primitive rows and source features. Show weights, scores, distances, radii, confidence, contract version, snapshot id and attribution.

- [ ] **Step 4: Implement the MapLibre adapter.**

Reuse the existing OSM raster style and attribution. Render listing marker, POI markers and GeoJSON line features; replacing selected listing/radius must not leak map instances. If tiles fail, keep evidence usable and show a recoverable alert.

- [ ] **Step 5: Add the Geo Lab tab and run tests.**

Run: \`npm test --workspace @umbral/web -- src/components/playground/geo-lab.test.tsx src/components/playground/evidence-tree.test.tsx\`

Expected: PASS.

- [ ] **Step 6: Commit the Geo Lab UI.**

\`\`\`powershell
git add apps/web/src/app/api/playground/geo apps/web/src/components/playground apps/web/src/app/playground/page.tsx
git commit -m "feat: add playground geo lab"
\`\`\`

## Task 7: Add local launch documentation and final verification

**Files:**
- Create: \`scripts/playground.ps1\`
- Modify: \`docs/runbooks/runtime-local.md\`
- Modify: \`apps/web/src/app/runtime-routes.test.ts\`
- Test: \`tests/contract/test_playground_local_guard.py\`

- [ ] **Step 1: Write failing local-only guard tests.**

\`\`\`python
def test_playground_is_local_only() -> None:
    assert playground_enabled("local") is True
    assert playground_enabled("preview") is False
    assert playground_enabled("production") is False
\`\`\`

- [ ] **Step 2: Run the tests and verify the expected missing-guard failure.**

Run: \`pytest tests/contract/test_playground_local_guard.py -q\`

Expected: FAIL because the guard/launcher does not exist.

- [ ] **Step 3: Add the one-command launcher and documentation.**

The launcher starts the local playground API and web app using the existing development environment, without invoking release, promote, full tests, harness, worker or scheduler. It prints URLs and fake/real model requirements and does not create or migrate a product database.

- [ ] **Step 4: Run focused backend/frontend verification.**

Run:

\`\`\`powershell
pytest tests/unit/application/playground tests/unit/infrastructure/playground tests/contract/test_playground_api.py tests/contract/test_playground_local_guard.py -q
npm test --workspace @umbral/web -- src/components/playground
npm run typecheck --workspace @umbral/web
npm run lint --workspace @umbral/web
\`\`\`

Expected: all commands exit \`0\` with no test failures, TypeScript errors or lint errors.

- [ ] **Step 5: Run frontend build and touched-layer checks.**

Run:

\`\`\`powershell
npm run build --workspace @umbral/web
.\\scripts\\check.ps1
\`\`\`

Expected: the build and checks pass; the mandatory harness remains unchanged and the playground routes are absent from the default production app.

- [ ] **Step 6: Inspect the diff and commit launcher/docs.**

\`\`\`powershell
git diff --check
git status --short
git add scripts/playground.ps1 docs/runbooks/runtime-local.md apps/web/src/app/runtime-routes.test.ts tests/contract/test_playground_local_guard.py
git commit -m "docs: add local playground launcher"
\`\`\`

Leave \`zonaprop-detail.html\` untracked and untouched.

---

## Self-review checklist

- Both labs are covered, including fixtures, in-memory isolation, trace inspection, profile diffs, assertions, map features, primitive/signal lineage, missing-vs-zero semantics and OSM attribution.
- No product persistence, workers, release gates, new ranking engine or second urban formula is added.
- The v3 explicit-tool topology is selected because it is the current product topology when \`COPILOT_ENABLED=false\) and exposes intent, allowed tools and tool execution.
- Every task names files, interfaces, failing tests, verification commands and a commit boundary.
- No placeholder work items remain.


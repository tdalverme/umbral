"""Executable dependency fixtures for the six Python runtime surfaces.

The fixtures in this package are deliberately independent from ``src.umbral``.
They model the architecture contract in a small, deterministic graph that can
later be consumed by the Import Linter and repository harness (T009/T013).
"""

import ast
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
LAYERS = (
    "agent",
    "api",
    "application",
    "domain",
    "infrastructure",
    "workers",
)

ALLOWED_EDGES = frozenset(
    {
        ("application", "domain"),
        ("agent", "application"),
        ("agent", "domain"),
        ("api", "application"),
        ("api", "domain"),
        ("workers", "application"),
        ("workers", "domain"),
        ("infrastructure", "application"),
        ("infrastructure", "domain"),
    }
)


@dataclass(frozen=True)
class DependencyViolation:
    """One direct or transitive forbidden path in a fixture graph."""

    kind: str
    path: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.kind}: {' -> '.join(self.path)}"


@dataclass(frozen=True)
class FixtureGraph:
    """Deterministic source-import graph and its architecture violations."""

    layers: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    violations: tuple[DependencyViolation, ...]

    @property
    def violation_labels(self) -> tuple[str, ...]:
        return tuple(violation.label for violation in self.violations)

    def has_violation(self, *, kind: str, path: tuple[str, ...]) -> bool:
        return any(
            violation.kind == kind and violation.path == path
            for violation in self.violations
        )


def scan_fixture_graph(root: Path) -> FixtureGraph:
    """Scan local fixture imports and report direct/transitive bad paths."""

    source_files = sorted(
        source for source in root.glob("*.py") if source.name != "__init__.py"
    )
    layers = tuple(source.stem for source in source_files)
    known_layers = frozenset(layers)
    adjacency: dict[str, set[str]] = defaultdict(set)

    for source in source_files:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names = (alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names = _resolve_fixture_imports(node, known_layers)
            else:
                continue
            adjacency[source.stem].update(
                imported for imported in imported_names if imported in known_layers
            )

    edges = tuple(
        sorted((source, target) for source in adjacency for target in adjacency[source])
    )
    direct = [
        DependencyViolation(kind="direct", path=edge)
        for edge in edges
        if edge not in ALLOWED_EDGES
    ]
    transitive = _transitive_violations(adjacency, direct)
    return FixtureGraph(
        layers=layers,
        edges=edges,
        violations=tuple(sorted(direct + transitive, key=lambda item: item.label)),
    )


def _resolve_fixture_imports(
    node: ast.ImportFrom, known_layers: frozenset[str]
) -> tuple[str, ...]:
    """Resolve same-package relative imports without importing the fixtures."""

    if node.level == 0:
        return (node.module,) if node.module in known_layers else ()
    if node.module in known_layers:
        return (node.module,)
    return tuple(alias.name for alias in node.names if alias.name in known_layers)


def _transitive_violations(
    adjacency: dict[str, set[str]], direct: list[DependencyViolation]
) -> list[DependencyViolation]:
    """Attach deterministic allowed prefixes to forbidden direct edges."""

    allowed_adjacency: dict[str, tuple[str, ...]] = {
        source: tuple(
            sorted(target for target in targets if (source, target) in ALLOWED_EDGES)
        )
        for source, targets in adjacency.items()
    }
    transitive: list[DependencyViolation] = []
    for violation in direct:
        bad_source, bad_target = violation.path
        for prefix in _allowed_prefixes(allowed_adjacency, bad_source):
            if len(prefix) > 1:
                transitive.append(
                    DependencyViolation(
                        kind="transitive",
                        path=prefix + (bad_target,),
                    )
                )
    return transitive


def _allowed_prefixes(
    adjacency: dict[str, tuple[str, ...]], target: str
) -> tuple[tuple[str, ...], ...]:
    prefixes: list[tuple[str, ...]] = []
    for start in sorted(adjacency):
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(start, (start,))])
        while queue:
            current, path = queue.popleft()
            if current == target:
                prefixes.append(path)
                continue
            for neighbor in adjacency.get(current, ()):
                if neighbor not in path:
                    queue.append((neighbor, path + (neighbor,)))
    return tuple(sorted(prefixes))


def test_allowed_fixture_exposes_all_runtime_layers() -> None:
    report = scan_fixture_graph(FIXTURES / "allowed")

    assert report.layers == LAYERS
    assert ("application", "domain") in report.edges
    assert report.violations == ()


def test_direct_forbidden_fixture_names_the_invalid_edge() -> None:
    report = scan_fixture_graph(FIXTURES / "forbidden_direct")

    assert report.has_violation(
        kind="direct",
        path=("domain", "infrastructure"),
    ), report.violation_labels


def test_transitive_forbidden_fixture_reports_the_full_path() -> None:
    report = scan_fixture_graph(FIXTURES / "forbidden_transitive")

    assert report.has_violation(
        kind="transitive",
        path=("agent", "application", "infrastructure"),
    ), report.violation_labels


def test_fixtures_do_not_import_production_modules() -> None:
    production_imports = []
    for source in FIXTURES.rglob("*.py"):
        if source.name == "__init__.py":
            continue
        if "src.umbral" in source.read_text(encoding="utf-8"):
            production_imports.append(source.relative_to(FIXTURES).as_posix())

    assert production_imports == []

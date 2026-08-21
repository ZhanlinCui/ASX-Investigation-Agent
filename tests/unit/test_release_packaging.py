from __future__ import annotations

import re
import subprocess
import tomllib
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT_DOCS = [
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "MASTER_DEVELOPMENT_PLAN.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "product.md",
    ROOT / "docs" / "product-design.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "evaluation.md",
    ROOT / "docs" / "release-status.md",
    ROOT / "docs" / "decisions" / "four-core-decisions.md",
    ROOT / "docs" / "phase-plans" / "phase-05-recall-and-release-closure.md",
    ROOT / "evals" / "results" / "final-release.md",
]


class _ReadmeHtmlReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.targets: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attribute = "href" if tag == "a" else "src" if tag == "img" else None
        if attribute is None:
            return
        values = dict(attrs)
        value = values.get(attribute)
        if value:
            self.targets.append(value)


def _heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, flags=re.MULTILINE):
        normalized = re.sub(r"[^a-z0-9 -]", "", heading.lower())
        anchors.add("#" + re.sub(r"[ -]+", "-", normalized).strip("-"))
    return anchors


def test_public_documentation_has_no_broken_local_links() -> None:
    broken: list[str] = []
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv", "node_modules"} for part in path.parts):
            continue
        for target in link_pattern.findall(path.read_text(encoding="utf-8")):
            clean = target.strip().strip("<>").split("#", 1)[0]
            if not clean or "://" in clean or clean.startswith("mailto:"):
                continue
            if not (path.parent / clean).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_current_docs_have_one_truthful_release_status() -> None:
    for path in CURRENT_DOCS:
        assert path.exists(), f"missing current document: {path.relative_to(ROOT)}"

    required_not_run = [
        ROOT / "README.md",
        ROOT / "MASTER_DEVELOPMENT_PLAN.md",
        ROOT / "docs" / "product.md",
        ROOT / "docs" / "product-design.md",
        ROOT / "docs" / "evaluation.md",
        ROOT / "docs" / "release-status.md",
        ROOT / "docs" / "phase-plans" / "phase-05-recall-and-release-closure.md",
        ROOT / "evals" / "results" / "final-release.md",
    ]
    for path in required_not_run:
        text = path.read_text(encoding="utf-8")
        assert "NOT_RUN" in text, f"external gate status missing from {path.relative_to(ROOT)}"
        assert "status: release-approved" not in text.lower()
        assert "status: production-validated" not in text.lower()

    assert "336 Python tests" in (ROOT / "docs" / "release-status.md").read_text(
        encoding="utf-8"
    )
    assert "336 tests passed" in (
        ROOT / "evals" / "results" / "final-release.md"
    ).read_text(encoding="utf-8")


def test_current_docs_contain_no_placeholders_or_stale_root_paths() -> None:
    prohibited = (
        "TODO",
        "TBD",
        "COMING SOON",
        "LOREM IPSUM",
        "design requirement document v1.md",
        "ASX Unusual Trading Investigation Agent.md",
        "output/pdf/asx-investigation-agent-architecture.pdf",
    )
    for path in CURRENT_DOCS:
        upper = path.read_text(encoding="utf-8").upper()
        for marker in prohibited:
            assert marker.upper() not in upper, f"{marker!r} remains in {path.relative_to(ROOT)}"


def test_tracked_text_has_no_live_credential_shape() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    secret_patterns = {
        "Gemini-style key": re.compile(rb"AQ\.[A-Za-z0-9_-]{20,}"),
        "EODHD-style key": re.compile(rb"\b[a-f0-9]{14,}\.[0-9]{6,}\b", re.IGNORECASE),
        "non-empty provider variable": re.compile(
            rb"(?:GEMINI|EODHD|MARKETSTACK|TAVILY)_API_KEY[ \t]*=[ \t]*[^\s#]{8,}",
        ),
    }
    findings: list[str] = []
    for raw_path in tracked:
        if not raw_path:
            continue
        path = ROOT / raw_path.decode()
        if path.suffix.lower() in {".pdf", ".png", ".lock"}:
            continue
        content = path.read_bytes()
        for label, pattern in secret_patterns.items():
            if pattern.search(content):
                findings.append(f"{label}: {path.relative_to(ROOT)}")
    assert findings == []


def test_readme_is_a_complete_truthful_repository_homepage() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '<h1 align="center">ASX Investigation Agent</h1>' in text
    for heading in (
        "## Why this exists",
        "## The investigation method",
        "## Agent architecture",
        "## Memory and evaluation boundary",
        "## What makes the agent different",
        "## Four core design decisions",
        "## Product capabilities",
        "## Technology",
        "## Recorded demo quick start",
        "## Live configuration",
        "## Evaluation status",
        "## Security and known limits",
        "## Documentation",
        "## License status",
    ):
        assert heading in text
    assert "24 recorded cases are synthetic policy sentinels" in text
    assert "not a probability" in text
    assert "No open-source license has been granted" in text
    assert "classDiagram" in text
    assert "sequenceDiagram" in text
    assert "flowchart LR" in text
    for architecture_term in (
        "InvestigationService",
        "InvestigationKernel",
        "RetrievalPlanner",
        "InvestigationTools",
        "InvestigationReasoner",
        "GeminiInvestigationReasoner",
        "SQLiteCaseRepository",
        "SQLiteEvidenceRegistry",
        "ArtifactStore",
        "SharedMemoryRepository",
        "ReleaseGates",
    ):
        assert architecture_term in text


def test_readme_navigation_assets_and_release_states_are_safe() -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    parser = _ReadmeHtmlReferences()
    parser.feed(text)
    markdown_targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text)
    anchors = _heading_anchors(text)

    for target in [*parser.targets, *markdown_targets]:
        clean = target.strip().strip("<>")
        if clean.startswith("#"):
            assert clean in anchors, f"missing README anchor: {clean}"
            continue
        if "://" in clean or clean.startswith("mailto:"):
            continue
        relative, _, fragment = clean.partition("#")
        resolved = (path.parent / relative).resolve()
        assert resolved.is_relative_to(ROOT.resolve()), f"README target escapes root: {target}"
        assert resolved.exists(), f"missing README target: {target}"
        if fragment and resolved.suffix == ".md":
            assert f"#{fragment}" in _heading_anchors(resolved.read_text(encoding="utf-8"))

    assert "| Recorded policy sentinels | `24/24 PASS` |" in text
    for row in (
        "| External development gold, 24 cases | `NOT_RUN` |",
        "| Sealed holdout, 12 cases | `NOT_RUN` |",
        "| Credentialed Live approval | `NOT_RUN` |",
    ):
        assert row in text


def test_readme_architecture_diagrams_match_runtime_ownership() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    diagrams = re.findall(r"```mermaid\n(.*?)\n```", text, flags=re.DOTALL)
    assert len(diagrams) == 3
    sequence, uml, boundary = diagrams
    assert sequence.startswith("sequenceDiagram")
    assert uml.startswith("classDiagram")
    assert boundary.startswith("flowchart LR")

    for relation in (
        "CaseManager --> InvestigationService",
        "InvestigationService *-- InvestigationKernel",
        "InvestigationKernel --> RetrievalPlanner",
        "InvestigationKernel --> InvestigationTools",
        "InvestigationKernel --> InvestigationReasoner",
        "GeminiInvestigationReasoner ..|> InvestigationReasoner",
        "CaseManager --> SQLiteCaseRepository",
        "CaseManager --> SQLiteEvidenceRegistry",
        "CaseManager --> SharedMemoryRepository",
        "LiveToolGateway ..|> InvestigationTools",
        "LiveToolGateway --> ArtifactStore",
    ):
        assert relation in uml
    for false_relation in (
        "InvestigationKernel --> SQLiteCaseRepository",
        "InvestigationKernel --> CaseRepository",
        "resolveExactPassage",
        "class DeterministicValidator",
        "class PublicProjection",
    ):
        assert false_relation not in uml

    assert "P->>A: Freeze raw response and document bytes by SHA-256" in sequence
    assert "CaseManager->>EvidenceRegistry: Persist version-scoped exact passages" in sequence
    assert "Artifact Store" not in sequence
    assert sequence.count("opt ") + sequence.count("alt ") == sequence.count("    end")
    assert boundary.count("subgraph ") == boundary.count("    end")


def test_ci_runs_every_local_release_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "name: Release quality gates" in workflow
    for command in (
        "python -m pip install --upgrade pip==25.3",
        "python -m ruff check src tests evals",
        "python -m compileall -q src",
        "python -m pytest -q",
        "python evals/run_recorded_evals.py",
        "pnpm lint",
        "pnpm test -- --run",
        "pnpm build",
    ):
        assert command in workflow


def test_quick_start_upgrades_bootstrap_pip_before_editable_install() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    upgrade = readme.index(".venv/bin/python -m pip install --upgrade pip==25.3")
    editable = readme.index(".venv/bin/python -m pip install -e '.[dev]'")
    assert upgrade < editable


def test_python_build_backend_is_reproducibly_pinned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["build-system"]["requires"] == ["setuptools==75.8.2"]

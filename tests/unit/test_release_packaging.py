from __future__ import annotations

import re
import subprocess
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
    for heading in (
        "# ASX Investigation Agent",
        "## Why this exists",
        "## What makes the agent different",
        "## Audited investigation workflow",
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


def test_ci_runs_every_local_release_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "name: Release quality gates" in workflow
    for command in (
        "python -m ruff check src tests evals",
        "python -m compileall -q src",
        "python -m pytest -q",
        "python evals/run_recorded_evals.py",
        "pnpm lint",
        "pnpm test -- --run",
        "pnpm build",
    ):
        assert command in workflow

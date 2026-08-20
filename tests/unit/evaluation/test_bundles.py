from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from asx_investigator.evaluation.bundles import (
    FrozenBundleError,
    FrozenCaseGateway,
    load_frozen_case_bundle,
)

SYDNEY = ZoneInfo("Australia/Sydney")


def _write_artifact(root: Path, content: bytes) -> str:
    artifact_id = hashlib.sha256(content).hexdigest()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / artifact_id).write_bytes(content)
    return artifact_id


def write_bundle(
    root: Path,
    *,
    ticker: str = "BHP",
    trade_date: str = "2026-08-20",
    artifact_hash: str | None = None,
    artifact_bytes: bytes | None = None,
    evidence_published_at: datetime | None = None,
    cutoff_timezone: str = "Australia/Sydney",
) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    target_date = date.fromisoformat(trade_date)
    published_at = evidence_published_at or datetime(
        target_date.year, target_date.month, target_date.day, 8, 30, tzinfo=SYDNEY
    )
    cutoff = datetime(target_date.year, target_date.month, target_date.day, 16, 10, tzinfo=SYDNEY)
    start = target_date - timedelta(days=60)
    bars = [
        {
            "trade_date": (start + timedelta(days=index)).isoformat(),
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.0,
            "adjusted_close": 10.0,
            "volume": 100_000,
        }
        for index in range(60)
    ]
    bars.append(
        {
            "trade_date": trade_date,
            "open": 10.5,
            "high": 11.2,
            "low": 10.4,
            "close": 11.0,
            "adjusted_close": 11.0,
            "volume": 500_000,
        }
    )
    market_artifact = _write_artifact(
        root, json.dumps(bars, sort_keys=True, separators=(",", ":")).encode()
    )
    actions_artifact = _write_artifact(root, b"[]")
    passage = b"BHP raised its FY26 production guidance before ASX trading opened."
    document_bytes = artifact_bytes or passage
    document_artifact = _write_artifact(root, document_bytes)
    declared_document_artifact = artifact_hash or document_artifact
    if artifact_hash is not None:
        (root / "artifacts" / artifact_hash).write_bytes(document_bytes)
    retrieved_at = published_at + timedelta(minutes=5)
    outcome_retrieved_at = datetime(
        target_date.year, target_date.month, target_date.day, 16, 5, tzinfo=SYDNEY
    )
    bundle = {
        "bundle_version": "frozen-case-v1",
        "case_id": "gold-01",
        "ticker": ticker,
        "trade_date": trade_date,
        "timezone": cutoff_timezone,
        "evidence_cutoff": cutoff.isoformat(),
        "provider_schema_version": "provider-outcome-v1",
        "instrument": {
            "asx_code": ticker,
            "company_name": "BHP Group Limited",
            "sector": "Materials",
        },
        "market": {
            "artifact_id": market_artifact,
            "selected_provider": "FROZEN_MARKET",
            "benchmark_return": 1.0,
            "outcome": {
                "status": "SUCCESS",
                "provider": "FROZEN_MARKET",
                "retrieved_at": outcome_retrieved_at.isoformat(),
                "coverage": "COMPLETE",
                "provenance": {"artifact_id": market_artifact},
                "source_version": "frozen-fixture-v1",
            },
        },
        "corporate_actions": {
            "artifact_id": actions_artifact,
            "outcome": {
                "status": "SUCCESS",
                "provider": "FROZEN_CORPORATE_ACTIONS",
                "retrieved_at": outcome_retrieved_at.isoformat(),
                "coverage": "COMPLETE",
                "provenance": {"artifact_id": actions_artifact},
                "source_version": "frozen-fixture-v1",
            },
        },
        "evidence": {
            "coverage_complete": True,
            "documents": [
                {
                    "artifact_id": declared_document_artifact,
                    "mime_type": "text/plain",
                    "metadata": {
                        "evidence_id": "E1",
                        "source_name": "BHP Investor Relations",
                        "source_url": "https://example.test/bhp/fy26-guidance-update",
                        "published_at": published_at.isoformat(),
                        "retrieved_at": retrieved_at.isoformat(),
                        "role": "CAUSAL_INPUT",
                        "authority": "PRIMARY_ISSUER",
                        "title": "FY26 guidance update",
                        "content_hash": declared_document_artifact,
                        "locator": "Frozen fixture: announcement summary",
                    },
                }
            ],
        },
    }
    (root / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    return {
        "market": market_artifact,
        "corporate_actions": actions_artifact,
        "document": declared_document_artifact,
    }


async def test_frozen_gateway_exposes_only_hash_verified_case_inputs(tmp_path: Path) -> None:
    write_bundle(tmp_path / "gold-01")

    bundle = load_frozen_case_bundle(tmp_path / "gold-01")
    gateway = FrozenCaseGateway(bundle)
    market = await gateway.get_market_data("BHP", date(2026, 8, 20))
    evidence = await gateway.get_evidence("BHP", date(2026, 8, 20))

    assert market.selected_provider == "FROZEN_MARKET"
    assert market.outcomes[0].artifact is not None
    assert evidence[0].passage.startswith("BHP raised")
    assert evidence[0].content_hash == bundle.document_artifact_ids[0]


def test_bundle_metadata_cannot_be_mutated_after_admission(tmp_path: Path) -> None:
    write_bundle(tmp_path / "gold-01")
    bundle = load_frozen_case_bundle(tmp_path / "gold-01")

    with pytest.raises(TypeError):
        bundle.market["selected_provider"] = "UNTRUSTED"
    mutable_view = bundle.instrument
    mutable_view.asx_code = "UNTRUSTED"

    assert bundle.instrument.asx_code == "BHP"


def test_bundle_rejects_mutated_artifact_hash(tmp_path: Path) -> None:
    write_bundle(tmp_path / "gold-01", artifact_hash="a" * 64, artifact_bytes=b"other")

    with pytest.raises(FrozenBundleError, match="hash"):
        load_frozen_case_bundle(tmp_path / "gold-01")


def test_bundle_rejects_missing_required_artifact(tmp_path: Path) -> None:
    root = tmp_path / "gold-01"
    artifacts = write_bundle(root)
    (root / "artifacts" / artifacts["document"]).unlink()

    with pytest.raises(FrozenBundleError, match="missing"):
        load_frozen_case_bundle(root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("provider_schema", "provider schema"),
        ("prebuilt_report", "prebuilt reports"),
        ("market_provenance", "provenance"),
    ],
)
def test_bundle_rejects_provider_contract_or_report_bypass(
    tmp_path: Path, mutation: str, message: str
) -> None:
    root = tmp_path / "gold-01"
    write_bundle(root)
    bundle_path = root / "bundle.json"
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    if mutation == "provider_schema":
        payload["provider_schema_version"] = "unknown-v1"
    elif mutation == "prebuilt_report":
        payload["report"] = {"outcome": "EXPLAINED"}
    else:
        payload["market"]["outcome"]["provenance"]["artifact_id"] = "0" * 64
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FrozenBundleError, match=message):
        load_frozen_case_bundle(root)


def test_bundle_rejects_non_trading_asx_session(tmp_path: Path) -> None:
    write_bundle(tmp_path / "gold-01", trade_date="2026-08-22")

    with pytest.raises(FrozenBundleError, match="ASX trading session"):
        load_frozen_case_bundle(tmp_path / "gold-01")


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"cutoff_timezone": "UTC"}, "Australia/Sydney"),
        (
            {"evidence_published_at": datetime(2026, 8, 20, 16, 5, tzinfo=SYDNEY)},
            "timing",
        ),
        (
            {"evidence_published_at": datetime(2026, 8, 19, 22, 30, tzinfo=UTC)},
            "Australia/Sydney",
        ),
    ],
)
def test_bundle_rejects_invalid_point_in_time_inputs(
    tmp_path: Path, updates: dict[str, object], message: str
) -> None:
    write_bundle(tmp_path / "gold-01", **updates)

    with pytest.raises(FrozenBundleError, match=message):
        load_frozen_case_bundle(tmp_path / "gold-01")

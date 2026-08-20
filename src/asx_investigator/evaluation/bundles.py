"""Immutable, artifact-backed inputs for production-path gold evaluation.

Frozen case bundles intentionally model the provider boundary rather than a
previous report. This keeps evaluation on the same investigation kernel used by
the product and makes a content change fail before it can become evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from asx_investigator.domain.models import EvidenceItem, EvidenceRole, InstrumentIdentity
from asx_investigator.evaluation.models import GoldCaseManifest
from asx_investigator.market.forensics import DailyBar
from asx_investigator.market.sessions import classify_event, resolve_session
from asx_investigator.providers.market import CorporateAction, MarketDataResult
from asx_investigator.providers.outcomes import ProviderOutcome
from asx_investigator.storage.artifacts import ArtifactReference

SYDNEY = ZoneInfo("Australia/Sydney")
_SHA256_HEX = set("0123456789abcdef")
_BUNDLE_VERSION = "frozen-case-v1"
_CORPUS_VERSION = "gold-frozen-v1"
_PROVIDER_SCHEMA_VERSION = "provider-outcome-v1"
_HOLDOUT_CASE_FIELDS = {"case_id", "bundle_path"}


class FrozenBundleError(ValueError):
    """A case input is not an immutable point-in-time evaluation fixture."""


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256_HEX for character in value)
    )


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FrozenBundleError(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise FrozenBundleError(f"{label} must be a non-empty string")
    return value


def _datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise FrozenBundleError(f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise FrozenBundleError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise FrozenBundleError(f"{label} must include a timezone")
    return parsed


def _is_sydney_timestamp(value: datetime) -> bool:
    """Accept only the AEST/AEDT offset applicable at a source timestamp."""

    return value.tzinfo is not None and value.utcoffset() == value.astimezone(SYDNEY).utcoffset()


def _date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise FrozenBundleError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise FrozenBundleError(f"{label} must be an ISO date") from error


def _parse_json(content: bytes, label: str) -> object:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FrozenBundleError(f"{label} must contain UTF-8 JSON") from error


def _freeze(value: object) -> object:
    """Freeze bundle metadata so a loaded fixture cannot be edited in memory."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class _ArtifactFile:
    artifact_id: str
    content: bytes
    mime_type: str

    def reference(self, *, locator: str) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=self.artifact_id,
            sha256=self.artifact_id,
            mime_type=self.mime_type,
            size_bytes=len(self.content),
            locator=locator,
        )


@dataclass(frozen=True)
class _DocumentDeclaration:
    artifact_id: str
    mime_type: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class FrozenCaseBundle:
    """A validated single-case provider snapshot held outside case memory."""

    root: Path
    case_id: str
    ticker: str
    trade_date: date
    evidence_cutoff: datetime
    instrument_data: Mapping[str, Any]
    market: Mapping[str, Any]
    corporate_actions: Mapping[str, Any]
    evidence_coverage_complete: bool
    documents: tuple[_DocumentDeclaration, ...]

    @property
    def instrument(self) -> InstrumentIdentity:
        """Return a fresh domain value so callers cannot change frozen identity."""

        return InstrumentIdentity.model_validate(self.instrument_data)

    @property
    def document_artifact_ids(self) -> list[str]:
        return [document.artifact_id for document in self.documents]

    @property
    def artifact_ids(self) -> list[str]:
        return [
            _string(self.market.get("artifact_id"), "market.artifact_id"),
            _string(
                self.corporate_actions.get("artifact_id"),
                "corporate_actions.artifact_id",
            ),
            *self.document_artifact_ids,
        ]

    def assert_request(self, ticker: str, trade_date: date) -> None:
        if ticker.upper().strip() != self.ticker or trade_date != self.trade_date:
            raise LookupError("Frozen case bundle does not cover this request")

    def _read_artifact(self, artifact_id: str, mime_type: str) -> _ArtifactFile:
        if not _is_sha256(artifact_id):
            raise FrozenBundleError("artifact IDs must be lowercase SHA-256 hashes")
        path = self.root / "artifacts" / artifact_id
        if not path.is_file():
            raise FrozenBundleError(f"required artifact is missing: {artifact_id}")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact_id:
            raise FrozenBundleError(f"artifact hash does not match declaration: {artifact_id}")
        return _ArtifactFile(artifact_id=artifact_id, content=content, mime_type=mime_type)

    def _provider_outcome(
        self,
        declaration: Mapping[str, Any],
        artifact: _ArtifactFile,
        data: list[Any],
        *,
        label: str,
    ) -> ProviderOutcome[list[Any]]:
        raw = _mapping(declaration.get("outcome"), f"{label}.outcome")
        if "data" in raw or "artifact" in raw:
            raise FrozenBundleError(f"{label}.outcome must reference artifact data only")
        provenance = _mapping(raw.get("provenance"), f"{label}.outcome.provenance")
        if provenance.get("artifact_id") != artifact.artifact_id:
            raise FrozenBundleError(f"{label}.outcome provenance does not bind its artifact")
        try:
            outcome = ProviderOutcome[list[Any]].model_validate(
                {
                    **raw,
                    "data": data,
                    "artifact": artifact.reference(locator=f"frozen:{artifact.artifact_id}"),
                }
            )
        except ValidationError as error:
            raise FrozenBundleError(
                f"{label}.outcome is invalid: {error.errors()[0]['msg']}"
            ) from error
        if not _is_sydney_timestamp(outcome.retrieved_at):
            raise FrozenBundleError(f"{label}.outcome timestamps must use Australia/Sydney time")
        if outcome.retrieved_at > self.evidence_cutoff:
            raise FrozenBundleError(f"{label}.outcome has invalid point-in-time timing")
        if not outcome.source_version:
            raise FrozenBundleError(f"{label}.outcome must declare source_version")
        return outcome

    def market_result(self) -> MarketDataResult:
        artifact = self._read_artifact(
            _string(self.market.get("artifact_id"), "market.artifact_id"),
            "application/json",
        )
        raw_bars = _parse_json(artifact.content, "market artifact")
        if not isinstance(raw_bars, list):
            raise FrozenBundleError("market artifact must contain a daily-bar array")
        bars = [_daily_bar(item, "market artifact") for item in raw_bars]
        if len(bars) < 2 or bars[-1].trade_date != self.trade_date:
            raise FrozenBundleError("market artifact must end at the requested ASX session")
        if any(item.trade_date > self.trade_date for item in bars) or any(
            right.trade_date <= left.trade_date for left, right in zip(bars, bars[1:])
        ):
            raise FrozenBundleError(
                "market artifact bars must be ordered, unique and point-in-time"
            )
        outcome = self._provider_outcome(self.market, artifact, bars, label="market")
        return MarketDataResult(
            bars=bars,
            selected_provider=_string(
                self.market.get("selected_provider"), "market.selected_provider"
            ),
            outcomes=[outcome],
        )

    def corporate_action_outcome(self) -> ProviderOutcome[list[CorporateAction]]:
        artifact = self._read_artifact(
            _string(
                self.corporate_actions.get("artifact_id"),
                "corporate_actions.artifact_id",
            ),
            "application/json",
        )
        raw_actions = _parse_json(artifact.content, "corporate actions artifact")
        if not isinstance(raw_actions, list):
            raise FrozenBundleError("corporate actions artifact must contain an array")
        try:
            actions = [CorporateAction.model_validate(item) for item in raw_actions]
        except ValidationError as error:
            raise FrozenBundleError("corporate actions artifact is invalid") from error
        return self._provider_outcome(
            self.corporate_actions,
            artifact,
            actions,
            label="corporate_actions",
        )

    def evidence_items(self) -> list[EvidenceItem]:
        evidence = [self._evidence_item(document) for document in self.documents]
        evidence_ids = [item.evidence_id for item in evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise FrozenBundleError("evidence IDs must be unique within a frozen bundle")
        return evidence

    def _evidence_item(self, document: _DocumentDeclaration) -> EvidenceItem:
        artifact = self._read_artifact(document.artifact_id, document.mime_type)
        try:
            passage = artifact.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FrozenBundleError("document artifact must be UTF-8 text") from error
        raw = document.metadata
        if raw.get("content_hash") != artifact.artifact_id:
            raise FrozenBundleError(
                "evidence metadata content hash does not match document artifact"
            )
        source_url = raw.get("source_url")
        if not isinstance(source_url, str) or urlparse(source_url).scheme != "https":
            raise FrozenBundleError("evidence metadata requires an HTTPS source URL")
        if "passage" in raw:
            raise FrozenBundleError("evidence passage must come from the frozen artifact")
        try:
            evidence = EvidenceItem.model_validate({**raw, "passage": passage})
        except ValidationError as error:
            raise FrozenBundleError(
                f"evidence metadata is invalid: {error.errors()[0]['msg']}"
            ) from error
        if not all(
            _is_sydney_timestamp(value) for value in (evidence.published_at, evidence.retrieved_at)
        ):
            raise FrozenBundleError("evidence timestamps must use Australia/Sydney time")
        if (
            evidence.published_at > evidence.retrieved_at
            or evidence.retrieved_at > self.evidence_cutoff
        ):
            raise FrozenBundleError("evidence metadata has invalid point-in-time timing")
        if evidence.published_at > self.evidence_cutoff:
            raise FrozenBundleError("evidence metadata is published after the evidence cutoff")
        if (
            evidence.role == EvidenceRole.CAUSAL_INPUT
            and not classify_event(
                evidence.published_at, resolve_session(self.trade_date)
            ).eligible_same_day_cause
        ):
            raise FrozenBundleError("causal evidence has invalid ASX-session timing")
        return evidence


@dataclass(frozen=True)
class FrozenCaseGateway:
    """The normal investigation provider protocol backed by one frozen bundle."""

    bundle: FrozenCaseBundle

    async def resolve_instrument(self, ticker: str) -> InstrumentIdentity:
        self.bundle.assert_request(ticker, self.bundle.trade_date)
        return self.bundle.instrument

    async def get_daily_bars(self, ticker: str, trade_date: date) -> list[DailyBar]:
        self.bundle.assert_request(ticker, trade_date)
        return list(self.bundle.market_result().bars)

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult:
        self.bundle.assert_request(ticker, trade_date)
        return self.bundle.market_result()

    async def get_benchmark_return(self, trade_date: date) -> float | None:
        self.bundle.assert_request(self.bundle.ticker, trade_date)
        value = self.bundle.market.get("benchmark_return")
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise FrozenBundleError("market.benchmark_return must be a finite number or null")
        return float(value)

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]:
        self.bundle.assert_request(ticker, trade_date)
        return self.bundle.corporate_action_outcome()

    async def get_evidence(self, ticker: str, trade_date: date) -> list[EvidenceItem]:
        self.bundle.assert_request(ticker, trade_date)
        return self.bundle.evidence_items()

    async def targeted_retrieve(
        self,
        ticker: str,
        trade_date: date,
        query: str,
        purpose: str,
    ) -> list[EvidenceItem]:
        self.bundle.assert_request(ticker, trade_date)
        del query, purpose
        return []

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date) -> bool:
        self.bundle.assert_request(ticker, trade_date)
        return self.bundle.evidence_coverage_complete


@dataclass(frozen=True)
class FrozenGoldCorpus:
    kind: Literal["development", "holdout"]
    corpus_version: str
    bundles: tuple[FrozenCaseBundle, ...]
    manifests: dict[str, GoldCaseManifest]


def load_frozen_case_bundle(root: Path) -> FrozenCaseBundle:
    """Load and exhaustively validate one bundle before exposing any provider data."""

    path = root / "bundle.json"
    if not path.is_file():
        raise FrozenBundleError(f"bundle is missing: {path}")
    raw = _mapping(_parse_json(path.read_bytes(), "bundle"), "bundle")
    if "report" in raw or "prebuilt_report" in raw:
        raise FrozenBundleError("prebuilt reports are not valid frozen execution inputs")
    if raw.get("bundle_version") != _BUNDLE_VERSION:
        raise FrozenBundleError(f"bundle_version must be {_BUNDLE_VERSION}")
    if raw.get("provider_schema_version") != _PROVIDER_SCHEMA_VERSION:
        raise FrozenBundleError("provider schema version is not supported")
    ticker = _string(raw.get("ticker"), "ticker").upper().strip()
    trade_date = _date(raw.get("trade_date"), "trade_date")
    session = resolve_session(trade_date)
    if not session.is_trading_day:
        raise FrozenBundleError("trade_date must be an ASX trading session")
    if raw.get("timezone") != "Australia/Sydney":
        raise FrozenBundleError("bundle timezone must be Australia/Sydney")
    evidence_cutoff = _datetime(raw.get("evidence_cutoff"), "evidence_cutoff")
    if not _is_sydney_timestamp(evidence_cutoff):
        raise FrozenBundleError("evidence_cutoff must use Australia/Sydney time")
    assert session.market_close is not None
    local_cutoff = evidence_cutoff.astimezone(SYDNEY)
    if local_cutoff.date() != trade_date or local_cutoff < session.market_close:
        raise FrozenBundleError("evidence_cutoff must be after the requested ASX session close")
    try:
        instrument = InstrumentIdentity.model_validate(
            _mapping(raw.get("instrument"), "instrument")
        )
    except ValidationError as error:
        raise FrozenBundleError(f"instrument is invalid: {error.errors()[0]['msg']}") from error
    if (
        instrument.asx_code.upper() != ticker
        or instrument.exchange != "ASX"
        or instrument.currency != "AUD"
    ):
        raise FrozenBundleError("instrument must be an ASX instrument quoted in AUD")
    market = _mapping(raw.get("market"), "market")
    corporate_actions = _mapping(raw.get("corporate_actions"), "corporate_actions")
    evidence = _mapping(raw.get("evidence"), "evidence")
    if not isinstance(evidence.get("coverage_complete"), bool):
        raise FrozenBundleError("evidence.coverage_complete must be boolean")
    raw_documents = evidence.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise FrozenBundleError("evidence.documents must contain at least one artifact")
    documents: list[_DocumentDeclaration] = []
    for index, raw_document in enumerate(raw_documents):
        document = _mapping(raw_document, f"evidence.documents[{index}]")
        artifact_id = _string(
            document.get("artifact_id"), f"evidence.documents[{index}].artifact_id"
        )
        documents.append(
            _DocumentDeclaration(
                artifact_id=artifact_id,
                mime_type=_string(
                    document.get("mime_type"), f"evidence.documents[{index}].mime_type"
                ),
                metadata=cast(
                    Mapping[str, Any],
                    _freeze(
                        _mapping(
                            document.get("metadata"),
                            f"evidence.documents[{index}].metadata",
                        )
                    ),
                ),
            )
        )
    bundle = FrozenCaseBundle(
        root=root,
        case_id=_string(raw.get("case_id"), "case_id"),
        ticker=ticker,
        trade_date=trade_date,
        evidence_cutoff=evidence_cutoff,
        instrument_data=cast(Mapping[str, Any], _freeze(instrument.model_dump(mode="json"))),
        market=cast(Mapping[str, Any], _freeze(market)),
        corporate_actions=cast(Mapping[str, Any], _freeze(corporate_actions)),
        evidence_coverage_complete=evidence["coverage_complete"],
        documents=tuple(documents),
    )
    # Force all content and outcome/evidence metadata validation at admission. The
    # gateway repeats it on access to detect mutation after the initial load.
    bundle.market_result()
    bundle.corporate_action_outcome()
    bundle.evidence_items()
    return bundle


def load_frozen_gold_corpus(
    root: Path, *, kind: Literal["development", "holdout"]
) -> FrozenGoldCorpus:
    """Load an external corpus without admitting holdout labels to execution."""

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FrozenBundleError(f"gold manifest is missing: {manifest_path}")
    payload = _mapping(_parse_json(manifest_path.read_bytes(), "gold manifest"), "gold manifest")
    if payload.get("schema_version") != _CORPUS_VERSION:
        raise FrozenBundleError(f"schema_version must be {_CORPUS_VERSION}")
    corpus_version = _string(payload.get("corpus_version"), "corpus_version")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise FrozenBundleError("gold manifest must contain at least one case")
    bundles: list[FrozenCaseBundle] = []
    manifests: dict[str, GoldCaseManifest] = {}
    case_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        case = _mapping(raw_case, f"cases[{index}]")
        case_id = _string(case.get("case_id"), f"cases[{index}].case_id")
        if case_id in case_ids:
            raise FrozenBundleError("gold manifest case IDs must be unique")
        case_ids.add(case_id)
        bundle_path = _string(case.get("bundle_path"), f"cases[{index}].bundle_path")
        relative = Path(bundle_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise FrozenBundleError("bundle_path must stay within the gold root")
        bundle = load_frozen_case_bundle(root / relative)
        if bundle.case_id != case_id:
            raise FrozenBundleError("manifest case_id does not match its frozen bundle")
        if kind == "holdout":
            unexpected = sorted(set(case) - _HOLDOUT_CASE_FIELDS)
            if unexpected:
                raise FrozenBundleError(
                    "holdout manifest must not contain sealed labels or case metadata"
                )
        else:
            try:
                manifest = GoldCaseManifest.model_validate(case)
            except ValidationError as error:
                raise FrozenBundleError(
                    f"development manifest case {case_id} is invalid: {error.errors()[0]['msg']}"
                ) from error
            if (
                manifest.ticker.upper() != bundle.ticker
                or manifest.trade_date != bundle.trade_date
                or manifest.timezone != "Australia/Sydney"
                or manifest.evidence_cutoff != bundle.evidence_cutoff
                or set(manifest.artifact_ids) != set(bundle.artifact_ids)
            ):
                raise FrozenBundleError(
                    "development manifest does not match frozen bundle provenance"
                )
            manifests[case_id] = manifest
        bundles.append(bundle)
    return FrozenGoldCorpus(
        kind=kind,
        corpus_version=corpus_version,
        bundles=tuple(bundles),
        manifests=manifests,
    )


def _daily_bar(raw: object, label: str) -> DailyBar:
    item = _mapping(raw, label)
    try:
        bar = DailyBar(
            trade_date=_date(item.get("trade_date"), f"{label}.trade_date"),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            adjusted_close=float(item["adjusted_close"]),
            volume=int(item["volume"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FrozenBundleError(f"{label} has an invalid daily bar") from error
    values = (bar.open, bar.high, bar.low, bar.close, bar.adjusted_close)
    if not all(math.isfinite(value) and value > 0 for value in values) or bar.volume < 0:
        raise FrozenBundleError(f"{label} has non-finite or invalid daily-bar values")
    return bar

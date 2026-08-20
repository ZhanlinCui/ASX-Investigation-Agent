from __future__ import annotations

from typing import Protocol

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from asx_investigator.domain.models import EvidenceItem, MarketMove
from asx_investigator.settings import Settings


class NarrativeDraft(BaseModel):
    primary_evidence_id: str
    explanation: str = Field(min_length=20, max_length=520)
    competing_explanation: str | None = Field(default=None, max_length=300)


class NarrativeGenerator(Protocol):
    async def explain(
        self, ticker: str, move: MarketMove, evidence: list[EvidenceItem]
    ) -> NarrativeDraft | None: ...


class GeminiNarrativeGenerator:
    """Gemini-backed synthesis constrained to the supplied evidence packet.

    This class is intentionally incapable of fetching data. Market/evidence tools
    establish facts first; Gemini can only express an evidence-cited hypothesis.
    """

    def __init__(self, settings: Settings) -> None:
        self.model = settings.gemini_model
        self.client = (
            genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        )

    async def explain(
        self, ticker: str, move: MarketMove, evidence: list[EvidenceItem]
    ) -> NarrativeDraft | None:
        if self.client is None or not evidence:
            return None
        evidence_packet = [
            {
                "evidence_id": item.evidence_id,
                "published_at": item.published_at.isoformat(),
                "source": item.source_name,
                "authority": item.authority,
                "title": item.title,
                "passage": item.passage,
            }
            for item in evidence
        ]
        prompt = (
            "Explain an ASX price move using only the evidence packet. Do not invent "
            "facts, dates, numbers, or sources. Select one supplied evidence_id. State "
            "uncertainty if the evidence does not prove causation. All returns are percent, "
            "all money is AUD, and the session timezone is Australia/Sydney.\n\n"
            f"Ticker: {ticker}\n"
            f"Market move: close return {move.close_return_pct:+.2f}%; "
            f"open gap {move.open_gap_pct:+.2f}%; turnover AUD {move.turnover_aud:,.0f}.\n"
            f"Evidence packet: {evidence_packet}"
        )
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are an evidence-bound market-investigation analyst. Return valid JSON "
                    "matching the requested schema."
                ),
                response_mime_type="application/json",
                response_schema=NarrativeDraft,
                temperature=0.1,
            ),
        )
        if not response.text:
            return None
        return NarrativeDraft.model_validate_json(response.text)

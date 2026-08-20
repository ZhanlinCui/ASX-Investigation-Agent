from __future__ import annotations

from asx_investigator.providers.outcomes import ProviderOutcome


class DataProviderUnavailable(RuntimeError):
    """A configured provider cannot safely satisfy a required capability."""

    def __init__(
        self,
        message: str,
        *,
        outcomes: list[ProviderOutcome[object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.outcomes = outcomes or []

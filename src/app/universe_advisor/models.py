"""Data models for Universe Advisor."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class MarketRegime(str, Enum):
    """Market regime classification."""

    BULL_LOW_VOL = "bull_low_vol"
    BULL_HIGH_VOL = "bull_high_vol"
    BEAR_LOW_VOL = "bear_low_vol"
    BEAR_HIGH_VOL = "bear_high_vol"
    UNKNOWN = "unknown"


@dataclass
class RegimeData:
    """Market regime detection result."""

    regime: MarketRegime
    spy_price: float
    spy_ma50: float
    trend: Literal["bull", "bear"]
    volatility: Literal["low", "medium", "high"]
    volatility_value: float  # Annualized std-dev
    confidence: float  # 0.0-1.0
    timestamp: str  # ISO format


ProposalStatus = Literal["NEW", "APPROVED", "REJECTED", "APPLIED", "EXPIRED"]


class ProposalType(str, Enum):
    """Type of universe proposal."""

    SECTOR_TOGGLE = "sector_toggle"  # Enable/disable entire sector
    CONSTITUENT_CHANGE = "constituent_change"  # Add/remove tickers from sector


class ConstituentChangeAction(str, Enum):
    """Action for constituent change."""

    ADD = "add"
    REMOVE = "remove"


@dataclass
class ConstituentChange:
    """Constituent add/remove change details."""

    action: ConstituentChangeAction
    tickers: list[str]
    reason: str
    constraints_checked: bool = True  # Whether validation was performed


@dataclass
class Proposal:
    """Universe change proposal (sector toggle or constituent change)."""

    proposal_id: str  # UUID
    sector_name: str
    confidence: float  # 0.0-1.0
    rationale: str  # LLM explanation
    supporting_headlines: list[str]  # Top 3-5 headlines
    provider: str  # "openai", "anthropic", "ensemble", "manual"
    created_at: str  # ISO timestamp
    expires_at: str  # ISO timestamp
    status: ProposalStatus
    proposal_type: ProposalType = ProposalType.SECTOR_TOGGLE
    recommended_enabled: bool | None = None  # For SECTOR_TOGGLE
    constituent_change: ConstituentChange | None = None  # For CONSTITUENT_CHANGE


@dataclass
class Disagreement:
    """Recorded provider disagreement (not actionable)."""

    disagreement_id: str  # UUID
    sector_name: str
    provider_a: str
    recommendation_a: bool
    confidence_a: float
    provider_b: str
    recommendation_b: bool
    confidence_b: float
    created_at: str


@dataclass
class ProposalSet:
    """Complete set of proposals from one generation run."""

    generation_id: str  # UUID
    proposals: list[Proposal]
    disagreements: list[Disagreement]
    regime: RegimeData
    headline_count: int
    generated_at: str

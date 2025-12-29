"""Base strategy interface for position intent generation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PositionIntent:
    """
    Represents a desired position state for a symbol.

    This is NOT an order - it's an intent that can be later
    translated into actual orders by an execution layer.
    """

    symbol: str
    target_quantity: int  # Target position size (positive for long, negative for short, 0 for flat)
    conviction: float  # Signal strength/conviction (0.0 to 1.0)
    reason: str  # Human-readable reason for this intent


class Strategy(ABC):
    """
    Base class for all trading strategies.

    Strategies analyze market data and output position intents
    (desired target positions), not direct orders.
    """

    def __init__(self, name: str):
        """
        Initialize strategy.

        Args:
            name: Strategy identifier
        """
        self.name = name

    @abstractmethod
    def generate_intents(self, universe: list[str], market_data: dict) -> list[PositionIntent]:
        """
        Generate position intents for the given universe.

        Args:
            universe: List of symbols to analyze
            market_data: Dictionary of symbol -> price/indicator data
                Example: {"SPY": {"price": 450.0, "sma_20": 445.0, ...}}

        Returns:
            List of PositionIntent objects
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"

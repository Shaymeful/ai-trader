"""Tests for exit advisor integration."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.app.exit_advisor import ExitAdvisor, ExitCandidate
from src.app.sell_scanner import SellScanner, SellSignal


def test_exit_advisor_initialization():
    """Test that ExitAdvisor can be initialized with a SellScanner."""
    # Create mock sell scanner
    mock_scanner = Mock(spec=SellScanner)
    mock_scanner.llm_provider = None

    # Initialize exit advisor
    advisor = ExitAdvisor(
        sell_scanner=mock_scanner,
        cooldown_hours=4,
        output_dir=Path("out/test_exit_advisor")
    )

    assert advisor.sell_scanner is mock_scanner
    assert advisor.cooldown_hours == 4
    assert advisor.output_dir == Path("out/test_exit_advisor")


def test_exit_advisor_scan_with_no_positions():
    """Test exit advisor returns empty list when no positions."""
    # Create mock sell scanner
    mock_scanner = Mock(spec=SellScanner)
    mock_scanner.llm_provider = None

    # Initialize exit advisor
    advisor = ExitAdvisor(
        sell_scanner=mock_scanner,
        cooldown_hours=4,
        output_dir=Path("out/test_exit_advisor")
    )

    # Scan with no positions
    candidates = advisor.scan_and_emit_candidates(
        current_positions={},
        market_data={},
        news_events=None,
        market_regime="bull_low_vol"
    )

    assert candidates == []
    # Sell scanner should not be called if no positions
    mock_scanner.scan_positions.assert_not_called()


def test_exit_advisor_generates_candidates(tmp_path):
    """Test exit advisor generates candidates from sell signals."""
    # Create mock sell scanner
    mock_scanner = Mock(spec=SellScanner)
    mock_scanner.llm_provider = None
    mock_scanner.llm_model = "gpt-4o-mini"

    # Mock sell signal
    mock_signal = SellSignal(
        symbol="AAPL",
        action="SELL_HALF",
        confidence=0.75,
        primary_reason="Trend breakdown",
        detailed_reasoning=["Price below MA20"],
        supporting_evidence=["AAPL -3.8% below MA20"],
        invalidation_criteria="Price recovers above MA20",
        expected_value=None,
        risk_regime="bear_low_vol",
        timestamp=datetime.now(UTC).isoformat()
    )

    # Mock scan result
    mock_scan_result = Mock()
    mock_scan_result.sell_signals = [mock_signal]
    mock_scan_result.scan_id = "test-scan-123"

    mock_scanner.scan_positions.return_value = mock_scan_result

    # Initialize exit advisor with temp output dir
    advisor = ExitAdvisor(
        sell_scanner=mock_scanner,
        cooldown_hours=4,
        output_dir=tmp_path / "exit_advisor"
    )

    # Scan with one position
    candidates = advisor.scan_and_emit_candidates(
        current_positions={"AAPL": (100, 150.0)},
        market_data={"AAPL": {"close": 145.0}},
        news_events=None,
        market_regime="bear_low_vol"
    )

    # Should generate 1 candidate
    assert len(candidates) == 1
    assert candidates[0].symbol == "AAPL"
    assert candidates[0].action == "sell"
    assert candidates[0].confidence == 0.75
    assert "SELL_HALF" in candidates[0].reason

    # Sell scanner should be called
    mock_scanner.scan_positions.assert_called_once()


def test_exit_advisor_filters_low_confidence(tmp_path):
    """Test exit advisor filters signals below confidence threshold."""
    # Create mock sell scanner
    mock_scanner = Mock(spec=SellScanner)
    mock_scanner.llm_provider = None
    mock_scanner.llm_model = "gpt-4o-mini"

    # Mock low-confidence signal
    mock_signal = SellSignal(
        symbol="AAPL",
        action="SELL_HALF",
        confidence=0.50,  # Below 0.60 threshold
        primary_reason="Weak signal",
        detailed_reasoning=[],
        supporting_evidence=[],
        invalidation_criteria="Signal strengthens",
        expected_value=None,
        risk_regime="bear_low_vol",
        timestamp=datetime.now(UTC).isoformat()
    )

    # Mock scan result
    mock_scan_result = Mock()
    mock_scan_result.sell_signals = [mock_signal]
    mock_scan_result.scan_id = "test-scan-123"

    mock_scanner.scan_positions.return_value = mock_scan_result

    # Initialize exit advisor
    advisor = ExitAdvisor(
        sell_scanner=mock_scanner,
        cooldown_hours=4,
        output_dir=tmp_path / "exit_advisor"
    )

    # Scan with one position
    candidates = advisor.scan_and_emit_candidates(
        current_positions={"AAPL": (100, 150.0)},
        market_data={"AAPL": {"close": 145.0}},
        news_events=None,
        market_regime="bear_low_vol"
    )

    # Should filter out low confidence signal
    assert len(candidates) == 0


def test_exit_advisor_filters_hold_signals(tmp_path):
    """Test exit advisor filters HOLD signals."""
    # Create mock sell scanner
    mock_scanner = Mock(spec=SellScanner)
    mock_scanner.llm_provider = None
    mock_scanner.llm_model = "gpt-4o-mini"

    # Mock HOLD signal
    mock_signal = SellSignal(
        symbol="AAPL",
        action="HOLD",
        confidence=0.80,
        primary_reason="Position looks good",
        detailed_reasoning=["Strong trend intact"],
        supporting_evidence=["Price above MA20"],
        invalidation_criteria="Trend breaks down",
        expected_value=None,
        risk_regime="bull_low_vol",
        timestamp=datetime.now(UTC).isoformat()
    )

    # Mock scan result
    mock_scan_result = Mock()
    mock_scan_result.sell_signals = [mock_signal]
    mock_scan_result.scan_id = "test-scan-123"

    mock_scanner.scan_positions.return_value = mock_scan_result

    # Initialize exit advisor
    advisor = ExitAdvisor(
        sell_scanner=mock_scanner,
        cooldown_hours=4,
        output_dir=tmp_path / "exit_advisor"
    )

    # Scan with one position
    candidates = advisor.scan_and_emit_candidates(
        current_positions={"AAPL": (100, 150.0)},
        market_data={"AAPL": {"close": 145.0}},
        news_events=None,
        market_regime="bull_low_vol"
    )

    # Should filter out HOLD signal
    assert len(candidates) == 0


def test_exit_advisor_cooldown_prevents_rescans(tmp_path):
    """Test exit advisor respects cooldown period."""
    # Create mock sell scanner
    mock_scanner = Mock(spec=SellScanner)
    mock_scanner.llm_provider = None
    mock_scanner.llm_model = "gpt-4o-mini"

    # Mock sell signal
    mock_signal = SellSignal(
        symbol="AAPL",
        action="SELL_HALF",
        confidence=0.75,
        primary_reason="Trend breakdown",
        detailed_reasoning=["Price below MA20"],
        supporting_evidence=["AAPL -3.8% below MA20"],
        invalidation_criteria="Price recovers above MA20",
        expected_value=None,
        risk_regime="bear_low_vol",
        timestamp=datetime.now(UTC).isoformat()
    )

    # Mock scan result
    mock_scan_result = Mock()
    mock_scan_result.sell_signals = [mock_signal]
    mock_scan_result.scan_id = "test-scan-123"

    mock_scanner.scan_positions.return_value = mock_scan_result

    # Initialize exit advisor
    advisor = ExitAdvisor(
        sell_scanner=mock_scanner,
        cooldown_hours=4,
        output_dir=tmp_path / "exit_advisor"
    )

    # First scan
    candidates1 = advisor.scan_and_emit_candidates(
        current_positions={"AAPL": (100, 150.0)},
        market_data={"AAPL": {"close": 145.0}},
        news_events=None,
        market_regime="bear_low_vol"
    )

    assert len(candidates1) == 1
    assert mock_scanner.scan_positions.call_count == 1

    # Second scan immediately after (should skip due to cooldown)
    candidates2 = advisor.scan_and_emit_candidates(
        current_positions={"AAPL": (100, 150.0)},
        market_data={"AAPL": {"close": 145.0}},
        news_events=None,
        market_regime="bear_low_vol"
    )

    # Should return empty due to cooldown (no positions to scan)
    assert len(candidates2) == 0
    # Scan should not be called again
    assert mock_scanner.scan_positions.call_count == 1

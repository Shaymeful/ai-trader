"""Tests for ticker validation."""

from src.app.selector.ticker_validation import TickerValidator


def test_validator_accepts_valid_ticker():
    """Test that validator accepts valid ticker symbols."""
    validator = TickerValidator()

    # Valid tickers
    assert validator.validate("AAPL") == (True, None)
    assert validator.validate("ROK") == (True, None)
    assert validator.validate("ABB") == (True, None)
    assert validator.validate("MSFT") == (True, None)
    assert validator.validate("TSLA") == (True, None)


def test_validator_rejects_stopword():
    """Test that validator rejects common stopwords."""
    validator = TickerValidator()

    # Stopwords
    is_valid, reason = validator.validate("CEO")
    assert not is_valid
    assert "Stopword" in reason

    is_valid, reason = validator.validate("AI")
    assert not is_valid
    assert "Stopword" in reason

    is_valid, reason = validator.validate("USA")
    assert not is_valid
    assert "Stopword" in reason


def test_validator_rejects_invalid_format():
    """Test that validator rejects invalid formats."""
    validator = TickerValidator()

    # Too long
    is_valid, reason = validator.validate("TOOLONG")
    assert not is_valid
    assert "Invalid format" in reason

    # Lowercase is normalized to uppercase and accepted
    is_valid, reason = validator.validate("aapl")
    assert is_valid  # Normalized to AAPL

    # Numbers
    is_valid, reason = validator.validate("A123")
    assert not is_valid
    assert "Invalid format" in reason

    # Empty
    is_valid, reason = validator.validate("")
    assert not is_valid
    assert "Invalid format" in reason


def test_validator_custom_stopwords():
    """Test validator with custom stopwords."""
    custom_stopwords = {"FAKE", "TEST", "DUMMY"}
    validator = TickerValidator(stopwords=custom_stopwords)

    # Custom stopword
    is_valid, reason = validator.validate("FAKE")
    assert not is_valid
    assert "Stopword" in reason

    # Valid ticker not in custom stopwords
    assert validator.validate("CEO") == (True, None)  # Not in custom stopwords

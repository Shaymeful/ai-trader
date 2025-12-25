"""Tests for Alpaca credential management with mode-specific env vars."""

import pytest

from src.app.config import get_alpaca_credentials, validate_alpaca_credentials


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment of all Alpaca credentials."""
    monkeypatch.delenv("ALPACA_PAPER_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_LIVE_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_LIVE_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_BASE_URL", raising=False)


def test_paper_mode_uses_paper_credentials(clean_env, monkeypatch):
    """Test that paper mode loads paper-specific credentials."""
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_PAPER_TEST")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "SECRET_PAPER_TEST")

    api_key, secret_key, base_url = get_alpaca_credentials("paper")

    assert api_key == "PK_PAPER_TEST"
    assert secret_key == "SECRET_PAPER_TEST"
    assert base_url == "https://paper-api.alpaca.markets"


def test_live_mode_uses_live_credentials(clean_env, monkeypatch):
    """Test that live mode loads live-specific credentials."""
    monkeypatch.setenv("ALPACA_LIVE_KEY_ID", "AK_LIVE_TEST")
    monkeypatch.setenv("ALPACA_LIVE_SECRET_KEY", "SECRET_LIVE_TEST")

    api_key, secret_key, base_url = get_alpaca_credentials("live")

    assert api_key == "AK_LIVE_TEST"
    assert secret_key == "SECRET_LIVE_TEST"
    assert base_url == "https://api.alpaca.markets"


def test_paper_mode_falls_back_to_legacy_vars(clean_env, monkeypatch):
    """Test that paper mode falls back to legacy ALPACA_API_KEY if mode-specific vars not set."""
    monkeypatch.setenv("ALPACA_API_KEY", "LEGACY_KEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "LEGACY_SECRET")

    api_key, secret_key, base_url = get_alpaca_credentials("paper")

    assert api_key == "LEGACY_KEY"
    assert secret_key == "LEGACY_SECRET"
    assert base_url == "https://paper-api.alpaca.markets"


def test_live_mode_falls_back_to_legacy_vars(clean_env, monkeypatch):
    """Test that live mode falls back to legacy ALPACA_API_KEY if mode-specific vars not set."""
    monkeypatch.setenv("ALPACA_API_KEY", "LEGACY_KEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "LEGACY_SECRET")

    api_key, secret_key, base_url = get_alpaca_credentials("live")

    assert api_key == "LEGACY_KEY"
    assert secret_key == "LEGACY_SECRET"
    assert base_url == "https://api.alpaca.markets"


def test_mode_specific_vars_take_precedence_over_legacy(clean_env, monkeypatch):
    """Test that mode-specific vars take precedence over legacy vars."""
    # Set both legacy and mode-specific vars
    monkeypatch.setenv("ALPACA_API_KEY", "LEGACY_KEY")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "LEGACY_SECRET")
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_PAPER_KEY")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "PAPER_SECRET")

    api_key, secret_key, base_url = get_alpaca_credentials("paper")

    # Should use paper-specific vars, not legacy
    assert api_key == "PK_PAPER_KEY"
    assert secret_key == "PAPER_SECRET"


def test_paper_and_live_credentials_can_coexist(clean_env, monkeypatch):
    """Test that paper and live credentials can coexist without interfering."""
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_PAPER")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "PAPER_SECRET")
    monkeypatch.setenv("ALPACA_LIVE_KEY_ID", "AK_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_SECRET_KEY", "LIVE_SECRET")

    # Get paper credentials
    paper_key, paper_secret, paper_url = get_alpaca_credentials("paper")
    assert paper_key == "PK_PAPER"
    assert paper_secret == "PAPER_SECRET"
    assert paper_url == "https://paper-api.alpaca.markets"

    # Get live credentials
    live_key, live_secret, live_url = get_alpaca_credentials("live")
    assert live_key == "AK_LIVE"
    assert live_secret == "LIVE_SECRET"
    assert live_url == "https://api.alpaca.markets"


def test_validation_passes_with_valid_paper_credentials(clean_env, monkeypatch):
    """Test that validation passes when paper credentials are set."""
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_PAPER")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "PAPER_SECRET")

    is_valid, error_msg = validate_alpaca_credentials("paper", require_credentials=True)

    assert is_valid is True
    assert error_msg == ""


def test_validation_passes_with_valid_live_credentials(clean_env, monkeypatch):
    """Test that validation passes when live credentials are set."""
    monkeypatch.setenv("ALPACA_LIVE_KEY_ID", "AK_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_SECRET_KEY", "LIVE_SECRET")

    is_valid, error_msg = validate_alpaca_credentials("live", require_credentials=True)

    assert is_valid is True
    assert error_msg == ""


def test_validation_fails_with_missing_paper_credentials(clean_env, monkeypatch):
    """Test that validation fails with helpful message when paper credentials are missing."""
    # No credentials set
    is_valid, error_msg = validate_alpaca_credentials("paper", require_credentials=True)

    assert is_valid is False
    assert "ERROR" in error_msg
    assert "ALPACA_PAPER_KEY_ID" in error_msg
    assert "ALPACA_PAPER_SECRET_KEY" in error_msg
    assert "PowerShell" in error_msg  # Should include Windows example


def test_validation_fails_with_missing_live_credentials(clean_env, monkeypatch):
    """Test that validation fails with helpful message when live credentials are missing."""
    # No credentials set
    is_valid, error_msg = validate_alpaca_credentials("live", require_credentials=True)

    assert is_valid is False
    assert "ERROR" in error_msg
    assert "ALPACA_LIVE_KEY_ID" in error_msg
    assert "ALPACA_LIVE_SECRET_KEY" in error_msg
    assert "REAL MONEY" in error_msg
    assert "PowerShell" in error_msg  # Should include Windows example


def test_mock_mode_does_not_require_credentials(clean_env, monkeypatch):
    """Test that mock/dry-run mode does not require credentials."""
    # No credentials set
    is_valid, error_msg = validate_alpaca_credentials("mock", require_credentials=True)

    assert is_valid is True
    assert error_msg == ""


def test_dry_run_mode_does_not_require_credentials(clean_env, monkeypatch):
    """Test that dry-run mode does not require credentials."""
    # No credentials set
    is_valid, error_msg = validate_alpaca_credentials("dry-run", require_credentials=True)

    assert is_valid is True
    assert error_msg == ""


def test_base_url_can_be_overridden(clean_env, monkeypatch):
    """Test that ALPACA_BASE_URL env var can override default base URLs."""
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_PAPER")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "PAPER_SECRET")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://custom-api.example.com")

    api_key, secret_key, base_url = get_alpaca_credentials("paper")

    assert base_url == "https://custom-api.example.com"


def test_check_env_integration(clean_env, monkeypatch):
    """Integration test for --check-env command."""
    from src.app.__main__ import run_check_env

    # Set valid paper credentials
    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_TEST1234")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "SECRET_TEST")

    # Should return 0 (success)
    exit_code = run_check_env("paper")
    assert exit_code == 0


def test_check_env_fails_with_missing_credentials(clean_env, monkeypatch, capsys):
    """Test that --check-env fails with missing credentials."""
    from src.app.__main__ import run_check_env

    # No credentials set
    exit_code = run_check_env("paper")
    assert exit_code == 1

    # Should print helpful error message
    captured = capsys.readouterr()
    assert "ALPACA_PAPER_KEY_ID" in captured.out
    assert "ALPACA_PAPER_SECRET_KEY" in captured.out


def test_check_env_in_dry_run_mode_succeeds(clean_env, monkeypatch):
    """Test that --check-env succeeds in dry-run mode without credentials."""
    from src.app.__main__ import run_check_env

    # No credentials needed for dry-run
    exit_code = run_check_env("dry-run")
    assert exit_code == 0


def test_check_env_shows_key_fingerprint_not_full_secret(clean_env, monkeypatch, capsys):
    """Test that --check-env shows only last 4 chars of API key, never shows secret."""
    from src.app.__main__ import run_check_env

    monkeypatch.setenv("ALPACA_PAPER_KEY_ID", "PK_ABCD1234")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "SECRET_SHOULD_NOT_APPEAR")

    exit_code = run_check_env("paper")
    assert exit_code == 0

    captured = capsys.readouterr()
    # Should show last 4 chars of API key
    assert "...1234" in captured.out
    # Should NEVER show the actual secret
    assert "SECRET_SHOULD_NOT_APPEAR" not in captured.out
    # Should show masked secret
    assert "...****" in captured.out

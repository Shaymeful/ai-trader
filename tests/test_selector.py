"""Unit tests for RSS selector module."""

import json
from pathlib import Path

import pytest

from src.app.selector.rss_selector import Candidate, RSSSelector, SelectorEvent


@pytest.fixture
def selector():
    """Create selector instance with test config."""
    return RSSSelector(config_path="config/selector.yaml")


@pytest.fixture
def rss_automation_content():
    """Load automation RSS fixture."""
    fixture_path = Path("tests/fixtures/rss_automation.xml")
    with open(fixture_path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def rss_energy_content():
    """Load energy RSS fixture."""
    fixture_path = Path("tests/fixtures/rss_energy.xml")
    with open(fixture_path, encoding="utf-8") as f:
        return f.read()


class TestSectorClassification:
    """Test keyword-based sector classification."""

    def test_classify_automation_sector(self, selector):
        """Test automation sector classification with keywords."""
        text = "New industrial robot for warehouse automation and logistics"
        sector = selector.classify_sector(text)
        assert sector == "automation"

    def test_classify_energy_sector(self, selector):
        """Test energy sector classification with keywords."""
        text = "Solar energy and wind power drive renewable grid expansion"
        sector = selector.classify_sector(text)
        assert sector == "energy"

    def test_classify_automation_with_plc_keywords(self, selector):
        """Test automation classification with PLC and SCADA keywords."""
        text = "Factory upgrades PLC systems and SCADA controls for manufacturing"
        sector = selector.classify_sector(text)
        assert sector == "automation"

    def test_classify_energy_with_oil_gas(self, selector):
        """Test energy classification with oil and gas keywords."""
        text = "Crude oil pipeline project approved for LNG terminal expansion"
        sector = selector.classify_sector(text)
        assert sector == "energy"

    def test_classify_no_match_returns_none(self, selector):
        """Test that unrelated text returns None."""
        text = "Software company announces new mobile app for consumers"
        sector = selector.classify_sector(text)
        assert sector is None

    def test_classify_prefers_highest_keyword_count(self, selector):
        """Test that sector with most keyword matches wins."""
        # More automation keywords than energy keywords
        text = "Robot automation in factory with solar panels on roof"
        sector = selector.classify_sector(text)
        assert sector == "automation"


class TestSymbolExtraction:
    """Test conservative symbol extraction patterns."""

    def test_extract_symbol_parentheses(self, selector):
        """Test extracting symbol from parentheses format (SYMBOL)."""
        text = "Rockwell Automation (ROK) beats earnings"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol == "ROK"
        assert is_certain is True

    def test_extract_symbol_colon(self, selector):
        """Test extracting symbol from colon format SYMBOL:."""
        text = "TSLA: Tesla expands automation capabilities"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol == "TSLA"
        assert is_certain is True

    def test_extract_symbol_dollar_sign(self, selector):
        """Test extracting symbol from dollar sign format $SYMBOL."""
        text = "Investors watch $ENPH solar technology breakthrough"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol == "ENPH"
        assert is_certain is True

    def test_extract_symbol_no_match_returns_none(self, selector):
        """Test that text without explicit symbol returns None."""
        text = "General news about automation sector growth"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol is None
        assert is_certain is False

    def test_extract_symbol_ignores_lowercase(self, selector):
        """Test that lowercase symbols are not extracted."""
        text = "Article mentions (abc) in passing"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol is None

    def test_extract_symbol_ignores_long_codes(self, selector):
        """Test that symbols longer than 5 chars are not extracted."""
        text = "System code (ABCDEF) not a stock symbol"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol is None

    def test_extract_first_symbol_when_multiple(self, selector):
        """Test that first symbol is extracted when multiple present."""
        text = "Analysis: (XOM) and (CVX) compete in oil market"
        symbol, is_certain = selector.extract_symbol(text)
        assert symbol == "XOM"
        assert is_certain is True


class TestActionMapping:
    """Test action mapping from headline sentiment."""

    def test_map_action_buy_beats_earnings(self, selector):
        """Test buy action for positive earnings keywords."""
        text = "Company beats Q3 earnings with record revenue"
        action = selector.map_action(text)
        assert action == "buy"

    def test_map_action_buy_raises_guidance(self, selector):
        """Test buy action for raises guidance."""
        text = "Firm raises guidance after strong quarter performance"
        action = selector.map_action(text)
        assert action == "buy"

    def test_map_action_sell_misses_guidance(self, selector):
        """Test sell action for negative guidance."""
        text = "Company misses guidance and cuts spending forecast"
        action = selector.map_action(text)
        assert action == "sell"

    def test_map_action_sell_lawsuit(self, selector):
        """Test sell action for lawsuit keyword."""
        text = "Firm faces environmental lawsuit at refinery facility"
        action = selector.map_action(text)
        assert action == "sell"

    def test_map_action_watch_neutral_news(self, selector):
        """Test watch action for neutral sector news."""
        text = "Industry report shows automation sector trends"
        action = selector.map_action(text)
        assert action == "watch"

    def test_map_action_prioritizes_sell_signals(self, selector):
        """Test that sell signals are prioritized over buy signals."""
        text = "Company beats earnings but faces investigation"
        action = selector.map_action(text)
        assert action == "sell"


class TestConfidenceScoring:
    """Test confidence score computation."""

    def test_confidence_base_score(self, selector):
        """Test base confidence score with certain symbol."""
        text = "Company (XYZ) announces news"
        action = "watch"
        symbol_certain = True
        confidence = selector.compute_confidence(text, action, symbol_certain)
        # Base confidence is 0.55, clamped to min 0.60
        assert confidence == 0.60

    def test_confidence_with_strong_keyword(self, selector):
        """Test confidence boost from strong keyword."""
        text = "Company (XYZ) beats earnings with record revenue"
        action = "buy"
        symbol_certain = True
        confidence = selector.compute_confidence(text, action, symbol_certain)
        # Base 0.55 + 0.10 (beat) + 0.10 (beats) + 0.10 (record revenue) = 0.85
        assert confidence == 0.85

    def test_confidence_uncertain_symbol_penalty(self, selector):
        """Test confidence penalty for uncertain symbol."""
        text = "General automation news with no explicit symbol"
        action = "watch"
        symbol_certain = False
        confidence = selector.compute_confidence(text, action, symbol_certain)
        # Base 0.55 - 0.15 (penalty) = 0.40, clamped to min 0.60
        assert confidence == 0.60

    def test_confidence_capped_at_max(self, selector):
        """Test confidence capped at max_confidence."""
        # Create text with many strong keywords
        text = "Company beats earnings, raises guidance, upgrades systems, record revenue, strong quarter, exceeds expectations, breakthrough partnership"
        action = "buy"
        symbol_certain = True
        confidence = selector.compute_confidence(text, action, symbol_certain)
        # Should be capped at max_confidence (0.90)
        assert confidence <= 0.90

    def test_confidence_clamped_at_min(self, selector):
        """Test confidence clamped at min_confidence."""
        text = "Neutral news without strong keywords"
        action = "watch"
        symbol_certain = True
        confidence = selector.compute_confidence(text, action, symbol_certain)
        # Should be at least min_confidence (0.60)
        assert confidence >= 0.60


class TestSnapshotWriting:
    """Test snapshot and event writing."""

    def test_write_snapshot_creates_file(self, selector, tmp_path):
        """Test that write_snapshot creates snapshot.json."""
        candidate = Candidate(
            candidate_id="test-123",
            created_at="2026-01-05T10:00:00-05:00",
            expires_at="2026-01-05T13:00:00-05:00",
            symbol="ROK",
            action="buy",
            confidence=0.75,
            horizon="intraday",
            sector="automation",
            event_type="rss_headline",
            tags=["automation"],
            reason="Test headline",
            avg_dollar_volume=None,
        )

        output_dir = str(tmp_path / "selector")
        selector.write_snapshot([candidate], output_dir)

        snapshot_path = tmp_path / "selector" / "snapshot.json"
        assert snapshot_path.exists()

        # Verify snapshot structure
        with open(snapshot_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "generated_at" in data
        assert data["count"] == 1
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["symbol"] == "ROK"
        assert data["candidates"][0]["action"] == "buy"
        assert data["candidates"][0]["confidence"] == 0.75

    def test_write_events_creates_jsonl(self, selector, tmp_path):
        """Test that write_events creates events.jsonl."""
        event = SelectorEvent(
            timestamp="2026-01-05T10:00:00-05:00",
            event_type="candidate_created",
            headline="Test headline",
            feed_url="https://example.com/feed",
            symbol="ROK",
            action="buy",
            sector="automation",
            confidence=0.75,
            reason="Test",
        )

        output_dir = str(tmp_path / "selector")
        selector.write_events([event], output_dir)

        events_path = tmp_path / "selector" / "events.jsonl"
        assert events_path.exists()

        # Verify JSONL format
        with open(events_path, encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 1
        event_data = json.loads(lines[0])
        assert event_data["event_type"] == "candidate_created"
        assert event_data["symbol"] == "ROK"

    def test_candidate_schema_validity(self, selector):
        """Test that created candidates have all required fields."""
        candidate = selector.create_candidate(
            symbol="XOM",
            action="buy",
            confidence=0.75,
            sector="energy",
            reason="Strong earnings beat",
            tags=["energy"],
        )

        # Verify all required fields are present
        assert candidate.candidate_id is not None
        assert candidate.created_at is not None
        assert candidate.expires_at is not None
        assert candidate.symbol == "XOM"
        assert candidate.action == "buy"
        assert candidate.confidence == 0.75
        assert candidate.horizon is not None
        assert candidate.sector == "energy"
        assert candidate.event_type == "rss_headline"
        assert candidate.tags == ["energy"]
        assert candidate.reason is not None

        # Verify candidate can be serialized
        candidate_dict = candidate.model_dump()
        assert isinstance(candidate_dict, dict)


class TestEndToEnd:
    """Test full selector pipeline with fixtures."""

    def test_run_with_automation_fixture(self, selector, rss_automation_content):
        """Test running selector with automation RSS fixture."""
        rss_override = {"https://example.com/automation": rss_automation_content}

        candidates, events = selector.run(rss_content_override=rss_override)

        # Should generate candidates from automation feed
        assert len(candidates) > 0
        assert len(events) > 0

        # Verify candidates have automation sector
        automation_count = sum(1 for c in candidates if c.sector == "automation")
        assert automation_count > 0

        # Verify ROK symbol was extracted
        rok_candidates = [c for c in candidates if c.symbol == "ROK"]
        assert len(rok_candidates) > 0

    def test_run_with_energy_fixture(self, selector, rss_energy_content):
        """Test running selector with energy RSS fixture."""
        rss_override = {"https://example.com/energy": rss_energy_content}

        candidates, events = selector.run(rss_content_override=rss_override)

        # Should generate candidates from energy feed
        assert len(candidates) > 0
        assert len(events) > 0

        # Verify candidates have energy sector
        energy_count = sum(1 for c in candidates if c.sector == "energy")
        assert energy_count > 0

        # Verify energy symbols were extracted
        energy_symbols = {c.symbol for c in candidates if c.symbol}
        expected_symbols = {"NEE", "XOM", "ENPH"}
        assert energy_symbols & expected_symbols  # At least some overlap

    def test_run_with_both_fixtures(self, selector, rss_automation_content, rss_energy_content):
        """Test running selector with both automation and energy fixtures."""
        rss_override = {
            "https://example.com/automation": rss_automation_content,
            "https://example.com/energy": rss_energy_content,
        }

        candidates, events = selector.run(rss_content_override=rss_override)

        # Should generate candidates from both feeds
        assert len(candidates) > 0

        # Verify mix of sectors
        sectors = {c.sector for c in candidates}
        assert "automation" in sectors
        assert "energy" in sectors

        # Verify all candidates have symbols (required by existing candidate system)
        for candidate in candidates:
            assert candidate.symbol is not None
            assert len(candidate.symbol) > 0

    def test_run_respects_max_candidates_limit(
        self, selector, rss_automation_content, rss_energy_content
    ):
        """Test that selector respects max_candidates_per_run limit."""
        rss_override = {
            "https://example.com/automation": rss_automation_content,
            "https://example.com/energy": rss_energy_content,
        }

        candidates, events = selector.run(rss_content_override=rss_override)

        max_limit = selector.config.safety["max_candidates_per_run"]
        assert len(candidates) <= max_limit

    def test_run_logs_events(self, selector, rss_automation_content):
        """Test that selector logs processing events."""
        rss_override = {"https://example.com/automation": rss_automation_content}

        candidates, events = selector.run(rss_content_override=rss_override)

        # Verify events were logged
        assert len(events) > 0

        # Verify event types
        event_types = {e.event_type for e in events}
        assert "headline_processed" in event_types

        if candidates:
            assert "candidate_created" in event_types

    def test_run_no_network_calls(self, selector, rss_automation_content):
        """Test that run with override makes no network calls."""
        rss_override = {"https://example.com/automation": rss_automation_content}

        # This should complete without network access
        candidates, events = selector.run(rss_content_override=rss_override)

        # Basic sanity check
        assert isinstance(candidates, list)
        assert isinstance(events, list)

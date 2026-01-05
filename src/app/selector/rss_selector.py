"""RSS-based candidate selector for automation and energy sectors."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
import yaml
from pydantic import BaseModel


class SelectorConfig(BaseModel):
    """Configuration for RSS selector."""

    sectors_enabled: list[str]
    rss_feeds: list[str]
    keyword_rules: dict[str, dict[str, Any]]
    action_keywords: dict[str, list[str]]
    confidence_modifiers: dict[str, float]
    defaults: dict[str, Any]
    safety: dict[str, Any]


class Candidate(BaseModel):
    """Candidate model matching existing schema."""

    candidate_id: str
    created_at: str
    expires_at: str
    symbol: str | None
    action: str  # buy, sell, watch
    confidence: float
    horizon: str
    sector: str | None
    event_type: str
    tags: list[str]
    reason: str
    avg_dollar_volume: float | None = None


class SelectorEvent(BaseModel):
    """Event log entry for selector runs."""

    timestamp: str
    event_type: str  # headline_processed, candidate_created, error
    headline: str | None = None
    feed_url: str | None = None
    symbol: str | None = None
    action: str | None = None
    sector: str | None = None
    confidence: float | None = None
    reason: str | None = None
    error: str | None = None


class RSSSelector:
    """RSS-based selector for automation and energy candidates."""

    def __init__(self, config_path: str = "config/selector.yaml"):
        """Initialize selector with configuration."""
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.eastern = ZoneInfo("America/New_York")

        # Symbol extraction pattern: (SYMBOL) or SYMBOL: or $SYMBOL
        self.symbol_pattern = re.compile(r"\(([A-Z]{1,5})\)|([A-Z]{1,5}):|\$([A-Z]{1,5})\b")

    def _load_config(self) -> SelectorConfig:
        """Load selector configuration from YAML."""
        if not self.config_path.exists():
            msg = f"Selector config not found: {self.config_path}"
            raise FileNotFoundError(msg)

        with open(self.config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return SelectorConfig(**config_data)

    def fetch_rss_feed(self, feed_url: str, timeout: int = 10) -> str:
        """Fetch RSS feed content."""
        if feed_url.startswith("placeholder://"):
            return ""  # Skip placeholder feeds

        response = requests.get(feed_url, timeout=timeout)
        response.raise_for_status()
        return response.text

    def parse_rss_simple(self, rss_content: str) -> list[dict[str, str]]:
        """Simple RSS parser extracting title and description."""
        items = []

        # Extract items between <item> tags
        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        title_pattern = re.compile(r"<title>(.*?)</title>", re.DOTALL)
        desc_pattern = re.compile(r"<description>(.*?)</description>", re.DOTALL)

        for item_match in item_pattern.finditer(rss_content):
            item_content = item_match.group(1)

            title_match = title_pattern.search(item_content)
            desc_match = desc_pattern.search(item_content)

            if title_match:
                title = title_match.group(1).strip()
                # Remove CDATA tags if present
                title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", title)

                description = ""
                if desc_match:
                    description = desc_match.group(1).strip()
                    description = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", description)

                items.append({"title": title, "description": description})

        return items

    def classify_sector(self, text: str) -> str | None:
        """Classify text into automation or energy sector."""
        text_lower = text.lower()

        # Count keyword matches for each sector
        sector_scores = {}
        for sector in self.config.sectors_enabled:
            if sector in self.config.keyword_rules:
                keywords = self.config.keyword_rules[sector]["keywords"]
                score = sum(1 for keyword in keywords if keyword.lower() in text_lower)
                sector_scores[sector] = score

        # Return sector with highest score (if > 0)
        if sector_scores:
            max_sector = max(sector_scores, key=sector_scores.get)
            if sector_scores[max_sector] > 0:
                return max_sector

        return None

    def extract_symbol(self, text: str) -> tuple[str | None, bool]:
        """
        Extract stock symbol from text conservatively.

        Returns:
            (symbol, is_certain) tuple
            - symbol: Extracted symbol or None
            - is_certain: True if symbol extraction is high confidence
        """
        matches = list(self.symbol_pattern.finditer(text))

        if not matches:
            return None, False

        # Extract first match (prefer explicit patterns)
        for match in matches:
            symbol = match.group(1) or match.group(2) or match.group(3)
            # Validate symbol (1-5 uppercase letters)
            if symbol and len(symbol) <= 5 and symbol.isupper():
                return symbol, True

        return None, False

    def map_action(self, text: str) -> str:
        """Map headline text to action (buy/sell/watch)."""
        text_lower = text.lower()

        # Check buy keywords
        buy_score = sum(1 for kw in self.config.action_keywords["buy"] if kw in text_lower)

        # Check sell keywords
        sell_score = sum(1 for kw in self.config.action_keywords["sell"] if kw in text_lower)

        # Prioritize sell signals (negative news)
        if sell_score > 0:
            return "sell"
        if buy_score > 0:
            return "buy"

        # Default to watch
        return self.config.safety["action_default_when_uncertain"]

    def compute_confidence(self, text: str, action: str, symbol_certain: bool) -> float:
        """
        Compute confidence score for candidate.

        Base confidence + keyword bonus - uncertainty penalty.
        """
        base = self.config.confidence_modifiers["base_confidence"]
        bonus = self.config.confidence_modifiers["strong_keyword_bonus"]
        max_conf = self.config.confidence_modifiers["max_confidence"]
        penalty = self.config.confidence_modifiers["uncertain_symbol_penalty"]

        text_lower = text.lower()

        # Count strong keyword matches for the action
        strong_keywords = self.config.action_keywords.get(action, [])
        keyword_count = sum(1 for kw in strong_keywords if kw in text_lower)

        confidence = base + (keyword_count * bonus)

        # Apply symbol uncertainty penalty
        if not symbol_certain:
            confidence -= penalty

        # Clamp to [min_confidence, max_confidence]
        confidence = max(self.config.defaults["min_confidence"], confidence)
        confidence = min(max_conf, confidence)

        return round(confidence, 2)

    def create_candidate(
        self,
        symbol: str | None,
        action: str,
        confidence: float,
        sector: str | None,
        reason: str,
        tags: list[str],
    ) -> Candidate:
        """Create candidate with expiration time."""
        now_et = datetime.now(self.eastern)
        candidate_id = f"rss-{now_et.strftime('%Y%m%d%H%M%S')}-{symbol or 'UNKNOWN'}"

        # Determine TTL based on action
        ttl_key = f"ttl_minutes_{action}"
        ttl_minutes = self.config.defaults.get(ttl_key, 180)
        expires_at = now_et + timedelta(minutes=ttl_minutes)

        return Candidate(
            candidate_id=candidate_id,
            created_at=now_et.isoformat(),
            expires_at=expires_at.isoformat(),
            symbol=symbol,
            action=action,
            confidence=confidence,
            horizon=self.config.defaults["horizon_default"],
            sector=sector,
            event_type="rss_headline",
            tags=tags,
            reason=reason[:200],  # Limit reason length
            avg_dollar_volume=None,  # Not available from RSS
        )

    def process_headline(
        self, headline: dict[str, str], feed_url: str
    ) -> tuple[Candidate | None, list[SelectorEvent]]:
        """
        Process a single RSS headline into a candidate.

        Returns:
            (candidate, events) tuple
        """
        events = []
        title = headline["title"]
        description = headline["description"]
        full_text = f"{title} {description}"

        # Log headline processing
        events.append(
            SelectorEvent(
                timestamp=datetime.now(self.eastern).isoformat(),
                event_type="headline_processed",
                headline=title,
                feed_url=feed_url,
            )
        )

        # Classify sector
        sector = self.classify_sector(full_text)
        if not sector:
            # Skip headlines that don't match our sectors
            return None, events

        # Extract symbol
        symbol, symbol_certain = self.extract_symbol(full_text)

        # Map action
        action = self.map_action(full_text)

        # Compute confidence
        confidence = self.compute_confidence(full_text, action, symbol_certain)

        # Check if meets minimum confidence
        if confidence < self.config.defaults["min_confidence"]:
            return None, events

        # Apply allowlist/denylist
        if self.config.safety["require_symbol_allowlist"]:
            allowlist = self.config.safety["symbol_allowlist"]
            if symbol and symbol not in allowlist:
                return None, events

        denylist = self.config.safety["symbol_denylist"]
        if symbol and symbol in denylist:
            return None, events

        # Get sector tags
        tags = []
        if sector in self.config.keyword_rules:
            tags = self.config.keyword_rules[sector]["tags"]

        # Create candidate
        candidate = self.create_candidate(
            symbol=symbol,
            action=action,
            confidence=confidence,
            sector=sector,
            reason=title,
            tags=tags,
        )

        # Log candidate creation
        events.append(
            SelectorEvent(
                timestamp=datetime.now(self.eastern).isoformat(),
                event_type="candidate_created",
                headline=title,
                feed_url=feed_url,
                symbol=symbol,
                action=action,
                sector=sector,
                confidence=confidence,
                reason=title[:100],
            )
        )

        return candidate, events

    def run(
        self, rss_content_override: dict[str, str] | None = None
    ) -> tuple[list[Candidate], list[SelectorEvent]]:
        """
        Run selector to generate candidates from RSS feeds.

        Args:
            rss_content_override: Optional dict of {feed_url: rss_xml_content}
                                  for testing (bypasses network fetching)

        Returns:
            (candidates, events) tuple
        """
        all_candidates = []
        all_events = []

        # Track candidate count by action
        action_counts = {"buy": 0, "sell": 0, "watch": 0}

        try:
            for feed_url in self.config.rss_feeds:
                if feed_url.startswith("placeholder://"):
                    continue  # Skip placeholder feeds

                try:
                    # Fetch RSS content (or use override for testing)
                    if rss_content_override and feed_url in rss_content_override:
                        rss_content = rss_content_override[feed_url]
                    else:
                        rss_content = self.fetch_rss_feed(feed_url)

                    if not rss_content:
                        continue

                    # Parse RSS items
                    headlines = self.parse_rss_simple(rss_content)

                    # Process each headline
                    for headline in headlines:
                        candidate, events = self.process_headline(headline, feed_url)

                        all_events.extend(events)

                        if candidate:
                            all_candidates.append(candidate)
                            action_counts[candidate.action] += 1

                            # Check max candidates limit
                            if len(all_candidates) >= self.config.safety["max_candidates_per_run"]:
                                break

                    # Check if reached max candidates
                    if len(all_candidates) >= self.config.safety["max_candidates_per_run"]:
                        break

                except Exception as e:
                    # Log feed fetch error
                    all_events.append(
                        SelectorEvent(
                            timestamp=datetime.now(self.eastern).isoformat(),
                            event_type="error",
                            feed_url=feed_url,
                            error=str(e),
                        )
                    )

        except Exception as e:
            # Log general error
            all_events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="error",
                    error=str(e),
                )
            )

        return all_candidates, all_events

    def write_snapshot(self, candidates: list[Candidate], output_dir: str = "out/selector") -> None:
        """Write candidates to snapshot.json."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        snapshot_file = output_path / "snapshot.json"

        snapshot = {
            "generated_at": datetime.now(self.eastern).isoformat(),
            "count": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
            "metadata": {"source": "rss_selector", "config": str(self.config_path)},
        }

        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)

    def write_events(self, events: list[SelectorEvent], output_dir: str = "out/selector") -> None:
        """Append events to events.jsonl."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        events_file = output_path / "events.jsonl"

        with open(events_file, "a", encoding="utf-8") as f:
            for event in events:
                f.write(event.model_dump_json() + "\n")

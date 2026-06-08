"""RSS-based candidate selector for automation and energy sectors."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
import yaml
from pydantic import BaseModel

from src.app.selector.llm_enrichment import create_enricher
from src.app.selector.sentiment_scorer import SentimentScorer
from src.app.selector.ticker_validation import create_validator


class SelectorConfig(BaseModel):
    """Configuration for RSS selector."""

    sectors_enabled: list[str]
    rss_feeds: list[str]
    keyword_rules: dict[str, dict[str, Any]]
    action_keywords: dict[str, list[str]]
    speculative_words: list[str]
    confidence_modifiers: dict[str, float]
    defaults: dict[str, Any]
    safety: dict[str, Any]
    screening: dict[str, Any]


class Candidate(BaseModel):
    """Candidate model matching existing schema."""

    candidate_id: str
    created_at: str
    expires_at: str
    symbol: str
    action: str  # buy, sell, watch
    confidence: float
    horizon: str
    sector: str | None
    event_type: str
    tags: list[str]
    reason: str
    avg_dollar_volume: float | None = None
    sentiment_factors: dict[str, float] | None = None


class SelectorEvent(BaseModel):
    """Event log entry for selector runs."""

    timestamp: str
    event_type: str  # headline_processed, candidate_created, candidate_rejected, error
    headline: str | None = None
    feed_url: str | None = None
    symbol: str | None = None
    action: str | None = None
    sector: str | None = None
    confidence: float | None = None
    reason: str | None = None
    rejection_reason: str | None = (
        None  # no_symbol, no_sector, low_confidence, allowlist, denylist, duplicate, liquidity_floor
    )
    error: str | None = None


class RSSSelector:
    """RSS-based selector for automation and energy candidates."""

    def __init__(self, config_path: str = "config/selector.yaml", alpaca_client: Any | None = None):
        """Initialize selector with configuration."""
        self.config_path = Path(config_path)
        self.config_dict = self._load_config_dict()
        self.config = SelectorConfig(**self.config_dict)
        self.eastern = ZoneInfo("America/New_York")

        # Symbol extraction pattern: (SYMBOL) or SYMBOL: or $SYMBOL
        self.symbol_pattern = re.compile(r"\(([A-Z]{1,5})\)|([A-Z]{1,5}):|\$([A-Z]{1,5})\b")

        # Company-name → ticker aliases loaded from config.
        # Fallback when regex finds no explicit ticker in the headline.
        # Maps ticker -> [list of lowercase name fragments]
        raw_aliases: dict[str, list[str]] = self.config_dict.get("company_aliases", {})
        self._company_aliases: list[tuple[str, list[str]]] = [
            (ticker.upper(), [name.lower() for name in names])
            for ticker, names in raw_aliases.items()
        ]

        # Duplicate suppression tracking: (symbol, action) -> timestamp
        self.recent_candidates: dict[tuple[str, str], datetime] = {}

        # Initialize ticker validator
        self.validator = create_validator(self.config_dict, alpaca_client)

        # Initialize LLM enricher (if enabled in config)
        self.enricher = create_enricher(self.config_dict)

        # Initialize sentiment scorer (if alpaca_client provided)
        self.sentiment_scorer = None
        if alpaca_client:
            rss_weight = self.config_dict.get("sentiment_weights", {}).get("rss", 0.4)
            momentum_weight = self.config_dict.get("sentiment_weights", {}).get("momentum", 0.3)
            volume_weight = self.config_dict.get("sentiment_weights", {}).get("volume", 0.3)
            self.sentiment_scorer = SentimentScorer(
                alpaca_client=alpaca_client,
                rss_weight=rss_weight,
                momentum_weight=momentum_weight,
                volume_weight=volume_weight,
            )

    def _load_config_dict(self) -> dict[str, Any]:
        """Load selector configuration from YAML as dict."""
        if not self.config_path.exists():
            msg = f"Selector config not found: {self.config_path}"
            raise FileNotFoundError(msg)

        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

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

        First tries explicit ticker patterns ((SYMBOL), SYMBOL:, $SYMBOL).
        If none found, falls back to company-name alias matching against the
        known universe from config.company_aliases.

        Returns:
            (symbol, is_certain) tuple
            - symbol: Extracted symbol or None
            - is_certain: True if symbol extraction is high confidence
        """
        matches = list(self.symbol_pattern.finditer(text))

        if matches:
            # Extract first match (prefer explicit patterns)
            for match in matches:
                symbol = match.group(1) or match.group(2) or match.group(3)
                # Validate symbol (1-5 uppercase letters)
                if symbol and len(symbol) <= 5 and symbol.isupper():
                    return symbol, True

        # Fallback: check company-name aliases (universe-restricted, deterministic)
        text_lower = text.lower()
        for ticker, name_fragments in self._company_aliases:
            for fragment in name_fragments:
                if fragment in text_lower:
                    return ticker, True  # Explicit alias match → certain

        return None, False

    def map_action(self, text: str, sentiment_score: float | None = None) -> str:
        """Map headline text to action (buy/sell/watch).

        If sentiment_score provided, uses sentiment thresholds for action mapping.
        Otherwise falls back to keyword-based mapping.

        Args:
            text: Headline text
            sentiment_score: Optional combined sentiment score (-1.0 to 1.0)

        Returns:
            Action string (buy/sell/watch)
        """
        # If sentiment scoring enabled and available, use thresholds
        if sentiment_score is not None:
            buy_threshold = self.config_dict.get("sentiment_thresholds", {}).get("buy", 0.65)
            sell_threshold = self.config_dict.get("sentiment_thresholds", {}).get("sell", -0.55)

            if sentiment_score >= buy_threshold:
                return "buy"
            if sentiment_score <= sell_threshold:
                return "sell"
            # Fall through to watch

        # Keyword-based action mapping (fallback or when sentiment not available)
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

    def compute_confidence(
        self, text: str, action: str, symbol_certain: bool, symbol: str | None = None
    ) -> tuple[float, dict[str, float] | None]:
        """
        Compute confidence score for candidate with optional sentiment scoring.

        Base confidence + keyword bonus - uncertainty penalty - vagueness penalty.
        If sentiment scorer available, computes multi-factor sentiment.

        Returns:
            (confidence, sentiment_factors) tuple
            - confidence: RSS confidence score (0.0-1.0)
            - sentiment_factors: Sentiment breakdown dict or None
        """
        base = self.config.confidence_modifiers["base_confidence"]
        bonus = self.config.confidence_modifiers["strong_keyword_bonus"]
        max_conf = self.config.confidence_modifiers["max_confidence"]
        penalty = self.config.confidence_modifiers["uncertain_symbol_penalty"]
        vagueness_penalty = self.config.confidence_modifiers["vagueness_penalty"]

        text_lower = text.lower()

        # Count strong keyword matches for the action
        strong_keywords = self.config.action_keywords.get(action, [])
        keyword_count = sum(1 for kw in strong_keywords if kw in text_lower)

        confidence = base + (keyword_count * bonus)

        # Apply symbol uncertainty penalty
        if not symbol_certain:
            confidence -= penalty

        # Apply vagueness penalty: if speculative words present without hard action keywords
        has_speculative = any(word in text_lower for word in self.config.speculative_words)
        has_hard_action = keyword_count > 0  # Has strong buy/sell keywords
        if has_speculative and not has_hard_action:
            confidence -= vagueness_penalty

        # Clamp to [min_confidence, max_confidence]
        confidence = max(self.config.defaults["min_confidence"], confidence)
        confidence = min(max_conf, confidence)

        confidence = round(confidence, 2)

        # Compute sentiment factors if scorer available
        sentiment_factors = None
        if self.sentiment_scorer and symbol:
            _, sentiment_factors = self.sentiment_scorer.compute_sentiment_score(
                symbol=symbol,
                text=text,
                rss_confidence=confidence,
            )

        return confidence, sentiment_factors

    def create_candidate(
        self,
        symbol: str,
        action: str,
        confidence: float,
        sector: str | None,
        reason: str,
        tags: list[str],
        avg_dollar_volume: float | None = None,
        sentiment_factors: dict[str, float] | None = None,
    ) -> Candidate:
        """Create candidate with expiration time."""
        now_et = datetime.now(self.eastern)
        candidate_id = f"rss-{now_et.strftime('%Y%m%d%H%M%S')}-{symbol}"

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
            avg_dollar_volume=avg_dollar_volume,  # May be None if not available
            sentiment_factors=sentiment_factors,  # Multi-factor sentiment scores
        )

    def check_liquidity(self, avg_dollar_volume: float | None) -> bool:
        """
        Check if candidate meets liquidity floor.

        Args:
            avg_dollar_volume: Average daily dollar volume, or None if not available

        Returns:
            True if candidate passes (meets floor or data not available), False otherwise
        """
        # If no data available, allow candidate through (don't block on missing data)
        if avg_dollar_volume is None:
            return True

        liquidity_floor = self.config.screening["liquidity_floor_usd"]
        return avg_dollar_volume >= liquidity_floor

    def is_duplicate(self, symbol: str, action: str, now: datetime | None = None) -> bool:
        """
        Check if candidate is a duplicate of recent candidate.

        Suppresses candidates with same symbol+action generated within
        duplicate_suppression_minutes window.

        Args:
            symbol: Stock symbol
            action: Action (buy, sell, watch)
            now: Current time (for testing), defaults to datetime.now(eastern)

        Returns:
            True if duplicate (should suppress), False otherwise
        """
        if now is None:
            now = datetime.now(self.eastern)

        key = (symbol, action)
        suppression_minutes = self.config.screening["duplicate_suppression_minutes"]

        # Clean up expired entries (older than suppression window)
        cutoff = now - timedelta(minutes=suppression_minutes)
        expired_keys = [k for k, ts in self.recent_candidates.items() if ts < cutoff]
        for k in expired_keys:
            del self.recent_candidates[k]

        # Check if duplicate
        if key in self.recent_candidates:
            last_time = self.recent_candidates[key]
            if now - last_time < timedelta(minutes=suppression_minutes):
                return True  # Duplicate within window

        # Not duplicate, track this candidate
        self.recent_candidates[key] = now
        return False

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
            events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="candidate_rejected",
                    headline=title,
                    feed_url=feed_url,
                    rejection_reason="no_sector",
                )
            )
            return None, events

        # Extract symbol
        symbol, symbol_certain = self.extract_symbol(full_text)

        # Skip candidates without symbols (existing candidate system requires symbols)
        if not symbol:
            events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="candidate_rejected",
                    headline=title,
                    feed_url=feed_url,
                    sector=sector,
                    rejection_reason="no_symbol",
                )
            )
            return None, events

        # Compute confidence and sentiment factors (sentiment may be None)
        confidence, sentiment_factors = self.compute_confidence(
            full_text, "watch", symbol_certain, symbol
        )

        # Map action (use sentiment score if available)
        sentiment_score = None
        if sentiment_factors:
            sentiment_score = sentiment_factors.get("combined")
        action = self.map_action(full_text, sentiment_score)

        # Recompute confidence with actual action (for keyword matching)
        confidence, sentiment_factors = self.compute_confidence(
            full_text, action, symbol_certain, symbol
        )

        # Check if meets minimum confidence
        if confidence < self.config.defaults["min_confidence"]:
            events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="candidate_rejected",
                    headline=title,
                    feed_url=feed_url,
                    symbol=symbol,
                    action=action,
                    sector=sector,
                    confidence=confidence,
                    rejection_reason="low_confidence",
                )
            )
            return None, events

        # Apply allowlist/denylist
        if self.config.safety["require_symbol_allowlist"]:
            allowlist = self.config.safety["symbol_allowlist"]
            if symbol and symbol not in allowlist:
                events.append(
                    SelectorEvent(
                        timestamp=datetime.now(self.eastern).isoformat(),
                        event_type="candidate_rejected",
                        headline=title,
                        feed_url=feed_url,
                        symbol=symbol,
                        action=action,
                        sector=sector,
                        confidence=confidence,
                        rejection_reason="allowlist",
                    )
                )
                return None, events

        denylist = self.config.safety["symbol_denylist"]
        if symbol and symbol in denylist:
            events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="candidate_rejected",
                    headline=title,
                    feed_url=feed_url,
                    symbol=symbol,
                    action=action,
                    sector=sector,
                    confidence=confidence,
                    rejection_reason="denylist",
                )
            )
            return None, events

        # Check for duplicates (suppress same symbol+action within time window)
        if self.is_duplicate(symbol, action):
            events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="candidate_rejected",
                    headline=title,
                    feed_url=feed_url,
                    symbol=symbol,
                    action=action,
                    sector=sector,
                    confidence=confidence,
                    rejection_reason="duplicate",
                )
            )
            return None, events

        # Note: avg_dollar_volume not available from RSS feeds
        # Liquidity check would happen here if we had market data
        avg_dollar_volume = None

        # Check liquidity floor (will pass if data not available)
        if not self.check_liquidity(avg_dollar_volume):
            events.append(
                SelectorEvent(
                    timestamp=datetime.now(self.eastern).isoformat(),
                    event_type="candidate_rejected",
                    headline=title,
                    feed_url=feed_url,
                    symbol=symbol,
                    action=action,
                    sector=sector,
                    confidence=confidence,
                    rejection_reason="liquidity_floor",
                )
            )
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
            avg_dollar_volume=avg_dollar_volume,
            sentiment_factors=sentiment_factors,
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

        # Apply deterministic validation
        validated_candidates, validation_stats = self._apply_validation(all_candidates)

        # Apply optional LLM enrichment
        final_candidates = validated_candidates
        enrichment_stats = {}

        if self.enricher:
            try:
                # Convert candidates to dict format for enricher
                candidate_dicts = [c.model_dump() for c in validated_candidates]

                # Enrich candidates
                enriched_dicts, enrichment_stats = self.enricher.enrich_candidates(candidate_dicts)

                # Convert back to Candidate objects
                final_candidates = [Candidate(**c) for c in enriched_dicts]

            except Exception as e:
                print(f"LLM enrichment failed: {e}")
                enrichment_stats = {"error": str(e)}

        # Store stats for snapshot metadata
        self._validation_stats = validation_stats
        self._enrichment_stats = enrichment_stats

        return final_candidates, all_events

    def _apply_validation(
        self, candidates: list[Candidate]
    ) -> tuple[list[Candidate], dict[str, int]]:
        """
        Apply deterministic ticker validation to candidates.

        Returns:
            (validated_candidates, stats)
        """
        validated = []
        stats = {
            "total_input": len(candidates),
            "rejected_stopword": 0,
            "rejected_format": 0,
            "rejected_not_tradable": 0,
            "total_output": 0,
        }

        for candidate in candidates:
            is_valid, rejection_reason = self.validator.validate(candidate.symbol)

            if not is_valid:
                # Track rejection reason
                if "Stopword" in str(rejection_reason):
                    stats["rejected_stopword"] += 1
                elif "Invalid format" in str(rejection_reason):
                    stats["rejected_format"] += 1
                elif "not tradable" in str(rejection_reason or ""):
                    stats["rejected_not_tradable"] += 1
                continue

            validated.append(candidate)

        stats["total_output"] = len(validated)
        return validated, stats

    def write_snapshot(self, candidates: list[Candidate], output_dir: str = "out/selector") -> None:
        """Write candidates to snapshot.json with validation and enrichment metadata."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        snapshot_file = output_path / "snapshot.json"

        # Determine source
        source = "rss"
        if hasattr(self, "_enrichment_stats") and self._enrichment_stats.get("llm_called"):
            source = "rss+llm"

        # Build metadata
        metadata = {
            "source": source,
            "config": str(self.config_path),
        }

        # Add validation stats
        if hasattr(self, "_validation_stats"):
            metadata["validation_stats"] = self._validation_stats

        # Add LLM enrichment stats
        if hasattr(self, "_enrichment_stats") and self._enrichment_stats:
            metadata["enrichment_stats"] = self._enrichment_stats
            if "model" in self._enrichment_stats:
                metadata["llm_model"] = self._enrichment_stats["model"]

        snapshot = {
            "generated_at": datetime.now(self.eastern).isoformat(),
            "count": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
            "metadata": metadata,
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

    @staticmethod
    def compute_stats(events: list[SelectorEvent]) -> dict[str, int]:
        """
        Compute statistics from events.

        Returns:
            dict with keys: headlines_processed, symbols_extracted, candidates_created,
            rejected_no_symbol, rejected_no_sector, rejected_low_confidence,
            rejected_duplicate, rejected_liquidity_floor, rejected_allowlist, rejected_denylist
        """
        stats = {
            "headlines_processed": 0,
            "symbols_extracted": 0,
            "candidates_created": 0,
            "rejected_no_symbol": 0,
            "rejected_no_sector": 0,
            "rejected_low_confidence": 0,
            "rejected_duplicate": 0,
            "rejected_liquidity_floor": 0,
            "rejected_allowlist": 0,
            "rejected_denylist": 0,
        }

        for event in events:
            if event.event_type == "headline_processed":
                stats["headlines_processed"] += 1
            elif event.event_type == "candidate_created":
                stats["candidates_created"] += 1
            elif event.event_type == "candidate_rejected" and event.rejection_reason:
                key = f"rejected_{event.rejection_reason}"
                if key in stats:
                    stats[key] += 1

            # Track symbols extracted (any event with symbol field set)
            if event.symbol:
                stats["symbols_extracted"] += 1

        return stats

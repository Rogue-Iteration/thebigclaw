"""
Tests for manage_watchlist.py — Phase 1 (TDD)

Tests cover:
- Loading and saving watchlist
- Adding tickers with default rules
- Removing tickers
- Setting per-ticker rule overrides
- Resetting ticker rules to defaults
- Setting global settings
- Displaying effective rules (defaults merged with overrides)
- Input validation and error handling
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# We'll import from the skill directory
import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

from manage_watchlist import (
    load_watchlist,
    save_watchlist,
    add_ticker,
    remove_ticker,
    set_rule,
    reset_rules,
    set_global,
    get_effective_rules,
    show_watchlist,
    find_ticker,
    set_directive,
)


@pytest.fixture
def sample_watchlist():
    """A minimal watchlist for testing."""
    return {
        "default_rules": {
            "price_movement_pct": 5,
            "sentiment_shift": True,
            "social_volume_spike": True,
            "sec_filing": True,
            "competitive_news": True,
        },
        "global_settings": {
            "significance_threshold": 6,
            "cheap_model": "qwen3-32b",
            "strong_model": "claude-sonnet-4-5-20250514",
        },
        "tickers": [
            {
                "symbol": "CAKE",
                "name": "The Cheesecake Factory",
                "added": "2026-02-12",
                "theme": None,
                "directive": None,
                "explore_adjacent": False,
                "rules": {},
            },
            {
                "symbol": "HOG",
                "name": "Harley-Davidson",
                "added": "2026-02-12",
                "theme": None,
                "directive": None,
                "explore_adjacent": False,
                "rules": {"price_movement_pct": 3},
            },
        ],
    }


@pytest.fixture
def watchlist_file(sample_watchlist, tmp_path):
    """Write sample watchlist to a temp file and return the path."""
    filepath = tmp_path / "watchlist.json"
    filepath.write_text(json.dumps(sample_watchlist, indent=2))
    return str(filepath)


# ─── Loading & Saving ─────────────────────────────────────────────


class TestLoadSave:
    def test_load_watchlist(self, watchlist_file, sample_watchlist):
        result = load_watchlist(watchlist_file)
        assert result == sample_watchlist

    def test_load_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_watchlist(str(tmp_path / "nope.json"))

    def test_load_invalid_json_raises(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            load_watchlist(str(bad_file))

    def test_save_watchlist(self, sample_watchlist, tmp_path):
        filepath = str(tmp_path / "out.json")
        save_watchlist(sample_watchlist, filepath)
        loaded = json.loads(Path(filepath).read_text())
        assert loaded == sample_watchlist

    def test_save_roundtrip(self, sample_watchlist, tmp_path):
        filepath = str(tmp_path / "roundtrip.json")
        save_watchlist(sample_watchlist, filepath)
        loaded = load_watchlist(filepath)
        assert loaded == sample_watchlist


# ─── Finding Tickers ──────────────────────────────────────────────


class TestFindTicker:
    def test_find_existing_ticker(self, sample_watchlist):
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker is not None
        assert ticker["symbol"] == "CAKE"

    def test_find_case_insensitive(self, sample_watchlist):
        ticker = find_ticker(sample_watchlist, "cake")
        assert ticker is not None
        assert ticker["symbol"] == "CAKE"

    def test_find_with_dollar_sign(self, sample_watchlist):
        ticker = find_ticker(sample_watchlist, "$CAKE")
        assert ticker is not None
        assert ticker["symbol"] == "CAKE"

    def test_find_nonexistent_returns_none(self, sample_watchlist):
        assert find_ticker(sample_watchlist, "AAPL") is None


# ─── Adding Tickers ───────────────────────────────────────────────


class TestAddTicker:
    def test_add_new_ticker(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "DIS", "The Walt Disney Company")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "DIS")
        assert ticker is not None
        assert ticker["name"] == "The Walt Disney Company"
        assert ticker["rules"] == {}
        assert "added" in ticker

    def test_add_duplicate_fails(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "CAKE", "Duplicate")
        assert result["success"] is False
        assert "already" in result["message"].lower()

    def test_add_strips_dollar_sign(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "$DIS", "Disney")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "DIS")
        assert ticker["symbol"] == "DIS"  # stored without $

    def test_add_uppercases_symbol(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "dis", "Disney")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "DIS")
        assert ticker["symbol"] == "DIS"

    def test_add_empty_symbol_fails(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "", "No Symbol")
        assert result["success"] is False

    def test_add_empty_name_fails(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "DIS", "")
        assert result["success"] is False

    def test_add_with_theme(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "BNTX", "BioNTech", theme="mRNA cancer research")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "BNTX")
        assert ticker["theme"] == "mRNA cancer research"
        assert "Theme" in result["message"]

    def test_add_with_directive(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "BNTX", "BioNTech", directive="Focus on clinical trials")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "BNTX")
        assert ticker["directive"] == "Focus on clinical trials"

    def test_add_with_explore_adjacent(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "BNTX", "BioNTech", explore_adjacent=True)
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "BNTX")
        assert ticker["explore_adjacent"] is True
        assert "exploration enabled" in result["message"]

    def test_add_defaults_for_new_fields(self, sample_watchlist):
        result = add_ticker(sample_watchlist, "DIS", "Disney")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "DIS")
        assert ticker["theme"] is None
        assert ticker["directive"] is None
        assert ticker["explore_adjacent"] is False


# ─── Removing Tickers ─────────────────────────────────────────────


class TestRemoveTicker:
    def test_remove_existing_ticker(self, sample_watchlist):
        result = remove_ticker(sample_watchlist, "CAKE")
        assert result["success"] is True
        assert find_ticker(sample_watchlist, "CAKE") is None
        assert len(sample_watchlist["tickers"]) == 1

    def test_remove_nonexistent_fails(self, sample_watchlist):
        result = remove_ticker(sample_watchlist, "AAPL")
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_remove_case_insensitive(self, sample_watchlist):
        result = remove_ticker(sample_watchlist, "$cake")
        assert result["success"] is True
        assert find_ticker(sample_watchlist, "CAKE") is None


# ─── Setting Per-Ticker Rules ─────────────────────────────────────


class TestSetRule:
    def test_set_valid_rule(self, sample_watchlist):
        result = set_rule(sample_watchlist, "CAKE", "price_movement_pct", 3)
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["rules"]["price_movement_pct"] == 3

    def test_set_boolean_rule(self, sample_watchlist):
        result = set_rule(sample_watchlist, "CAKE", "sec_filing", False)
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["rules"]["sec_filing"] is False

    def test_set_rule_nonexistent_ticker_fails(self, sample_watchlist):
        result = set_rule(sample_watchlist, "AAPL", "sec_filing", False)
        assert result["success"] is False

    def test_set_invalid_rule_name_fails(self, sample_watchlist):
        result = set_rule(sample_watchlist, "CAKE", "made_up_rule", 42)
        assert result["success"] is False
        assert "invalid" in result["message"].lower() or "unknown" in result["message"].lower()

    def test_set_rule_wrong_type_fails(self, sample_watchlist):
        # price_movement_pct should be numeric, not a string
        result = set_rule(sample_watchlist, "CAKE", "price_movement_pct", "not_a_number")
        assert result["success"] is False


# ─── Resetting Rules ──────────────────────────────────────────────


class TestResetRules:
    def test_reset_clears_overrides(self, sample_watchlist):
        # HOG has price_movement_pct: 3 override
        ticker = find_ticker(sample_watchlist, "HOG")
        assert ticker["rules"] != {}

        result = reset_rules(sample_watchlist, "HOG")
        assert result["success"] is True
        assert ticker["rules"] == {}

    def test_reset_nonexistent_ticker_fails(self, sample_watchlist):
        result = reset_rules(sample_watchlist, "AAPL")
        assert result["success"] is False


# ─── Global Settings ──────────────────────────────────────────────


class TestSetGlobal:
    def test_set_significance_threshold(self, sample_watchlist):
        result = set_global(sample_watchlist, "significance_threshold", 4)
        assert result["success"] is True
        assert sample_watchlist["global_settings"]["significance_threshold"] == 4

    def test_set_invalid_global_key_fails(self, sample_watchlist):
        result = set_global(sample_watchlist, "nonexistent_key", 42)
        assert result["success"] is False

    def test_set_model(self, sample_watchlist):
        result = set_global(sample_watchlist, "cheap_model", "llama-3-70b")
        assert result["success"] is True
        assert sample_watchlist["global_settings"]["cheap_model"] == "llama-3-70b"


# ─── Effective Rules (Defaults + Overrides) ───────────────────────


class TestEffectiveRules:
    def test_no_overrides_returns_defaults(self, sample_watchlist):
        effective = get_effective_rules(sample_watchlist, "CAKE")
        assert effective == sample_watchlist["default_rules"]

    def test_override_merges_with_defaults(self, sample_watchlist):
        effective = get_effective_rules(sample_watchlist, "HOG")
        # HOG overrides price_movement_pct to 3
        assert effective["price_movement_pct"] == 3
        # But inherits all other defaults
        assert effective["sentiment_shift"] is True
        assert effective["social_volume_spike"] is True
        assert effective["sec_filing"] is True
        assert effective["competitive_news"] is True

    def test_nonexistent_ticker_returns_none(self, sample_watchlist):
        assert get_effective_rules(sample_watchlist, "AAPL") is None


# ─── Show Watchlist ───────────────────────────────────────────────


class TestShowWatchlist:
    def test_show_returns_string(self, sample_watchlist):
        output = show_watchlist(sample_watchlist)
        assert isinstance(output, str)

    def test_show_includes_all_tickers(self, sample_watchlist):
        output = show_watchlist(sample_watchlist)
        assert "CAKE" in output
        assert "HOG" in output

    def test_show_includes_overrides(self, sample_watchlist):
        output = show_watchlist(sample_watchlist)
        # HOG has a custom price_movement_pct of 3
        assert "3" in output

    def test_show_empty_watchlist(self):
        empty = {
            "default_rules": {},
            "global_settings": {},
            "tickers": [],
        }
        output = show_watchlist(empty)
        assert "no tickers" in output.lower() or output  # should handle gracefully

    def test_show_includes_theme_directive(self, sample_watchlist):
        sample_watchlist["tickers"][0]["theme"] = "Casual dining expansion"
        sample_watchlist["tickers"][0]["directive"] = "Watch franchise deals"
        output = show_watchlist(sample_watchlist)
        assert "Casual dining expansion" in output
        assert "Watch franchise deals" in output
        assert "🎯" in output
        assert "📌" in output


# ─── Set Directive ────────────────────────────────────────────────


class TestSetDirective:
    def test_set_theme(self, sample_watchlist):
        result = set_directive(sample_watchlist, "CAKE", theme="Casual dining")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["theme"] == "Casual dining"

    def test_set_directive_text(self, sample_watchlist):
        result = set_directive(sample_watchlist, "CAKE", directive="Focus on franchise expansion")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["directive"] == "Focus on franchise expansion"

    def test_set_explore_adjacent(self, sample_watchlist):
        result = set_directive(sample_watchlist, "CAKE", explore_adjacent=True)
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["explore_adjacent"] is True

    def test_set_multiple_fields(self, sample_watchlist):
        result = set_directive(
            sample_watchlist,
            "CAKE",
            theme="Casual dining",
            directive="Watch franchise deals",
            explore_adjacent=True,
        )
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["theme"] == "Casual dining"
        assert ticker["directive"] == "Watch franchise deals"
        assert ticker["explore_adjacent"] is True

    def test_clear_theme(self, sample_watchlist):
        # First set a theme
        set_directive(sample_watchlist, "CAKE", theme="Test theme")
        # Then clear it
        result = set_directive(sample_watchlist, "CAKE", theme="")
        assert result["success"] is True
        ticker = find_ticker(sample_watchlist, "CAKE")
        assert ticker["theme"] is None

    def test_nonexistent_ticker_fails(self, sample_watchlist):
        result = set_directive(sample_watchlist, "AAPL", theme="Test")
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_no_changes_fails(self, sample_watchlist):
        result = set_directive(sample_watchlist, "CAKE")
        assert result["success"] is False
        assert "no changes" in result["message"].lower()

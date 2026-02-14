"""
Tests for manage_watchlist.py — SQLite-backed watchlist management.

Tests cover:
- Adding tickers with default rules
- Removing tickers
- Setting per-ticker rule overrides
- Resetting ticker rules to defaults
- Setting global settings
- Displaying effective rules (defaults merged with overrides)
- Setting directives (theme, directive, explore_adjacent)
- Input validation and error handling
"""

import json

import pytest

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

from db import get_connection, init_db, get_default_rules
from manage_watchlist import (
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
def conn():
    """In-memory database with schema and two sample tickers."""
    c = get_connection(":memory:")
    init_db(c)
    # Seed two tickers like the old sample_watchlist
    add_ticker(c, "CAKE", "The Cheesecake Factory")
    add_ticker(c, "HOG", "Harley-Davidson")
    # Set HOG price_movement_pct override to 3
    set_rule(c, "HOG", "price_movement_pct", 3)
    yield c
    c.close()


# ─── Finding Tickers ──────────────────────────────────────────────


class TestFindTicker:
    def test_find_existing_ticker(self, conn):
        ticker = find_ticker(conn, "CAKE")
        assert ticker is not None
        assert ticker["symbol"] == "CAKE"

    def test_find_case_insensitive(self, conn):
        ticker = find_ticker(conn, "cake")
        assert ticker is not None
        assert ticker["symbol"] == "CAKE"

    def test_find_with_dollar_sign(self, conn):
        ticker = find_ticker(conn, "$CAKE")
        assert ticker is not None
        assert ticker["symbol"] == "CAKE"

    def test_find_nonexistent_returns_none(self, conn):
        assert find_ticker(conn, "AAPL") is None


# ─── Adding Tickers ───────────────────────────────────────────────


class TestAddTicker:
    def test_add_new_ticker(self, conn):
        result = add_ticker(conn, "DIS", "The Walt Disney Company")
        assert result["success"] is True
        ticker = find_ticker(conn, "DIS")
        assert ticker is not None
        assert ticker["name"] == "The Walt Disney Company"
        assert ticker["rules"] == {}
        assert "added_at" in ticker

    def test_add_duplicate_fails(self, conn):
        result = add_ticker(conn, "CAKE", "Duplicate")
        assert result["success"] is False
        assert "already" in result["message"].lower()

    def test_add_strips_dollar_sign(self, conn):
        result = add_ticker(conn, "$DIS", "Disney")
        assert result["success"] is True
        ticker = find_ticker(conn, "DIS")
        assert ticker["symbol"] == "DIS"  # stored without $

    def test_add_uppercases_symbol(self, conn):
        result = add_ticker(conn, "dis", "Disney")
        assert result["success"] is True
        ticker = find_ticker(conn, "DIS")
        assert ticker["symbol"] == "DIS"

    def test_add_empty_symbol_fails(self, conn):
        result = add_ticker(conn, "", "No Symbol")
        assert result["success"] is False

    def test_add_empty_name_fails(self, conn):
        result = add_ticker(conn, "DIS", "")
        assert result["success"] is False

    def test_add_with_theme(self, conn):
        result = add_ticker(conn, "BNTX", "BioNTech", theme="mRNA cancer research")
        assert result["success"] is True
        ticker = find_ticker(conn, "BNTX")
        assert ticker["theme"] == "mRNA cancer research"
        assert "Theme" in result["message"]

    def test_add_with_directive(self, conn):
        result = add_ticker(conn, "BNTX", "BioNTech", directive="Focus on clinical trials")
        assert result["success"] is True
        ticker = find_ticker(conn, "BNTX")
        assert ticker["directive"] == "Focus on clinical trials"

    def test_add_with_explore_adjacent(self, conn):
        result = add_ticker(conn, "BNTX", "BioNTech", explore_adjacent=True)
        assert result["success"] is True
        ticker = find_ticker(conn, "BNTX")
        assert ticker["explore_adjacent"] is True
        assert "exploration enabled" in result["message"]

    def test_add_defaults_for_new_fields(self, conn):
        result = add_ticker(conn, "DIS", "Disney")
        assert result["success"] is True
        ticker = find_ticker(conn, "DIS")
        assert ticker["theme"] is None
        assert ticker["directive"] is None
        assert ticker["explore_adjacent"] is False


# ─── Removing Tickers ─────────────────────────────────────────────


class TestRemoveTicker:
    def test_remove_existing_ticker(self, conn):
        result = remove_ticker(conn, "CAKE")
        assert result["success"] is True
        assert find_ticker(conn, "CAKE") is None

    def test_remove_nonexistent_fails(self, conn):
        result = remove_ticker(conn, "AAPL")
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_remove_case_insensitive(self, conn):
        result = remove_ticker(conn, "$cake")
        assert result["success"] is True
        assert find_ticker(conn, "CAKE") is None


# ─── Setting Per-Ticker Rules ─────────────────────────────────────


class TestSetRule:
    def test_set_valid_rule(self, conn):
        result = set_rule(conn, "CAKE", "price_movement_pct", 3)
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["rules"]["price_movement_pct"] == 3

    def test_set_boolean_rule(self, conn):
        result = set_rule(conn, "CAKE", "sec_filing", False)
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["rules"]["sec_filing"] is False

    def test_set_rule_nonexistent_ticker_fails(self, conn):
        result = set_rule(conn, "AAPL", "sec_filing", False)
        assert result["success"] is False

    def test_set_invalid_rule_name_fails(self, conn):
        result = set_rule(conn, "CAKE", "made_up_rule", 42)
        assert result["success"] is False
        assert "invalid" in result["message"].lower() or "unknown" in result["message"].lower()

    def test_set_rule_wrong_type_fails(self, conn):
        # price_movement_pct should be numeric, not a string
        result = set_rule(conn, "CAKE", "price_movement_pct", "not_a_number")
        assert result["success"] is False


# ─── Resetting Rules ──────────────────────────────────────────────


class TestResetRules:
    def test_reset_clears_overrides(self, conn):
        # HOG has price_movement_pct: 3 override
        ticker = find_ticker(conn, "HOG")
        assert ticker["rules"] != {}

        result = reset_rules(conn, "HOG")
        assert result["success"] is True
        ticker = find_ticker(conn, "HOG")
        assert ticker["rules"] == {}

    def test_reset_nonexistent_ticker_fails(self, conn):
        result = reset_rules(conn, "AAPL")
        assert result["success"] is False


# ─── Global Settings ──────────────────────────────────────────────


class TestSetGlobal:
    def test_set_significance_threshold(self, conn):
        result = set_global(conn, "significance_threshold", 4)
        assert result["success"] is True
        from db import get_setting
        assert get_setting(conn, "significance_threshold") == 4

    def test_set_invalid_global_key_fails(self, conn):
        result = set_global(conn, "nonexistent_key", 42)
        assert result["success"] is False

    def test_set_model(self, conn):
        result = set_global(conn, "cheap_model", "llama-3-70b")
        assert result["success"] is True
        from db import get_setting
        assert get_setting(conn, "cheap_model") == "llama-3-70b"


# ─── Effective Rules (Defaults + Overrides) ───────────────────────


class TestEffectiveRules:
    def test_no_overrides_returns_defaults(self, conn):
        effective = get_effective_rules(conn, "CAKE")
        defaults = get_default_rules(conn)
        assert effective == defaults

    def test_override_merges_with_defaults(self, conn):
        effective = get_effective_rules(conn, "HOG")
        # HOG overrides price_movement_pct to 3
        assert effective["price_movement_pct"] == 3
        # But inherits all other defaults
        assert effective["sentiment_shift"] is True
        assert effective["social_volume_spike"] is True
        assert effective["sec_filing"] is True
        assert effective["competitive_news"] is True

    def test_nonexistent_ticker_returns_none(self, conn):
        assert get_effective_rules(conn, "AAPL") is None


# ─── Show Watchlist ───────────────────────────────────────────────


class TestShowWatchlist:
    def test_show_returns_string(self, conn):
        output = show_watchlist(conn)
        assert isinstance(output, str)

    def test_show_includes_all_tickers(self, conn):
        output = show_watchlist(conn)
        assert "CAKE" in output
        assert "HOG" in output

    def test_show_includes_overrides(self, conn):
        output = show_watchlist(conn)
        # HOG has a custom price_movement_pct of 3
        assert "3" in output

    def test_show_empty_watchlist(self):
        c = get_connection(":memory:")
        init_db(c)
        output = show_watchlist(c)
        assert "no tickers" in output.lower() or output
        c.close()

    def test_show_includes_theme_directive(self, conn):
        set_directive(conn, "CAKE", theme="Casual dining expansion")
        set_directive(conn, "CAKE", directive="Watch franchise deals")
        output = show_watchlist(conn)
        assert "Casual dining expansion" in output
        assert "Watch franchise deals" in output
        assert "🎯" in output
        assert "📌" in output


# ─── Set Directive ────────────────────────────────────────────────


class TestSetDirective:
    def test_set_theme(self, conn):
        result = set_directive(conn, "CAKE", theme="Casual dining")
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["theme"] == "Casual dining"

    def test_set_directive_text(self, conn):
        result = set_directive(conn, "CAKE", directive="Focus on franchise expansion")
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["directive"] == "Focus on franchise expansion"

    def test_set_explore_adjacent(self, conn):
        result = set_directive(conn, "CAKE", explore_adjacent=True)
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["explore_adjacent"] is True

    def test_set_multiple_fields(self, conn):
        result = set_directive(
            conn,
            "CAKE",
            theme="Casual dining",
            directive="Watch franchise deals",
            explore_adjacent=True,
        )
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["theme"] == "Casual dining"
        assert ticker["directive"] == "Watch franchise deals"
        assert ticker["explore_adjacent"] is True

    def test_clear_theme(self, conn):
        # First set a theme
        set_directive(conn, "CAKE", theme="Test theme")
        # Then clear it
        result = set_directive(conn, "CAKE", theme="")
        assert result["success"] is True
        ticker = find_ticker(conn, "CAKE")
        assert ticker["theme"] is None

    def test_nonexistent_ticker_fails(self, conn):
        result = set_directive(conn, "AAPL", theme="Test")
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_no_changes_fails(self, conn):
        result = set_directive(conn, "CAKE")
        assert result["success"] is False
        assert "no changes" in result["message"].lower()

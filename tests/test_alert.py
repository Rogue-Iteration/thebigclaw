"""
Tests for alert.py — Phase 5 (TDD) + Multi-Agent Extensions

Tests cover:
- Alert message formatting (severity, reasons, actions)
- Agent name prefix in alerts
- Heartbeat summary formatting
- Alert threshold logic
- Morning briefing formatting (Max)
"""

from pathlib import Path

import pytest

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant" / "scripts"
sys.path.insert(0, str(SKILL_DIR))

from alert import (
    format_alert_message,
    format_heartbeat_summary,
    should_alert,
    format_morning_briefing,
    AGENT_PREFIXES,
)


# ─── Fixtures ─────────────────────────────────────────────────────


HIGH_SCORE_ANALYSIS = {
    "success": True,
    "significance_score": 8,
    "summary": "CAKE beat earnings by 12% with strong institutional buying.",
    "alert_reasons": ["Earnings beat >10%", "Institutional buying detected"],
    "should_alert": True,
    "recommended_action": "Review earnings report and consider adding to position.",
    "model_used": "claude-sonnet-4-5-20250514",
    "pass": "deep",
    "market_context": "Casual dining sector outperforming broad market.",
    "risks": ["Valuation stretched", "Consumer spending uncertainty"],
}

MEDIUM_SCORE_ANALYSIS = {
    "success": True,
    "significance_score": 6,
    "summary": "Notable insider selling detected at HOG.",
    "alert_reasons": ["Form 4 filing: CFO sold shares"],
    "should_alert": True,
    "recommended_action": "Monitor for further insider activity.",
    "model_used": "qwen3-32b",
    "pass": "initial",
}

LOW_SCORE_ANALYSIS = {
    "success": True,
    "significance_score": 3,
    "summary": "Routine trading day with no significant events.",
    "alert_reasons": [],
    "should_alert": False,
    "recommended_action": "No action needed.",
    "model_used": "qwen3-32b",
    "pass": "initial",
}


# ─── Alert Message Formatting ─────────────────────────────────────


class TestFormatAlertMessage:
    def test_includes_ticker(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "$CAKE" in msg
        assert "Cheesecake Factory" in msg

    def test_includes_score(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "8/10" in msg

    def test_high_score_has_red_emoji(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "🔴" in msg

    def test_medium_score_has_yellow_emoji(self):
        msg = format_alert_message("HOG", "Harley-Davidson", MEDIUM_SCORE_ANALYSIS)
        assert "🟡" in msg

    def test_includes_reasons(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "Earnings beat" in msg
        assert "Institutional buying" in msg

    def test_includes_action(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "Review earnings" in msg

    def test_includes_market_context_when_present(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "Casual dining" in msg

    def test_includes_risks_when_present(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "Valuation stretched" in msg

    def test_shows_analysis_type(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "Deep analysis" in msg


# ─── Heartbeat Summary ───────────────────────────────────────────


class TestFormatHeartbeatSummary:
    def test_empty_results(self):
        msg = format_heartbeat_summary([])
        assert "no tickers" in msg.lower() or "💤" in msg

    def test_all_clear(self):
        results = [
            {"ticker": "CAKE", "should_alert": False, "significance_score": 2},
            {"ticker": "HOG", "should_alert": False, "significance_score": 3},
        ]
        msg = format_heartbeat_summary(results)
        assert "2 tickers" in msg or "checked 2" in msg
        assert "All clear" in msg or "✅" in msg

    def test_with_alerts(self):
        results = [
            {"ticker": "CAKE", "should_alert": True, "significance_score": 8},
            {"ticker": "HOG", "should_alert": False, "significance_score": 2},
        ]
        msg = format_heartbeat_summary(results)
        assert "1 alert" in msg
        assert "$CAKE" in msg

    def test_shows_quiet_tickers(self):
        results = [
            {"ticker": "CAKE", "should_alert": True, "significance_score": 8},
            {"ticker": "HOG", "should_alert": False, "significance_score": 2},
            {"ticker": "BOOM", "should_alert": False, "significance_score": 1},
        ]
        msg = format_heartbeat_summary(results)
        assert "$HOG" in msg
        assert "$BOOM" in msg


# ─── Alert Threshold Logic ───────────────────────────────────────


class TestShouldAlert:
    def test_high_score_alerts(self):
        assert should_alert(HIGH_SCORE_ANALYSIS, threshold=6) is True

    def test_low_score_does_not_alert(self):
        assert should_alert(LOW_SCORE_ANALYSIS, threshold=6) is False

    def test_exact_threshold_alerts(self):
        assert should_alert(MEDIUM_SCORE_ANALYSIS, threshold=6) is True

    def test_failed_analysis_does_not_alert(self):
        failed = {"success": False, "significance_score": 10}
        assert should_alert(failed, threshold=6) is False

    def test_custom_threshold(self):
        assert should_alert(HIGH_SCORE_ANALYSIS, threshold=9) is False
        assert should_alert(HIGH_SCORE_ANALYSIS, threshold=8) is True


# ─── Agent Name Prefix ───────────────────────────────────────────


class TestAgentNamePrefix:
    def test_alert_with_nova_prefix(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS, agent_name="nova")
        assert "📰 **Nova here**" in msg

    def test_alert_with_max_prefix(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS, agent_name="max")
        assert "🧠 **Max here**" in msg

    def test_alert_without_agent_name(self):
        msg = format_alert_message("CAKE", "The Cheesecake Factory", HIGH_SCORE_ANALYSIS)
        assert "Nova" not in msg
        assert "Max" not in msg

    def test_heartbeat_with_agent_name(self):
        results = [
            {"ticker": "CAKE", "should_alert": False, "significance_score": 2},
        ]
        msg = format_heartbeat_summary(results, agent_name="nova")
        assert "📰 **Nova here**" in msg

    def test_heartbeat_empty_with_agent_name(self):
        msg = format_heartbeat_summary([], agent_name="nova")
        assert "📰 **Nova here**" in msg


# ─── Morning Briefing ────────────────────────────────────────────


class TestFormatMorningBriefing:
    def test_basic_briefing(self):
        summaries = [
            {
                "ticker": "CAKE",
                "company": "The Cheesecake Factory",
                "thesis": "Strong earnings trajectory, bullish momentum.",
                "conviction": "high",
                "overnight": ["Q4 earnings beat estimates by 12%"],
            },
        ]
        msg = format_morning_briefing(summaries)
        assert "🧠 **Max here**" in msg
        assert "Morning Briefing" in msg
        assert "$CAKE" in msg
        assert "Conviction: high" in msg
        assert "🟢" in msg
        assert "Q4 earnings" in msg

    def test_empty_watchlist(self):
        msg = format_morning_briefing([])
        assert "No tickers" in msg

    def test_team_activity(self):
        summaries = [
            {
                "ticker": "CAKE",
                "company": "The Cheesecake Factory",
                "thesis": "Watching",
                "conviction": "medium",
                "overnight": [],
            },
        ]
        team = {
            "nova_articles": 15,
            "nova_filings": 3,
            "inter_agent_highlights": ["Nova flagged new 8-K for $CAKE"],
        }
        msg = format_morning_briefing(summaries, team_activity=team)
        assert "TEAM ACTIVITY" in msg
        assert "15 articles" in msg
        assert "3 filings" in msg
        assert "8-K" in msg

    def test_includes_disclaimer(self):
        msg = format_morning_briefing([])
        assert "not financial advice" in msg

    def test_includes_question(self):
        msg = format_morning_briefing([])
        assert "dig into" in msg

    def test_quiet_overnight(self):
        summaries = [
            {
                "ticker": "HOG",
                "company": "Harley-Davidson",
                "thesis": "Sideways trading.",
                "conviction": "low",
                "overnight": [],
            },
        ]
        msg = format_morning_briefing(summaries)
        assert "Quiet overnight" in msg
        assert "🔴" in msg  # Low conviction

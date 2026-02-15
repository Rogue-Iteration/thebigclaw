"""
Tests for analyze.py — Phase 3 (TDD)

Tests cover:
- Prompt construction (analysis + deep analysis)
- LLM response parsing (clean JSON, markdown-wrapped, malformed)
- Two-pass model routing logic
- Error handling (missing API key, API failures)
"""

import json
from pathlib import Path

import pytest
import responses

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant" / "scripts"
INFERENCE_DIR = Path(__file__).parent.parent / "skills" / "gradient-inference" / "scripts"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(INFERENCE_DIR))

from analyze import (
    build_analysis_prompt,
    build_deep_analysis_prompt,
    parse_llm_response,
    call_gradient_inference,
    analyze_ticker,
    GRADIENT_INFERENCE_URL,
    DEEP_ANALYSIS_THRESHOLD,
)


# ─── Fixtures ─────────────────────────────────────────────────────


SAMPLE_RULES = {
    "price_movement_pct": 5,
    "sentiment_shift": True,
    "social_volume_spike": True,
    "sec_filing": True,
    "competitive_news": True,
}

SAMPLE_RESEARCH = """# Research Report: CAKE
## News
Cheesecake Factory beat Q4 earnings by 12%.
## Reddit
Strong bullish sentiment on r/stocks.
## SEC
10-K annual report filed.
"""

SAMPLE_ANALYSIS_RESPONSE = {
    "significance_score": 7,
    "summary": "CAKE beat earnings by 12% with strong social sentiment. Major annual filing detected.",
    "alert_reasons": ["Earnings beat >10%", "Bullish social sentiment"],
    "should_alert": True,
    "recommended_action": "Review earnings report details and consider position sizing.",
}

LOW_SCORE_RESPONSE = {
    "significance_score": 3,
    "summary": "Routine trading day with no significant events.",
    "alert_reasons": [],
    "should_alert": False,
    "recommended_action": "No action needed.",
}

DEEP_ANALYSIS_RESPONSE = {
    "significance_score": 8,
    "summary": "Earnings beat is significant and validated by strong institutional sentiment.",
    "alert_reasons": ["Earnings beat", "Institutional buying"],
    "should_alert": True,
    "recommended_action": "Consider adding to position before momentum builds.",
    "market_context": "Casual dining sector is outperforming.",
    "risks": ["Valuation may be stretched", "Consumer spending could slow"],
}

SAMPLE_GLOBAL_SETTINGS = {
    "significance_threshold": 6,
    "cheap_model": "qwen3-32b",
    "strong_model": "claude-sonnet-4-5-20250514",
}


# ─── Prompt Construction ─────────────────────────────────────────


class TestBuildAnalysisPrompt:
    def test_includes_ticker(self):
        prompt = build_analysis_prompt("CAKE", "The Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_RULES)
        assert "CAKE" in prompt
        assert "Cheesecake Factory" in prompt

    def test_includes_rules(self):
        prompt = build_analysis_prompt("CAKE", "The Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_RULES)
        assert "price_movement_pct" in prompt
        assert "sentiment_shift" in prompt

    def test_includes_research_data(self):
        prompt = build_analysis_prompt("CAKE", "The Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_RULES)
        assert "beat Q4 earnings" in prompt

    def test_requests_json_response(self):
        prompt = build_analysis_prompt("CAKE", "The Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_RULES)
        assert "JSON" in prompt


class TestBuildDeepAnalysisPrompt:
    def test_includes_initial_analysis(self):
        prompt = build_deep_analysis_prompt("CAKE", "The Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_ANALYSIS_RESPONSE)
        assert "7" in prompt  # significance score from initial
        assert "junior analyst" in prompt.lower() or "Junior" in prompt

    def test_includes_research_data(self):
        prompt = build_deep_analysis_prompt("CAKE", "The Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_ANALYSIS_RESPONSE)
        assert "beat Q4 earnings" in prompt


# ─── Response Parsing ─────────────────────────────────────────────


class TestParseLLMResponse:
    def test_parses_clean_json(self):
        result = parse_llm_response(json.dumps(SAMPLE_ANALYSIS_RESPONSE))
        assert result == SAMPLE_ANALYSIS_RESPONSE

    def test_parses_json_with_code_fences(self):
        wrapped = f"```json\n{json.dumps(SAMPLE_ANALYSIS_RESPONSE)}\n```"
        result = parse_llm_response(wrapped)
        assert result == SAMPLE_ANALYSIS_RESPONSE

    def test_parses_json_with_whitespace(self):
        padded = f"\n\n  {json.dumps(SAMPLE_ANALYSIS_RESPONSE)}  \n\n"
        result = parse_llm_response(padded)
        assert result == SAMPLE_ANALYSIS_RESPONSE

    def test_returns_none_for_invalid_json(self):
        assert parse_llm_response("not json at all") is None

    def test_returns_none_for_empty_string(self):
        assert parse_llm_response("") is None


# ─── Gradient API Call (Mocked) ───────────────────────────────────


class TestCallGradientInference:
    @responses.activate
    def test_successful_call(self):
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={
                "choices": [{"message": {"content": json.dumps(SAMPLE_ANALYSIS_RESPONSE)}}]
            },
            status=200,
        )
        result = call_gradient_inference("test prompt", "qwen3-32b", "fake-key")
        assert result is not None
        assert "significance_score" in result

    @responses.activate
    def test_handles_api_error(self):
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            body="Internal Server Error",
            status=500,
        )
        result = call_gradient_inference("test prompt", "qwen3-32b", "fake-key")
        assert result is None

    @responses.activate
    def test_handles_malformed_response(self):
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"unexpected": "format"},
            status=200,
        )
        result = call_gradient_inference("test prompt", "qwen3-32b", "fake-key")
        assert result is None


# ─── Full Analysis Pipeline ──────────────────────────────────────


class TestAnalyzeTicker:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = analyze_ticker("CAKE", "Cheesecake Factory", SAMPLE_RESEARCH, SAMPLE_RULES, SAMPLE_GLOBAL_SETTINGS)
        assert result["success"] is False
        assert "API_KEY" in result["error"]

    @responses.activate
    def test_low_score_skips_deep_analysis(self):
        """When initial score < threshold, no second pass."""
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"choices": [{"message": {"content": json.dumps(LOW_SCORE_RESPONSE)}}]},
            status=200,
        )
        result = analyze_ticker(
            "CAKE", "Cheesecake Factory", SAMPLE_RESEARCH,
            SAMPLE_RULES, SAMPLE_GLOBAL_SETTINGS, api_key="fake-key"
        )
        assert result["success"] is True
        assert result["significance_score"] == 3
        assert result["should_alert"] is False
        assert result["model_used"] == "qwen3-32b"
        # Only one API call should have been made
        assert len(responses.calls) == 1

    @responses.activate
    def test_high_score_triggers_deep_analysis(self):
        """When initial score >= DEEP_ANALYSIS_THRESHOLD, second pass runs."""
        # First call: initial analysis with high score
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"choices": [{"message": {"content": json.dumps(SAMPLE_ANALYSIS_RESPONSE)}}]},
            status=200,
        )
        # Second call: deep analysis
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"choices": [{"message": {"content": json.dumps(DEEP_ANALYSIS_RESPONSE)}}]},
            status=200,
        )

        result = analyze_ticker(
            "CAKE", "Cheesecake Factory", SAMPLE_RESEARCH,
            SAMPLE_RULES, SAMPLE_GLOBAL_SETTINGS, api_key="fake-key"
        )

        assert result["success"] is True
        assert result["pass"] == "deep"
        assert result["model_used"] == "claude-sonnet-4-5-20250514"
        assert result["significance_score"] == 8
        assert "initial_analysis" in result
        # Two API calls: initial + deep
        assert len(responses.calls) == 2

    @responses.activate
    def test_deep_analysis_failure_falls_back_to_initial(self):
        """If deep analysis fails, fall back to initial result."""
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"choices": [{"message": {"content": json.dumps(SAMPLE_ANALYSIS_RESPONSE)}}]},
            status=200,
        )
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            body="Error",
            status=500,
        )

        result = analyze_ticker(
            "CAKE", "Cheesecake Factory", SAMPLE_RESEARCH,
            SAMPLE_RULES, SAMPLE_GLOBAL_SETTINGS, api_key="fake-key"
        )

        assert result["success"] is True
        assert result["pass"] == "initial"  # fell back
        assert result["significance_score"] == 7

"""
Tests for gather_web.py — Nova's web research gathering.

Tests cover:
- News RSS parsing (reuses gather.py test patterns)
- SEC filing parsing
- Theme-aware news fetching
- Combined gather_web() function
"""

from pathlib import Path

import pytest

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "web-researcher"
sys.path.insert(0, str(SKILL_DIR))

# Also add original skill dir for shared fixtures
ORIGINAL_SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(ORIGINAL_SKILL_DIR))

from gather_web import (
    parse_news_rss,
    format_news_markdown,
    fetch_news,
    parse_sec_filings,
    format_sec_markdown,
    fetch_sec_filings,
    gather_web,
)


# ─── Fixtures ─────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def google_news_xml():
    return (FIXTURES_DIR / "google_news_CAKE.xml").read_text()


@pytest.fixture
def sec_edgar_json():
    import json
    return json.loads((FIXTURES_DIR / "sec_edgar_CAKE.json").read_text())


# ─── News Parsing ─────────────────────────────────────────────────


class TestParseNewsRSS:
    def test_parses_valid_rss(self, google_news_xml):
        items = parse_news_rss(google_news_xml)
        assert len(items) > 0
        assert "title" in items[0]
        assert "link" in items[0]
        assert "published" in items[0]

    def test_returns_empty_for_empty_string(self):
        items = parse_news_rss("")
        assert items == []

    def test_returns_empty_for_invalid_xml(self):
        items = parse_news_rss("not xml at all")
        # feedparser may return empty entries for non-XML
        assert isinstance(items, list)


class TestFormatNewsMarkdown:
    def test_format_with_items(self, google_news_xml):
        items = parse_news_rss(google_news_xml)
        md = format_news_markdown("CAKE", items)
        assert "# News: CAKE" in md
        assert "##" in md  # At least one headline

    def test_format_empty_items(self):
        md = format_news_markdown("CAKE", [])
        assert "No recent news found" in md


# ─── SEC Filing Parsing ──────────────────────────────────────────


class TestParseSecFilings:
    def test_parses_valid_data(self, sec_edgar_json):
        filings = parse_sec_filings(sec_edgar_json)
        assert len(filings) > 0
        assert "form_type" in filings[0]
        assert "file_date" in filings[0]

    def test_returns_empty_for_empty_hits(self):
        filings = parse_sec_filings({"hits": {"hits": []}})
        assert filings == []

    def test_returns_empty_for_invalid_data(self):
        filings = parse_sec_filings({})
        assert filings == []

    def test_returns_empty_for_none(self):
        filings = parse_sec_filings(None)
        assert filings == []


class TestFormatSecMarkdown:
    def test_format_with_filings(self, sec_edgar_json):
        filings = parse_sec_filings(sec_edgar_json)
        md = format_sec_markdown("CAKE", filings)
        assert "# SEC Filings: CAKE" in md

    def test_format_empty_filings(self):
        md = format_sec_markdown("CAKE", [])
        assert "No recent SEC filings found" in md


# ─── Combined Gather ─────────────────────────────────────────────


class TestGatherWeb:
    def test_returns_required_keys(self, monkeypatch):
        # Mock the network calls to return empty
        monkeypatch.setattr("gather_web.fetch_news", lambda *a, **kw: [])
        monkeypatch.setattr("gather_web.fetch_sec_filings", lambda *a, **kw: [])

        result = gather_web("CAKE", "The Cheesecake Factory")

        assert result["ticker"] == "CAKE"
        assert result["company"] == "The Cheesecake Factory"
        assert "timestamp" in result
        assert "markdown" in result
        assert "sources" in result
        assert "news" in result["sources"]
        assert "sec" in result["sources"]

    def test_includes_theme_in_result(self, monkeypatch):
        monkeypatch.setattr("gather_web.fetch_news", lambda *a, **kw: [])
        monkeypatch.setattr("gather_web.fetch_sec_filings", lambda *a, **kw: [])

        result = gather_web("BNTX", "BioNTech SE", theme="mRNA cancer research")

        assert result["theme"] == "mRNA cancer research"
        assert "mRNA cancer research" in result["markdown"]

    def test_includes_directive_in_result(self, monkeypatch):
        monkeypatch.setattr("gather_web.fetch_news", lambda *a, **kw: [])
        monkeypatch.setattr("gather_web.fetch_sec_filings", lambda *a, **kw: [])

        result = gather_web("BNTX", "BioNTech SE", directive="Focus on clinical trials")

        assert result["directive"] == "Focus on clinical trials"
        assert "Focus on clinical trials" in result["markdown"]

    def test_no_reddit_in_sources(self, monkeypatch):
        """gather_web should NOT include Reddit data — that's Pixel's job."""
        monkeypatch.setattr("gather_web.fetch_news", lambda *a, **kw: [])
        monkeypatch.setattr("gather_web.fetch_sec_filings", lambda *a, **kw: [])

        result = gather_web("CAKE", "The Cheesecake Factory")

        assert "reddit" not in result["sources"]

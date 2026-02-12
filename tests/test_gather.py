"""
Tests for gather.py — Phase 2 (TDD)

Tests cover:
- Parsing news from RSS feeds (Google News format)
- Parsing Reddit posts from JSON API
- Parsing SEC EDGAR filings
- Formatting results as structured Markdown
- Building the combined research document
- Error handling for malformed responses
"""

import json
from pathlib import Path

import pytest
import responses

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

FIXTURES_DIR = Path(__file__).parent / "fixtures"

from gather import (
    parse_news_rss,
    parse_reddit_posts,
    parse_sec_filings,
    format_news_markdown,
    format_reddit_markdown,
    format_sec_markdown,
    fetch_news,
    fetch_reddit,
    fetch_sec_filings,
    gather_all,
)


# ─── Fixture Loaders ──────────────────────────────────────────────


@pytest.fixture
def news_rss_xml():
    return (FIXTURES_DIR / "google_news_CAKE.xml").read_text()


@pytest.fixture
def reddit_json():
    return json.loads((FIXTURES_DIR / "reddit_CAKE.json").read_text())


@pytest.fixture
def sec_json():
    return json.loads((FIXTURES_DIR / "sec_edgar_CAKE.json").read_text())


# ─── News RSS Parsing ─────────────────────────────────────────────


class TestParseNewsRSS:
    def test_parses_correct_number_of_items(self, news_rss_xml):
        items = parse_news_rss(news_rss_xml)
        assert len(items) == 3

    def test_item_has_required_fields(self, news_rss_xml):
        items = parse_news_rss(news_rss_xml)
        for item in items:
            assert "title" in item
            assert "link" in item
            assert "published" in item
            assert "summary" in item

    def test_first_item_content(self, news_rss_xml):
        items = parse_news_rss(news_rss_xml)
        assert "Cheesecake Factory" in items[0]["title"]
        assert "Q4" in items[0]["title"]
        assert items[0]["link"].startswith("http")

    def test_empty_rss_returns_empty_list(self):
        empty_rss = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        items = parse_news_rss(empty_rss)
        assert items == []

    def test_malformed_rss_returns_empty_list(self):
        items = parse_news_rss("not xml at all")
        assert items == []


class TestFormatNewsMarkdown:
    def test_output_is_markdown(self, news_rss_xml):
        items = parse_news_rss(news_rss_xml)
        md = format_news_markdown("CAKE", items)
        assert "# News: CAKE" in md
        assert "##" in md  # sub-headers for each article

    def test_includes_all_articles(self, news_rss_xml):
        items = parse_news_rss(news_rss_xml)
        md = format_news_markdown("CAKE", items)
        assert "Cheesecake Factory" in md
        assert "Menu Expansion" in md
        assert "Restaurant Industry" in md

    def test_empty_items_produces_no_findings(self):
        md = format_news_markdown("CAKE", [])
        assert "no" in md.lower() or "CAKE" in md  # should handle gracefully


# ─── Reddit Parsing ───────────────────────────────────────────────


class TestParseRedditPosts:
    def test_parses_correct_number_of_posts(self, reddit_json):
        posts = parse_reddit_posts(reddit_json)
        assert len(posts) == 3

    def test_post_has_required_fields(self, reddit_json):
        posts = parse_reddit_posts(reddit_json)
        for post in posts:
            assert "title" in post
            assert "text" in post
            assert "author" in post
            assert "score" in post
            assert "comments" in post
            assert "subreddit" in post
            assert "url" in post

    def test_first_post_content(self, reddit_json):
        posts = parse_reddit_posts(reddit_json)
        assert "crushed earnings" in posts[0]["title"]
        assert posts[0]["score"] == 847
        assert posts[0]["subreddit"] == "stocks"

    def test_empty_response_returns_empty_list(self):
        empty = {"kind": "Listing", "data": {"children": []}}
        posts = parse_reddit_posts(empty)
        assert posts == []

    def test_malformed_response_returns_empty_list(self):
        posts = parse_reddit_posts({"unexpected": "format"})
        assert posts == []


class TestFormatRedditMarkdown:
    def test_output_is_markdown(self, reddit_json):
        posts = parse_reddit_posts(reddit_json)
        md = format_reddit_markdown("CAKE", posts)
        assert "# Reddit: CAKE" in md

    def test_includes_scores_and_comments(self, reddit_json):
        posts = parse_reddit_posts(reddit_json)
        md = format_reddit_markdown("CAKE", posts)
        assert "847" in md
        assert "234" in md  # num_comments from first post


# ─── SEC EDGAR Parsing ────────────────────────────────────────────


class TestParseSecFilings:
    def test_parses_correct_number_of_filings(self, sec_json):
        filings = parse_sec_filings(sec_json)
        assert len(filings) == 3

    def test_filing_has_required_fields(self, sec_json):
        filings = parse_sec_filings(sec_json)
        for filing in filings:
            assert "form_type" in filing
            assert "file_date" in filing
            assert "description" in filing
            assert "url" in filing

    def test_first_filing_is_10k(self, sec_json):
        filings = parse_sec_filings(sec_json)
        assert filings[0]["form_type"] == "10-K"
        assert filings[0]["description"] == "Annual Report"

    def test_includes_insider_form4(self, sec_json):
        filings = parse_sec_filings(sec_json)
        form_types = [f["form_type"] for f in filings]
        assert "4" in form_types

    def test_empty_response_returns_empty_list(self):
        empty = {"hits": {"hits": [], "total": {"value": 0}}}
        filings = parse_sec_filings(empty)
        assert filings == []

    def test_malformed_response_returns_empty_list(self):
        filings = parse_sec_filings({"unexpected": "format"})
        assert filings == []


class TestFormatSecMarkdown:
    def test_output_is_markdown(self, sec_json):
        filings = parse_sec_filings(sec_json)
        md = format_sec_markdown("CAKE", filings)
        assert "# SEC Filings: CAKE" in md

    def test_includes_form_types(self, sec_json):
        filings = parse_sec_filings(sec_json)
        md = format_sec_markdown("CAKE", filings)
        assert "10-K" in md
        assert "8-K" in md


# ─── HTTP Fetching (mocked) ──────────────────────────────────────


class TestFetchNews:
    @responses.activate
    def test_fetch_returns_parsed_items(self, news_rss_xml):
        responses.add(
            responses.GET,
            "https://news.google.com/rss/search",
            body=news_rss_xml,
            status=200,
            content_type="application/xml",
        )
        items = fetch_news("CAKE")
        assert len(items) == 3
        assert "Cheesecake Factory" in items[0]["title"]

    @responses.activate
    def test_fetch_handles_http_error(self):
        responses.add(
            responses.GET,
            "https://news.google.com/rss/search",
            body="Server Error",
            status=500,
        )
        items = fetch_news("CAKE")
        assert items == []


class TestFetchReddit:
    @responses.activate
    def test_fetch_returns_parsed_posts(self):
        reddit_data = json.loads((FIXTURES_DIR / "reddit_CAKE.json").read_text())
        responses.add(
            responses.GET,
            "https://www.reddit.com/search.json",
            json=reddit_data,
            status=200,
        )
        posts = fetch_reddit("CAKE")
        assert len(posts) == 3

    @responses.activate
    def test_fetch_handles_http_error(self):
        responses.add(
            responses.GET,
            "https://www.reddit.com/search.json",
            body="Too Many Requests",
            status=429,
        )
        posts = fetch_reddit("CAKE")
        assert posts == []


class TestFetchSecFilings:
    @responses.activate
    def test_fetch_returns_parsed_filings(self):
        sec_data = json.loads((FIXTURES_DIR / "sec_edgar_CAKE.json").read_text())
        responses.add(
            responses.GET,
            "https://efts.sec.gov/LATEST/search-index",
            json=sec_data,
            status=200,
        )
        filings = fetch_sec_filings("CAKE")
        assert len(filings) == 3

    @responses.activate
    def test_fetch_handles_http_error(self):
        responses.add(
            responses.GET,
            "https://efts.sec.gov/LATEST/search-index",
            body="Error",
            status=403,
        )
        filings = fetch_sec_filings("CAKE")
        assert filings == []


# ─── Gather All ───────────────────────────────────────────────────


class TestGatherAll:
    @responses.activate
    def test_gather_all_returns_combined_document(self):
        news_xml = (FIXTURES_DIR / "google_news_CAKE.xml").read_text()
        reddit_data = json.loads((FIXTURES_DIR / "reddit_CAKE.json").read_text())
        sec_data = json.loads((FIXTURES_DIR / "sec_edgar_CAKE.json").read_text())

        responses.add(responses.GET, "https://news.google.com/rss/search", body=news_xml, status=200)
        responses.add(responses.GET, "https://www.reddit.com/search.json", json=reddit_data, status=200)
        responses.add(responses.GET, "https://efts.sec.gov/LATEST/search-index", json=sec_data, status=200)

        result = gather_all("CAKE", "The Cheesecake Factory")
        assert "ticker" in result
        assert result["ticker"] == "CAKE"
        assert "markdown" in result
        assert "# Research Report: CAKE" in result["markdown"]
        assert "News" in result["markdown"]
        assert "Reddit" in result["markdown"]
        assert "SEC" in result["markdown"]

    @responses.activate
    def test_gather_all_handles_partial_failures(self):
        """Even if some sources fail, gather_all should still return what it can."""
        news_xml = (FIXTURES_DIR / "google_news_CAKE.xml").read_text()
        responses.add(responses.GET, "https://news.google.com/rss/search", body=news_xml, status=200)
        responses.add(responses.GET, "https://www.reddit.com/search.json", body="Error", status=500)
        responses.add(responses.GET, "https://efts.sec.gov/LATEST/search-index", body="Error", status=500)

        result = gather_all("CAKE", "The Cheesecake Factory")
        assert result["ticker"] == "CAKE"
        assert "News" in result["markdown"]
        # Reddit and SEC sections should still exist but indicate no data

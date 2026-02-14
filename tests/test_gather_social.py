"""
Tests for gather_social.py — Luna's social sentiment gathering.

Tests cover:
- Reddit post parsing
- Sentiment signal calculation
- Markdown formatting
- Combined gather_social() function
"""

from pathlib import Path

import pytest
import json

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "social-researcher"
sys.path.insert(0, str(SKILL_DIR))

from gather_social import (
    parse_reddit_posts,
    fetch_reddit,
    fetch_subreddit_posts,
    calculate_sentiment_signals,
    format_social_markdown,
    gather_social,
)


# ─── Fixtures ─────────────────────────────────────────────────────


SAMPLE_REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "CAKE earnings beat expectations",
                    "selftext": "Just saw the Q4 report, revenue up 12%",
                    "author": "stockfan123",
                    "score": 245,
                    "num_comments": 67,
                    "subreddit": "stocks",
                    "permalink": "/r/stocks/comments/abc123/cake_earnings",
                    "upvote_ratio": 0.89,
                    "created_utc": 1707900000,
                }
            },
            {
                "data": {
                    "title": "Is $CAKE a good buy right now?",
                    "selftext": "Looking at the fundamentals...",
                    "author": "investor42",
                    "score": 120,
                    "num_comments": 34,
                    "subreddit": "wallstreetbets",
                    "permalink": "/r/wallstreetbets/comments/def456/cake_buy",
                    "upvote_ratio": 0.75,
                    "created_utc": 1707890000,
                }
            },
            {
                "data": {
                    "title": "Cheesecake Factory expanding to Asia",
                    "selftext": "",
                    "author": "newsguy",
                    "score": 89,
                    "num_comments": 12,
                    "subreddit": "investing",
                    "permalink": "/r/investing/comments/ghi789/cheesecake_asia",
                    "upvote_ratio": 0.92,
                    "created_utc": 1707880000,
                }
            },
        ]
    }
}


@pytest.fixture
def reddit_data():
    return SAMPLE_REDDIT_RESPONSE


@pytest.fixture
def parsed_posts(reddit_data):
    return parse_reddit_posts(reddit_data)


# ─── Reddit Parsing ──────────────────────────────────────────────


class TestParseRedditPosts:
    def test_parses_valid_data(self, reddit_data):
        posts = parse_reddit_posts(reddit_data)
        assert len(posts) == 3
        assert posts[0]["title"] == "CAKE earnings beat expectations"
        assert posts[0]["score"] == 245
        assert posts[0]["comments"] == 67
        assert posts[0]["subreddit"] == "stocks"
        assert posts[0]["upvote_ratio"] == 0.89

    def test_returns_empty_for_missing_data(self):
        assert parse_reddit_posts({}) == []

    def test_returns_empty_for_none(self):
        assert parse_reddit_posts(None) == []

    def test_returns_empty_for_no_children(self):
        assert parse_reddit_posts({"data": {"children": []}}) == []

    def test_skips_empty_post_data(self):
        data = {"data": {"children": [{"data": {}}, {"data": None}]}}
        posts = parse_reddit_posts(data)
        assert len(posts) == 0

    def test_includes_url(self, reddit_data):
        posts = parse_reddit_posts(reddit_data)
        assert "reddit.com" in posts[0]["url"]

    def test_includes_created_utc(self, reddit_data):
        posts = parse_reddit_posts(reddit_data)
        assert posts[0]["created_utc"] == 1707900000


# ─── Sentiment Signal Calculation ─────────────────────────────────


class TestCalculateSentimentSignals:
    def test_calculates_from_valid_posts(self, parsed_posts):
        signals = calculate_sentiment_signals(parsed_posts)
        assert signals["post_count"] == 3
        assert signals["avg_score"] > 0
        assert signals["avg_comments"] > 0
        assert signals["avg_upvote_ratio"] > 0
        assert signals["cross_subreddit_spread"] == 3
        assert signals["volume_signal"] == "low"  # 3 posts = low
        assert signals["sentiment_signal"] == "bullish"  # avg ratio > 0.75

    def test_empty_posts(self):
        signals = calculate_sentiment_signals([])
        assert signals["post_count"] == 0
        assert signals["volume_signal"] == "none"
        assert signals["sentiment_signal"] == "no_data"

    def test_high_volume_signal(self):
        # Create 15 posts for high volume
        posts = [
            {"title": f"Post {i}", "score": 100, "comments": 20,
             "subreddit": "stocks", "upvote_ratio": 0.8, "url": f"/post/{i}"}
            for i in range(15)
        ]
        signals = calculate_sentiment_signals(posts)
        assert signals["volume_signal"] == "high"

    def test_moderate_volume_signal(self):
        posts = [
            {"title": f"Post {i}", "score": 50, "comments": 10,
             "subreddit": "stocks", "upvote_ratio": 0.7, "url": f"/post/{i}"}
            for i in range(7)
        ]
        signals = calculate_sentiment_signals(posts)
        assert signals["volume_signal"] == "moderate"

    def test_bearish_sentiment(self):
        posts = [
            {"title": "Bad news", "score": 10, "comments": 5,
             "subreddit": "stocks", "upvote_ratio": 0.35, "url": "/post/1"},
            {"title": "Terrible Q4", "score": 5, "comments": 3,
             "subreddit": "investing", "upvote_ratio": 0.40, "url": "/post/2"},
        ]
        signals = calculate_sentiment_signals(posts)
        assert signals["sentiment_signal"] == "bearish"

    def test_neutral_sentiment(self):
        posts = [
            {"title": "Meh", "score": 20, "comments": 5,
             "subreddit": "stocks", "upvote_ratio": 0.55, "url": "/post/1"},
        ]
        signals = calculate_sentiment_signals(posts)
        assert signals["sentiment_signal"] == "neutral"

    def test_top_post(self, parsed_posts):
        signals = calculate_sentiment_signals(parsed_posts)
        assert signals["top_post"]["title"] == "CAKE earnings beat expectations"
        assert signals["top_post"]["score"] == 245

    def test_subreddit_distribution(self, parsed_posts):
        signals = calculate_sentiment_signals(parsed_posts)
        assert "stocks" in signals["subreddits"]
        assert "wallstreetbets" in signals["subreddits"]
        assert "investing" in signals["subreddits"]


# ─── Markdown Formatting ─────────────────────────────────────────


class TestFormatSocialMarkdown:
    def test_format_with_posts(self, parsed_posts):
        signals = calculate_sentiment_signals(parsed_posts)
        md = format_social_markdown("CAKE", parsed_posts, signals)
        assert "Social Sentiment: $CAKE" in md
        assert "Sentiment Signals" in md
        assert "Recent Discussions" in md

    def test_format_empty_posts(self):
        signals = calculate_sentiment_signals([])
        md = format_social_markdown("CAKE", [], signals)
        assert "Social Sentiment: $CAKE" in md
        assert "No recent Reddit discussions found" in md

    def test_includes_signal_data(self, parsed_posts):
        signals = calculate_sentiment_signals(parsed_posts)
        md = format_social_markdown("CAKE", parsed_posts, signals)
        assert "Volume" in md
        assert "Sentiment" in md
        assert "Engagement Ratio" in md

    def test_includes_subreddit_breakdown(self, parsed_posts):
        signals = calculate_sentiment_signals(parsed_posts)
        md = format_social_markdown("CAKE", parsed_posts, signals)
        assert "r/stocks" in md
        assert "r/wallstreetbets" in md


# ─── Combined Gather ─────────────────────────────────────────────


class TestGatherSocial:
    def test_returns_required_keys(self, monkeypatch):
        monkeypatch.setattr("gather_social.fetch_reddit", lambda *a, **kw: [])
        monkeypatch.setattr("gather_social.fetch_subreddit_posts", lambda *a, **kw: [])

        result = gather_social("CAKE", "The Cheesecake Factory")

        assert result["ticker"] == "CAKE"
        assert result["company"] == "The Cheesecake Factory"
        assert "timestamp" in result
        assert "markdown" in result
        assert "signals" in result
        assert "sources" in result
        assert "reddit" in result["sources"]

    def test_includes_theme_and_directive(self, monkeypatch):
        monkeypatch.setattr("gather_social.fetch_reddit", lambda *a, **kw: [])
        monkeypatch.setattr("gather_social.fetch_subreddit_posts", lambda *a, **kw: [])

        result = gather_social("BNTX", "BioNTech SE", theme="mRNA", directive="Focus on trials")

        assert result["theme"] == "mRNA"
        assert result["directive"] == "Focus on trials"
        assert "mRNA" in result["markdown"]

    def test_deduplicates_posts(self, monkeypatch):
        """Posts from global search and subreddit search should be deduplicated."""
        post = {
            "title": "Test", "text": "", "author": "user", "score": 10,
            "comments": 5, "subreddit": "stocks",
            "url": "https://www.reddit.com/r/stocks/123",
            "upvote_ratio": 0.8, "created_utc": 1707900000,
        }
        monkeypatch.setattr("gather_social.fetch_reddit", lambda *a, **kw: [post])
        monkeypatch.setattr("gather_social.fetch_subreddit_posts", lambda *a, **kw: [post])

        result = gather_social("CAKE", "The Cheesecake Factory")

        # Should only have 1 post, not duplicated
        assert len(result["sources"]["reddit"]) == 1

#!/usr/bin/env python3
"""
Social data gathering for Luna (Social Researcher).

Fetches public social sentiment data for a given stock ticker from:
- Reddit (public JSON API — r/wallstreetbets, r/stocks, r/investing, etc.)

Calculates sentiment signals:
- Post volume vs. estimated baseline
- Average score / engagement ratio
- Comment-to-post ratio
- Cross-subreddit spread

Usage:
    python3 gather_social.py --ticker CAKE --company "The Cheesecake Factory"
    python3 gather_social.py --ticker HOG --theme "EV motorcycle transition"
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import requests

# ─── Constants ────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "GradientResearchBot/1.0 (research; educational)",
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 15

# Subreddits to scan (in priority order)
TARGET_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "pennystocks",
    "options",
    "stockmarket",
]


# ─── Reddit Data Fetching ────────────────────────────────────────


def parse_reddit_posts(data: dict) -> list[dict]:
    """Parse Reddit listing JSON into structured posts.

    Returns:
        List of dicts with keys: title, text, author, score, comments,
        subreddit, url, upvote_ratio, created_utc
    """
    try:
        children = data.get("data", {}).get("children", [])
    except (AttributeError, TypeError):
        return []

    posts = []
    for child in children:
        post_data = child.get("data", {})
        if not post_data:
            continue
        posts.append({
            "title": post_data.get("title", ""),
            "text": post_data.get("selftext", ""),
            "author": post_data.get("author", "[deleted]"),
            "score": post_data.get("score", 0),
            "comments": post_data.get("num_comments", 0),
            "subreddit": post_data.get("subreddit", ""),
            "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
            "upvote_ratio": post_data.get("upvote_ratio", 0.0),
            "created_utc": post_data.get("created_utc", 0),
        })

    return posts


def fetch_reddit(
    ticker: str,
    theme: Optional[str] = None,
    directive: Optional[str] = None,
) -> list[dict]:
    """Fetch Reddit posts mentioning a ticker.

    Uses Reddit's public JSON search endpoint (no auth required).
    When a theme is provided, it's appended to the search query.

    Returns parsed posts or empty list on failure.
    """
    # Build query — include theme for focused results
    query_parts = [f"${ticker}", f"{ticker} stock"]
    if theme:
        query_parts.append(f"{ticker} {theme}")
    query = " OR ".join(query_parts)

    url = "https://www.reddit.com/search.json"
    params = {
        "q": query,
        "sort": "relevance",
        "t": "week",
        "limit": 25,
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return parse_reddit_posts(resp.json())
    except (requests.RequestException, json.JSONDecodeError, Exception):
        return []


def fetch_subreddit_posts(
    ticker: str,
    subreddit: str,
) -> list[dict]:
    """Fetch posts from a specific subreddit mentioning a ticker.

    Returns parsed posts or empty list on failure.
    """
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": f"${ticker} OR {ticker}",
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",
        "limit": 10,
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return parse_reddit_posts(resp.json())
    except (requests.RequestException, json.JSONDecodeError, Exception):
        return []


# ─── Sentiment Signal Calculation ─────────────────────────────────


def calculate_sentiment_signals(posts: list[dict]) -> dict:
    """Calculate sentiment signals from a set of Reddit posts.

    Returns:
        dict with:
        - post_count: total posts found
        - avg_score: average upvote score
        - avg_comments: average comments per post
        - avg_upvote_ratio: average upvote ratio (0-1)
        - engagement_ratio: total comments / total posts
        - subreddits: list of unique subreddits and post counts
        - cross_subreddit_spread: number of distinct subreddits
        - top_post: highest-scored post summary
        - volume_signal: 'high', 'moderate', or 'low'
        - sentiment_signal: 'bullish', 'bearish', or 'neutral' (based on upvote ratios)
    """
    if not posts:
        return {
            "post_count": 0,
            "avg_score": 0,
            "avg_comments": 0,
            "avg_upvote_ratio": 0,
            "engagement_ratio": 0,
            "subreddits": {},
            "cross_subreddit_spread": 0,
            "top_post": None,
            "volume_signal": "none",
            "sentiment_signal": "no_data",
        }

    total_score = sum(p.get("score", 0) for p in posts)
    total_comments = sum(p.get("comments", 0) for p in posts)
    total_upvote_ratio = sum(p.get("upvote_ratio", 0.5) for p in posts)

    count = len(posts)
    avg_score = total_score / count
    avg_comments = total_comments / count
    avg_upvote_ratio = total_upvote_ratio / count

    # Subreddit distribution
    subreddit_counts: dict[str, int] = {}
    for p in posts:
        sub = p.get("subreddit", "unknown")
        subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1

    # Top post
    top_post = max(posts, key=lambda p: p.get("score", 0))

    # Volume signal classification
    if count >= 15:
        volume_signal = "high"
    elif count >= 5:
        volume_signal = "moderate"
    else:
        volume_signal = "low"

    # Sentiment signal based on upvote ratios
    if avg_upvote_ratio >= 0.75:
        sentiment_signal = "bullish"
    elif avg_upvote_ratio <= 0.45:
        sentiment_signal = "bearish"
    else:
        sentiment_signal = "neutral"

    return {
        "post_count": count,
        "avg_score": round(avg_score, 1),
        "avg_comments": round(avg_comments, 1),
        "avg_upvote_ratio": round(avg_upvote_ratio, 3),
        "engagement_ratio": round(total_comments / count, 1) if count else 0,
        "subreddits": subreddit_counts,
        "cross_subreddit_spread": len(subreddit_counts),
        "top_post": {
            "title": top_post.get("title", ""),
            "score": top_post.get("score", 0),
            "comments": top_post.get("comments", 0),
            "subreddit": top_post.get("subreddit", ""),
            "url": top_post.get("url", ""),
        },
        "volume_signal": volume_signal,
        "sentiment_signal": sentiment_signal,
    }


# ─── Markdown Formatting ─────────────────────────────────────────


def format_social_markdown(
    ticker: str,
    posts: list[dict],
    signals: dict,
) -> str:
    """Format Reddit posts and sentiment signals as a Markdown report."""
    lines = [f"# Social Sentiment: ${ticker}", ""]

    # Signals summary
    lines.append("## Sentiment Signals")
    lines.append("")
    lines.append(f"- **Volume**: {signals.get('volume_signal', 'unknown')} ({signals.get('post_count', 0)} posts)")
    lines.append(f"- **Sentiment**: {signals.get('sentiment_signal', 'unknown')} (avg upvote ratio: {signals.get('avg_upvote_ratio', 0):.1%})")
    lines.append(f"- **Avg Score**: {signals.get('avg_score', 0)}")
    lines.append(f"- **Avg Comments**: {signals.get('avg_comments', 0)}")
    lines.append(f"- **Engagement Ratio**: {signals.get('engagement_ratio', 0):.1f} comments/post")
    lines.append(f"- **Subreddit Spread**: {signals.get('cross_subreddit_spread', 0)} subreddits")
    lines.append("")

    # Subreddit breakdown
    subreddits = signals.get("subreddits", {})
    if subreddits:
        lines.append("### Subreddit Breakdown")
        for sub, count in sorted(subreddits.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- r/{sub}: {count} posts")
        lines.append("")

    # Top post
    top_post = signals.get("top_post")
    if top_post and top_post.get("title"):
        lines.append("### Top Post")
        lines.append(f"**{top_post['title']}**")
        lines.append(f"*r/{top_post.get('subreddit', '?')} | ⬆ {top_post.get('score', 0)} | 💬 {top_post.get('comments', 0)}*")
        if top_post.get("url"):
            lines.append(f"[View on Reddit]({top_post['url']})")
        lines.append("")

    # Recent posts
    if posts:
        lines.append("## Recent Discussions")
        lines.append("")
        for post in posts[:10]:
            lines.append(f"### {post['title']}")
            lines.append(f"*r/{post['subreddit']} | ⬆ {post['score']} | 💬 {post['comments']} | u/{post['author']}*")
            lines.append("")
            if post.get("text"):
                text = post["text"][:500]
                if len(post["text"]) > 500:
                    text += "..."
                lines.append(text)
            lines.append(f"\n[View on Reddit]({post['url']})")
            lines.append("")
    else:
        lines.append("No recent Reddit discussions found.")

    return "\n".join(lines)


# ─── Combined Social Gather ─────────────────────────────────────


def gather_social(
    ticker: str,
    company_name: str,
    theme: Optional[str] = None,
    directive: Optional[str] = None,
) -> dict:
    """Gather social sentiment data for a ticker.

    This is Luna's primary entry point — Reddit sentiment and signals.

    Args:
        ticker: Stock ticker symbol
        company_name: Full company name
        theme: Optional research theme to focus the search
        directive: Optional research directive

    Returns:
        dict with keys:
        - ticker: the symbol
        - company: the company name
        - timestamp: ISO timestamp of the gather
        - markdown: the formatted Markdown report
        - signals: dict of calculated sentiment signals
        - sources: dict with raw parsed data
        - theme: the research theme (if any)
        - directive: the research directive (if any)
    """
    now = datetime.now(timezone.utc).isoformat()

    # Fetch from Reddit global search
    posts = fetch_reddit(ticker, theme=theme, directive=directive)

    # Also check target subreddits individually for broader coverage
    seen_urls = {p.get("url") for p in posts}
    for subreddit in TARGET_SUBREDDITS[:3]:  # Top 3 subreddits only to avoid rate limits
        sub_posts = fetch_subreddit_posts(ticker, subreddit)
        for post in sub_posts:
            if post.get("url") not in seen_urls:
                posts.append(post)
                seen_urls.add(post.get("url"))

    # Calculate sentiment signals
    signals = calculate_sentiment_signals(posts)

    # Format markdown
    markdown = format_social_markdown(ticker, posts, signals)

    # Add header
    header = f"# Social Research Report: ${ticker} ({company_name})\n"
    header += f"*Generated: {now}*\n"
    if theme:
        header += f"*Theme: {theme}*\n"
    if directive:
        header += f"*Directive: {directive}*\n"
    header += "\n---\n\n"

    return {
        "ticker": ticker,
        "company": company_name,
        "timestamp": now,
        "markdown": header + markdown,
        "signals": signals,
        "sources": {"reddit": posts},
        "theme": theme,
        "directive": directive,
    }


# ─── CLI Interface ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Gather social sentiment data for a stock ticker"
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--company", default=None, help="Company name")
    parser.add_argument("--theme", default=None, help="Research theme")
    parser.add_argument("--directive", default=None, help="Research directive")
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of markdown"
    )

    args = parser.parse_args()
    company = args.company or args.ticker

    result = gather_social(
        args.ticker.upper(),
        company,
        theme=args.theme,
        directive=args.directive,
    )

    if args.json:
        # Output JSON with signals
        output = {
            "ticker": result["ticker"],
            "company": result["company"],
            "timestamp": result["timestamp"],
            "signals": result["signals"],
            "sources": {"reddit_count": len(result["sources"]["reddit"])},
        }
        print(json.dumps(output, indent=2))
    else:
        print(result["markdown"])

    # Summary to stderr
    signals = result["signals"]
    print(
        f"\n📱 {result['ticker']}: {signals['post_count']} posts, "
        f"volume={signals['volume_signal']}, "
        f"sentiment={signals['sentiment_signal']}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

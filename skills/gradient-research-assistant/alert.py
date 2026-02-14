#!/usr/bin/env python3
"""
Alert formatting for the Gradient Research Team.

Formats analysis results into user-friendly Telegram messages
that OpenClaw delivers proactively. Supports agent name prefixes
so each agent's alerts are identifiable.

Usage:
    Called programmatically from the heartbeat cycle, not directly.
"""

import json
from datetime import datetime, timezone
from typing import Optional

# Agent name prefixes
AGENT_PREFIXES = {
    "nova": "📰 **Nova here** —",
    "max": "🧠 **Max here** —",
    "luna": "📱 **Luna here** —",
    "ace": "📈 **Ace here** —",
}


def format_alert_message(
    ticker: str,
    company_name: str,
    analysis: dict,
    agent_name: Optional[str] = None,
) -> str:
    """Format an analysis result as a proactive alert message.

    Args:
        ticker: Stock ticker symbol
        company_name: Full company name
        analysis: The result dict from analyze_ticker()
        agent_name: Optional agent name for message prefix (e.g., 'nova', 'max')

    Returns:
        Human-readable alert message string
    """
    score = analysis.get("significance_score", 0)
    summary = analysis.get("summary", "No summary available.")
    reasons = analysis.get("alert_reasons", [])
    action = analysis.get("recommended_action", "")
    model = analysis.get("model_used", "unknown")
    pass_type = analysis.get("pass", "initial")

    # Severity emoji
    if score >= 8:
        severity = "🔴"
    elif score >= 6:
        severity = "🟡"
    else:
        severity = "🟢"

    lines = []

    # Agent name prefix
    if agent_name and agent_name.lower() in AGENT_PREFIXES:
        lines.append(AGENT_PREFIXES[agent_name.lower()])
        lines.append("")

    lines.append(f"{severity} **Alert: ${ticker}** ({company_name})")
    lines.append(f"Significance: **{score}/10**")
    lines.append("")
    lines.append(f"📋 **Summary:** {summary}")
    lines.append("")

    if reasons:
        lines.append("🎯 **Why I'm alerting you:**")
        for reason in reasons:
            lines.append(f"  • {reason}")
        lines.append("")

    if action:
        lines.append(f"💡 **Recommended action:** {action}")
        lines.append("")

    # Additional deep analysis info
    market_context = analysis.get("market_context")
    if market_context:
        lines.append(f"🌍 **Market context:** {market_context}")
        lines.append("")

    risks = analysis.get("risks", [])
    if risks:
        lines.append("⚠️ **Risks to consider:**")
        for risk in risks:
            lines.append(f"  • {risk}")
        lines.append("")

    # Footer with metadata
    analysis_type = "Deep analysis" if pass_type == "deep" else "Quick scan"
    lines.append(f"_({analysis_type} via {model})_")
    lines.append("")
    lines.append("👉 Ask me for a **deep dive** on this ticker for more details.")

    return "\n".join(lines)


def format_heartbeat_summary(
    results: list[dict],
    agent_name: Optional[str] = None,
) -> str:
    """Format a summary of the entire heartbeat cycle.

    Args:
        results: List of analysis results for all tickers
        agent_name: Optional agent name for message prefix

    Returns:
        Summary message string
    """
    if not results:
        prefix = f"{AGENT_PREFIXES.get(agent_name.lower(), '')} " if agent_name else ""
        return f"{prefix}💤 Heartbeat complete. No tickers to check."

    alerts = [r for r in results if r.get("should_alert")]
    ok = [r for r in results if not r.get("should_alert")]

    lines = []

    if agent_name and agent_name.lower() in AGENT_PREFIXES:
        lines.append(AGENT_PREFIXES[agent_name.lower()])
        lines.append("")

    lines.append(f"💓 **Heartbeat Complete** — checked {len(results)} tickers")
    lines.append("")

    if alerts:
        lines.append(f"🚨 **{len(alerts)} alert(s) triggered:**")
        for r in alerts:
            ticker = r.get("ticker", "?")
            score = r.get("significance_score", 0)
            lines.append(f"  • ${ticker}: {score}/10")
    else:
        lines.append("✅ All clear — no significant events detected.")

    if ok:
        lines.append("")
        lines.append(f"😴 {len(ok)} ticker(s) quiet: {', '.join('$' + r.get('ticker', '?') for r in ok)}")

    return "\n".join(lines)


def should_alert(analysis: dict, threshold: int = 6) -> bool:
    """Determine whether an analysis result should trigger an alert.

    Args:
        analysis: The analysis result dict
        threshold: Minimum significance score to alert

    Returns:
        True if the user should be alerted
    """
    if not analysis.get("success", False):
        return False

    score = analysis.get("significance_score", 0)
    return score >= threshold


def format_morning_briefing(
    ticker_summaries: list[dict],
    team_activity: Optional[dict] = None,
) -> str:
    """Format Max's daily morning briefing.

    Args:
        ticker_summaries: List of dicts, each with:
            - ticker: symbol
            - company: company name
            - thesis: current thesis string
            - conviction: 'low', 'medium', or 'high'
            - overnight: list of overnight developments
        team_activity: Optional dict with:
            - nova_articles: count of articles Nova gathered
            - nova_filings: count of filings Nova found
            - luna_posts: count of Reddit posts Luna tracked
            - luna_sentiment: overall sentiment direction
            - ace_signals: count of technical signals Ace detected
            - inter_agent_highlights: list of notable inter-agent messages

    Returns:
        Formatted morning briefing message
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = []
    lines.append("🧠 **Max here** — Morning Briefing")
    lines.append(f"*{now}*")
    lines.append("")

    # Watchlist overview
    lines.append("📊 **WATCHLIST OVERVIEW**")
    lines.append("")

    if not ticker_summaries:
        lines.append("No tickers on the watchlist yet.")
    else:
        for ts in ticker_summaries:
            ticker = ts.get("ticker", "?")
            company = ts.get("company", "")
            thesis = ts.get("thesis", "No thesis yet.")
            conviction = ts.get("conviction", "—")

            conviction_emoji = {
                "high": "🟢",
                "medium": "🟡",
                "low": "🔴",
            }.get(conviction, "⚪")

            lines.append(f"**${ticker}** ({company}) {conviction_emoji} Conviction: {conviction}")
            lines.append(f"  {thesis}")

            overnight = ts.get("overnight", [])
            if overnight:
                for item in overnight:
                    lines.append(f"  • {item}")
            else:
                lines.append("  • Quiet overnight")
            lines.append("")

    # Team activity
    if team_activity:
        lines.append("📋 **TEAM ACTIVITY** (last 24h)")
        nova_articles = team_activity.get("nova_articles", 0)
        nova_filings = team_activity.get("nova_filings", 0)
        lines.append(f"  📰 Nova: {nova_articles} articles, {nova_filings} filings gathered")

        luna_posts = team_activity.get("luna_posts", 0)
        luna_sentiment = team_activity.get("luna_sentiment", "")
        if luna_posts or luna_sentiment:
            sentiment_str = f" ({luna_sentiment})" if luna_sentiment else ""
            lines.append(f"  📱 Luna: {luna_posts} social posts tracked{sentiment_str}")

        ace_signals = team_activity.get("ace_signals", 0)
        if ace_signals:
            lines.append(f"  📈 Ace: {ace_signals} technical signal(s) flagged")

        highlights = team_activity.get("inter_agent_highlights", [])
        if highlights:
            for h in highlights:
                lines.append(f"  • {h}")
        lines.append("")

    # Closing
    lines.append("❓ Anything you want me to dig into today?")
    lines.append("")
    lines.append("_Research data only — not financial advice._")

    return "\n".join(lines)

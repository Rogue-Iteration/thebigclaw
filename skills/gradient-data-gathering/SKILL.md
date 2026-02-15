---
name: gradient-data-gathering
description: >
  Data gathering tools for the Gradient Research Team. Fetches news (Google News RSS),
  SEC filings (EDGAR), Reddit sentiment, and technical price data (yfinance) for stock
  tickers on the watchlist.
metadata:
  clawdbot:
    requires:
      env:
        - GRADIENT_API_KEY
      bins:
        - python3
files: ["scripts/*"]
homepage: https://github.com/Rogue-Iteration/TheBigClaw
---

# Data Gathering

Three data-gathering scripts used by the Gradient Research Team agents.
Each agent runs its own gatherer on a heartbeat cycle and stores results via the
`gradient-research-assistant` shared skill.

## Scripts

### gather_web.py — News & SEC Filings (Nova)

```bash
python3 gather_web.py --ticker BNTX --name "BioNTech SE" --theme "mRNA cancer research"
```

Fetches from Google News RSS and SEC EDGAR full-text search.
Outputs a combined Markdown report with sourced articles and filings.

### gather_social.py — Reddit Sentiment (Luna)

```bash
python3 gather_social.py --ticker CAKE --company "The Cheesecake Factory"
python3 gather_social.py --ticker HOG --json
```

Searches Reddit (r/wallstreetbets, r/stocks, r/investing, etc.) and calculates
sentiment signals: volume, engagement ratio, cross-subreddit spread, upvote ratio.

### gather_technicals.py — Price & Indicators (Ace)

```bash
python3 gather_technicals.py --ticker CAKE --company "The Cheesecake Factory"
python3 gather_technicals.py --ticker HOG --json
```

Uses `yfinance` to fetch 6 months of OHLCV data and calculates:
SMA (20/50/200), RSI(14), MACD(12,26,9), Bollinger Bands(20,2), volume analysis.
Identifies signals: golden/death crosses, RSI overbought/oversold, MACD crossovers,
Bollinger squeezes, volume spikes.

## External Endpoints

| Endpoint | Data Sent | Script |
|----------|-----------|--------|
| `news.google.com/rss/search` | Ticker + theme as query | `gather_web.py` |
| `efts.sec.gov/LATEST/search-index` | Ticker as query | `gather_web.py` |
| `www.reddit.com/search.json` | Ticker as query | `gather_social.py` |
| `www.reddit.com/r/{sub}/search.json` | Ticker as query | `gather_social.py` |
| Yahoo Finance (via `yfinance`) | Ticker symbol | `gather_technicals.py` |

## Security & Privacy

- All data sources are **public APIs** — no authentication required
- No user data or API keys are sent to these endpoints
- The SEC EDGAR endpoint requires a user-agent with contact info (demo email used)
- Reddit requests use a research bot user-agent
- `yfinance` downloads publicly available market data

## Trust Statement

> By using this skill, public market data is fetched from Google News, SEC EDGAR,
> Reddit, and Yahoo Finance. No private data leaves the machine. Only install if you
> trust these public data sources.

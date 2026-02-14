---
name: social-researcher
description: Gather social sentiment data (Reddit) for stock tickers
---

# Social Researcher Skill

This skill provides Luna's social media monitoring capabilities.

## Tools

### gather_social.py

Fetch Reddit posts and calculate sentiment signals for a ticker.

```bash
# Basic usage
python3 gather_social.py --ticker CAKE --company "The Cheesecake Factory"

# With theme/directive for focused search
python3 gather_social.py --ticker HOG --company "Harley-Davidson" --theme "EV motorcycle transition"

# JSON output (signals data only)
python3 gather_social.py --ticker WOOF --json
```

**Output**: Markdown report with sentiment signals (volume, engagement, cross-subreddit spread) and recent Reddit discussions.

### Shared Tools (from gradient-research-assistant)

- `store.py` — Upload research to DO Spaces and trigger KB indexing
- `query_kb.py` — Query the knowledge base for historical context
- `manage_watchlist.py` — Read the watchlist
- `alert.py` — Format and send alerts

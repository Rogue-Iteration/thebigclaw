---
name: research-heartbeat
description: Run periodic research cycle for all tracked tickers
frequency: 30m
---

# Research Heartbeat

Run a full research cycle for every ticker in the watchlist.

## Steps

1. Load the watchlist:
```bash
python3 manage_watchlist.py --show
```

2. For **each ticker** in the watchlist, delegate to the specialist agents:

```bash
# Nova: gather news + SEC filings
python3 gather_web.py --ticker {{ticker}} --name "{{company_name}}" --output /tmp/web_{{ticker}}.md

# Luna: gather social sentiment
python3 gather_social.py --ticker {{ticker}} --company "{{company_name}}" --output /tmp/social_{{ticker}}.md

# Ace: gather technical data
python3 gather_technicals.py --ticker {{ticker}} --company "{{company_name}}" --output /tmp/technicals_{{ticker}}.md

# Store all reports to DO Spaces and trigger KB re-indexing
python3 store.py --ticker {{ticker}} --data /tmp/web_{{ticker}}.md
python3 store.py --ticker {{ticker}} --data /tmp/social_{{ticker}}.md
python3 store.py --ticker {{ticker}} --data /tmp/technicals_{{ticker}}.md

# Max: analyze significance across all data
python3 analyze.py --ticker {{ticker}} --name "{{company_name}}" --data /tmp/web_{{ticker}}.md --verbose
```

3. **If any ticker's analysis returns `should_alert: true`**, proactively send the user an alert message with the formatted details. Use the severity-appropriate emoji:
   - 🔴 Score 8-10 (critical)
   - 🟡 Score 6-7 (notable)
   - 🟢 Score 1-5 (low significance)

4. After processing all tickers, send a brief heartbeat summary:
   - How many tickers were checked
   - Any alerts triggered
   - Which tickers were quiet

## Notes

- Process tickers sequentially to respect rate limits on public APIs
- If a data source fails, continue with the remaining sources — partial data is better than none
- The Knowledge Base grows with each heartbeat, making future queries richer
- All research is stored as Markdown in DO Spaces at `research/{date}/{TICKER}_{source}.md`

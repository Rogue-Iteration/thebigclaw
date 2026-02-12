# 🔬 Proactive Research Assistant

> **Investment research on autopilot.** This AI agent monitors stocks, gathers data from news, Reddit, and SEC filings, and alerts you on Telegram when something significant happens.
>
> Built with [OpenClaw](https://github.com/openclaw/openclaw) + [DigitalOcean Gradient AI](https://www.digitalocean.com/products/ai).

> [!CAUTION]
> This is a **demo project** for educational purposes. **Not financial advice.** Do not make investment decisions based on this tool. Always consult a licensed financial advisor.

---

## ✨ What It Does

- 📊 **Monitors your watchlist** — tracks stocks like $CAKE, $HOG, $BOOM, $LUV, $WOOF
- 🔍 **Gathers research automatically** every 30 minutes from Google News, Reddit, and SEC EDGAR
- 🧠 **Analyzes significance** using AI (cheap model for quick scan, strong model for deep analysis)
- 🚨 **Alerts you proactively** on Telegram when something important happens
- 💬 **Answers your questions** — "What do you know about $CAKE?" → AI-powered response using all accumulated research
- ⚙️ **Configurable by chat** — "Add $DIS to my watchlist" or "Lower the price alert for $HOG to 3%"

---

## 🚀 Setup

### Step 1: Create Your DigitalOcean Resources

You need to set up a few things in your [DigitalOcean Dashboard](https://cloud.digitalocean.com). Click each link and follow the instructions:

| # | What to Create | Where | What You'll Get |
|---|---------------|-------|-----------------|
| 1 | **API Token** | [API → Tokens → Generate](https://cloud.digitalocean.com/account/api/tokens) | A token starting with `dop_v1_...` |
| 2 | **Gradient AI Key** | [Gradient AI → API Keys](https://cloud.digitalocean.com/gen-ai/api-keys) | An API key for AI inference |
| 3 | **Spaces Bucket** | [Spaces → Create](https://cloud.digitalocean.com/spaces/new) | A bucket name (e.g., `my-research`) |
| 4 | **Spaces Keys** | [API → Spaces Keys → Generate](https://cloud.digitalocean.com/account/api/spaces) | An Access Key + Secret Key pair |
| 5 | **Knowledge Base** | [Gradient AI → Knowledge Bases](https://cloud.digitalocean.com/gen-ai/knowledge-bases) | A UUID (visible in the URL after creation) |

> [!TIP]
> When creating the **Knowledge Base** (#5), connect it to your **Spaces bucket** (#3) as a data source. This is how the assistant stores and later retrieves research.

**Save all these values** somewhere safe (e.g., a password manager). You'll need them in Step 4.

### Step 2: Install & Authenticate doctl

```bash
# macOS
brew install doctl

# Authenticate with your API token from Step 1
doctl auth init
# Paste your API token when prompted
```

### Step 3: Deploy the App

Copy the prompt below and paste it into your AI assistant (ChatGPT, Claude, Gemini, etc.). It will deploy the app for you — **no credentials needed in this step**.

````
Deploy the OpenClaw Research Assistant to DigitalOcean App Platform.

1. Clone the repository:
   git clone https://github.com/Rogue-Iteration/openclaw-do-gradient.git
   cd openclaw-do-gradient

2. Verify doctl is authenticated:
   doctl account get

3. Create the app from the spec:
   doctl apps create --spec .do/app.yaml --wait

4. Confirm the app was created and show me its ID and status:
   doctl apps list

If anything fails, show me the error and suggest a fix.
Do NOT ask me for any API keys or secrets — I will add those
manually through the DigitalOcean web interface.
````

### Step 4: Add Your Secrets

After the app is deployed, you need to add your credentials so the assistant can connect to Gradient AI and Spaces.

1. Go to your [DigitalOcean Apps Dashboard](https://cloud.digitalocean.com/apps)
2. Click on **research-assistant**
3. Go to **Settings** → **Components** → **agent** → **Environment Variables**
4. Click **Edit** and add each variable from the table below:

| Variable Name | What to Enter | Why It's Needed |
|--------------|---------------|-----------------|
| `GRADIENT_API_KEY` | Your Gradient AI API key | Powers the AI analysis of your stocks |
| `DO_API_TOKEN` | Your personal access token | Triggers Knowledge Base re-indexing |
| `DO_SPACES_ACCESS_KEY` | Your Spaces access key | Uploads research data to storage |
| `DO_SPACES_SECRET_KEY` | Your Spaces secret key | Authenticates with storage |
| `GRADIENT_KB_UUID` | Your Knowledge Base UUID | Connects to your research knowledge base |

> [!NOTE]
> `DO_SPACES_ENDPOINT` and `DO_SPACES_BUCKET` are already set in the app spec. You only need to update them if your bucket is in a different region or has a different name than the defaults.

5. Click **Save** — the app will automatically redeploy with the new credentials.

**That's it!** Your research assistant is now live. 🎉

---

## 💬 How to Use It

Once deployed, chat with your assistant on Telegram:

| You Say | It Does |
|---------|---------|
| *(first message)* | Introduces itself with your watchlist and capabilities |
| "What do you know about $CAKE?" | Searches the knowledge base and gives a sourced answer |
| "Add $DIS to my watchlist" | Adds Disney with default alert rules |
| "Lower the price alert for $HOG to 3%" | Updates the alert threshold |
| "Show me my settings" | Displays all tickers and their active rules |

The assistant also runs **automatically every 30 minutes**, checking all your tickers and alerting you if something significant happens — no action needed on your part.

---

## 🏗️ Architecture

```
You (Telegram) ←→ OpenClaw Agent
                        │
                        ├── Every 30 min: gather → store → analyze → alert
                        ├── Your questions: knowledge base → AI answer
                        └── Your commands: add/remove tickers, change rules
                        │
                ┌───────┼───────────────┐
                ▼       ▼               ▼
         Gradient AI   DO Spaces    Knowledge Base
         (analysis)    (storage)    (RAG queries)
```

---

## 🧪 For Developers

<details>
<summary>Click to expand development guide</summary>

### Local Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run all tests (130 tests, ~1 second)
pytest tests/ -v
```

### Test Layers

| Layer | Tests | API Keys? |
|-------|-------|-----------|
| Unit | 121 | ❌ No |
| Mocked Integration | 9 | ❌ No |
| Live Integration | — | ✅ Yes |

### Project Structure

```
skills/gradient-research-assistant/
├── SKILL.md              # Agent persona and tools
├── HEARTBEAT.md          # 30-min research cycle
├── watchlist.json        # Tickers + alert rules
├── manage_watchlist.py   # Watchlist CRUD
├── gather.py             # News/Reddit/SEC scraper
├── analyze.py            # Two-pass LLM analysis
├── store.py              # Spaces upload + KB indexing
├── alert.py              # Alert formatting
└── query_kb.py           # RAG query pipeline
```

### Docker (Local Testing)

```bash
docker compose up --build
```

</details>

---

## 📜 License

MIT

---

*Built with [OpenClaw](https://github.com/openclaw/openclaw) × [DigitalOcean Gradient AI](https://www.digitalocean.com/products/ai)*

# CLAUDE.md — OpenClaw + Gradient AI Research Assistant

## Project Overview

A proactive investment research assistant running in **Docker** on a DigitalOcean Droplet, powered by Gradient AI models via OpenClaw. Four specialized agents (Max, Nova, Luna, Ace) monitor a stock watchlist, gather research from multiple sources, and alert the user via Telegram.

## Architecture

- **Runtime**: OpenClaw gateway running in a Docker container on a DO Droplet
- **AI Backend**: Gradient AI (GPT OSS 120B, Llama 3.3, DeepSeek R1, Qwen3) via DO Inference API
- **Agents**: Max (fundamental analyst, default), Nova (web researcher), Luna (social researcher), Ace (technical analyst)
- **Messaging**: Telegram — one bot per agent, routed via OpenClaw bindings
- **Storage**: DigitalOcean Spaces (S3-compatible) + Gradient Knowledge Base for RAG
- **State**: SQLite database (`~/.openclaw/research.db`) — watchlist, settings, tasks, logs
- **Skills**: Python scripts in `skills/` — shared and per-skill

> **📖 OpenClaw Reference**: Consult [`openclawdoc.md`](openclawdoc.md) for detailed documentation on OpenClaw's folder structure, workspace files, skills (`SKILL.md` format, locations, precedence, gating), plugins (discovery, API, config), tools (inventory, profiles, allow/deny), multi-agent routing (bindings, routing rules, per-agent sandbox), and configuration (`openclaw.json`). Always reference this file when working with OpenClaw-specific conventions.

## Tech Stack

| Layer         | Technology                                  |
|---------------|---------------------------------------------|
| Language      | Python 3, Bash                              |
| Testing       | pytest, responses (HTTP mocking), moto (S3) |
| Dependencies  | requests, beautifulsoup4, feedparser, boto3, yfinance |
| Infra         | Docker, DigitalOcean Droplet, Spaces, Gradient AI |
| Gateway       | OpenClaw (Node.js / pnpm)                   |

## Key Directories

```
skills/
├── gradient-research-assistant/     → Main shared skill (gather, analyze, alert, store, watchlist)
├── gradient-inference/              → Publishable skill: model listing, chat, pricing lookup
├── gradient-knowledge-base/         → Publishable skill: RAG queries via DO Gradient KB
└── gradient-data-gathering/         → Agent-specific data gathering tools

data/
├── workspace/                       → Shared persona files (AGENTS.md — all agents see this)
└── workspaces/{agent-name}/         → Per-agent persona files (IDENTITY.md, AGENTS.md, HEARTBEAT.md)

tests/                               → pytest unit tests (test_*.py)
```

---

## Development Flow

All development happens **locally**. All testing happens against the **Droplet**.

### The Loop

1. **Edit code locally** — skill scripts, persona files, entrypoint, etc.
2. **Run tests locally** — `python3 -m pytest tests/ -v`
3. **Commit and push** — `git add -A && git commit -m "..." && git push origin main`
4. **Deploy** — `bash install.sh --update` (from your local machine)
5. **Test on Telegram** — talk to the bots, verify behavior

### Deploy Workflow

There is a codified workflow at `.agent/workflows/deploy.md`. The steps:

```bash
# Step 1: Commit and push
git add -A && git commit -m "<message>" && git push origin main

# Step 2: Deploy to Droplet (SCPs .env, git pulls, rebuilds Docker)
bash install.sh --update
```

`install.sh --update` does:
- SCPs `.env` to the Droplet
- Runs `git pull origin main` on the Droplet
- Runs `docker compose up -d --build` to rebuild and restart
- Verifies the container is running

### Alternative: Deploy from the Droplet

```bash
ssh root@<droplet-ip>
cd /opt/openclaw && bash deploy.sh
```

`deploy.sh` only does `git pull` + `docker compose up -d --build` — it does NOT sync `.env`.

---

## First-Time Setup (for users)

### Prerequisites

1. **doctl** — DigitalOcean CLI ([install guide](https://docs.digitalocean.com/reference/doctl/how-to/install/))
2. **Docker** — only needed if running locally without a Droplet
3. A set of API keys — see `.env.example` for the full list with instructions

### Steps

```bash
git clone https://github.com/Rogue-Iteration/TheBigClaw.git
cd TheBigClaw
cp .env.example .env
# Fill in .env — every key has instructions in the file

# Validate your config
bash install.sh --dry-run

# Deploy to DigitalOcean (interactive — prompts for region + SSH key)
bash install.sh

# Or non-interactively:
DROPLET_REGION=nyc3 DROPLET_SSH_KEY_IDS=12345 bash install.sh
```

After deployment, pair your Telegram — see `README.md` for the full walkthrough.

### Running Locally (without DigitalOcean)

```bash
cp .env.example .env
# Fill in .env
docker compose up -d
```

---

## Container Management

```bash
# SSH into the Droplet
ssh root@<droplet-ip>

# Tail logs
docker logs -f openclaw-research

# Restart
docker compose restart

# Stop
docker compose down

# Rebuild and start
docker compose up -d --build
```

---

## Droplet Safety

> **⚠️ Always ask before performing destructive actions on the Droplet.**
>
> This includes but is not limited to:
> - Deleting or overwriting files on the Droplet
> - Stopping or removing Docker containers
> - Modifying `.env` or OpenClaw state files
> - Any `rm`, destructive SSH commands, or `docker system prune`
>
> Non-destructive reads (checking logs, status, listing files) are fine without asking.

---

## Testing

### Approach

- **Use TDD where it makes sense** — particularly for new skill scripts and data-processing logic where inputs/outputs are well-defined.
- **Otherwise, write test cases afterwards** — especially for integration-style work, persona file changes, or deployment scripts.
- Tests live in `tests/` and follow the naming convention `test_<skill_name>.py`.

### Running Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

### Test Fixtures

Mock data and fixtures live in `tests/fixtures/`. Tests use `responses` for HTTP mocking and `moto` for S3/Spaces mocking.

---

## Code Style & Documentation

- **Document files inline** — every Python skill script should have:
  - A module-level docstring explaining what the skill does
  - Docstrings on all public functions describing purpose, parameters, and return values
  - Inline comments for non-obvious logic
- Bash scripts should have header comments and section markers
- Persona files (IDENTITY.md, AGENTS.md, HEARTBEAT.md) use Markdown

## Environment Variables

All secrets live in `.env` (locally and on the Droplet). **Never commit real secrets.**

See `.env.example` for the full list with inline documentation.

---

## Common Workflows

### Adding a new skill script

1. Create `skills/<skill-name>/scripts/<script_name>.py`
2. Add inline documentation (module docstring + function docstrings)
3. Document the tool in the relevant SKILL.md
4. If specific agents need it: add to their `IDENTITY.md` under Available Tools
5. Write tests in `tests/test_<skill_name>.py` (TDD preferred)
6. Run `python3 -m pytest tests/ -v` to verify
7. Add the exec pattern to `docker-entrypoint.sh` allowlist (if new skill dir)
8. Deploy: commit → push → `bash install.sh --update`

### Updating agent personas

1. Edit the relevant files in `data/workspaces/<agent-name>/`
2. Deploy: `bash install.sh --update`
3. The Docker entrypoint syncs persona files on every container start

### How the entrypoint works

`docker-entrypoint.sh` runs on every container start and:
- **First run only**: Generates `openclaw.json` (models, agents, Telegram config, exec allowlist)
- **Every start**: Syncs persona files from `data/workspaces/` into agent workspaces, creates skill symlinks, initializes the SQLite database, seeds default schedules

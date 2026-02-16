# OpenClaw Reference Guide

> Synthesized from https://docs.openclaw.ai/ — last updated 2026-02-16
>
> This document is an AI-assistant reference for working on this project.
> It covers folder structure, skills, plugins, multi-agent routing, tools,
> and configuration as they apply to the `openclaw-do-gradient` deployment.

---

## Table of Contents

1. [What is OpenClaw?](#what-is-openclaw)
2. [Folder Structure & Paths](#folder-structure--paths)
3. [Agent Workspace](#agent-workspace)
4. [Skills](#skills)
5. [Plugins (Extensions)](#plugins-extensions)
6. [Tools](#tools)
7. [Multi-Agent Routing](#multi-agent-routing)
8. [Configuration (`openclaw.json`)](#configuration)
9. [Channels](#channels)
10. [Security & Sandboxing](#security--sandboxing)

---

## What is OpenClaw?

OpenClaw is a **self-hosted gateway** for AI agents across WhatsApp, Telegram, Discord, iMessage, and more. Key traits:

- **Self-hosted**: runs on your hardware
- **Multi-channel**: one gateway serves WhatsApp, Telegram, Discord, etc. simultaneously
- **Agent-native**: built for coding agents with tool use, sessions, memory, and multi-agent routing
- **Open source**: MIT licensed

### Quick Start

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
openclaw channels login
openclaw gateway --port 18789
```

Dashboard: `http://127.0.0.1:18789/`

---

## Folder Structure & Paths

### Key Paths (Quick Map)

| Path | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Main config (or `OPENCLAW_CONFIG_PATH`) |
| `~/.openclaw/` | State directory (or `OPENCLAW_STATE_DIR`) |
| `~/.openclaw/workspace` | Default workspace (or `~/.openclaw/workspace-<agentId>`) |
| `~/.openclaw/agents/<agentId>/agent` | Agent state directory (or `agents.list[].agentDir`) |
| `~/.openclaw/agents/<agentId>/sessions` | Session transcripts + metadata |
| `~/.openclaw/skills/` | Managed/shared skills (visible to all agents) |
| `~/.openclaw/credentials/` | OAuth tokens, API keys |
| `~/.openclaw/extensions/` | Installed plugins |
| `<workspace>/skills/` | Per-agent workspace skills |

### What is NOT in the Workspace

These live outside the workspace under `~/.openclaw/`:
- `openclaw.json` (config)
- `credentials/` (OAuth tokens, API keys)
- `agents/<agentId>/sessions/` (session transcripts)
- `skills/` (managed/shared skills)

---

## Agent Workspace

The workspace is the agent's "home directory" containing persona files, memory, and skills.

**Default location:** `~/.openclaw/workspace`
- If `OPENCLAW_PROFILE` is set: `~/.openclaw/workspace-<profile>`
- Override in config: `agents.defaults.workspace` or per-agent `agents.list[].workspace`

### Workspace File Map

| File | Purpose | Loaded |
|------|---------|--------|
| `AGENTS.md` | Operating instructions; how the agent should use memory. Rules, priorities, behavior details. | Every session |
| `SOUL.md` | Persona, tone, and boundaries. | Every session |
| `USER.md` | Who the user is and how to address them. | Every session |
| `IDENTITY.md` | The agent's name, vibe, and emoji. Created/updated during bootstrap. | Every session |
| `TOOLS.md` | Notes about local tools and conventions. Does NOT control tool availability — guidance only. | Every session |
| `HEARTBEAT.md` | Optional tiny checklist for heartbeat runs. Keep short to avoid token burn. | Heartbeat only |
| `BOOT.md` | Optional startup checklist on gateway restart (when internal hooks enabled). | On boot |
| `BOOTSTRAP.md` | One-time first-run ritual. Delete after completion. | First run only |
| `memory/YYYY-MM-DD.md` | Daily memory log (one file per day). Read today + yesterday on session start. | On access |
| `MEMORY.md` | Curated long-term memory. Only load in the main, private session. | On access |
| `skills/` | Workspace-specific skills. Overrides managed/bundled skills on name collision. | Auto-loaded |
| `canvas/` | Canvas UI files for node displays (e.g., `canvas/index.html`). | On access |

---

## Skills

Skills are instruction files (with optional scripts) that extend agent capabilities. They follow the **AgentSkills** spec.

### Locations and Precedence (highest → lowest)

1. **Bundled skills**: shipped with OpenClaw install
2. **Managed/local skills**: `~/.openclaw/skills/`
3. **Workspace skills**: `<workspace>/skills/`
4. **Extra dirs**: `skills.load.extraDirs` in config (lowest precedence)

**Important:** Workspace skills override managed/bundled skills when names collide.

### Per-Agent vs Shared Skills

- **Per-agent**: `<workspace>/skills/` — only that agent sees them
- **Shared**: `~/.openclaw/skills/` — visible to all agents on the machine
- **Extra dirs**: `skills.load.extraDirs` — common skills pack for multiple agents

### Skill File Format (`SKILL.md`)

Each skill is a folder containing a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: my-skill-name
description: Short description of what the skill does
metadata:
  openclaw:
    requires:
      bins: ["python3"]       # Must be on PATH
      env: ["MY_API_KEY"]     # Must be set
      config: ["browser.enabled"]  # Must be truthy in openclaw.json
    primaryEnv: "MY_API_KEY"  # Maps to skills.entries.<name>.apiKey
    emoji: "🔧"
    homepage: "https://example.com"
    os: ["darwin", "linux"]   # Optional OS filter
    install:                  # Optional installer specs
      - id: "brew"
        kind: "brew"
        formula: "my-tool"
        bins: ["my-tool"]
---

# Skill Instructions

Your skill instructions go here. Use {baseDir} to reference the skill folder path.

## Tools

### tool_name
Description of what this tool does.

\```bash
python3 {baseDir}/scripts/my_script.py --arg {{value}}
\```
```

### Optional Frontmatter Keys

| Key | Default | Purpose |
|-----|---------|---------|
| `homepage` | — | URL shown in Skills UI |
| `user-invocable` | `true` | Expose as user slash command |
| `disable-model-invocation` | `false` | Exclude from model prompt (still available via user invocation) |
| `command-dispatch` | — | Set to `tool` for direct tool dispatch |
| `command-tool` | — | Tool name to invoke with `command-dispatch: tool` |
| `command-arg-mode` | `raw` | For tool dispatch, forwards raw args |

### Gating (Load-Time Filters)

Skills are gated at load time using `metadata.openclaw`:

- `always: true` — skip all other gates, always include
- `requires.bins` — each must exist on `PATH`
- `requires.anyBins` — at least one must exist on `PATH`
- `requires.env` — env var must be set (or provided in config)
- `requires.config` — `openclaw.json` paths that must be truthy
- `os` — only eligible on listed OSes: `darwin`, `linux`, `win32`

> **Sandbox note:** `requires.bins` is checked on the host. If an agent is sandboxed, the binary must also exist inside the container. Install via `agents.defaults.sandbox.docker.setupCommand`.

### Config Overrides for Skills

In `openclaw.json`:

```json5
{
  skills: {
    entries: {
      "my-skill": {
        enabled: true,
        apiKey: "KEY_HERE",
        env: {
          MY_API_KEY: "KEY_HERE",
        },
        config: {
          endpoint: "https://example.com",
          model: "my-model",
        },
      },
      "unwanted-skill": { enabled: false },
    },
  },
}
```

- `enabled: false` — disables the skill even if bundled/installed
- `env` — injected only if the variable isn't already set
- `apiKey` — convenience for skills with `metadata.openclaw.primaryEnv`
- `config` — optional bag for custom per-skill fields

### Skills Watcher (Auto-Refresh)

```json5
{
  skills: {
    load: {
      watch: true,
      watchDebounceMs: 250,
    },
  },
}
```

Edit a `SKILL.md` and changes are picked up without restart.

---

## Plugins (Extensions)

Plugins extend the Gateway's runtime with new channels, tools, services, CLI commands, and skills.

### Discovery & Precedence

1. **Config paths**: `plugins.load.paths`
2. **Workspace extensions**: `<workspace>/.openclaw/extensions/*.ts` or `*/index.ts`
3. **Global extensions**: `~/.openclaw/extensions/*.ts` or `*/index.ts`
4. **Bundled extensions**: shipped with OpenClaw (disabled by default)

Enable bundled plugins: `plugins.entries.<id>.enabled: true` or `openclaw plugins enable <id>`

### Plugin Manifest (`openclaw.plugin.json`)

Plugins can provide:
- Gateway RPC methods
- Gateway HTTP handlers
- Agent tools
- CLI commands
- Background services
- Config validation (JSON Schema via `configSchema`)
- Skills (by listing skills directories in the manifest)
- Auto-reply commands (execute without invoking the AI agent)

### Plugin API

A plugin is either:
- A function: `(api) => { ... }`
- An object: `{ id, name, configSchema, register(api) { ... } }`

### Plugin Config

```json5
{
  plugins: {
    enabled: true,               // Master toggle (default: true)
    allow: ["voice-call"],       // Allowlist (optional)
    deny: ["untrusted-plugin"],  // Denylist (deny wins)
    load: {
      paths: ["~/Projects/my-plugin"],  // Extra plugin paths
    },
    entries: {
      "voice-call": {
        enabled: true,
        config: { provider: "twilio" },
      },
    },
    slots: {
      memory: "memory-core",    // Or "memory-lancedb" or "none"
    },
  },
}
```

### Plugin Slots (Exclusive Categories)

`plugins.slots` assigns one plugin per category (e.g., `memory`). Only one memory plugin runs at a time.

### Available Official Plugins

- **Voice Call**: `@openclaw/voice-call`
- **Matrix**: `@openclaw/matrix`
- **Nostr**: `@openclaw/nostr`
- **Zalo**: `@openclaw/zalo`
- **Microsoft Teams**: `@openclaw/msteams`
- **Memory (Core)**: bundled (default)
- **Memory (LanceDB)**: bundled (set `plugins.slots.memory = "memory-lancedb"`)
- **Provider auth plugins**: Google, Gemini CLI, Qwen, Copilot (all bundled, disabled by default)

### Plugin CLI

```bash
openclaw plugins list
openclaw plugins install @openclaw/voice-call   # from npm
openclaw plugins install ./my-plugin             # from local path
openclaw plugins install -l ./my-plugin          # link for dev
openclaw plugins enable <id>
openclaw plugins disable <id>
openclaw plugins update --all
openclaw plugins doctor
```

### Plugin Skills

Skills can be bundled with plugins by listing a `skills/` directory in the plugin manifest. The skill format (`SKILL.md`) is identical to regular skills.

### Naming Conventions

- Gateway RPC methods: `pluginId.action` (e.g., `voicecall.status`)
- Agent tools: `snake_case` (e.g., `voice_call`)
- CLI commands: kebab or camel, avoid clashing with core commands

---

## Tools

Tools are the capabilities available to the AI agent during a session. They are different from skills.

### Built-in Tool Inventory

| Tool | Group | Description |
|------|-------|-------------|
| `read`, `write`, `edit`, `apply_patch` | `group:fs` | File system operations |
| `exec`, `bash`, `process` | `group:runtime` | Shell/process execution |
| `web_search`, `web_fetch` | `group:web` | Web search and fetching |
| `browser`, `canvas` | `group:ui` | Browser automation, Canvas surface |
| `message` | `group:messaging` | Send messages |
| `sessions_list`, `sessions_history`, `sessions_send`, `sessions_spawn`, `session_status` | `group:sessions` | Session management |
| `memory_search`, `memory_get` | `group:memory` | Memory operations |
| `cron`, `gateway` | `group:automation` | Cron jobs, gateway control |
| `nodes` | `group:nodes` | iOS/Android node control |
| `image` | — | Image generation |
| `agents_list` | — | List available agents |

### Disabling / Allowing Tools

```json5
{
  tools: {
    allow: ["group:fs", "exec"],  // Only these tools available
    deny: ["browser"],            // Block specific tools
  },
}
```

- Matching is case-insensitive
- `*` wildcards supported (`"*"` = all tools)
- `deny` overrides `allow`

### Tool Profiles (Base Allowlist)

| Profile | Tools |
|---------|-------|
| `minimal` | `session_status` only |
| `coding` | `group:fs`, `group:runtime`, `group:sessions`, `group:memory`, `image` |
| `messaging` | `group:messaging`, `sessions_list`, `sessions_history`, `sessions_send`, `session_status` |
| `full` | No restriction (default) |

```json5
{
  tools: { profile: "coding" },
  agents: {
    list: [
      {
        id: "support",
        tools: { profile: "messaging", allow: ["slack"] },
      },
    ],
  },
}
```

### Tool Groups (Shorthands)

Use `group:*` syntax in `tools.allow` / `tools.deny`:

- `group:runtime` → exec, bash, process
- `group:fs` → read, write, edit, apply_patch
- `group:sessions` → sessions_list, sessions_history, sessions_send, sessions_spawn, session_status
- `group:memory` → memory_search, memory_get
- `group:web` → web_search, web_fetch
- `group:ui` → browser, canvas
- `group:automation` → cron, gateway
- `group:messaging` → message
- `group:nodes` → nodes
- `group:openclaw` → all built-in tools (excludes plugin tools)

### Tool Allow/Deny vs Skills

> **Important:** Tool allow/deny lists control *tools*, not *skills*. If a skill needs to run a binary, ensure `exec` is allowed and the binary exists (in sandbox if sandboxed).

---

## Multi-Agent Routing

### What is "One Agent"?

Each agent has:
- **Workspace** (files: AGENTS.md, SOUL.md, USER.md, skills, etc.)
- **State directory** (`agentDir`) for auth profiles, model registry, per-agent config
- **Session store** under `~/.openclaw/agents/<agentId>/sessions`

### Single-Agent Mode (Default)

- `agentId` defaults to `main`
- Sessions keyed as `agent:main:<mainKey>`
- Workspace: `~/.openclaw/workspace`
- State: `~/.openclaw/agents/main/agent`

### Multi-Agent Setup

Define multiple agents in `agents.list` and route with `bindings`:

```json5
{
  agents: {
    list: [
      {
        id: "home",
        default: true,
        name: "Home",
        workspace: "~/.openclaw/workspace-home",
        agentDir: "~/.openclaw/agents/home/agent",
      },
      {
        id: "work",
        name: "Work",
        workspace: "~/.openclaw/workspace-work",
        agentDir: "~/.openclaw/agents/work/agent",
      },
    ],
  },
  bindings: [
    { agentId: "home", match: { channel: "whatsapp", accountId: "personal" } },
    { agentId: "work", match: { channel: "telegram" } },
  ],
}
```

### Routing Rules (Message → Agent Resolution)

First match wins, ordered by specificity:
1. `peer` match (exact DM/group/channel ID)
2. `parentPeer` match (thread inheritance)
3. `guildId` + `roles` (Discord role routing)
4. `guildId` (Discord)
5. `teamId` (Slack)
6. `accountId` match for a channel
7. Channel-level match (`accountId: "*"`)
8. Fallback to default agent (`agents.list[].default`, else first entry, default: `main`)

### Key Concepts

| Concept | Definition |
|---------|------------|
| `agentId` | One "brain" (workspace, auth, sessions) |
| `accountId` | One channel account instance (e.g., WhatsApp "personal" vs "biz") |
| `binding` | Routes inbound messages to an `agentId` by (channel, accountId, peer) |
| Session key | Direct chats collapse to `agent:<agentId>:<mainKey>` |

### Per-Agent Tool & Sandbox Configuration

```json5
{
  agents: {
    list: [
      {
        id: "personal",
        workspace: "~/.openclaw/workspace-personal",
        sandbox: { mode: "off" },
        // All tools available
      },
      {
        id: "family",
        workspace: "~/.openclaw/workspace-family",
        sandbox: {
          mode: "all",
          scope: "agent",
          docker: {
            setupCommand: "apt-get update && apt-get install -y git curl",
          },
        },
        tools: {
          allow: ["read"],
          deny: ["exec", "write", "edit", "apply_patch"],
        },
      },
    ],
  },
}
```

### Group Chat + Mention Gating

```json5
{
  agents: {
    list: [{
      id: "main",
      groupChat: {
        mentionPatterns: ["@openclaw", "openclaw"],
      },
    }],
  },
  channels: {
    whatsapp: {
      groups: { "*": { requireMention: true } },
    },
  },
}
```

---

## Configuration

Config file: `~/.openclaw/openclaw.json` (JSON5 format, supports comments)

### Minimal Config

```json5
{
  agents: {
    defaults: { workspace: "~/.openclaw/workspace" },
  },
  channels: {
    whatsapp: { allowFrom: ["+15555550123"] },
  },
}
```

### Editing Config

| Method | Command |
|--------|---------|
| Interactive wizard | `openclaw onboard` or `openclaw configure` |
| CLI one-liners | `openclaw config set agents.defaults.heartbeat.every "2h"` |
| Control UI | `http://127.0.0.1:18789` |
| Direct edit | `~/.openclaw/openclaw.json` (supports hot reload) |

### Config Hot Reload

Editing `openclaw.json` triggers automatic hot-reload for most settings. Some changes require a full restart.

### Environment Variables

OpenClaw loads `.env` files from:
1. Current working directory
2. `~/.openclaw/.env` (global fallback)

Environment variable substitution in config values:

```json5
{
  gateway: {
    auth: { token: "${OPENCLAW_GATEWAY_TOKEN}" },
  },
}
```

- Only `UPPERCASE_NAMES` matched: `[A-Z_][A-Z0-9_]*`
- Missing/empty vars throw an error at load time
- Escape with `$${VAR}` for literal output

### DM Access Policies

| Policy | Behavior |
|--------|----------|
| `"pairing"` (default) | Unknown senders get a one-time pairing code |
| `"allowlist"` | Only senders in `allowFrom` |
| `"open"` | Allow all inbound DMs (requires `allowFrom: ["*"]`) |
| `"disabled"` | Ignore all DMs |

### Model Configuration

```json5
{
  agents: {
    defaults: {
      model: {
        primary: "anthropic/claude-sonnet-4-5",
        fallbacks: ["openai/gpt-5.2"],
      },
      models: {
        "anthropic/claude-sonnet-4-5": { alias: "Sonnet" },
        "openai/gpt-5.2": { alias: "GPT" },
      },
    },
  },
}
```

Model refs use `provider/model` format (e.g., `anthropic/claude-opus-4-6`).

---

## Channels

Supported channels and their config keys:

| Channel | Config Key | Notes |
|---------|-----------|-------|
| WhatsApp | `channels.whatsapp` | Via Baileys (WhatsApp Web) |
| Telegram | `channels.telegram` | grammY bot framework |
| Discord | `channels.discord` | discord.js |
| Slack | `channels.slack` | — |
| Signal | `channels.signal` | — |
| iMessage | `channels.imessage` | macOS only (imsg CLI) |
| Google Chat | `channels.googlechat` | — |
| Mattermost | `channels.mattermost` | Plugin-based |
| MS Teams | `channels.msteams` | Plugin-only (`@openclaw/msteams`) |

### Telegram Config Example

```json5
{
  channels: {
    telegram: {
      enabled: true,
      botToken: "123:abc",
      dmPolicy: "allowlist",     // pairing | allowlist | open | disabled
      allowFrom: ["tg:123"],    // Telegram user IDs
    },
  },
}
```

### Multi-Account Channels

```json5
{
  channels: {
    whatsapp: {
      accounts: {
        personal: { /* authDir override optional */ },
        biz: { /* authDir override optional */ },
      },
    },
  },
}
```

### Multi-Bot Telegram (Per-Agent)

Each agent can have its own Telegram bot by mapping `accountId` in bindings:

```json5
{
  channels: {
    telegram: {
      accounts: {
        bot1: { botToken: "TOKEN_1" },
        bot2: { botToken: "TOKEN_2" },
      },
    },
  },
  bindings: [
    { agentId: "agent-a", match: { channel: "telegram", accountId: "bot1" } },
    { agentId: "agent-b", match: { channel: "telegram", accountId: "bot2" } },
  ],
}
```

---

## Security & Sandboxing

### Tool Safety

- `tools.allow` / `tools.deny` — global or per-agent
- Tool profiles for preset allowlists
- `tools.elevated` — tools requiring explicit approval

### Sandboxing

```json5
{
  agents: {
    list: [{
      id: "untrusted",
      sandbox: {
        mode: "all",       // "off" | "all"
        scope: "agent",    // "agent" | "shared"
        docker: {
          setupCommand: "apt-get update && apt-get install -y python3",
        },
      },
    }],
  },
}
```

- `mode: "off"` — no sandbox
- `mode: "all"` — always sandboxed
- `scope: "agent"` — one container per agent
- `scope: "shared"` — shared container across agents
- `setupCommand` — runs once after container creation

### Security Best Practices

- Treat third-party skills as untrusted code — read them before enabling
- Use `skills.entries.*.env` / `skills.entries.*.apiKey` carefully — they inject into the host process
- Keep secrets out of prompts and logs
- Use `plugins.allow` allowlists
- Restart gateway after plugin changes

---

## Project-Specific Notes (openclaw-do-gradient)

This project uses OpenClaw with:
- **Docker deployment** on DigitalOcean
- **Multi-agent setup** with 4 specialized agents (Max, Nova, Luna, Ace) + a main research assistant
- **Per-agent workspaces** under `data/workspaces/`
- **Shared skills** under `skills/` (mapped to `/app/skills/` in Docker)
- **Skills use absolute paths** in Docker: `/app/skills/gradient-research-assistant/scripts/...`
- **Shared SQLite database** at `~/.openclaw/research.db`
- **Telegram** as the primary channel with per-agent bot bindings

### Project Folder Structure

```
openclaw-do-gradient/
├── data/
│   ├── workspace/          # Main agent workspace
│   │   ├── AGENTS.md       # Operating instructions
│   │   ├── HEARTBEAT.md    # Heartbeat checklist
│   │   └── IDENTITY.md     # Agent identity
│   └── workspaces/         # Per-agent workspaces
│       ├── fundamental-analyst/
│       ├── social-researcher/
│       ├── technical-analyst/
│       └── web-researcher/
├── skills/                 # Shared skill definitions
│   ├── gradient-data-gathering/
│   │   └── SKILL.md
│   ├── gradient-inference/
│   │   └── SKILL.md
│   ├── gradient-knowledge-base/
│   │   └── SKILL.md
│   └── gradient-research-assistant/
│       ├── SKILL.md
│       └── scripts/        # Python scripts for all tools
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── install.sh
├── deploy.sh
├── .env / .env.example
├── CLAUDE.md
└── README.md
```

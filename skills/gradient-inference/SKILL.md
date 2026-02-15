---
name: gradient-inference
description: >
  Call DigitalOcean Gradient AI LLMs via Serverless Inference.
  Discover available models, run chat completions or the Responses API
  with prompt caching, and generate images. OpenAI-compatible.
files: ["scripts/*"]
homepage: https://github.com/Rogue-Iteration/TheBigClaw
metadata:
  clawdbot:
    requires:
      env:
        - GRADIENT_API_KEY
      bins:
        - python3
  author: Rogue Iteration
  version: "0.1.0"
  tags: ["gradient", "inference", "llm", "do", "digitalocean"]
---

# 🦞 Gradient AI — Serverless Inference

> *"Why manage GPUs when the ocean provides?" — ancient lobster proverb*

Use DigitalOcean's [Gradient Serverless Inference](https://docs.digitalocean.com/products/gradient-ai-platform/how-to/use-serverless-inference/) to call large language models without managing infrastructure. The API is **OpenAI-compatible**, so standard SDKs and patterns work — just point at `https://inference.do-ai.run/v1` and swim.

## Authentication

All requests need a **Model Access Key** in the `Authorization: Bearer` header.

```bash
export GRADIENT_API_KEY="your-model-access-key"
```

**Where to get one:** [DigitalOcean Console](https://cloud.digitalocean.com) → Gradient AI → Model Access Keys → Create Key.

📖 *[Full auth docs](https://docs.digitalocean.com/products/gradient-ai-platform/how-to/use-serverless-inference/#create-a-model-access-key)*

---

## Tools

### 🔍 List Available Models

Window-shop for LLMs before you swipe the card.

```bash
python3 gradient_models.py                    # Pretty table
python3 gradient_models.py --json             # Machine-readable
python3 gradient_models.py --filter "llama"   # Search by name
```

Use this before hardcoding model IDs — models are added and deprecated over time.

**Direct API call:**
```bash
curl -s https://inference.do-ai.run/v1/models \
  -H "Authorization: Bearer $GRADIENT_API_KEY" | python3 -m json.tool
```

📖 *[Models reference](https://docs.digitalocean.com/products/gradient-ai-platform/details/models/)*

---

### 💬 Chat Completions

The classic. Send structured messages (system/user/assistant roles), get a response. OpenAI-compatible, so you probably already know how this works.

```bash
python3 gradient_chat.py \
  --model "openai-gpt-oss-120b" \
  --system "You are a helpful assistant." \
  --prompt "Explain serverless inference in one paragraph."

# Different model
python3 gradient_chat.py \
  --model "llama3.3-70b-instruct" \
  --prompt "Write a haiku about cloud computing."
```

**Direct API call:**
```bash
curl -s https://inference.do-ai.run/v1/chat/completions \
  -H "Authorization: Bearer $GRADIENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai-gpt-oss-120b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.7,
    "max_tokens": 1000
  }'
```

📖 *[Chat Completions docs](https://docs.digitalocean.com/products/gradient-ai-platform/how-to/use-serverless-inference/#chat-completions)*

---

### ⚡ Responses API (Recommended)

DigitalOcean's [recommended endpoint](https://docs.digitalocean.com/products/gradient-ai-platform/how-to/use-serverless-inference/#responses-api) for new integrations. Simpler request format and supports **prompt caching** — a.k.a. "stop paying twice for the same context."

```bash
# Basic usage
python3 gradient_chat.py \
  --model "openai-gpt-oss-120b" \
  --prompt "Summarize this earnings report." \
  --responses-api

# With prompt caching (saves cost on follow-up queries)
python3 gradient_chat.py \
  --model "openai-gpt-oss-120b" \
  --prompt "Now compare it to last quarter." \
  --responses-api --cache
```

**Direct API call:**
```bash
curl -s https://inference.do-ai.run/v1/responses \
  -H "Authorization: Bearer $GRADIENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai-gpt-oss-120b",
    "input": "Explain prompt caching.",
    "store": true
  }'
```

**When to use which:**
| | Chat Completions | Responses API |
|---|---|---|
| **Request format** | Array of messages with roles | Single `input` string |
| **Prompt caching** | ❌ | ✅ via `store: true` |
| **Multi-step tool use** | Manual | Built-in |
| **Best for** | Structured conversations | Simple queries, cost savings |

📖 *[Responses API docs](https://docs.digitalocean.com/products/gradient-ai-platform/how-to/use-serverless-inference/#responses-api)*

---

### 🖼️ Generate Images

Turn text prompts into images. Because sometimes a chart isn't enough.

```bash
python3 gradient_image.py --prompt "A lobster trading stocks on Wall Street"
python3 gradient_image.py --prompt "Sunset over the NYSE" --output sunset.png
python3 gradient_image.py --prompt "Fintech logo" --json
```

**Direct API call:**
```bash
curl -s https://inference.do-ai.run/v1/images/generations \
  -H "Authorization: Bearer $GRADIENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dall-e-3",
    "prompt": "A lobster analyzing candlestick charts",
    "n": 1
  }'
```

📖 *[Image generation docs](https://docs.digitalocean.com/products/gradient-ai-platform/how-to/use-serverless-inference/#image-generation)*

---

## 🧠 Model Selection Guide

Not all models are created equal. Choose wisely, young crustacean:

| Model | Best For | Speed | Quality | Context |
|-------|----------|-------|---------|---------|
| `openai-gpt-oss-120b` | Complex reasoning, analysis, writing | Medium | ★★★★★ | 128K |
| `llama3.3-70b-instruct` | General tasks, instruction following | Fast | ★★★★ | 128K |
| `deepseek-r1-distill-llama-70b` | Math, code, step-by-step reasoning | Slow | ★★★★★ | 128K |
| `qwen3-32b` | Quick triage, short tasks | Fastest | ★★★ | 32K |

> **🦞 Pro tip: Cost-aware routing.** Use a fast model (e.g., `qwen3-32b`) to score or triage, then only escalate to a strong model (e.g., `openai-gpt-oss-120b`) when depth is needed. Enable prompt caching for repeated context.

Always run `python3 gradient_models.py` to check what's currently available — the menu changes.

📖 *[Available models](https://docs.digitalocean.com/products/gradient-ai-platform/details/models/)*

---

## CLI Reference

All scripts accept `--json` for machine-readable output.

```
gradient_models.py   [--json] [--filter QUERY]
gradient_chat.py     --prompt TEXT [--model ID] [--system TEXT]
                     [--responses-api] [--cache] [--temperature F]
                     [--max-tokens N] [--json]
gradient_image.py    --prompt TEXT [--model ID] [--output PATH]
                     [--size WxH] [--json]
```

## External Endpoints

| Endpoint | Purpose |
|----------|---------|
| `https://inference.do-ai.run/v1/models` | List available models |
| `https://inference.do-ai.run/v1/chat/completions` | Chat Completions API |
| `https://inference.do-ai.run/v1/responses` | Responses API (recommended) |
| `https://inference.do-ai.run/v1/images/generations` | Image generation |

## Security & Privacy

- All requests go to `inference.do-ai.run` — DigitalOcean's own endpoint
- Your `GRADIENT_API_KEY` is sent as a Bearer token in the Authorization header
- No other credentials or local data leave the machine
- Model Access Keys are scoped to inference only — they can't manage your DO account
- Prompt caching entries are scoped to your account and automatically expire

## Trust Statement

> By using this skill, prompts and data are sent to DigitalOcean's Gradient Inference API.
> Only install if you trust DigitalOcean with the content you send to their LLMs.

## Important Notes

- Run `python3 gradient_models.py` before assuming a model exists — they rotate
- All scripts exit with code 1 and print errors to stderr on failure

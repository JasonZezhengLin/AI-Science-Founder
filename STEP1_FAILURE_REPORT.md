# STEP 1 FAILURE REPORT — yunwu provider wiring

**Date:** 2026-07-05 (SLURM autonomous run)
**Result:** STOPPED at STEP 1. yunwu could not be made to work. **No fallback used. $0.00 spent.**

## Root cause
The key file `/home/zezhenglin/.yunwu_key` contains the literal placeholder string
`NEW_TOKEN` (9 bytes, no trailing newline) — **not a real API key**.

```
$ xxd /home/zezhenglin/.yunwu_key
00000000: 4e45 575f 544f 4b45 4e                   NEW_TOKEN
```

## What was tested (real calls, zero cost — rejected at auth)
Endpoint detection actually **succeeded**: both candidate base URLs are genuine
yunwu OpenAI-compatible endpoints (they return yunwu's structured `new_api_error`,
not a connection error or generic 404). The blocker is purely the token.

| Endpoint | Model | HTTP | Response |
|---|---|---|---|
| `https://yunwu.ai/v1/chat/completions` | gpt-4.1-nano | 401 | `无效的令牌` (invalid token) |
| `https://api.yunwu.ai/v1/chat/completions` | gpt-4.1-nano | 401 | `无效的令牌` (invalid token) |

`max_tokens:1`, single minimal message. No completion tokens were generated → **$0.00 billed.**

This differs from the previous stop (commit `e5b60f1`), where the token existed but was
disabled (`该令牌状态不可用` / token status unavailable). This time the token is a placeholder,
so auth fails with `无效的令牌` / invalid token before anything else.

## Repo config wiring (confirmed, for when a real key is supplied)
- The project reads an **OpenAI-compatible** provider via `OPENAI_API_KEY` + `OPENAI_BASE_URL`
  (see `.env`, `.env.example`, `ai_scientist/llm.py`).
- `.env.example` already targets yunwu: `OPENAI_BASE_URL=https://yunwu.ai/v1`.
- Model names needed by the pipeline (OpenAI-style, served by yunwu's compat layer):
  - `BFTS_MODEL=gpt-4.1-nano` (experiment/BFTS)
  - `LITERATURE_EMBED_MODEL=text-embedding-3-small` (embeddings)
  - plus whatever ideation/writeup/review models the orchestrator requests.
- The **working endpoint is `https://yunwu.ai/v1`** (both resolve, prefer the documented one).

## What was NOT done (by design)
- **Did NOT** write any yunwu config into `.env` (no valid key to write).
- **Did NOT** fall back to the existing OpenRouter key in `.env` (explicitly forbidden).
- **Did NOT** run STEP 3/4/5 (ideation, experiments, writeup, PDF) — impossible without a
  working LLM provider.
- `.env` left untouched (still holds the prior OpenRouter config; unused).

## To unblock
Replace the contents of `/home/zezhenglin/.yunwu_key` with a **valid, active yunwu API key**
(typically `sk-...`). Re-run. STEP 1 will then: probe `https://yunwu.ai/v1`, smoke-test the
required models with one call each, write key + base URL + model map into `.env`, and proceed.

## Spend
| Stage | Tokens | Cost |
|---|---|---|
| Endpoint/auth probes (2× 401) | 0 completion | $0.00 |
| **TOTAL** | — | **$0.00 / $20.00 cap** |

# YUNWU PROVIDER SETUP — FAILURE REPORT (STOP at STEP 1)

**Date:** 2026-07-05 (SLURM unattended run)
**Outcome:** ❌ Could not wire up yunwu. Pipeline (STEPS 3–5) was **NOT run**.
**Money spent:** **$0.00** — no billable completion ever succeeded; every attempt was
rejected by yunwu's gateway *before* any model inference (HTTP 401, pre-billing).
**Fallback:** **NONE.** Per instructions, I did not fall back to the old OpenRouter key.
`.env` was left **untouched** (still points at OpenRouter — no pipeline was run against it).
The hard $20 cap was never approached.

---

## What was verified to be WORKING

1. **Key file read correctly.** `/home/zezhenglin/.yunwu_key` is exactly 51 bytes,
   value `sk-PQM9…` (redacted — 50-char `sk-` token), **no** trailing newline
   or hidden characters (`repr` confirmed). This is the same key stored in
   `.env.yunwu_backup`.
2. **Base URL detected and reachable.** Both candidate endpoints resolve and answer
   through yunwu's "New-API" gateway:
   - `https://yunwu.ai/v1`  ✅ reachable
   - `https://api.yunwu.ai/v1`  ✅ reachable
   Network egress from the compute node to yunwu works.
3. **The account exists.** `GET /v1/dashboard/billing/subscription` returned
   `token_name: "林泽正"`, `has_payment_method: true`. Usage endpoint returned
   `total_usage: 106015.87` (New-API internal units), i.e. the account has a large
   history of prior spend.

## What FAILED — the blocker

**The API token itself is disabled/expired/exhausted.** It is recognized by the gateway
but its status gate rejects every request *before* model routing:

| Request | Gateway response |
|---|---|
| Our key → `POST /v1/chat/completions` (gpt-4o-mini) | `401 该令牌状态不可用` ("this token's status is unavailable") |
| Our key → same, `api.yunwu.ai/v1` | `401 该令牌状态不可用` (identical) |
| **Control: a deliberately garbage key** | `401 无效的令牌` ("invalid token") — **different message** |
| Our key → `GET /v1/models` (after repeats) | `您多次使用无效令牌，请等待 120 秒后再试` (rate-limited as invalid) |

The two distinct error strings are the key diagnostic:
- `无效的令牌` = the token does not exist / is malformed.
- `该令牌状态不可用` = the token **exists on the account** but its *status* is not usable
  — in New-API this means the token has been **manually disabled, has expired, or its
  quota is exhausted** (quota exhaustion auto-flips status to disabled).

Because this gate fires ahead of model selection, **no model names could be tested** and
**no chat/embedding completion could be produced** on any endpoint. There is no
configuration, endpoint, or model-name change that can work around a disabled token.

## Endpoints tested
- `https://yunwu.ai/v1`  → token rejected (`该令牌状态不可用`)
- `https://api.yunwu.ai/v1`  → token rejected (`该令牌状态不可用`)

## Models tested
- None reachable. The token-status gate rejects all requests before model routing, so
  `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4.1-nano`, `deepseek-chat`, `deepseek-v3`,
  `gpt-4o`, and `text-embedding-3-small` could not be exercised.

## Reproduction
```
KEY=$(cat /home/zezhenglin/.yunwu_key)
curl -sS https://yunwu.ai/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"OK"}],"max_tokens":3}'
# -> {"error":{"message":"该令牌状态不可用 ...","type":"new_api_error"}}
```
Raw probe output is in `probe_results.json`; probe script is `probe_yunwu.py`.

## What the user needs to do to unblock
Get a **fresh, enabled yunwu API token** (or re-enable/top-up the existing one) from the
yunwu.ai console (令牌管理 / Token management → ensure status = enabled, not expired, quota
remaining). Then drop it into `/home/zezhenglin/.yunwu_key` and re-run this job. The base
URL `https://yunwu.ai/v1` is already confirmed correct, so wiring will proceed
automatically once the token is valid.

## Steps NOT executed (blocked by the above)
- STEP 2 cost tracking — n/a, nothing spent.
- STEP 3 Config A full pipeline — **not run**.
- STEP 4 Config B ideation+experiments — **not run**.
- STEP 5 detailed records / summary reports — n/a, no runs produced.

**Grand total spend: $0.00. Cap ($20) not hit. No stages ran; the single failed stage is
"STEP 1 provider wiring", failing with the real error `该令牌状态不可用` (yunwu token
status unavailable / disabled).**

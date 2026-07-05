import os, sys, json, time
from openai import OpenAI

KEY = open("/home/zezhenglin/.yunwu_key").read().strip()
ENDPOINTS = ["https://yunwu.ai/v1", "https://api.yunwu.ai/v1"]
# Models the project needs to cover: a main chat model + a coding (BFTS) model.
CANDIDATES = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "deepseek-chat", "deepseek-v3", "gpt-4o"]

def try_call(base, model):
    c = OpenAI(api_key=KEY, base_url=base, timeout=40, max_retries=0)
    t0 = time.time()
    r = c.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=5, temperature=0,
    )
    dt = time.time() - t0
    txt = r.choices[0].message.content
    usage = r.usage
    return {"ok": True, "text": txt, "dt": round(dt, 2),
            "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
            "model_returned": getattr(r, "model", None)}

results = {}
working_base = None
# Step 1: find working endpoint using one cheap model
for base in ENDPOINTS:
    try:
        res = try_call(base, "gpt-4o-mini")
        print(f"[ENDPOINT OK] {base} -> {res}")
        results.setdefault(base, {})["gpt-4o-mini"] = res
        working_base = base
        break
    except Exception as e:
        print(f"[ENDPOINT FAIL] {base}: {type(e).__name__}: {str(e)[:300]}")
        results.setdefault(base, {})["gpt-4o-mini"] = {"ok": False, "err": f"{type(e).__name__}: {str(e)[:300]}"}

if not working_base:
    print("NO WORKING ENDPOINT")
    json.dump(results, open("probe_results.json", "w"), indent=2)
    sys.exit(1)

# Step 2: test each candidate model on the working endpoint
for model in CANDIDATES:
    if model in results.get(working_base, {}):
        continue
    try:
        res = try_call(working_base, model)
        print(f"[MODEL OK] {model} -> {res}")
        results[working_base][model] = res
    except Exception as e:
        print(f"[MODEL FAIL] {model}: {type(e).__name__}: {str(e)[:300]}")
        results[working_base][model] = {"ok": False, "err": f"{type(e).__name__}: {str(e)[:300]}"}

# Step 3: test embedding
try:
    c = OpenAI(api_key=KEY, base_url=working_base, timeout=40, max_retries=0)
    er = c.embeddings.create(model="text-embedding-3-small", input="hello")
    results[working_base]["_embed:text-embedding-3-small"] = {"ok": True, "dim": len(er.data[0].embedding)}
    print(f"[EMBED OK] text-embedding-3-small dim={len(er.data[0].embedding)}")
except Exception as e:
    results[working_base]["_embed:text-embedding-3-small"] = {"ok": False, "err": f"{type(e).__name__}: {str(e)[:300]}"}
    print(f"[EMBED FAIL] {type(e).__name__}: {str(e)[:300]}")

results["_working_base"] = working_base
json.dump(results, open("probe_results.json", "w"), indent=2)
print("WORKING_BASE=" + working_base)

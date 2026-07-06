"""全 prompt 落盘：每次 LLM 调用的 prompt/response 全文 + 真实 token + OpenRouter cost。
LOG_LLM_FULL=1 开启；路径 LLM_FULL_LOG_PATH 或 <RUN_ROOT>/llm_calls_full.jsonl。不截断。"""
import os, json, threading
from datetime import datetime
_lock = threading.Lock()
_last = {"prompt":0,"completion":0,"reasoning":0,"cached":0,"model":"","cost":None}

def _path():
    return os.environ.get("LLM_FULL_LOG_PATH",
        os.path.join(os.environ.get("RUN_ROOT","ai_system_runs/oneshot"),"llm_calls_full.jsonl"))

def install():
    if os.environ.get("LOG_LLM_FULL","0") != "1":
        return
    try:
        from ai_scientist.utils.token_tracker import TokenTracker
    except Exception as e:
        print(f"[llm_full_logger] import 失败: {e}"); return

    o_tok = TokenTracker.add_tokens
    o_int = TokenTracker.add_interaction

    def p_tok(self, model, pt, ct, rt=0, cc=0):
        _last.update({"prompt":pt or 0,"completion":ct or 0,"reasoning":rt or 0,
                      "cached":cc or 0,"model":model})
        return o_tok(self, model, pt, ct, rt, cc)

    def p_int(self, model, sysmsg, prompt, response, ts):
        path = _path(); os.makedirs(os.path.dirname(path), exist_ok=True)
        rec = {"ts_wall":datetime.now().isoformat(),"ts_api":str(ts),"model":model,
               "prompt_tokens":_last["prompt"],"completion_tokens":_last["completion"],
               "reasoning_tokens":_last["reasoning"],"cached_tokens":_last["cached"],
               "system_message":sysmsg or "","prompt":prompt or "","response":response or ""}
        with _lock:
            with open(path,"a") as f: f.write(json.dumps(rec,ensure_ascii=False)+"\n")
        return o_int(self, model, sysmsg, prompt, response, ts)

    TokenTracker.add_tokens = p_tok
    TokenTracker.add_interaction = p_int
    print(f"[llm_full_logger] 全 prompt 落盘已开 → {_path()}")

"""
llm.py — JARVIS LLM backend.

Priority order: fcc → openrouter → ollama → anthropic
Auto-detects which backends are available and falls back gracefully.

FIX: fcc proxy with NVIDIA NIM ignores stream=False and always returns SSE.
     _parse_fcc_response() handles BOTH plain JSON and SSE stream transparently.
"""

import os, json, urllib.request, urllib.error


def _load_cfg(p):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return {}


def _fcc_token(cfg):
    t = cfg.get("fcc_token", "").strip()
    if t and t != "fcc-no-auth": return t
    t = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
    if t: return t
    # read fcc .env
    ai  = os.path.dirname(os.path.abspath(__file__))
    env = os.path.join(os.path.dirname(os.path.dirname(ai)), ".env")
    if os.path.isfile(env):
        for line in open(env):
            line = line.strip()
            if line.startswith("#") or "=" not in line: continue
            k, _, v = line.partition("=")
            if k.strip() == "ANTHROPIC_AUTH_TOKEN":
                v = v.strip().strip('"').strip("'")
                if v: return v
    return ""


# ── SSE / JSON dual parser ────────────────────────────────────────────────────
def _parse_fcc_response(raw: bytes) -> dict:
    """
    Parse fcc server response — handles BOTH plain JSON and SSE stream.

    The fcc proxy with NVIDIA NIM ignores stream=False and returns SSE events:
        event: message_start
        data: {"type":"message_start", ...}

        event: content_block_delta
        data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}

    We collect all text_delta pieces and tool_use blocks, then return the
    same dict shape as a normal non-stream Anthropic response.
    """
    text = raw.decode("utf-8", errors="replace").strip()

    # ── Plain JSON path ──────────────────────────────────────────────────────
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if "error" in data and "content" not in data:
                err = data["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return {"error": msg}
            texts, tc_list = [], []
            for blk in data.get("content", []):
                if blk.get("type") == "text":
                    texts.append(blk["text"])
                elif blk.get("type") == "tool_use":
                    tc_list.append({"name": blk["name"], "arguments": blk.get("input", {})})
            return {"text": "\n".join(texts), "tool_calls": tc_list}
        except json.JSONDecodeError:
            pass  # fall through to SSE parser

    # ── SSE stream path ──────────────────────────────────────────────────────
    # Parse lines like:
    #   event: content_block_delta
    #   data: {"type":"content_block_delta","delta":{"text":"hello"}}
    texts     = []
    tc_list   = []
    tc_buffer = {}   # index → {id, name, input_str}
    error_msg = None

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            ev = json.loads(payload)
        except json.JSONDecodeError:
            continue

        etype = ev.get("type", "")

        # Anthropic native SSE events
        if etype == "content_block_delta":
            delta = ev.get("delta", {})
            if delta.get("type") == "text_delta":
                texts.append(delta.get("text", ""))
            elif delta.get("type") == "input_json_delta":
                idx = ev.get("index", 0)
                if idx in tc_buffer:
                    tc_buffer[idx]["input_str"] += delta.get("partial_json", "")

        elif etype == "content_block_start":
            blk = ev.get("content_block", {})
            if blk.get("type") == "tool_use":
                idx = ev.get("index", len(tc_buffer))
                tc_buffer[idx] = {
                    "id":        blk.get("id", ""),
                    "name":      blk.get("name", ""),
                    "input_str": "",
                }

        elif etype == "content_block_stop":
            idx = ev.get("index")
            if idx in tc_buffer:
                buf = tc_buffer.pop(idx)
                try:    args = json.loads(buf["input_str"]) if buf["input_str"] else {}
                except: args = {}
                tc_list.append({"name": buf["name"], "arguments": args})

        elif etype == "error":
            err = ev.get("error", {})
            error_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)

        # OpenAI-style SSE (openrouter / NIM via openai compat)
        elif etype == "" and "choices" in ev:
            for ch in ev.get("choices", []):
                delta = ch.get("delta", {})
                piece = delta.get("content") or ""
                if piece:
                    texts.append(piece)
                # tool_calls in openai streaming delta
                for tc in delta.get("tool_calls", []) or []:
                    idx = tc.get("index", len(tc_buffer))
                    fn  = tc.get("function", {})
                    if idx not in tc_buffer:
                        tc_buffer[idx] = {"name": fn.get("name",""), "input_str": ""}
                    else:
                        tc_buffer[idx]["name"] = tc_buffer[idx]["name"] or fn.get("name","")
                    tc_buffer[idx]["input_str"] += fn.get("arguments","")
                # finish_reason → flush openai tool buffers
                if ch.get("finish_reason") == "tool_calls":
                    for idx, buf in tc_buffer.items():
                        try:    args = json.loads(buf["input_str"]) if buf["input_str"] else {}
                        except: args = {}
                        tc_list.append({"name": buf["name"], "arguments": args})
                    tc_buffer.clear()

    if error_msg:
        return {"error": error_msg}

    # flush any remaining openai-style tool buffers
    for buf in tc_buffer.values():
        try:    args = json.loads(buf["input_str"]) if buf["input_str"] else {}
        except: args = {}
        if buf.get("name"):
            tc_list.append({"name": buf["name"], "arguments": args})

    result_text = "".join(texts)
    if not result_text and not tc_list:
        return {"error": "Empty response from fcc server (no text or tool calls found in SSE stream)"}

    return {"text": result_text, "tool_calls": tc_list}


def chat(messages, system_prompt, cfg_path, tools=None, stream_callback=None):
    cfg     = _load_cfg(cfg_path)
    backend = cfg.get("llm_backend", "fcc")
    if backend == "fcc":
        return _fcc(messages, system_prompt, cfg, tools, stream_callback)
    if backend == "openrouter":
        return _openrouter(messages, system_prompt, cfg, tools)
    if backend == "anthropic":
        return _anthropic(messages, system_prompt, cfg, tools)
    return _ollama(messages, system_prompt, cfg, tools, stream_callback)


# ── fcc proxy ────────────────────────────────────────────────────────────────
def _fcc(messages, system_prompt, cfg, tools, stream_callback=None):
    url   = cfg.get("fcc_url", "http://127.0.0.1:8082")
    token = _fcc_token(cfg)
    model = cfg.get("fcc_model", "claude-sonnet-4-6")
    body  = {
        "model": model, "max_tokens": cfg.get("fcc_max_tokens", 2048),
        "system": system_prompt, "messages": messages,
        # NOTE: stream=False is sent but fcc+NIM may return SSE anyway.
        # _parse_fcc_response handles both transparently.
        "stream": False,
    }
    if tools: body["tools"] = tools
    hdrs = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    if token: hdrs["x-api-key"] = token

    try:
        req = urllib.request.Request(
            f"{url}/v1/messages",
            data=json.dumps(body).encode(), headers=hdrs
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try: detail = json.loads(e.read()).get("detail", "")
        except Exception: pass
        if e.code == 401:
            return {"text": (
                "❌ fcc 401 Unauthorized.\n\n"
                "Check your ANTHROPIC_AUTH_TOKEN in .env matches fcc_token in jarvis_config.json.\n"
                f"Detail: {detail}"
            ), "tool_calls": []}
        return {"text": f"❌ fcc HTTP {e.code}: {detail}", "tool_calls": []}
    except urllib.error.URLError as e:
        return {"text": f"❌ fcc unreachable: {e}\nRun: uv run fcc-server", "tool_calls": []}
    except Exception as e:
        return {"text": f"❌ fcc error: {e}", "tool_calls": []}

    if not raw or not raw.strip():
        return {"text": (
            "❌ fcc returned empty response.\n\n"
            "Your provider API key is missing or wrong in the Admin UI.\n"
            "→ http://127.0.0.1:8082/admin  → paste your NVIDIA NIM key\n"
            "  Get free key: https://build.nvidia.com/settings/api-keys"
        ), "tool_calls": []}

    result = _parse_fcc_response(raw)

    if "error" in result:
        return {"text": f"❌ Provider error: {result['error']}", "tool_calls": []}

    text = result.get("text", "")
    if stream_callback and text:
        stream_callback(text)
    return {"text": text, "tool_calls": result.get("tool_calls", [])}


# ── openrouter ───────────────────────────────────────────────────────────────
def _openrouter(messages, system_prompt, cfg, tools):
    key = (cfg.get("openrouter_api_key") or "").strip() or os.environ.get("OPENROUTER_API_KEY","").strip()
    if not key: return {"text": "❌ openrouter: no API key in jarvis_config.json", "tool_calls": []}
    base  = cfg.get("openrouter_url", "https://openrouter.ai/api/v1")
    model = cfg.get("openrouter_model", "deepseek/deepseek-chat:free")
    body  = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "max_tokens": 1500, "temperature": 0.4,
    }
    if tools: body["tools"] = tools
    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = ""
        try: detail = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception: pass
        if e.code == 402:
            return {"text": (
                "❌ OpenRouter 402 Payment Required.\n\n"
                "Use a FREE model — change openrouter_model in jarvis_config.json:\n"
                '  "openrouter_model": "deepseek/deepseek-r1:free"\n'
                "Other free options:\n"
                "  meta-llama/llama-3.3-70b-instruct:free\n"
                "  google/gemma-3-27b-it:free"
            ), "tool_calls": []}
        return {"text": f"❌ OpenRouter {e.code}: {detail}", "tool_calls": []}
    except Exception as e:
        return {"text": f"❌ OpenRouter error: {e}", "tool_calls": []}

    parts = [c.get("message", {}).get("content", "") for c in data.get("choices", []) if c.get("message", {}).get("content")]
    return {"text": "\n".join(parts), "tool_calls": []}


# ── anthropic direct ─────────────────────────────────────────────────────────
def _anthropic(messages, system_prompt, cfg, tools):
    key = (cfg.get("anthropic_api_key") or "").strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key: return {"text": "❌ anthropic: no API key", "tool_calls": []}
    model = cfg.get("anthropic_model", "claude-sonnet-4-6")
    body  = {"model": model, "max_tokens": cfg.get("anthropic_max_tokens", 2048),
             "system": system_prompt, "messages": messages}
    if tools: body["tools"] = tools
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
    except Exception as e:
        return {"text": f"❌ Anthropic error: {e}", "tool_calls": []}
    texts, tc_list = [], []
    for blk in data.get("content", []):
        if blk.get("type") == "text": texts.append(blk["text"])
        elif blk.get("type") == "tool_use":
            tc_list.append({"name": blk["name"], "arguments": blk.get("input", {})})
    return {"text": "\n".join(texts), "tool_calls": tc_list}


# ── ollama ───────────────────────────────────────────────────────────────────
def _ollama(messages, system_prompt, cfg, tools, stream_callback=None):
    url   = cfg.get("ollama_url", "http://localhost:11434") + "/api/chat"
    model = cfg.get("ollama_model", "qwen3:1.7b")
    msgs  = [{"role": "system", "content": system_prompt}] + messages
    opts  = {
        "num_ctx":     cfg.get("ollama_num_ctx",     2048),
        "num_predict": cfg.get("ollama_num_predict", 400),
        "temperature": cfg.get("ollama_temperature", 0.4),
    }
    opts.update(cfg.get("ollama_options", {}))
    use_stream = bool(stream_callback) and not tools
    body = {"model": model, "messages": msgs, "stream": use_stream, "options": opts}
    if tools: body["tools"] = tools
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    if use_stream: return _ollama_stream(req, stream_callback)
    try:
        with urllib.request.urlopen(req, timeout=180) as r: data = json.load(r)
    except urllib.error.URLError as e:
        return {"text": f"❌ Ollama unreachable: {e}\nRun: ollama serve", "tool_calls": []}
    except Exception as e:
        return {"text": f"❌ Ollama error: {e}", "tool_calls": []}
    msg = data.get("message", {})
    tc_list = []
    for tc in msg.get("tool_calls", []) or []:
        fn = tc.get("function", {}); args = fn.get("arguments", {})
        if isinstance(args, str):
            try: args = json.loads(args)
            except Exception: args = {}
        tc_list.append({"name": fn.get("name"), "arguments": args})
    return {"text": msg.get("content", ""), "tool_calls": tc_list}


def _ollama_stream(req, stream_callback):
    full = []
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            for line in r:
                line = line.strip()
                if not line: continue
                try: chunk = json.loads(line)
                except Exception: continue
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    full.append(piece)
                    stream_callback(piece)
                if chunk.get("done"): break
    except Exception as e:
        m = f"❌ Ollama stream error: {e}"
        stream_callback(m)
        return {"text": m, "tool_calls": []}
    return {"text": "".join(full), "tool_calls": []}


def available_backends(cfg_path=None):
    cfg = _load_cfg(cfg_path) if cfg_path else {}
    out = {}
    fcc_url = cfg.get("fcc_url", "http://127.0.0.1:8082")
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{fcc_url}/health"), timeout=2): pass
        out["fcc"] = True
    except Exception: out["fcc"] = False
    try:
        with urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/tags"), timeout=2): pass
        out["ollama"] = True
    except Exception: out["ollama"] = False
    out["anthropic"]  = bool((cfg.get("anthropic_api_key") or "").strip() or os.environ.get("ANTHROPIC_API_KEY","").strip())
    out["openrouter"] = bool((cfg.get("openrouter_api_key") or "").strip() or os.environ.get("OPENROUTER_API_KEY","").strip())
    return out

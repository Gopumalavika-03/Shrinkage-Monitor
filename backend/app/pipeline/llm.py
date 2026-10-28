"""Optional LLM step: rewrite alerts in plain language for a store manager.

The LLM only rephrases facts the detector already computed (it never sees raw data and adds
no numbers). Works with any OpenAI-compatible chat endpoint (OpenAI, Groq, Gemini, Ollama, ...):

    copy backend/.env.example to backend/.env, fill LLM_API_KEY + LLM_MODEL, then
    python -m app.pipeline.run --llm      (or use the dashboard's Explain button)

Answers are cached by alert content in llm_cache/alert_narratives.json, so reruns give the same text
and cost nothing. The output file is kept out of the reproducibility checksums.
"""
import hashlib
import json
import os
import urllib.request

from .. import settings   # loads backend/.env into os.environ

CACHE = settings.BACKEND / "llm_cache" / "alert_narratives.json"
PROMPT = ("You are a retail loss-prevention analyst. Rewrite the alert for a store manager in 2-3 short sentences. "
          "Use only the facts given; never invent numbers, names or causes. Say whether it looks like theft, a data "
          "error or a process gap, and name the first thing to check.")
FIELDS = ["alert_type", "classification", "store_id", "employee_id", "loss_units", "loss_value_inr", "severity", "reason_text"]


class LLMNotConfigured(RuntimeError):
    pass


# Provider picked from the key's prefix, so LLM_BASE_URL is only needed for other endpoints (e.g. Ollama, Azure).
KEY_PREFIXES = [("sk-ant-", "https://api.anthropic.com/v1"), ("gsk_", "https://api.groq.com/openai/v1"),
                ("AIza", "https://generativelanguage.googleapis.com/v1beta/openai"), ("sk-", "https://api.openai.com/v1")]


def base_url():
    explicit = os.environ.get("LLM_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    return next((url for prefix, url in KEY_PREFIXES if key.startswith(prefix)), "https://api.openai.com/v1")


def configured():
    return bool(os.environ.get("LLM_API_KEY") and os.environ.get("LLM_MODEL"))


def explain(alert):
    """alert: mapping with FIELDS. Returns {"model", "text", "cached"}."""
    facts = {f: str(alert.get(f)) for f in FIELDS}
    h = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if h in cache:
        return {**cache[h], "cached": True}
    if not configured():
        raise LLMNotConfigured("Set LLM_API_KEY and LLM_MODEL in backend/.env.")
    url = base_url() + "/chat/completions"
    body = {"model": os.environ["LLM_MODEL"], "temperature": 0,
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": json.dumps(facts)}]}
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {os.environ['LLM_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    cache[h] = {"model": body["model"], "text": text}
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return {**cache[h], "cached": False}


def narrate(alerts, out_path, limit=25):
    """Top alerts by risk -> JSON file of plain-language summaries."""
    out = [{"alert_id": r["alert_id"], **explain(r)}
           for r in alerts.sort_values("risk_score", ascending=False).head(limit).to_dict("records")]
    Path(out_path).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

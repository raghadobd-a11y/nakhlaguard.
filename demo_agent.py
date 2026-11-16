"""
Public demo of the agentic assistant, on a FAKE farm (NakhlaGuard).

Why it exists: the real assistant (agent.py + /agent/chat) lives in the private owner site and reads
the owner's own data. The public home page lets a visitor try the same agent loop on a small
built-in sample farm, so nobody's real data is ever involved.

What is real: the Gemini calls and the tool-calling loop (agent.run_agent): the model decides by itself
which tool to call. What is fake: the five palms below.

Safety: the endpoint is public, so it is capped. Per visitor and per day; the message is cut to 300
characters; no conversation history is accepted from the browser; the tools only read the sample list.
Settings (environment variables, all optional):
    NAKHLA_PUBLIC_DEMO=off          turns the public demo off (default: on)
    NAKHLA_DEMO_IP_HOURLY=8         questions per visitor per hour
    NAKHLA_DEMO_DAILY=300           questions for the whole site per day
"""
import collections
import os
import time
from datetime import datetime, timedelta

from agent import run_agent

MAX_MESSAGE_CHARS = 300
_IP_HITS = collections.defaultdict(collections.deque)
_DAY_HITS = collections.deque()


def _int_env(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def _iso(days_ago):
    return (datetime.utcnow() - timedelta(days=days_ago)).isoformat()


# (id, location, notes, age, [(class, score, days_ago), ...])  classes use the same Arabic labels as the real database
_SAMPLE = [
    ("Palm-A12", "Demo farm, row 1", "Small fresh holes near the base", 8, [("سليم", 0.12, 40), ("مبكرة", 0.41, 12), ("متوسطة", 0.63, 3)]),
    ("Palm-B03", "Demo farm, row 1", None, 14, [("سليم", 0.10, 45), ("سليم", 0.09, 5)]),
    ("Palm-C07", "Demo farm, row 2", "Young offshoot planted last year", 3, [("سليم", 0.15, 60)]),
    ("Palm-D21", "Demo farm, row 2", None, 21, [("مبكرة", 0.38, 20)]),
    ("Palm-E05", "Demo farm, row 3", "Frond bases look damaged", 6, [("متقدمة", 0.88, 1)]),
]
_ALERT = {"متوسطة", "متقدمة"}


def _history(entry):
    return [{"class": c, "score": s, "date": _iso(d)} for (c, s, d) in entry[4]]


def _palm_row(entry):
    hist = _history(entry)
    last = hist[-1] if hist else None
    return {
        "palm_id": entry[0], "location": entry[1], "notes": entry[2], "age_years": entry[3],
        "registered_at": _iso(90),
        "latest_status": last["class"] if last else None,
        "latest_score": last["score"] if last else None,
        "latest_check": last["date"] if last else None,
    }


def list_palms():
    return [_palm_row(e) for e in _SAMPLE]


def get_palm_details(palm_id):
    for e in _SAMPLE:
        if e[0].lower() == str(palm_id).strip().lower():
            row = _palm_row(e)
            return {**{k: row[k] for k in ("palm_id", "location", "notes", "age_years", "registered_at")},
                    "check_history": _history(e)}
    return {"error": f"No palm registered with ID '{palm_id}'."}


def palms_needing_attention():
    return [p for p in list_palms() if p["latest_status"] in _ALERT]


def palms_due_for_recheck(days=30):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    due = []
    for p in list_palms():
        last = p["latest_check"] or p["registered_at"]
        if last < cutoff:
            due.append({**p, "days_since_last_check": (datetime.utcnow() - datetime.fromisoformat(last)).days})
    return due


def get_farm_contact():
    return {"contact_name": "Demo contact (sample data)", "contact_phone": "0500000000"}


TOOL_EXECUTOR = {
    "list_palms": list_palms,
    "get_palm_details": get_palm_details,
    "palms_needing_attention": palms_needing_attention,
    "palms_due_for_recheck": palms_due_for_recheck,
    "get_farm_contact": get_farm_contact,
}


def client_ip(request):
    """Same rule as the main rate limiter: the last X-Forwarded-For hop (Render), else the socket address."""
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[-1].strip() if xff else "") or (request.client.host if request.client else "unknown")


def _allowed(ip, now):
    per_ip = _int_env("NAKHLA_DEMO_IP_HOURLY", 8)
    per_day = _int_env("NAKHLA_DEMO_DAILY", 300)
    q = _IP_HITS[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    while _DAY_HITS and now - _DAY_HITS[0] > 86400:
        _DAY_HITS.popleft()
    if len(q) >= per_ip or len(_DAY_HITS) >= per_day:
        return False
    q.append(now)
    _DAY_HITS.append(now)
    return True


async def demo_chat(message, language, ip):
    """Returns (http_status, json_payload)."""
    if os.environ.get("NAKHLA_PUBLIC_DEMO", "on").strip().lower() in ("off", "0", "false", "no"):
        return 403, {"error": "demo_off", "message": "The public demo is switched off."}
    message = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if not message:
        return 400, {"error": "empty", "message": "Empty question."}
    language = language if language in ("ar", "en", "ur") else "en"
    if not _allowed(ip, time.time()):
        return 429, {"error": "demo_limit", "message": "The demo question limit was reached. Please try again later."}
    result = await run_agent(message, TOOL_EXECUTOR, [], language=language)
    return 200, {"answer": result.get("answer", ""), "trace": result.get("trace", []), "demo": True}


# ---------------------------------------------------------------------------
# "Try the device" box: the visitor picks one of the four ready simulated recordings and the trained
# model classifies it. This uses only the local scikit-learn model (no Gemini, no key, no cost).
# ---------------------------------------------------------------------------
SAMPLES = {"healthy": "1_healthy.wav", "early": "2_early.wav", "moderate": "3_moderate.wav", "advanced": "4_advanced.wav"}
STAGES = ["healthy", "early", "moderate", "advanced"]   # same order as the model's four classes


def analyze_sample(sample, base_dir, predict_fn):
    """Returns (http_status, json_payload). predict_fn(path) is predict.predict_severity_from_file."""
    if os.environ.get("NAKHLA_PUBLIC_DEMO", "on").strip().lower() in ("off", "0", "false", "no"):
        return 403, {"error": "demo_off", "message": "The public demo is switched off."}
    name = SAMPLES.get(str(sample))
    path = os.path.join(base_dir, "demo_wavs", name) if name else None
    if not name or not os.path.exists(path):
        return 404, {"error": "sample_not_found", "message": "Sample recording not found."}
    try:
        r = predict_fn(path)
    except Exception as e:
        print(f"[NakhlaGuard demo] sample analysis failed: {type(e).__name__}: {e}")
        return 503, {"error": "model_unavailable", "message": "The model is not ready on this server."}
    keys = list(r["probabilities"].keys())
    if len(keys) != 4:
        return 503, {"error": "model_unavailable", "message": "Unexpected model output."}
    return 200, {
        "sample": sample,
        "stage": STAGES[keys.index(r["predicted_class"])],
        "confidence": float(r["confidence"]),
        "probabilities": {STAGES[i]: float(r["probabilities"][k]) for i, k in enumerate(keys)},
        "simulated": True, "demo": True,
    }


def allow_report(ip):
    """Gemini report from the public try page: same per-visitor and daily caps as the assistant (one report = one question)."""
    return _allowed(ip, time.time())


def demo_enabled():
    return os.environ.get("NAKHLA_PUBLIC_DEMO", "on").strip().lower() not in ("off", "0", "false", "no")

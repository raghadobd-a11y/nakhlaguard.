"""
إشعار على الجوال عند اشتباه إصابة متوسطة/متقدمة، حتى لو كان الموقع مغلقًا على الجوال.
يستخدم خدمة ntfy.sh المجانية: لا حساب ولا Firebase ولا مكتبات إضافية (مكتبة بايثون القياسية فقط).

الإعداد (في Render ضمن Environment):
    NAKHLA_NTFY_TOPIC   اسم قناة سرّي صعب التخمين (حروف إنجليزية وأرقام و - و _ فقط، من 20 حرفًا فأكثر).
                        من يعرف الاسم يستطيع قراءة الإشعارات، فلا تنشره ولا تضعه في ملصق أو باركود.
    NAKHLA_SITE_URL     (اختياري) رابط موقعك، يُفتح عند الضغط على الإشعار. مثل https://xxxx.onrender.com
    NAKHLA_NTFY_SERVER  (اختياري) الافتراضي https://ntfy.sh

على الجوال: ثبّت تطبيق ntfy (مجاني) ثم Subscribe to topic واكتب نفس اسم القناة.
لا يُرسل الإشعار إلا رقم النخلة ودرجة الاشتباه والموقع، بدون التوصية الكاملة وبدون أي مفتاح.
"""
import json
import os
import threading
import time
import urllib.request

_LAST = {}              # (نخلة، درجة) -> وقت آخر إرسال، لتخفيف التكرار السريع
_LOCK = threading.Lock()
THROTTLE_SEC = 15
TIMEOUT_SEC = 6


def _deliver(payload):
    server = (os.environ.get("NAKHLA_NTFY_SERVER", "") or "https://ntfy.sh").strip().rstrip("/")
    req = urllib.request.Request(
        server + "/",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
            ok = 200 <= r.status < 300
            print(f"[phone_push] status {r.status}", flush=True)
            return ok, f"status {r.status}"
    except Exception as e:                       # لا نوقف التحليل أبدًا بسبب فشل الإشعار
        print(f"[phone_push] failed: {type(e).__name__}", flush=True)
        return False, type(e).__name__


def send_phone_push(palm_id, severity, location=None, test=False, wait=False):
    """يرجع (هل الإعداد موجود، هل وصل الإرسال). بدون wait يُرسل في خيط خلفي ولا يؤخر الرد."""
    topic = (os.environ.get("NAKHLA_NTFY_TOPIC", "") or "").strip()
    if not topic:
        return False, False
    now = time.time()
    if not test:
        with _LOCK:
            key = (palm_id, severity)
            if now - _LAST.get(key, 0) < THROTTLE_SEC:
                return True, False
            _LAST[key] = now
    if test:
        title, message, prio = "🌴 اختبار NakhlaGuard", "إذا ظهر هذا الإشعار على جوالك فالربط يعمل.", 3
    else:
        title = f"🌴 NakhlaGuard: اشتباه إصابة {severity}"
        message = f"النخلة {palm_id}" + (f" — {location}" if location else "") + "\nافتح الموقع لرؤية التفاصيل."
        prio = 5 if severity == "متقدمة" else 4
    payload = {"topic": topic, "title": title, "message": message, "priority": prio, "tags": ["warning"]}
    site = (os.environ.get("NAKHLA_SITE_URL", "") or "").strip()
    if site.startswith("http"):
        payload["click"] = site.rstrip("/") + "/dashboard.html"
    if wait:
        return True, _deliver(payload)[0]
    threading.Thread(target=_deliver, args=(payload,), daemon=True).start()
    return True, True

"""
تطبيق NakhlaGuard - كشف مبكر لإصابة النخيل بسوسة النخيل الحمراء
================================================================
نفس نمط مشروعك بصيرة: FastAPI + Gemini + واجهة ويب بسيطة.

ملاحظة هيكلية: كل ملفات المشروع (بايثون وHTML) بمستوى واحد بدون
مجلدات فرعية (عشان تتوافق مع الرفع المباشر على GitHub عبر السحب
والإفلات بدون مشاكل مجلدات). كل صفحة HTML تُخدَّم مباشرة من الجذر
(/index.html بدل /static/index.html).

المسارات:
- GET  /                  : الصفحة الرئيسية (index.html)
- GET  /<اسم>.html        : أي صفحة ويب بالمشروع (test, dashboard, palms, agent)
- POST /predict-audio     : يرفع تسجيل صوتي -> شدة الإصابة + الثقة
- POST /predict-full      : صوت (+ صورة اختياري + موقع) -> دمج + توصية Gemini
                            (تقرير كامل تلقائيًا لو الحالة تستدعي عناية)
                            + إشعار فوري تلقائي لو الحالة متوسطة/متقدمة
- GET  /history/{palm_id} : سجل فحوصات نخلة معينة (لرسم منحنى التطور)
- GET  /palms             : سجل كل النخيل المسجّلة + مواقعها + آخر حالة لكل وحدة
- POST /palms             : تسجيل/تحديث نخلة (رقمها + موقعها + ملاحظات)
- WS   /ws/alerts         : اتصال مباشر (WebSocket) - لوحة المزارع تستقبل
                            عليه إشعارات لحظية بمجرد اكتشاف إصابة، بدون
                            حاجة لتحديث الصفحة يدويًا
- POST /agent/chat        : وكيل ذكاء اصطناعي (Agentic AI) - يجاوب أسئلة
                            المزارع عن نخيله عبر استدعاء أدوات حقيقية على
                            قاعدة البيانات (مو نص مبرمج مسبقًا) - شوفي agent.py
"""
import os
import json
import tempfile
import time
import collections
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# كل الملفات بنفس مجلد app.py، فـ Python يضيف هذا المجلد لمسار
# البحث تلقائيًا - ما نحتاج أي sys.path.append إضافي
from predict import predict_severity_from_file  # noqa: E402
from fusion import fuse_audio_image, get_gemini_recommendation, estimate_age_and_health_from_image  # noqa: E402
from agent import run_agent  # noqa: E402
from locate import locate_signs_from_image  # noqa: E402
from sensor_location import locate_from_json, save_latest, get_latest, demo_location  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nakhla.db")

app = FastAPI(title="NakhlaGuard API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---- حماية بسيطة لأن النموذج مفتوح للجميع (حصة Gemini ومفتاحه على حسابك) ----
# حد للطلبات لكل زائر في الدقيقة، وحد للموقع كله، وحد لحجم الملف الصوتي. للتعديل: متغيرات البيئة NAKHLA_RATE_MAX و NAKHLA_RATE_GLOBAL.
_RATE_HITS = collections.defaultdict(collections.deque)
_RATE_PATHS = {"/predict-full", "/predict-audio", "/locate-signs", "/agent/chat", "/estimate-age-health"}
_RATE_MAX = int(os.environ.get("NAKHLA_RATE_MAX", "20"))
_RATE_GLOBAL = int(os.environ.get("NAKHLA_RATE_GLOBAL", "150"))
MAX_AUDIO_BYTES = 6 * 1024 * 1024


@app.middleware("http")
async def rate_limit(request, call_next):
    if request.method == "POST" and (request.url.path in _RATE_PATHS
                                     or request.url.path.startswith(("/helpers", "/visit-requests"))):
        xff = request.headers.get("x-forwarded-for", "")
        ip = (xff.split(",")[-1].strip() if xff else "") or (request.client.host if request.client else "unknown")
        now = time.time()
        for key in (ip, "__all__"):
            q = _RATE_HITS[key]
            while q and now - q[0] > 60:
                q.popleft()
        if len(_RATE_HITS[ip]) >= _RATE_MAX or len(_RATE_HITS["__all__"]) >= _RATE_GLOBAL:
            return JSONResponse({"error": "rate_limited", "message": "Too many requests. Please try again in a minute."}, status_code=429)
        _RATE_HITS[ip].append(now)
        _RATE_HITS["__all__"].append(now)
    return await call_next(request)


def _html(filename):
    """يرجّع صفحة HTML من نفس مجلد المشروع (بدون الحاجة لمجلد static/ منفصل)."""
    return FileResponse(os.path.join(BASE_DIR, filename))


@app.get("/")
def serve_home():
    return _html("index.html")


@app.get("/index.html")
def serve_index():
    return _html("index.html")


@app.get("/test.html")
def serve_test():
    return _html("test.html")


@app.get("/locate.html")
def serve_locate():
    return _html("locate.html")


@app.get("/evidence.html")
def serve_evidence():
    return _html("evidence.html")


@app.get("/claims.json")
def serve_claims():
    return FileResponse(os.path.join(BASE_DIR, "claims.json"), media_type="application/json")


@app.get("/verification_report.json")
def serve_verification_json():
    path = os.path.join(BASE_DIR, "verification_report.json")
    if not os.path.exists(path):
        return JSONResponse({"error": "not run yet: python verify_all.py"}, status_code=404)
    return FileResponse(path, media_type="application/json")


@app.get("/verification_report.html")
def serve_verification_html():
    path = os.path.join(BASE_DIR, "verification_report.html")
    if not os.path.exists(path):
        return JSONResponse({"error": "not run yet: python verify_all.py"}, status_code=404)
    return FileResponse(path)


@app.get("/nav.js")
def serve_nav():
    return FileResponse(os.path.join(BASE_DIR, "nav.js"), media_type="application/javascript")


@app.get("/health")
def health():
    return {"ok": True}


# تسجيلات تجريبية مُحاكاة (من make_demo_wavs.py) ليجرّب الزائر بدون ما يملك ملفًا صوتيًا
DEMO_WAVS = {"1_healthy.wav", "2_early.wav", "3_moderate.wav", "4_advanced.wav"}


@app.get("/demo-wav/{name}")
def demo_wav(name: str):
    path = os.path.join(BASE_DIR, "demo_wavs", name)
    if name not in DEMO_WAVS or not os.path.exists(path):
        return JSONResponse({"error": "sample not found; run make_demo_wavs.py"}, status_code=404)
    return FileResponse(path, media_type="audio/wav")


@app.get("/dashboard.html")
def serve_dashboard():
    return _html("dashboard.html")


@app.get("/palms.html")
def serve_palms_page():
    return _html("palms.html")


@app.get("/agent.html")
def serve_agent_page():
    return _html("agent.html")


@app.get("/instructions.html")
def serve_instructions_page():
    return _html("instructions.html")


@app.get("/palm.html")
def serve_palm_detail_page():
    return _html("palm.html")


@app.get("/farmers.html")
def serve_farmers_page():
    return _html("farmers.html")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palm_id TEXT NOT NULL,
            predicted_class TEXT,
            final_score REAL,
            created_at TEXT
        )
    """)
    # سجل النخيل: كل نخلة مسجّلة بموقعها (نص حر - رقم صف، إحداثيات،
    # أي وصف يفهمه المزارع)، عشان لو عنده نخل كثير يلقى كل وحدة بسهولة
    conn.execute("""
        CREATE TABLE IF NOT EXISTS palms (
            palm_id TEXT PRIMARY KEY,
            location TEXT,
            notes TEXT,
            age_years INTEGER,
            created_at TEXT
        )
    """)
    # ترقية آمنة لقاعدة بيانات قديمة ما فيها عمود العمر بعد (لو الجدول
    # كان موجود قبل ما نضيف هالميزة) - نتجاهل الخطأ لو العمود موجود أصلاً
    try:
        conn.execute("ALTER TABLE palms ADD COLUMN age_years INTEGER")
    except sqlite3.OperationalError:
        pass

    # تأكيد المزارع: "هل هذي النتيجة صحيحة؟" بعد كل فحص - NULL (ما تأكد
    # بعد) أو 'correct' أو 'incorrect'. هذا يبني بيانات حقيقية بمرور
    # الوقت، تمهيدًا لإعادة تدريب مستقبلية على ملاحظات فعلية من الميدان
    # (إعادة التدريب نفسها عمل مستقبلي، هذا بس جمع البيانات)
    try:
        conn.execute("ALTER TABLE readings ADD COLUMN confirmed TEXT")
    except sqlite3.OperationalError:
        pass

    # جهة اتصال احتياطية واحدة للمزرعة كاملة (مو لكل نخلة لحالها) - تبان
    # بكل تنبيه خطر، عشان لو صاحب المزرعة مو متوفر (مسافر مثلاً)، فيه
    # شخص ثاني (عامل، قريب) يقدر يتواصلون معه يروح يعالج النخلة
    conn.execute("""
        CREATE TABLE IF NOT EXISTS farm_contact (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            contact_name TEXT,
            contact_phone TEXT
        )
    """)
    # شبكة المساعدين: مزارعون/عمال يسجّلون أنفسهم بإرادتهم ليستقبلوا طلبات الزيارة.
    # لا توجد أي بيانات جاهزة؛ العدد يبدأ من صفر ويزيد فقط بتسجيل فعلي.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS helpers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            area TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palm_id TEXT,
            area TEXT NOT NULL,
            details TEXT,
            severity TEXT,
            requester_name TEXT NOT NULL,
            requester_phone TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            helper_id INTEGER,
            created_at TEXT NOT NULL,
            accepted_at TEXT
        )
    """)
    # أعمدة أُضيفت لاحقًا (متى يحتاج المساعد، لأي غرض، موقع دقيق اختياري): تُضاف لقواعد بيانات قديمة أيضًا
    for col in ("when_needed", "purpose", "coords"):
        try:
            conn.execute(f"ALTER TABLE visit_requests ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


init_db()


def save_reading(palm_id, predicted_class, final_score):
    """يسجّل فحصًا جديدًا، ويرجّع رقم الفحص (reading_id) عشان تقدر الواجهة
    تربط زر 'هل كانت صحيحة؟' بنفس هالفحص بالضبط."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO readings (palm_id, predicted_class, final_score, created_at) VALUES (?,?,?,?)",
        (palm_id, predicted_class, final_score, datetime.utcnow().isoformat()),
    )
    reading_id = cur.lastrowid
    conn.commit()
    conn.close()
    return reading_id


def set_reading_confirmation(reading_id, confirmed):
    """يسجّل تأكيد المزارع لفحص معيّن: 'correct' أو 'incorrect'."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE readings SET confirmed=? WHERE id=?", (confirmed, reading_id))
    conn.commit()
    conn.close()


def get_history(palm_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT predicted_class, final_score, created_at FROM readings "
        "WHERE palm_id=? ORDER BY created_at",
        (palm_id,),
    ).fetchall()
    conn.close()
    return [{"class": r[0], "score": r[1], "date": r[2]} for r in rows]


def upsert_palm(palm_id, location=None, notes=None, age_years=None):
    """يسجّل نخلة جديدة أو يحدّث موقعها/ملاحظاتها/عمرها لو كانت مسجّلة مسبقًا."""
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT palm_id FROM palms WHERE palm_id=?", (palm_id,)).fetchone()
    if existing:
        if location is not None:
            conn.execute("UPDATE palms SET location=? WHERE palm_id=?", (location, palm_id))
        if notes is not None:
            conn.execute("UPDATE palms SET notes=? WHERE palm_id=?", (notes, palm_id))
        if age_years is not None:
            conn.execute("UPDATE palms SET age_years=? WHERE palm_id=?", (age_years, palm_id))
    else:
        conn.execute(
            "INSERT INTO palms (palm_id, location, notes, age_years, created_at) VALUES (?,?,?,?,?)",
            (palm_id, location, notes, age_years, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()


def get_palm_location(palm_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT location FROM palms WHERE palm_id=?", (palm_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def list_palms():
    """يرجّع كل النخيل المسجّلة مع آخر حالة فحص لكل وحدة (لعرضها كقائمة/خريطة)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT p.palm_id, p.location, p.notes, p.age_years, p.created_at,
               r.predicted_class, r.final_score, r.created_at
        FROM palms p
        LEFT JOIN readings r ON r.id = (
            SELECT id FROM readings WHERE palm_id = p.palm_id
            ORDER BY created_at DESC LIMIT 1
        )
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    return [
        {
            "palm_id": r[0], "location": r[1], "notes": r[2], "age_years": r[3], "registered_at": r[4],
            "latest_status": r[5], "latest_score": r[6], "latest_check": r[7],
        }
        for r in rows
    ]


def get_palm_details(palm_id):
    """أداة الوكيل: تفاصيل نخلة معينة كاملة (موقع، ملاحظات، عمر، تاريخ فحوصات)."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT location, notes, age_years, created_at FROM palms WHERE palm_id=?", (palm_id,)
    ).fetchone()
    conn.close()
    check_history = get_history(palm_id)
    if not row and not check_history:
        return {"error": f"No palm registered with ID '{palm_id}'."}
    return {
        "palm_id": palm_id,
        "location": row[0] if row else None,
        "notes": row[1] if row else None,
        "age_years": row[2] if row else None,
        "registered_at": row[3] if row else None,
        "check_history": check_history,
    }


def palms_needing_attention():
    """أداة الوكيل: النخيل اللي حالتها الحالية متوسطة أو متقدمة بس."""
    return [p for p in list_palms() if p["latest_status"] in ALERT_LEVELS]


# عدد الأيام الافتراضي اللي لو عدّى بدون فحص جديد، النخلة تعتبر "محتاجة
# فحص دوري" - ممارسة وقائية عامة، مو مبنية على موسم مرض معيّن
RECHECK_DUE_DAYS = 30


def palms_due_for_recheck(days=RECHECK_DUE_DAYS):
    """
    أداة الوكيل + لوحة المزارع: النخيل اللي ما انفحصت من (days) يوم أو أكثر
    (أو ما انفحصت أبدًا من وقت تسجيلها). هذا تذكير فحص دوري وقائي عام، مو
    تنبؤًا بموسم إصابة لمرض معيّن.
    """
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    due = []
    for p in list_palms():
        last = p["latest_check"] or p["registered_at"]
        if last is None or last < cutoff:
            due.append({**p, "days_since_last_check": (
                (datetime.utcnow() - datetime.fromisoformat(last)).days if last else None
            )})
    return due


def get_farm_contact():
    """جهة الاتصال الاحتياطية للمزرعة (صف واحد بس) - أو None لو ما سُجّلت."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT contact_name, contact_phone FROM farm_contact WHERE id=1").fetchone()
    conn.close()
    if not row or (not row[0] and not row[1]):
        return None
    return {"contact_name": row[0], "contact_phone": row[1]}


def set_farm_contact(contact_name, contact_phone):
    """يسجّل أو يحدّث جهة الاتصال الاحتياطية (صف واحد ثابت id=1)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO farm_contact (id, contact_name, contact_phone) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET contact_name=excluded.contact_name, contact_phone=excluded.contact_phone",
        (contact_name, contact_phone),
    )
    conn.commit()
    conn.close()


# ---------- نظام الإشعارات الفورية (WebSocket) ----------
# الحد الأدنى لشدة الإصابة اللي يستدعي إرسال إشعار للمزارع
ALERT_LEVELS = {"متوسطة", "متقدمة"}
DEMO_LOCATION = os.environ.get("NAKHLA_DEMO_LOCATION", "1") != "0"
LAST_DEVICE = {}      # آخر قراءة وصلت من جهاز المستشعرات (في الذاكرة فقط؛ تُصفَّر عند إعادة تشغيل الخادم)

connected_clients: list[WebSocket] = []


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """
    لوحة المزارع (dashboard.html) تفتح اتصال هنا وتبقى منتظرة.
    بمجرد ما فحص جديد يطلع بنتيجة خطرة، يوصلها إشعار فوري بدون
    ما تحتاج تحدّث الصفحة أو ترسل طلب بنفسها (Push بدل Polling).
    """
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # نخليه مفتوح، ما نحتاج نستقبل شي فعليًا
    except WebSocketDisconnect:
        connected_clients.remove(websocket)


async def broadcast_alert(payload: dict):
    """يرسل الإشعار لكل الشاشات المفتوحة على لوحة المزارع حاليًا."""
    dead = []
    for client in connected_clients:
        try:
            await client.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            dead.append(client)
    for d in dead:
        connected_clients.remove(d)


@app.post("/predict-audio")
async def predict_audio(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename)[1] or ".wav"
    raw = await audio.read()
    if len(raw) > MAX_AUDIO_BYTES:
        return JSONResponse({"error": "too_large", "message": "The audio file is too large (maximum 6 MB)."}, status_code=413)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        result = predict_severity_from_file(tmp_path)
    finally:
        os.remove(tmp_path)
    return JSONResponse(result)


@app.post("/predict-full")
async def predict_full(
    audio: UploadFile = File(...),
    palm_id: str = Form(...),
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    image_infested_probability: Optional[float] = Form(None),
    language: str = Form("en"),
    age_years: Optional[int] = Form(None),
    visual_notes: Optional[str] = Form(None),
    sensor_rms: Optional[str] = Form(None),
):
    """
    التحليل الكامل: صوت (إلزامي) + موقع النخلة (اختياري، يُسجَّل تلقائيًا)
    + وصف إضافي (اختياري) + احتمال إصابة من الصورة (اختياري) + عمر النخلة
    (اختياري، يدوي أو مُقدَّر من الصورة) + ملاحظات بصرية صحية عامة (اختياري)
    + لغة الجواب (en/ar) -> دمج + توصية/تقرير كامل + حفظ بالسجل.
    """
    suffix = os.path.splitext(audio.filename)[1] or ".wav"
    raw = await audio.read()
    if len(raw) > MAX_AUDIO_BYTES:
        return JSONResponse({"error": "too_large", "message": "The audio file is too large (maximum 6 MB)."}, status_code=413)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        audio_result = predict_severity_from_file(tmp_path)
    finally:
        os.remove(tmp_path)

    # نسجّل/نحدّث موقع النخلة ووصفها وعمرها تلقائيًا لو انبعثوا معنا - يبني
    # سجل النخيل تدريجيًا بدون ما يحتاج المزارع خطوة تسجيل منفصلة إجبارية
    upsert_palm(palm_id, location=location, notes=notes, age_years=age_years)
    saved_location = location or get_palm_location(palm_id)

    # موقع مصدر الاهتزاز على الجذع من الحساسات الثلاثة (يرسله الجسر مع التسجيل: {"rms": [..], "base": [..]}).
    # نخزّنه لصفحة النخلة، ويرجع بالنتيجة والتنبيه حتى تعرضه الواجهة مباشرة. بدون sensor_rms لا نغيّر المخزَّن.
    sensor_location = locate_from_json(sensor_rms)
    if sensor_rms:
        save_latest(palm_id, sensor_location)

    fusion_result = fuse_audio_image(audio_result, image_infested_probability)
    # عرض توضيحي: إن لم تصل أي قراءات مستشعرات مع الطلب (مثل تسجيل جاهز يُرفع في المعرض) وكانت النتيجة اشتباهًا بإصابة،
    # نُرفق نقطة موقع محاكاة موسومة mode="demo" حتى تُعرض على الجذع ثلاثي الأبعاد في صفحة الفحص وفي التنبيه.
    # ليست قياسًا. تُعطَّل بالمتغير NAKHLA_DEMO_LOCATION=0 عند الاستخدام الحقيقي. ولا تُخزَّن كأنها قراءة مستشعرات.
    if sensor_rms:      # وجود sensor_rms يعني أن الطلب جاء من الجهاز عبر الجسر، لا من رفع ملف في الموقع
        LAST_DEVICE.clear()
        LAST_DEVICE.update({"palm_id": palm_id, "time": datetime.utcnow().isoformat(),
                            "class": fusion_result["final_class"], "located": sensor_location is not None})
    if (not sensor_rms and sensor_location is None and DEMO_LOCATION
            and fusion_result["final_class"] != "سليم"):
        sensor_location = demo_location(palm_id)
    history = get_history(palm_id)
    recommendation = await get_gemini_recommendation(
        fusion_result, palm_id, history, saved_location, language, age_years, visual_notes
    )
    reading_id = save_reading(palm_id, fusion_result["final_class"], fusion_result["final_score"])

    # إرسال إشعار فوري للمزارع لو الحالة وصلت لمستوى خطورة يستدعي تنبيه
    # - نرفق جهة الاتصال الاحتياطية (لو مسجّلة) عشان لو صاحب المزرعة مو
    #   متوفر، يبان بنفس التنبيه مين يتواصلون معه بدلًا عنه
    if fusion_result["final_class"] in ALERT_LEVELS:
        await broadcast_alert({
            "type": "alert",
            "palm_id": palm_id,
            "location": saved_location,
            "severity": fusion_result["final_class"],
            "score": fusion_result["final_score"],
            "recommendation": recommendation,
            "farm_contact": get_farm_contact(),
            "sensor_location": sensor_location,
            "timestamp": datetime.utcnow().isoformat(),
        })

    return JSONResponse({
        "audio_result": audio_result,
        "fusion_result": fusion_result,
        "recommendation": recommendation,
        "history": get_history(palm_id),
        "location": saved_location,
        "sensor_location": sensor_location,
        "needs_attention": fusion_result["final_class"] in ALERT_LEVELS,
        "reading_id": reading_id,
    })


@app.get("/device/status")
def device_status():
    """آخر قراءة وصلت من جهاز المستشعرات (أو null إن لم تصل أي قراءة منذ تشغيل الخادم)."""
    return JSONResponse({"last": dict(LAST_DEVICE) if LAST_DEVICE else None})


@app.get("/palms/{palm_id}/sensor-location")
def palm_sensor_location(palm_id: str):
    """آخر موقع لمصدر الاهتزاز على جذع النخلة قدّرته الحساسات الثلاثة (أو null)، مع وقته."""
    return JSONResponse(get_latest(palm_id))


@app.post("/estimate-age-health")
async def estimate_age_health(photo: UploadFile = File(...)):
    """
    ترفع صورة عادية للنخلة (مو تسجيل صوتي) -> Gemini Vision يقدّر عمرها
    التقريبي (من طول/سمك الجذع وكثافة السعف) ويفحص علامات إجهاد/جفاف
    بصرية بسيطة - كل هذا بدون أي حساس إضافي، بس من نفس الكاميرا.
    """
    photo_bytes = await photo.read()
    mime_type = photo.content_type or "image/jpeg"
    result = await estimate_age_and_health_from_image(photo_bytes, mime_type)
    if result is None:
        return JSONResponse(
            {"error": "Could not estimate from this photo right now. You can enter the age manually instead."},
            status_code=200,
        )
    return JSONResponse(result)


@app.post("/locate-signs")
async def locate_signs(photo: UploadFile = File(...), language: str = Form("ar"), verify: str = Form("0")):
    """
    ترفع صورة لجذع النخلة -> Gemini Vision يعلّم العلامات الخارجية الظاهرة التي تستحق الفحص
    (فتحات، إفرازات، نشارة ألياف، تلف السعف) مع مواضعها على الصورة وعلى الجذع.
    لا يحدد مواضع اليرقات داخل الجذع، ولا يقترح مبيدًا ولا جرعة ولا مواضع حقن (انظر locate.py).
    """
    photo_bytes = await photo.read()
    if len(photo_bytes) > 8 * 1024 * 1024:
        return JSONResponse({"error": "Photo is too large (max 8 MB)."}, status_code=200)
    mime_type = photo.content_type or "image/jpeg"
    if not mime_type.startswith("image/"):
        return JSONResponse({"error": "Please upload an image file."}, status_code=200)
    result = await locate_signs_from_image(photo_bytes, mime_type, language if language in ("ar", "en", "ur") else "ar", verify=(verify == "1"))
    if result is None:
        return JSONResponse({"error": "Could not analyze this photo right now (check the Gemini connection)."}, status_code=200)
    return JSONResponse(result)


@app.get("/history/{palm_id}")
def history(palm_id: str):
    return {"palm_id": palm_id, "readings": get_history(palm_id)}


@app.get("/palms")
def palms():
    """سجل كل النخيل المسجّلة مع موقعها وعمرها وآخر حالة فحص - قائمة سهلة
    يستخدمها المزارع لتتبع نخيله كلها بنظرة وحدة."""
    return {"palms": list_palms()}


@app.get("/palms/{palm_id}")
def palm_detail_route(palm_id: str):
    """تفاصيل نخلة واحدة كاملة (موقع، عمر، تاريخ كل الفحوصات) - هذي
    نقطة النهاية اللي تفتحها صفحة palm.html، وهي نفس الصفحة اللي يشير
    لها رمز QR الخاص بكل نخلة بسجل النخيل."""
    result = get_palm_details(palm_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result


@app.get("/palms/due-for-recheck")
def palms_due_for_recheck_route():
    """النخيل اللي تحتاج فحصًا دوريًا (ما انفحصت من 30 يوم أو أكثر) -
    تذكير وقائي عام، مو تنبؤًا بموسم مرض معيّن."""
    return {"palms": palms_due_for_recheck(), "threshold_days": RECHECK_DUE_DAYS}


@app.post("/confirm-reading")
async def confirm_reading_route(
    reading_id: int = Form(...),
    confirmed: str = Form(...),  # "correct" أو "incorrect"
):
    """تأكيد المزارع على نتيجة فحص معيّن - يبني بيانات ملاحظات حقيقية
    بمرور الوقت (إعادة التدريب على هذي البيانات عمل مستقبلي منفصل)."""
    if confirmed not in ("correct", "incorrect"):
        return JSONResponse({"error": "confirmed must be 'correct' or 'incorrect'"}, status_code=400)
    set_reading_confirmation(reading_id, confirmed)
    return {"status": "ok", "reading_id": reading_id, "confirmed": confirmed}


@app.get("/farm-contact")
def farm_contact_route():
    """جهة الاتصال الاحتياطية للمزرعة (null لو ما سُجّلت بعد)."""
    return get_farm_contact() or {"contact_name": None, "contact_phone": None}


@app.post("/farm-contact")
async def set_farm_contact_route(
    contact_name: str = Form(...),
    contact_phone: str = Form(...),
):
    """يسجّل/يحدّث جهة الاتصال الاحتياطية - تبان بكل تنبيه خطر مستقبلي،
    عشان لو صاحب المزرعة مو متوفر (مسافر مثلًا) فيه شخص ثاني يتواصلون
    معه يروح يعالج النخلة."""
    set_farm_contact(contact_name, contact_phone)
    return {"status": "ok", "contact_name": contact_name, "contact_phone": contact_phone}


# ---------- شبكة المساعدين وطلبات الزيارة ----------
# فكرة الميزة: إذا كان صاحب النخلة بعيدًا عن المزرعة وجاءه تنبيه، يقدر يطلب من
# مزارع مسجّل في المنطقة أن يزور النخلة. النظام نموذج أولي: المساعدون هم من سجّلوا
# أنفسهم فقط، ولا نضمن وجود أحد في كل منطقة ولا زمن الاستجابة.
# الخصوصية: رقم المساعد لا يظهر علنًا، ولا يصل لصاحب الطلب إلا بعد أن يقبل الطلب؛
# ورقم صاحب الطلب لا يظهر إلا للمساعدين المسجّلين.

def _clean_phone(raw: str) -> str:
    keep = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == "+")
    digits = "".join(ch for ch in keep if ch.isdigit())
    return keep if 7 <= len(digits) <= 15 else ""


def _clean_text(raw, limit: int) -> str:
    return " ".join((raw or "").split())[:limit]


VISIT_WHEN = {"urgent", "3days", "week", "flexible"}
VISIT_PURPOSE = {"inspect", "treat", "remove", "other"}


def _clean_coords(raw) -> str:
    """إحداثيات اختيارية بصيغة lat,lon؛ أي شيء آخر يُهمل."""
    s = "".join((raw or "").split())
    parts = s.split(",")
    if len(parts) != 2:
        return ""
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return ""
    return f"{lat:.5f},{lon:.5f}" if -90 <= lat <= 90 and -180 <= lon <= 180 else ""


def _phone_key(phone: str) -> str:
    """مفتاح مقارنة: الأرقام فقط، وآخر 9 أرقام (يتجاوز اختلاف 05.. و +9665..)."""
    return "".join(ch for ch in phone if ch.isdigit())[-9:]


def _find_helper_by_phone(phone: str):
    key = _phone_key(phone)
    if len(key) < 7:
        return None
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, name, phone, area FROM helpers").fetchall()
    conn.close()
    for r in rows:
        if _phone_key(r[2]) == key:
            return {"id": r[0], "name": r[1], "phone": r[2], "area": r[3]}
    return None


@app.post("/helpers")
async def register_helper(
    name: str = Form(...),
    phone: str = Form(...),
    area: str = Form(...),
    note: Optional[str] = Form(None),
    consent: str = Form(...),
):
    """مزارع/عامل يسجّل نفسه ليستقبل طلبات زيارة النخيل في منطقته."""
    if consent != "yes":
        return JSONResponse({"error": "consent_required"}, status_code=400)
    name, area, note = _clean_text(name, 60), _clean_text(area, 80), _clean_text(note, 160)
    phone = _clean_phone(phone)
    if not name or not area or not phone:
        return JSONResponse({"error": "invalid_input"}, status_code=400)
    existing = _find_helper_by_phone(phone)
    conn = sqlite3.connect(DB_PATH)
    if existing:
        conn.execute("UPDATE helpers SET name=?, area=?, note=? WHERE id=?", (name, area, note, existing["id"]))
        status = "updated"
    else:
        conn.execute(
            "INSERT INTO helpers (name, phone, area, note, created_at) VALUES (?,?,?,?,?)",
            (name, phone, area, note, datetime.utcnow().isoformat()),
        )
        status = "created"
    conn.commit()
    conn.close()
    return {"status": status}


@app.get("/helpers/count")
def helpers_count():
    """عدد المساعدين المسجّلين فعليًا (يبدأ من صفر) مع المناطق التي سجّلوها."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT area FROM helpers").fetchall()
    conn.close()
    areas = collections.Counter(r[0] for r in rows)
    return {"count": len(rows), "areas": [{"area": a, "count": c} for a, c in areas.most_common(30)]}


@app.get("/helpers")
def helpers_public(area: Optional[str] = None):
    """قائمة عامة بدون أرقام هواتف: الاسم والمنطقة والملاحظة فقط."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT name, area, note FROM helpers ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    items = [{"name": r[0], "area": r[1], "note": r[2]} for r in rows]
    if area:
        a = _clean_text(area, 80).lower()
        items = [i for i in items if a in i["area"].lower()]
    return {"helpers": items}


@app.post("/visit-requests")
async def create_visit_request(
    area: str = Form(...),
    requester_name: str = Form(...),
    requester_phone: str = Form(...),
    palm_id: Optional[str] = Form(None),
    details: Optional[str] = Form(None),
    severity: Optional[str] = Form(None),
    when_needed: Optional[str] = Form(None),
    purpose: Optional[str] = Form(None),
    coords: Optional[str] = Form(None),
    consent: str = Form(...),
):
    """صاحب نخلة بعيد عن المزرعة يطلب أن يزورها مساعد مسجّل في المنطقة."""
    if consent != "yes":
        return JSONResponse({"error": "consent_required"}, status_code=400)
    area, requester_name = _clean_text(area, 80), _clean_text(requester_name, 60)
    palm_id, details, severity = _clean_text(palm_id, 60), _clean_text(details, 300), _clean_text(severity, 20)
    phone = _clean_phone(requester_phone)
    when_needed = when_needed if when_needed in VISIT_WHEN else ""
    purpose = purpose if purpose in VISIT_PURPOSE else ""
    coords = _clean_coords(coords)
    if not area or not requester_name or not phone:
        return JSONResponse({"error": "invalid_input"}, status_code=400)
    conn = sqlite3.connect(DB_PATH)
    open_n = conn.execute(
        "SELECT COUNT(*) FROM visit_requests WHERE requester_phone=? AND status='open'", (phone,)
    ).fetchone()[0]
    if open_n >= 5:
        conn.close()
        return JSONResponse({"error": "too_many_open_requests"}, status_code=429)
    cur = conn.execute(
        "INSERT INTO visit_requests (palm_id, area, details, severity, requester_name, requester_phone, created_at, "
        "when_needed, purpose, coords) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (palm_id, area, details, severity, requester_name, phone, datetime.utcnow().isoformat(),
         when_needed, purpose, coords),
    )
    conn.commit()
    req_id = cur.lastrowid
    conn.close()
    return {"status": "ok", "id": req_id, "registered_helpers": helpers_count()["count"]}


@app.get("/visit-requests")
def list_visit_requests(phone: str):
    """للمساعدين المسجّلين فقط (يُتحقق برقم الجوال المسجّل): الطلبات المفتوحة مع رقم صاحب الطلب."""
    helper = _find_helper_by_phone(phone)
    if not helper:
        return JSONResponse({"error": "not_a_registered_helper"}, status_code=403)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, palm_id, area, details, severity, requester_name, requester_phone, created_at, "
        "when_needed, purpose, coords FROM visit_requests WHERE status='open' ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    keys = ["id", "palm_id", "area", "details", "severity", "requester_name", "requester_phone", "created_at",
            "when_needed", "purpose", "coords"]
    return {"helper": {"name": helper["name"], "area": helper["area"]}, "requests": [dict(zip(keys, r)) for r in rows]}


@app.post("/visit-requests/{req_id}/accept")
async def accept_visit_request(req_id: int, helper_phone: str = Form(...)):
    """المساعد يقبل طلبًا مفتوحًا؛ بعدها يرى صاحب الطلب اسم المساعد ورقمه."""
    helper = _find_helper_by_phone(helper_phone)
    if not helper:
        return JSONResponse({"error": "not_a_registered_helper"}, status_code=403)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT status FROM visit_requests WHERE id=?", (req_id,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "not_found"}, status_code=404)
    if row[0] != "open":
        conn.close()
        return JSONResponse({"error": "already_taken"}, status_code=409)
    conn.execute(
        "UPDATE visit_requests SET status='accepted', helper_id=?, accepted_at=? WHERE id=? AND status='open'",
        (helper["id"], datetime.utcnow().isoformat(), req_id),
    )
    conn.commit()
    conn.close()
    return {"status": "accepted", "id": req_id}


@app.get("/visit-requests/mine")
def my_visit_requests(phone: str):
    """صاحب الطلب يتابع طلباته برقم جواله؛ يظهر رقم المساعد فقط بعد قبوله."""
    key = _phone_key(phone)
    if len(key) < 7:
        return JSONResponse({"error": "invalid_input"}, status_code=400)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT r.id, r.palm_id, r.area, r.details, r.status, r.created_at, r.requester_phone, h.name, h.phone, "
        "r.when_needed, r.purpose "
        "FROM visit_requests r LEFT JOIN helpers h ON h.id = r.helper_id ORDER BY r.id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        if _phone_key(r[6]) != key:
            continue
        item = {"id": r[0], "palm_id": r[1], "area": r[2], "details": r[3], "status": r[4], "created_at": r[5],
                "when_needed": r[9], "purpose": r[10]}
        if r[4] == "accepted":
            item["helper"] = {"name": r[7], "phone": r[8]}
        out.append(item)
    return {"requests": out[:20]}


@app.post("/palms")
async def register_palm(
    palm_id: str = Form(...),
    location: str = Form(...),
    notes: Optional[str] = Form(None),
    age_years: Optional[int] = Form(None),
):
    """تسجيل نخلة جديدة بموقعها مسبقًا (قبل أول فحص لها)، أو تحديث موقع نخلة موجودة."""
    upsert_palm(palm_id, location=location, notes=notes, age_years=age_years)
    return {"status": "ok", "palm_id": palm_id, "location": location}


# الأدوات الحقيقية اللي الوكيل الذكي يقدر يستدعيها - نفس أسماء
# TOOLS المعرّفة بـ agent.py بالضبط
AGENT_TOOL_EXECUTOR = {
    "list_palms": lambda: list_palms(),
    "get_palm_details": lambda palm_id: get_palm_details(palm_id),
    "palms_needing_attention": lambda: palms_needing_attention(),
    "palms_due_for_recheck": lambda: palms_due_for_recheck(),
    "get_farm_contact": lambda: (get_farm_contact() or {"status": "no backup contact registered yet"}),
}


@app.post("/agent/chat")
async def agent_chat(message: str = Form(...), history: Optional[str] = Form(None), language: str = Form("en")):
    """
    وكيل ذكاء اصطناعي (Agentic AI): يجاوب أسئلة المزارع عن نخيله باستدعاء
    أدوات حقيقية على قاعدة البيانات بنفسه - انظري agent.py للحلقة الكاملة.
    """
    parsed_history = json.loads(history) if history else []
    result = await run_agent(message, AGENT_TOOL_EXECUTOR, parsed_history, language=language)
    return JSONResponse(result)


if __name__ == "__main__":
    import uvicorn
    # Render (وخدمات الاستضافة المشابهة) تحدد رقم المنفذ تلقائيًا عبر
    # متغير بيئة PORT - نستخدمه لو موجود، وإلا نرجع للمنفذ 8000 للتشغيل المحلي
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

"""
جسر الاتصال بين Arduino والسيرفر - مشروع "نخلة"
================================================
يشتغل على الكمبيوتر المتصل بـ Arduino عبر USB:
1. يقرأ عينات الصوت المرسلة من nakhla_sensor_uno.ino عبر Serial
2. يبنيها كملف WAV
3. يرسله لسيرفر FastAPI (/predict-full) ويطبع النتيجة

الاستخدام:
    pip install pyserial requests numpy scipy
    python serial_bridge.py             # يكتشف منفذ الأردوينو تلقائيًا إن كان واحدًا
    python serial_bridge.py COM3        # على ويندوز
    python serial_bridge.py /dev/ttyUSB0  # على لينكس/ماك

عند التشغيل يسألك عن رابط موقعك على Render ومفتاح الجهاز (لا يُحفظ في أي ملف).
أو ضعهما مسبقًا بمتغيرين: NAKHLA_SERVER_URL و NAKHLA_KEY

اضغطي زر الفحص المتصل بـ Arduino (أو اكتبي R بالمنفذ التسلسلي)
لبدء تسجيل جديد.
"""
import os
import sys
import time
import getpass
import numpy as np
import requests
import serial
from scipy.io import wavfile

SAMPLE_RATE = 4000  # يجب أن يطابق SAMPLE_RATE بملف الأردوينو وfeatures.py
BAUD = 250000       # يجب أن يطابق Serial.begin بملف الأردوينو
# عنوان الموقع ومفتاح الجهاز: من متغيري البيئة، وإلا يسألك عنهما البرنامج عند التشغيل
BASE_URL = os.environ.get("NAKHLA_SERVER_URL", "").strip()
# مفتاح الجهاز (نفس المفتاح داخل الباركود): الموقع لا يقبل قراءات الجهاز بدونه
DEVICE_KEY = os.environ.get("NAKHLA_KEY", "").strip()
REQUEST_TIMEOUT = 120   # الموقع المجاني على Render قد يحتاج دقيقة ليصحو، والتحليل بالذكاء الاصطناعي يأخذ وقتًا
DEFAULT_PALM_ID = "Palm-A12"  # يستخدم بس لو ضغطتِ Enter بدون كتابة رقم جديد


def read_one_recording(ser):
    """يقرأ تسجيل واحد كامل بين إشارتي START و END من Arduino."""
    samples = []
    print("في انتظار بدء التسجيل (يرسل الجسر الأمر تلقائيًا؛ وزر D2 اختياري)...")
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if line == "START":
            print("جارٍ استقبال العينات...")
            samples = []
        elif line == "END":
            # الأردوينو يطبع بعدها ELAPSED_MS,<ملّي ثانية>: زمن التسجيل الفعلي
            elapsed = None
            nxt = ser.readline().decode(errors="ignore").strip()
            if nxt.startswith("ELAPSED_MS,"):
                try: elapsed = int(nxt.split(",")[1])
                except ValueError: pass
            print(f"اكتمل التسجيل: {len(samples)} عينة" + (f" خلال {elapsed / 1000:.2f} ثانية" if elapsed else ""))
            return np.array(samples, dtype=np.float32), elapsed
        elif line.isdigit() or (line.startswith("-") and line[1:].isdigit()):
            samples.append(int(line))


def fix_rate(samples, elapsed_ms):
    """لو المعدل الفعلي يختلف عن 4000 عينة/ثانية بأكثر من 5% نعيد أخذ العينات على الزمن الحقيقي، حتى لا تتشوّه الترددات."""
    n = len(samples)
    if not elapsed_ms or n < 2:
        return samples
    actual = n / (elapsed_ms / 1000.0)
    if abs(actual - SAMPLE_RATE) / SAMPLE_RATE > 0.05:
        print(f"تنبيه: المعدل الفعلي {actual:.0f} عينة/ثانية (المطلوب {SAMPLE_RATE}). صحّحته بإعادة أخذ العينات.")
        dur = elapsed_ms / 1000.0
        t_old = np.linspace(0, dur, n, endpoint=False)
        t_new = np.arange(int(round(dur * SAMPLE_RATE))) / SAMPLE_RATE
        samples = np.interp(t_new, t_old, samples).astype(np.float32)
    return samples


def samples_to_wav(samples, path):
    # تحويل من مدى ADC (0-1023) إلى موجة موقّعة طبيعية
    centered = samples - np.mean(samples)
    normalized = centered / (np.max(np.abs(centered)) + 1e-9)
    audio_int16 = (normalized * 32767 * 0.9).astype(np.int16)
    wavfile.write(path, SAMPLE_RATE, audio_int16)


def normalize_base(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def wake_server(base):
    """الموقع المجاني ينام بعد فترة خمول؛ نطرقه أولًا ونعطيه وقتًا ليصحو. أي رد (حتى الرفض) يعني أنه صحا."""
    print("جارٍ التأكد أن الموقع يعمل (قد يستغرق حتى دقيقة إن كان نائمًا)...")
    try:
        requests.get(base + "/", timeout=REQUEST_TIMEOUT)
        print("الموقع جاهز.")
        return True
    except requests.exceptions.RequestException as e:
        print("تعذّر الوصول للموقع:", explain_error(e, base))
        return False


def explain_error(e, base):
    """يحوّل الخطأ التقني لسبب مفهوم."""
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        code = e.response.status_code
        if code == 401:
            return "الموقع رفض المفتاح (401). المفتاح خطأ، أو غير مسجّل في Render ضمن NAKHLA_DEVICE_KEYS."
        if code == 429:
            return "الموقع رفض مؤقتًا (429): محاولات كثيرة. انتظر دقيقة، وإن تكرر الخطأ انتظر ١٠ دقائق."
        if code == 413:
            return "الملف أكبر من الحد المسموح (413)."
        if code == 404:
            return "العنوان غير موجود (404). تأكد من رابط الموقع."
        if code >= 500:
            return f"خطأ داخل الموقع ({code}). افتح Logs في Render لترى السبب."
        return f"رفض الموقع الطلب (رمز {code})."
    if isinstance(e, requests.exceptions.Timeout):
        return "الموقع تأخر في الرد. أعد المحاولة بعد قليل."
    if isinstance(e, requests.exceptions.ConnectionError):
        if "localhost" in base or "127.0.0.1" in base:
            return "الرابط يشير إلى جهازك نفسه، وليس إلى موقعك على Render. ضع رابط موقعك."
        return "لا يوجد اتصال بالموقع. تأكد من الإنترنت ومن كتابة الرابط صحيحًا: " + base
    return str(e)


def send_to_server(wav_path, palm_id, base, key):
    url = base + "/predict-full"
    last = None
    for attempt in (1, 2):                      # محاولة ثانية تلقائية لو تأخر الموقع أو انقطع الاتصال لحظة
        try:
            with open(wav_path, "rb") as f:
                files = {"audio": ("recording.wav", f, "audio/wav")}
                data = {"palm_id": palm_id}
                resp = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT,
                                     headers={"X-Nakhla-Key": key} if key else None)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = e
            if attempt == 1:
                print("لم يصل الرد، أعيد المحاولة مرة واحدة...")
                continue
        break
    raise last


def main():
    global BASE_URL, DEVICE_KEY
    if len(sys.argv) >= 2:
        port = sys.argv[1]
    else:
        from serial.tools import list_ports
        found = list(list_ports.comports())
        if len(found) == 1:
            port = found[0].device
            print(f"وجدت منفذًا واحدًا واستخدمته: {port}")
        else:
            print("لم أستطع تحديد منفذ الأردوينو تلقائيًا. المنافذ المتاحة:" if found else "لم أجد أي منفذ. تأكد أن كيبل USB موصول.")
            for p in found:
                print("  -", p.device, p.description)
            print("الاستخدام: python serial_bridge.py <PORT>  مثال: COM3 أو /dev/ttyUSB0")
            sys.exit(1)

    BASE_URL = normalize_base(BASE_URL or input("رابط موقعك على Render (مثل https://xxxx.onrender.com): "))
    if not BASE_URL:
        print("لا بد من رابط الموقع.")
        sys.exit(1)
    if not DEVICE_KEY:
        DEVICE_KEY = getpass.getpass("مفتاح الجهاز (لن يظهر أثناء الكتابة، والصق بزر الفأرة الأيمن): ").strip()
    print(f"الموقع: {BASE_URL}")
    wake_server(BASE_URL)

    ser = serial.Serial(port, BAUD, timeout=2)
    time.sleep(2)  # وقت إعادة تشغيل Arduino بعد فتح المنفذ

    # يحفظ آخر رقم نخلة استُخدم، عشان لو تفحصين نفس النخلة مرتين على التوالي
    # تضغطين Enter بس بدل ما تعيدين كتابة نفس الرقم من جديد
    last_palm_id = DEFAULT_PALM_ID

    while True:
        # لو نقلتِ الحساس لنخلة جديدة، اكتبي رقمها هنا قبل كل تسجيل.
        # لو هي نفس النخلة اللي فحصتيها قبل شوي، بس اضغطي Enter فاضي.
        entered = input(f"\nرقم النخلة الحالية [{last_palm_id}]: ").strip()
        palm_id = entered if entered else last_palm_id
        last_palm_id = palm_id
        ser.reset_input_buffer()
        ser.write(b"R")   # يطلب من الأردوينو بدء تسجيل (ما تحتاجين زرًا)

        samples, elapsed = read_one_recording(ser)
        samples = fix_rate(samples, elapsed)
        if len(samples) < SAMPLE_RATE:  # تسجيل ناقص/فاشل
            print("التسجيل قصير جدًا فتم تجاهله. حاوِل مرة أخرى.")
            continue

        wav_path = "recording_tmp.wav"
        samples_to_wav(samples, wav_path)
        print(f"جارٍ الإرسال إلى الخادم (النخلة: {palm_id})...")
        try:
            result = send_to_server(wav_path, palm_id, BASE_URL, DEVICE_KEY)
            cls = result["fusion_result"]["final_class"]
            print(f"\n>>> النخلة: {palm_id}")
            print(f">>> النتيجة: {cls}")
            print(">>> التوصية:", result["recommendation"], "\n")
        except Exception as e:
            print("فشل الإرسال:", explain_error(e, BASE_URL))
            print("   (التفاصيل التقنية:", type(e).__name__, ")")


if __name__ == "__main__":
    main()

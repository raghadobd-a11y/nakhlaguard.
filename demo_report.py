"""
Treatment report for the public try page: short headings that open into the details, and a one-month plan, week by week.

The AI assistant of NakhlaGuard (named "Haris" / "حارس" on the site; it is Gemini underneath) writes the content as JSON.
The headings are fixed here, so the page always looks the same. If the AI key is missing, the AI is busy, or its answer is
not usable, a ready-made report (the same structure, written by us) is returned and labelled as such, so the demo never
shows an empty or broken report.

General guidance only: no product names, no doses, nothing that replaces the field inspection by a specialist.
"""
import json
import re

STAGES = ("healthy", "early", "moderate", "advanced")

TITLES = {
    "ar": {"today": "ماذا أفعل اليوم؟", "plan": "خطة الشهر، أسبوعًا بأسبوع", "w1": "الأسبوع الأول", "w2": "الأسبوع الثاني", "w3": "الأسبوع الثالث",
           "w4": "الأسبوع الرابع", "watch": "متى أستدعي مختصًا؟",
           "note": "إرشادات عامة وليست وصفة علاج. الحكم النهائي للمختص بعد الفحص الميداني."},
    "en": {"today": "What do I do today?", "plan": "The month plan, week by week", "w1": "Week 1", "w2": "Week 2", "w3": "Week 3", "w4": "Week 4",
           "watch": "When do I call a specialist?",
           "note": "General guidance, not a treatment prescription. The specialist decides after the field inspection."},
    "ur": {"today": "آج کیا کروں؟", "plan": "مہینے کا منصوبہ، ہفتہ بہ ہفتہ", "w1": "پہلا ہفتہ", "w2": "دوسرا ہفتہ", "w3": "تیسرا ہفتہ", "w4": "چوتھا ہفتہ",
           "watch": "ماہر کو کب بلاؤں؟",
           "note": "عمومی رہنمائی ہے، علاج کا نسخہ نہیں۔ میدانی معائنے کے بعد فیصلہ ماہر کرتا ہے۔"},
}

# ---------------------------------------------------------------- ready-made reports (3 groups x 3 languages)
# each: headline per stage, today, four weeks (focus + tasks), watch
_T = {
    "healthy": {
        "ar": {"headline": {"healthy": "لا مؤشرات إصابة في هذا الصوت. خطتك هذا الشهر وقاية ومتابعة."},
               "today": ["سجّل هذا الفحص كقراءة أساس للنخلة: التاريخ والمكان والتسجيل.", "تفقّد الجذع وقلب النخلة بحثًا عن ثقوب أو سائل بني أو نشارة.", "لا تقلّم ولا تجرح النخلة إلا للضرورة: الجروح تجذب السوسة."],
               "weeks": [("خط الأساس", ["افحص النخيل المجاورة بالنظر.", "ثبّت الجهاز في الموضع نفسه في كل فحص حتى تصح المقارنة."]),
                         ("نظافة المزرعة", ["أزل السعف اليابس والمخلفات المتراكمة حول النخيل.", "إن اضطررت للتقليم فاطلب إرشاد مختص لمعالجة مكان القطع."]),
                         ("المصائد والإرشاد", ["اسأل مكتب الإرشاد الزراعي في منطقتك عن مصائد الفرمون وبرنامج المكافحة المحلي.", "اطلب زيارة تفتيش إن ظهرت أي علامة."]),
                         ("إعادة الفحص", ["أعد تسجيل كل نخلة وقارنها بقراءة الأسبوع الأول.", "حدّد موعد الفحص القادم بعد نحو 30 يومًا."])],
               "watch": ["ظهور ثقوب أو سائل بني أو نشارة أو رائحة تخمّر.", "ذبول القلب (السعف الأوسط) أو ميلانه.", "أي نتيجة غير سليمة في فحص لاحق."]},
        "en": {"headline": {"healthy": "No sign of infestation in this sound. Your plan this month is prevention and monitoring."},
               "today": ["Save this check as the palm's baseline: date, place and recording.", "Look at the trunk and the crown for holes, brown fluid or sawdust.", "Do not prune or wound the palm unless you must: wounds attract the weevil."],
               "weeks": [("Baseline", ["Look over the neighbouring palms.", "Place the device in the same spot every time so comparisons are fair."]),
                         ("Keep the farm clean", ["Remove dry fronds and debris piled around the palms.", "If you must prune, ask a specialist how to treat the cut."]),
                         ("Traps and advice", ["Ask your local agricultural extension office about pheromone traps and the local control programme.", "Ask for an inspection visit if any sign appears."]),
                         ("Check again", ["Record each palm again and compare with week 1.", "Set the next check for about 30 days later."])],
               "watch": ["Holes, brown fluid, sawdust or a fermenting smell.", "A wilting or leaning crown (the middle fronds).", "Any result other than healthy in a later check."]},
        "ur": {"headline": {"healthy": "اس آواز میں حملے کی علامت نہیں۔ اس مہینے آپ کا منصوبہ بچاؤ اور نگرانی ہے۔"},
               "today": ["اس جانچ کو کھجور کی بنیادی ریڈنگ کے طور پر محفوظ کریں: تاریخ، جگہ اور ریکارڈنگ۔", "تنے اور چوٹی میں سوراخ، بھورا مائع یا برادہ دیکھیں۔", "بلا ضرورت کھجور کی کٹائی نہ کریں اور اسے زخمی نہ کریں: زخم سنڈی کو کھینچتے ہیں۔"],
               "weeks": [("بنیادی ریڈنگ", ["پاس کی کھجوروں کو غور سے دیکھیں۔", "ہر بار ڈیوائس ایک ہی جگہ لگائیں تاکہ موازنہ درست رہے۔"]),
                         ("باغ کی صفائی", ["کھجوروں کے گرد سوکھے پتے اور کچرا ہٹائیں۔", "کٹائی ضروری ہو تو کٹی جگہ کے علاج کے لیے ماہر سے پوچھیں۔"]),
                         ("پھندے اور مشورہ", ["اپنے علاقے کے زرعی توسیعی دفتر سے فیرومون پھندوں اور مقامی کنٹرول پروگرام کا پوچھیں۔", "کوئی علامت ظاہر ہو تو معائنے کی درخواست کریں۔"]),
                         ("دوبارہ جانچ", ["ہر کھجور دوبارہ ریکارڈ کریں اور پہلے ہفتے سے موازنہ کریں۔", "اگلی جانچ تقریباً 30 دن بعد طے کریں۔"])],
               "watch": ["سوراخ، بھورا مائع، برادہ یا خمیر کی بو۔", "چوٹی (درمیانے پتوں) کا مرجھانا یا جھکنا۔", "بعد کی جانچ میں صحت مند کے علاوہ کوئی نتیجہ۔"]},
    },
    "infested": {
        "ar": {"headline": {"early": "مؤشرات إصابة مبكرة. الأسابيع الأولى هي الأهم: أكّد الإصابة ميدانيًا وابدأ العلاج بسرعة.",
                            "moderate": "إصابة متوسطة محتملة. تحتاج تأكيدًا ميدانيًا وعلاجًا بإشراف مختص خلال أيام."},
               "today": ["علّم النخلة وأبعد عنها كل نشاط غير ضروري.", "اتصل بالمرشد الزراعي أو وزارة البيئة والمياه والزراعة لطلب فحص ميداني.", "لا تقلّم ولا تنقل أي جزء من النخلة أو فسائلها خارج المزرعة."],
               "weeks": [("التأكيد والعزل", ["يؤكد المختص الإصابة ويحدد مداها.", "افحص النخيل المجاورة بالنظر وبالجهاز.", "أعد التسجيل على النخلة مرتين هذا الأسبوع."]),
                         ("العلاج", ["ابدأ العلاج الذي يحدده المختص، ولا تستعمل أي مادة بلا إشراف.", "ينظّف المختص الأنسجة المصابة ويعالج الجروح بالطريقة المناسبة."]),
                         ("المتابعة", ["أعد التسجيل وقارن عدد النبضات بالأسبوع الأول.", "افحص النخيل المجاورة مرة أخرى.", "ثبّت مصائد الفرمون بإرشاد المختص."]),
                         ("التقييم", ["إن انخفض النشاط فاستمر بالمتابعة كل أسبوعين.", "وإن لم ينخفض فاطلب من المختص تقييم إعادة العلاج أو الإزالة.", "دوّن ما فعلته وتواريخه."])],
               "watch": ["زيادة النبضات في فحص لاحق.", "سائل بني أو نشارة أو ثقوب أو ذبول في القلب.", "ظهور أعراض على نخلة مجاورة."]},
        "en": {"headline": {"early": "Early signs of infestation. The first weeks matter most: confirm it in the field and start treatment fast.",
                            "moderate": "A moderate infestation is possible. It needs field confirmation and treatment under a specialist within days."},
               "today": ["Mark the palm and keep unnecessary activity away from it.", "Call the agricultural extension service or the Ministry of Environment, Water and Agriculture to ask for a field inspection.", "Do not prune, and do not move any part of the palm or its offshoots off the farm."],
               "weeks": [("Confirm and contain", ["A specialist confirms the infestation and its extent.", "Check the neighbouring palms by eye and with the device.", "Record this palm twice this week."]),
                         ("Treatment", ["Start the treatment the specialist decides. Do not use any product without supervision.", "The specialist cleans the infested tissue and treats the wounds the right way."]),
                         ("Follow-up", ["Record again and compare the pulse count with week 1.", "Check the neighbouring palms again.", "Set up pheromone traps with the specialist's advice."]),
                         ("Review", ["If activity dropped, keep monitoring every two weeks.", "If it did not, ask the specialist whether to treat again or remove the palm.", "Write down what you did and when."])],
               "watch": ["More pulses in a later check.", "Brown fluid, sawdust, holes or a wilting crown.", "Signs on a neighbouring palm."]},
        "ur": {"headline": {"early": "حملے کی ابتدائی علامات۔ ابتدائی ہفتے سب سے اہم ہیں: میدان میں تصدیق کریں اور جلد علاج شروع کریں۔",
                            "moderate": "درمیانے حملے کا امکان۔ چند دنوں میں میدانی تصدیق اور ماہر کی نگرانی میں علاج چاہیے۔"},
               "today": ["کھجور پر نشان لگائیں اور اس کے پاس غیر ضروری سرگرمی روکیں۔", "زرعی توسیعی سروس یا وزارتِ ماحولیات، پانی و زراعت کو فون کر کے میدانی معائنہ مانگیں۔", "کٹائی نہ کریں اور کھجور یا اس کے پودوں کا کوئی حصہ باغ سے باہر نہ لے جائیں۔"],
               "weeks": [("تصدیق اور علیحدگی", ["ماہر حملے اور اس کی حد کی تصدیق کرتا ہے۔", "پاس کی کھجوروں کو نظر سے اور ڈیوائس سے جانچیں۔", "اس ہفتے اس کھجور کی دو بار ریکارڈنگ کریں۔"]),
                         ("علاج", ["ماہر جو علاج طے کرے وہ شروع کریں، کوئی چیز بغیر نگرانی استعمال نہ کریں۔", "ماہر متاثرہ حصہ صاف کرتا ہے اور زخموں کا صحیح علاج کرتا ہے۔"]),
                         ("فالو اپ", ["دوبارہ ریکارڈ کریں اور پلس کی تعداد پہلے ہفتے سے ملائیں۔", "پاس کی کھجوروں کو دوبارہ جانچیں۔", "ماہر کے مشورے سے فیرومون پھندے لگائیں۔"]),
                         ("جائزہ", ["سرگرمی کم ہوئی ہو تو ہر دو ہفتے بعد نگرانی جاری رکھیں۔", "کم نہ ہوئی ہو تو ماہر سے پوچھیں کہ دوبارہ علاج کریں یا کھجور ہٹائیں۔", "جو کیا اور کب کیا، لکھ لیں۔"])],
               "watch": ["بعد کی جانچ میں پلس زیادہ ہوں۔", "بھورا مائع، برادہ، سوراخ یا چوٹی کا مرجھانا۔", "پاس کی کھجور پر علامات۔"]},
    },
    "advanced": {
        "ar": {"headline": {"advanced": "إصابة متقدمة محتملة. تحتاج تدخلًا عاجلًا: أكّد ميدانيًا خلال أيام وقرّر مع المختص بين العلاج والإزالة."},
               "today": ["اتصل بالمرشد الزراعي أو وزارة البيئة والمياه والزراعة اليوم لطلب فحص عاجل.", "اعزل النخلة وامنع نقل أي جزء منها أو من فسائلها.", "لا تعالجها بنفسك بمواد غير مرخّصة."],
               "weeks": [("التدخل العاجل", ["يفحص المختص النخلة ويقرر: علاج أم إزالة.", "افحص كل النخيل القريبة اليوم أو غدًا.", "دوّن مكان النخلة وتاريخ الفحص."]),
                         ("العلاج أو الإزالة", ["إن أمكن إنقاذها فاتبع خطة المختص للعلاج.", "وإن تقررت الإزالة فتُزال وتُتلف بالطريقة التي يحددها المختص حتى لا تنتشر الحشرة."]),
                         ("حماية النخيل المجاورة", ["افحص النخيل المجاورة بالجهاز وبالنظر.", "ثبّت مصائد الفرمون ونفّذ المعالجة الوقائية التي يوصي بها المختص."]),
                         ("إعادة التقييم", ["قيّم المزرعة كلها وأعد تسجيل النخيل المجاورة.", "لا تزرع بديلًا في المكان قبل مشورة المختص.", "دوّن كل ما تم."])],
               "watch": ["انتشار الأعراض إلى نخلة ثانية.", "سقوط القلب أو ميلان الجذع: خطر على من حولها.", "تأخر وصول المختص: أعد الاتصال ولا تنتظر."]},
        "en": {"headline": {"advanced": "An advanced infestation is possible. It needs urgent action: confirm in the field within days and decide with a specialist between treatment and removal."},
               "today": ["Call the agricultural extension service or the Ministry of Environment, Water and Agriculture today and ask for an urgent inspection.", "Isolate the palm and do not move any part of it or its offshoots.", "Do not treat it yourself with unlicensed products."],
               "weeks": [("Urgent action", ["A specialist inspects the palm and decides: treat or remove.", "Check all the nearby palms today or tomorrow.", "Write down the palm's place and the date of the inspection."]),
                         ("Treat or remove", ["If it can be saved, follow the specialist's treatment plan.", "If removal is decided, it is removed and destroyed the way the specialist says, so the insect does not spread."]),
                         ("Protect the neighbours", ["Check the neighbouring palms with the device and by eye.", "Set up pheromone traps and do the preventive treatment the specialist recommends."]),
                         ("Review", ["Review the whole farm and record the neighbouring palms again.", "Do not replant in that spot before asking the specialist.", "Write down everything that was done."])],
               "watch": ["Signs spreading to a second palm.", "A falling crown or a leaning trunk: a danger to people nearby.", "The specialist is late: call again and do not wait."]},
        "ur": {"headline": {"advanced": "شدید حملے کا امکان۔ فوری کارروائی چاہیے: چند دنوں میں میدان میں تصدیق کریں اور ماہر کے ساتھ علاج یا ہٹانے کا فیصلہ کریں۔"},
               "today": ["آج ہی زرعی توسیعی سروس یا وزارتِ ماحولیات، پانی و زراعت کو فون کر کے فوری معائنہ مانگیں۔", "کھجور کو الگ کریں اور اس کا یا اس کے پودوں کا کوئی حصہ منتقل نہ کریں۔", "غیر منظور شدہ چیزوں سے خود علاج نہ کریں۔"],
               "weeks": [("فوری کارروائی", ["ماہر کھجور کا معائنہ کر کے فیصلہ کرتا ہے: علاج یا ہٹانا۔", "قریب کی تمام کھجوریں آج یا کل جانچیں۔", "کھجور کی جگہ اور معائنے کی تاریخ لکھ لیں۔"]),
                         ("علاج یا ہٹانا", ["بچائی جا سکتی ہو تو ماہر کے علاج کے منصوبے پر چلیں۔", "ہٹانا طے ہو تو ماہر کے بتائے طریقے سے ہٹا کر ختم کریں تاکہ کیڑا نہ پھیلے۔"]),
                         ("پاس کی کھجوروں کا تحفظ", ["پاس کی کھجوریں ڈیوائس سے اور نظر سے جانچیں۔", "فیرومون پھندے لگائیں اور ماہر کا بتایا احتیاطی علاج کریں۔"]),
                         ("جائزہ", ["پورے باغ کا جائزہ لیں اور پاس کی کھجوریں دوبارہ ریکارڈ کریں۔", "ماہر سے پوچھے بغیر اس جگہ نیا پودا نہ لگائیں۔", "جو کچھ ہوا لکھ لیں۔"])],
               "watch": ["علامات دوسری کھجور تک پھیلنا۔", "چوٹی کا گرنا یا تنے کا جھکنا: قریب کے لوگوں کے لیے خطرہ۔", "ماہر دیر کرے تو دوبارہ فون کریں، انتظار نہ کریں۔"]},
    },
}

AI_NAME = {"ar": "حارس", "en": "Haris", "ur": "حارس"}


def _group(stage):
    return "healthy" if stage == "healthy" else ("advanced" if stage == "advanced" else "infested")


def _cards(language, today, weeks, watch):
    t = TITLES[language]
    cards = [{"id": "today", "title": t["today"], "items": today}]
    for i, (focus, tasks) in enumerate(weeks, 1):
        cards.append({"id": f"w{i}", "group": "plan", "title": t[f"w{i}"], "focus": focus, "items": tasks})
    cards.append({"id": "watch", "title": t["watch"], "items": watch})
    return cards


def template_report(stage, language):
    language = language if language in TITLES else "en"
    stage = stage if stage in STAGES else "healthy"
    c = _T[_group(stage)][language]
    return {"source": "template", "ai_name": AI_NAME[language], "headline": c["headline"].get(stage) or next(iter(c["headline"].values())),
            "plan_title": TITLES[language]["plan"], "cards": _cards(language, c["today"], c["weeks"], c["watch"]), "note": TITLES[language]["note"]}


# ---------------------------------------------------------------- the AI version
_LANG_NAME = {"ar": "Arabic", "en": "English", "ur": "Urdu"}


def build_prompt(stage, risk, evidence, language):
    lang = _LANG_NAME.get(language, "English")
    system = (
        "You are Haris, the assistant of NakhlaGuard, a prototype that listens to a date palm's trunk to look for red palm weevil larvae. "
        f"Write for a farmer in {lang}. Answer with ONE JSON object and nothing else, with exactly these keys: "
        '"headline" (one sentence, max 160 characters), '
        '"today" (2 to 4 short action sentences), '
        '"weeks" (exactly 4 objects, week 1 to week 4, each {"focus": 2 to 4 words, "tasks": 2 to 4 short action sentences}), '
        '"call_expert" (2 to 4 short warning signs that mean call a specialist). '
        "Every sentence is at most 150 characters. Plan one month, week by week, in a sensible order (confirm, treat, follow up, review). "
        "General guidance only: never name pesticide brands, never give doses, never promise a cure. Always leave the confirmation and the treatment decision to a specialist "
        "(the agricultural extension service or the Ministry of Environment, Water and Agriculture). "
        "The result came from a model trained on simulated recordings, so say the farmer must confirm in the field. "
        "Say 'palm', never 'tree'. No markdown, no emojis."
    )
    ev = evidence or {}
    user = (f"Result: stage = {stage}"
            + (f", risk = {round(float(risk) * 100)}%" if risk is not None else "")
            + f". Short pulses heard: {ev.get('pulses', 'unknown')} in {ev.get('duration_s', 'unknown')} s. "
              "Write the report.")
    return system, user


def _clean_list(v, lo, hi, maxlen=170):
    if not isinstance(v, list):
        return None
    out = []
    for x in v:
        if isinstance(x, str) and x.strip():
            out.append(re.sub(r"\s+", " ", x.strip())[:maxlen])
    return out[:hi] if len(out) >= lo else None


def parse_ai_json(text):
    """Returns (headline, today, weeks[(focus, tasks)], watch) or None if the answer is not usable."""
    if not isinstance(text, str):
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    headline = d.get("headline")
    today = _clean_list(d.get("today"), 2, 5)
    watch = _clean_list(d.get("call_expert"), 2, 5)
    weeks_raw = d.get("weeks")
    if not (isinstance(headline, str) and headline.strip() and today and watch and isinstance(weeks_raw, list) and len(weeks_raw) >= 4):
        return None
    weeks = []
    for w in weeks_raw[:4]:
        if not isinstance(w, dict) or not isinstance(w.get("focus"), str):
            return None
        tasks = _clean_list(w.get("tasks"), 1, 5)
        if not tasks:
            return None
        weeks.append((re.sub(r"\s+", " ", w["focus"].strip())[:60], tasks))
    return re.sub(r"\s+", " ", headline.strip())[:200], today, weeks, watch


async def make_report(stage, risk, evidence, language, ask_ai):
    """ask_ai(system, user) -> text (async). It may raise or return None; then the ready-made report is used.
    Returns the dict the page renders; "source" says "ai" or "template"."""
    language = language if language in TITLES else "en"
    base = template_report(stage, language)
    if ask_ai is None:
        return base
    system, user = build_prompt(stage, risk, evidence, language)
    try:
        parsed = parse_ai_json(await ask_ai(system, user))
    except Exception as e:
        print(f"[NakhlaGuard demo] AI report failed: {type(e).__name__}: {e}")
        parsed = None
    if not parsed:
        return base
    headline, today, weeks, watch = parsed
    return {"source": "ai", "ai_name": AI_NAME[language], "headline": headline, "plan_title": TITLES[language]["plan"],
            "cards": _cards(language, today, weeks, watch), "note": TITLES[language]["note"]}

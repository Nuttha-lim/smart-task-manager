import os
import json
import datetime
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# เดิมสร้าง client ตอน import → แอปตายถ้ายังไม่ตั้ง GROQ_API_KEY (Render ตั้งทีหลังได้)
# เก็บชื่อ `client` ไว้ให้เทสต์ที่ monkeypatch ตัวนี้ยังใช้ได้ แต่สร้างแบบ lazy ตอนเรียกจริง
client = None


def _get_client():
    """คืน Groq client (สร้างครั้งแรกตอนเรียกเท่านั้น) — กันแอป crash ตอน import"""
    global client
    if client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY ไม่ได้ตั้งค่าใน environment")
        client = Groq(api_key=key)
    return client


def parse_tasks_text(user_input: str, today: datetime.date = None):
    """แปลงข้อความ → รายการงาน (JSON array) — AI แยกให้เองว่าข้อความเดียวอาจมีหลายงาน

    แต่ละรายการ: {title, estimated_time, deadline, deadline_time}
    ถ้า AI คืน object เดียว (พลาด) ให้ห่อเป็น array กัน crash"""
    if today is None:
        today = datetime.date.today()
    weekday_names = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']

    # สร้างตารางวันที่ล่วงหน้า 14 วัน ให้ AI เลือกแทนการคำนวณเอง
    # (AGENTS.md gotcha #2: LLM คำนวณวันที่เองไม่แม่น)
    date_table_lines = []
    for i in range(14):
        d = today + datetime.timedelta(days=i)
        wd = weekday_names[d.weekday()]
        label = "วันนี้" if i == 0 else ("พรุ่งนี้" if i == 1 else ("มะรืนนี้" if i == 2 else ""))
        date_table_lines.append(f"{d.isoformat()} = วัน{wd}" + (f" ({label})" if label else ""))
    date_table = "\n".join(date_table_lines)

    prompt = f"""วันนี้คือวันที่ {today.isoformat()}

ตารางวันที่ล่วงหน้าสำหรับอ้างอิง (ห้ามคำนวณเอง ให้เลือกจากตารางนี้เท่านั้น):
{date_table}

แปลงข้อความต่อไปนี้เป็น JSON array ของงานทั้งหมดที่ผู้ใช้พูดถึง
ข้อความเดียวอาจมีหลายงาน ให้แยกออกมาให้ครบทุกงาน

แต่ละรายการมี field: title, estimated_time (นาที), deadline, deadline_time
- title: ชื่องานสั้น ๆ ภาษาไทย
- deadline ต้องเป็นรูปแบบ YYYY-MM-DD เท่านั้น โดยเลือกวันที่จากตารางด้านบนให้ตรงกับที่ข้อความระบุ ถ้าหาไม่ได้ให้ใส่ null
- deadline_time ต้องเป็นรูปแบบ HH:MM (24 ชั่วโมง) แปลจากคำบอกช่วงเวลาในข้อความ เช่น "ตอนเช้า"=09:00, "ก่อนเที่ยง"=12:00, "ตอนบ่าย"=13:00, "เย็นๆ"=17:00, "ตอนค่ำ"=19:00, "กลางคืน"=21:00 ถ้าข้อความระบุเวลาชัดเจน (เช่น "บ่ายโมง") ให้แปลงเป็น HH:MM ตรงๆ ถ้าไม่มีคำใบ้เรื่องเวลาเลย ให้ใส่ null
- estimated_time: นาที ถ้าข้อความไม่บอกให้ใส่ null
ตอบเป็น JSON array เท่านั้น ห้ามมีข้อความอื่น เช่น [{{"title": "งานที่ 1", "estimated_time": 30, ...}}, {{"title": "งานที่ 2", ...}}]

ข้อความ: "{user_input}"
"""
    response = _get_client().chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content.strip()
    try:
        parsed = _parse_json(text)
    except Exception:
        return []
    if isinstance(parsed, list):
        return [p for p in parsed if isinstance(p, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def parse_task_text(user_input: str, today: datetime.date = None):
    """compat เดิม: คืนงานตัวแรกของ parse_tasks_text (หน้าเก่าที่คาดว่าได้ object เดียว)"""
    tasks = parse_tasks_text(user_input, today)
    return tasks[0] if tasks else {}


def decompose_goal(goal_title: str):
    prompt = f"""แตกเป้าหมายต่อไปนี้เป็นงานย่อย 4-7 ข้อที่ทำได้จริง เรียงลำดับตามที่ควรทำก่อน-หลัง
ตอบเป็น JSON array ของ object เช่น [{{"title": "งานย่อยที่ 1", "estimated_time": 30}}, {{"title": "งานย่อยที่ 2", "estimated_time": 45}}]
- title: งานย่อยภาษาไทย
- estimated_time: นาทีโดยประมาณที่คาดว่าต้องใช้ ถ้าเดาไม่ออกให้ใส่ null (ค่านี้ใช้จัดตารางเตรียมสอบ)
ห้ามมีข้อความอื่นนอกเหนือจาก JSON array

เป้าหมาย: "{goal_title}"
"""
    response = _get_client().chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.choices[0].message.content.strip()
    return _parse_json(text)


def normalize_subtasks(raw):
    """ทำรายการงานย่อยให้เป็นรูปแบบเดียวกัน → [{"title": str, "estimated_time": int|None}]

    รับได้ทั้ง string, dict {title, estimated_time} และ list ปนกัน (AI หรือผู้ใช้ส่งมา)
    — กรองข้อว่าง + ตัวเลขเพี้ยนทิ้ง ไม่ crash (หลัก §9)
    """
    if isinstance(raw, dict):
        if isinstance(raw.get("tasks"), list):
            raw = raw["tasks"]
        else:
            raw = [raw]
    if not isinstance(raw, list):
        return []

    out = []
    for item in raw:
        if isinstance(item, str):
            title, est = item.strip(), None
        elif isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            est = item.get("estimated_time")
        else:
            continue
        if not title:
            continue
        if est is not None:
            try:
                est = int(est)
                if est <= 0:
                    est = None
            except Exception:
                est = None
        out.append({"title": title, "estimated_time": est})
    return out


def assess_breakdown(tasks):
    """ประเมินว่าการแตกเป้าหมายเป็นงานย่อย "พอไหม" และมีตรงไหนต้องแก้

    เป็น deterministic heuristic (ไม่เรียก AI) หลัก conservative: ติเฉพาะที่ชัดเจน
    เพื่อไม่รบกวนรายการที่โอเคอยู่แล้ว (AGENTS.md: ช่วยไม่กดดัน)

    คืน dict: {
        "verdict": "good" | "needs_review",
        "issues": [{"index": int, "type": str, "message": str}],  # ต้องแก้ต่อข้อ
        "warnings": [str],                                        # ข้อควรพิจารณารวม
        "summary": str,
    }
    """
    cleaned = [t.strip() for t in tasks if isinstance(t, str) and t.strip()]

    issues = []
    for i, t in enumerate(cleaned):
        if len(t) < 3:
            issues.append({
                "index": i, "type": "too_short",
                "message": f"ข้อนี้สั้นเกินไป ({len(t)} ตัวอักษร) — อาจไม่ใช่งานที่ทำได้จริง ลองเขียนให้ชัดขึ้น",
            })
        if len(t) > 60:
            issues.append({
                "index": i, "type": "too_long",
                "message": f"ข้อนี้ยาวเกินไป ({len(t)} ตัวอักษร) — ลองแบ่งเป็นหลายงานย่อย",
            })
        for j in range(i):
            if cleaned[j] and cleaned[j].lower() == t.lower():
                issues.append({
                    "index": i, "type": "duplicate",
                    "message": f"ซ้ำกับข้อ {j + 1} — ลบข้อหนึ่งทิ้ง",
                })
                break

    warnings = []
    n = len(cleaned)
    if n < 3:
        warnings.append(f"แตกมาน้อยไป ({n} ข้อ) — ลองให้ AI แตกเพิ่ม หรือเพิ่มงานย่อยเอง")
    if n > 7:
        warnings.append(f"แตกมาเยอะไป ({n} ข้อ) — ลองรวมข้อที่ใกล้กันเข้าด้วยกัน")

    verdict = "good" if (not issues and not warnings) else "needs_review"
    if verdict == "good":
        summary = f"แตกงานย่อยมา {n} ข้อ ดูครบถ้วน ใช้ได้เลย"
    else:
        summary = f"พบ {len(issues)} ข้อที่ควรดู และ {len(warnings)} ข้อควรพิจารณา — แก้ให้ชัดแล้วยืนยัน หรือใช้ต่อได้เลยถ้าโอเค"
    return {
        "verdict": verdict,
        "issues": issues,
        "warnings": warnings,
        "summary": summary,
    }


# ---------- Helpers สำหรับ parse JSON ที่ AI คืนมา ----------

def _clean_json_text(text: str) -> str:
    """ตัด ``` fence, <think>…</think> และข้อความไทยที่ AI พิมพ์แทรกออก เหลือเฉพาะ JSON ตัวแรก
    (qwen3.6-27b ใส่ reasoning ไว้ใน content ด้วยแท็ก <think>…</think> — ต้องตัดก่อน parse ไม่ใช่แค่ fence)
    ใช้ raw_decode จริง ๆ (นับวงเล็บให้ถูกต้องใน string) กันพลาดกับ ] หรือ } ในชื่องาน"""
    text = text.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        text = text.rstrip("`").strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return json.dumps(obj, ensure_ascii=False)
            except Exception:
                continue
    return text


def _parse_json(text: str):
    return json.loads(_clean_json_text(text))


def _date_table(from_date: datetime.date, days: int):
    weekday_names = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์']
    lines = []
    for i in range(days):
        d = from_date + datetime.timedelta(days=i)
        wd = weekday_names[d.weekday()]
        label = "วันนี้" if i == 0 else ("พรุ่งนี้" if i == 1 else "")
        lines.append(f"{d.isoformat()} = วัน{wd}" + (f" ({label})" if label else ""))
    return "\n".join(lines)


# ---------- File Upload & AI Content Analysis ----------

VISION_MODEL = "qwen/qwen3.6-27b"


def _prep_image(image_bytes: bytes):
    """ย่อ/บีบอัดภาพก่อนส่ง vision — กันเกินขีดจำกัด tokens ของ free tier
    (สกรีนช็อตความละเอียดสูงแปลงเป็น token เยอะเกิน 8000 TPM ได้ ตาม AGENTS.md gotcha #16)
    คืน (mime, bytes) — คลาย JPEG หลังย่อ; ถ้า PIL ใช้ไม่ได้/อ่านภาพไม่ได้ → คืนของเดิม (fallback ไม่ crash)"""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        max_side = 800
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80)
        return "jpeg", out.getvalue()
    except Exception:
        return None, image_bytes


def _chat_json(messages, model="openai/gpt-oss-120b", **kwargs):
    """ส่ง messages ไป Groq แล้ว parse JSON จากคำตอบ (ตัด ``` fence + <think> + ข้อความแทรก)
    kwargs ผ่านเข้า create ตรง ๆ (เช่น reasoning_effort/max_completion_tokens)"""
    response = _get_client().chat.completions.create(model=model, messages=messages, **kwargs)
    text = response.choices[0].message.content.strip()
    return _parse_json(text)


# ---------- Class Timetable extraction (ตารางเรียน) ----------

_TIMETABLE_PROMPT = """จากข้อความ/รูปภาพตารางเรียนด้านล่าง ให้แปลงเป็น JSON:
{"entries": [{"day_of_week": 1-7, "start_time": "HH:MM", "end_time": "HH:MM", "subject": "...", "location": "..."}], "skipped": ["บรรทัดที่อ่านไม่ออก..."]}

แผนที่วัน (ห้ามใช้เลขอื่น): จันทร์=1, อังคาร=2, พุธ=3, พฤหัสบดี/พฤหัส=4, ศุกร์=5, เสาร์=6, อาทิตย์=7
Monday=1, Tuesday=2, Wednesday=3, Thursday=4, Friday=5, Saturday=6, Sunday=7

กฎ:
- start_time/end_time: คัดลอกจากตารางต้นฉบับตรง ๆ รูปแบบ HH:MM (เช่น "9:00" ให้เขียน "09:00") ห้ามคำนวณ/เดาเอง
- subject = ชื่อวิชา, location = ห้อง/อาคาร (ไม่มีให้ null)
- บรรทัด/แถวไหนอ่านไม่ออกหรือไม่ใช่คาบเรียน ให้ข้าม (ไปอยู่ skipped)
- ถ้าไม่ใช่ตารางเรียนเลย ให้คืน {"entries": [], "skipped": []}"""


def _normalize_timetable_result(result):
    """กัน model คืนโครงสร้างเพี้ยน — normalize เป็น {"entries": [...], "skipped": [...]} เสมอ
    (คิดเองว่าเป็น object วิชาเดียว/ไม่ใช่ตาราง → ก็คืนว่าง ไม่ crash ตามหลัก §9)"""
    if isinstance(result, dict):
        if isinstance(result.get("entries"), list):
            return result
        if result.get("subject") or result.get("day_of_week") is not None:
            return {"entries": [result], "skipped": []}
    return {"entries": [], "skipped": []}


def extract_timetable(document_text: str, today: datetime.date = None):
    """แปลงข้อความตารางเรียน (จากไฟล์/ที่ผู้ใช้วางมา) → {"entries": [...], "skipped": [...]}
    entries แต่ละตัว: {day_of_week 1-7, start_time, end_time, subject, location}
    ยังไม่เซฟ — main จะ clean อีกชั้น + ให้ผู้ใช้ตรวจก่อน"""
    prompt = f"""{_TIMETABLE_PROMPT}

ตารางเรียน:
{document_text}"""
    return _normalize_timetable_result(_chat_json([{"role": "user", "content": prompt}]))


def extract_timetable_image(image_bytes: bytes, filename: str, today: datetime.date = None):
    """วิเคราะห์รูปภาพตารางเรียนด้วย AI vision → {"entries": [...], "skipped": [...]}
    ใช้ reasoning_effort=none + max_completion_tokens ต่ำ — โมเดล thinking (qwen3.6-27b) ใช้ token
    ใน reasoning เยอะมาก ถ้าไม่ปิด จะพิมพ์ JSON ไม่จบ (TokenTruncation → JSONDecodeError)
    และ Groq คิด TPM รวม max_completion_tokens → ตั้งสูงเกินจะ 413 เกิน limit free tier
    (ทั้งคู่ลงไว้ใน AGENTS.md gotcha #16)"""
    import base64
    ext = (filename or "image.jpg").rsplit(".", 1)[-1].lower()
    mime, data = _prep_image(image_bytes)
    if mime is None:
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
        data = image_bytes
    b64 = base64.b64encode(data).decode("utf-8")
    content = [
        {"type": "text", "text": _TIMETABLE_PROMPT + " รูปภาพตารางเรียน:"},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}},
    ]
    parsed = _chat_json([{"role": "user", "content": content}], model=VISION_MODEL,
                        reasoning_effort="none", max_completion_tokens=1500)
    return _normalize_timetable_result(parsed)


def analyze_file_text(document_text: str, today: datetime.date = None):
    """วิเคราะห์ข้อความจากเอกสาร → คืน {summary, tasks[]}
    tasks แต่ละตัว: {title, description, estimated_time, deadline, deadline_time, notes}"""
    if today is None:
        today = datetime.date.today()
    date_table = _date_table(today, 14)
    prompt = f"""วันนี้คือวันที่ {today.isoformat()}

ตารางวันที่ล่วงหน้าสำหรับอ้างอิง (ห้ามคำนวณเอง ให้เลือกจากตารางนี้เท่านั้น):
{date_table}

จากเนื้อหาเอกสารด้านล่าง ให้ดึง "งาน / การบ้าน / สิ่งที่ต้องทำ" ทั้งหมดเป็น JSON array

แต่ละรายการมี field:
- title: ชื่องานสั้น ๆ
- description: รายละเอียดสั้น ๆ จากเอกสาร (ไม่เกิน 200 ตัวอักษร; ถ้าไม่มีให้ null)
- notes: โน้ต/เงื่อนไขที่ต้องรู้ (เช่น "ส่งทางระบบ", "ทำงานเป็นกลุ่ม"; ถ้าไม่มีให้ null)
- estimated_time: เวลาที่คาดว่าต้องใช้เป็นนาที (ถ้าเอกสารไม่บอก ให้ประมาณตามความยาก; ถ้าไม่แน่ใจให้ null)
- deadline: วันที่ต้องส่ง รูปแบบ YYYY-MM-DD เท่านั้น — ถ้าเอกสารระบุวันที่ ให้คัดลอกตรง ๆ จากเอกสาร; ถ้าเป็นคำสัมพัทธ์ (เช่น "พรุ่งนี้" "สัปดาห์หน้า") ให้เลือกจากตารางอ้างอิงด้านบน; ถ้าหาไม่ได้ให้ null
- deadline_time: เวลา HH:MM (ถ้าเอกสารระบุ ให้คัดลอก; ไม่ระบุให้ null)

หลักการ: ถ้าข้อมูลไหนไม่ชัดเจนให้ใส่ null ดีกว่าเดา ถ้าเอกสารไม่มีงานเลยให้คืน tasks เป็น []

ตอบเป็น JSON ตามโครงสร้างนี้:
{{
  "summary": "สรุปเอกสาร 1-2 ประโยคภาษาไทย",
  "tasks": [ ... ]
}}

เนื้อหาเอกสาร:
{document_text}
"""
    return _chat_json([{"role": "user", "content": prompt}])


def analyze_image_file(image_bytes: bytes, filename: str, today: datetime.date = None):
    """วิเคราะห์รูปภาพ (สกรีนช็อตตารางงาน/ใบสั่งงาน) ด้วย AI vision → คืน {summary, tasks[]}"""
    import base64
    if today is None:
        today = datetime.date.today()
    ext = (filename or "image.jpg").rsplit(".", 1)[-1].lower()
    mime, data = _prep_image(image_bytes)
    if mime is None:
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
        data = image_bytes
    b64 = base64.b64encode(data).decode("utf-8")

    prompt = """จากรูปภาพนี้ ให้อ่านงาน / การบ้าน / สิ่งที่ต้องทำทั้งหมด แล้วตอบเป็น JSON:
{
  "summary": "สรุปสิ่งที่เห็นในภาพ 1-2 ประโยคภาษาไทย",
  "tasks": [ {"title": "...", "description": "...", "estimated_time": นาทีหรือnull, "deadline": "YYYY-MM-DDหรือnull", "deadline_time": "HH:MMหรือnull", "notes": "..."} ]
}
ถ้าในภาพไม่มีงานเลยให้ tasks เป็น []"""

    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}},
    ]
    # reasoning_effort=none + max_completion_tokens ต่ำ — กัน (1) thinking กิน token จน JSON ไม่จบ
    # (2) Groq คิด TPM รวม max_completion_tokens → ตั้งสูงเกินจะ 413 เกิน limit free tier (AGENTS.md gotcha #16)
    return _chat_json([{"role": "user", "content": content}], model=VISION_MODEL,
                      reasoning_effort="none", max_completion_tokens=2000)


# ---------- Travel Planning ----------

def plan_trip(destination: str, start_date: datetime.date, end_date: datetime.date,
              notes: str = None, today: datetime.date = None):
    """วางแผนทริป → คืน {days[], prep_tasks[]}
    days: [{date, title, items[]}] ครบทุกวันตั้งแต่ start ถึง end
    prep_tasks: [{title, deadline, deadline_time, estimated_time}] — งานเตรียมตัวก่อนเดินทาง"""
    if today is None:
        today = datetime.date.today()
    trip_days = (end_date - start_date).days + 1
    if trip_days < 1:
        raise ValueError("วันสุดท้ายของทริปต้องไม่ก่อนวันแรก")
    # ตารางวันที่ตั้งแต่ก่อนเดินทาง 7 วัน ถึงวันสุดท้าย (ให้ AI เลือกวัน deadline ของ prep tasks ได้)
    date_table = _date_table(start_date - datetime.timedelta(days=7), trip_days + 7)

    prompt = f"""วันนี้คือวันที่ {today.isoformat()}

ตารางวันที่อ้างอิง (ห้ามคำนวณเอง ให้เลือกจากตารางนี้เท่านั้น):
{date_table}

วางแผนทริปต่อไปนี้:
- ปลายทาง: {destination}
- เดินทางวันที่ {start_date.isoformat()} ถึง {end_date.isoformat()} (รวม {trip_days} วัน)
- ข้อมูลเพิ่มเติม: {notes if notes else "ไม่มี"}

ตอบเป็น JSON:
{{
  "days": [
    {{ "date": "YYYY-MM-DD", "title": "หัวข้อประจำวัน (ภาษาไทย)", "items": ["กิจกรรม/ที่เที่ยว 2-5 ข้อ", "..."] }}
  ],
  "prep_tasks": [
    {{ "title": "งานเตรียมตัว (ภาษาไทย)", "deadline": "YYYY-MM-DD", "deadline_time": "HH:MMหรือnull", "estimated_time": นาที }}
  ]
}}

หลักการ:
- days ต้องครบทุกวันตั้งแต่วันแรกถึงวันสุดท้ายของทริป ใช้ตารางวันที่อ้างอิงด้านบนเท่านั้น ห้ามคำนวณวันเอง
- items สรุปสั้น ๆ ภาษาไทย (ชื่อสถานที่ที่เป็นสากลให้ใช้ชื่อเดิม)
- prep_tasks 3-8 ข้อ เช่น จองที่พัก/ตั๋ว เตรียมเอกสาร จัดกระเป๋า เช็คสภาพอากาศ ฯลฯ
- deadline ของ prep_tasks ต้องเป็นวันที่ก่อนวันแรกของทริป เลือกจากตารางอ้างอิง ถ้าไม่แน่ใจให้ null
- ตอบเป็น JSON เท่านั้น"""
    result = _chat_json([{"role": "user", "content": prompt}])
    return {
        "days": result.get("days", []),
        "prep_tasks": result.get("prep_tasks", []),
    }


# ---------- Chat: แยกแยะเจตนาจากข้อความ (ใช้ AI แต่มี keyword fallback กัน offline) ----------

CHAT_KEYWORDS = {
    # ทริปตรวจก่อน "แพลน" เพราะ "แพลนเที่ยว/แพลนทริป" ต้องไปทริป
    "plan_trip": ["เที่ยว", "ทริป", "travel", "trip", "ไปเที่ยว", "ท่องเที่ยว", "วางแผนเที่ยว"],
    # คำสั่งแก้ตารางเรียน ตรวจก่อน set_timetable (ข้อความอาจมีคำว่า "ตารางเรียน" ปนมา)
    "update_timetable": ["เพิ่มวิชา", "ลบวิชา", "ย้ายวิชา", "เพิ่มคาบ", "ลบคาบ", "ย้ายคาบ",
                         "ล้างตาราง", "เคลียร์ตาราง", "ลบตารางทั้งหมด", "ลบตารางเรียนทั้งหมด"],
    # "ยกเลิกเรียน/ไม่มีเรียน" ต้องมาก่อน cancel_task — กัน "ยกเลิกเรียนวันจันทร์" ไปเป็น "ลบงาน"
    "cancel_classes": ["ไม่มีเรียน", "ไม่มีการเรียน", "หยุดเรียน", "ยกเลิกเรียน", "ไม่ไปเรียน",
                       "ยกเลิกคาบ", "ตัดคาบ", "ไม่มาเรียน", "เลิกเรียนวัน", "ปิดคาบ", "ไม่มีคาบ"],
    "cancel_task": ["ยกเลิกงาน", "ลบงาน", "เอางานออก", "ลบการบ้าน", "ยกเลิกการบ้าน",
                    "เอาการบ้านออก", "ยกเลิก", "ลบงานที่", "เอาเลิก"],
    "set_timetable": ["ตารางเรียน", "ตารางสอน", "ตารางวิชา", "ตารางคาบ", "ตารางเวลาเรียน",
                      "ตารางเวลา", "timetable", "class schedule", "ตารางแนบ", "ตารางที่ส่ง"],
    "plan_daily": ["แพลนวันนี้", "แผนวันนี้", "จัดตาราง", "วันนี้ควรทำ", "แพลน", "schedule", "ตารางงาน",
                   "แพลนงาน", "วางแผนวันนี้", "ทำอะไรวันนี้"],
    "chat": ["สวัสดี", "hi", "hello", "ช่วย", "ขอบคุณ", "ขอบใจ", "你好", "你好吗", "help", "who are you",
             "คืออะไร", "ใช้ยังไง"],
}


def classify_chat(text: str):
    """แยกแยะข้อความว่าผู้ใช้อยากทำอะไร:
    create_task / cancel_task / cancel_classes / plan_daily / plan_trip /
    set_timetable / update_timetable / chat
    ใช้ keyword heuristic (deterministic) กัน offline — AI ช่วยได้แต่ไม่จำเป็น"""
    t = (text or "").lower()
    for intent, kws in CHAT_KEYWORDS.items():
        if intent == "chat":
            continue
        if any(k in t for k in kws):
            return intent
    if any(k in t for k in CHAT_KEYWORDS["chat"]):
        return "chat"
    return "create_task"


# ---------- Rewards: AI คิด point_cost เอง (ไม่ให้ผู้ใช้ตั้งเอง) ----------

REWARD_COST_HINTS = {
    "ดูหนัง": 80, "ซีรีส์": 80, "เกม": 60, "ขนม": 30, "ช้อปปิ้ง": 150, "ช้อป": 150,
    "เที่ยว": 200, "ร้าน": 50, "กาแฟ": 40, "ชา": 40, "บุฟเฟ่ต์": 200, "ช็อก": 40,
    "หนังสือ": 90, "นอน": 20, "พัก": 20, "โทรศัพท์": 30, "ไถมือถือ": 30,
}


def suggest_reward_cost(title: str):
    """AI ประเมินแต้มที่เหมาะสมของรางวัล (ยังไม่บันทึก) — ผิดพลาดได้เสมอต้องมี fallback
    ใช้ heuristic ตามคำหลัก + ช่วง 20-200 แต้ม; ถ้าไม่มีคำหลักให้ใช้ 50 กลาง ๆ"""
    t = (title or "").lower()
    for kw, cost in REWARD_COST_HINTS.items():
        if kw in t:
            return cost
    return 50


def generate_reward_ideas(n: int = 5):
    """AI คิดไอเดียรางวัลให้อย่างน้อย n ช่อง (พร้อมแต้ม + จำกัดสิทธิ์)
    deterministic pool กัน offline — ผู้ใช้เลือกมาใช้เป็นรางวัลของตัวเองได้"""
    pool = [
        {"title": "ดูหนัง/ซีรีส์ 1 ตอน", "point_cost": 80,
         "max_per_day": 1, "max_per_month": 8, "max_per_year": 80},
        {"title": "ซื้อขนมที่ชอบ 1 อย่าง", "point_cost": 30,
         "max_per_day": 1, "max_per_month": 10, "max_per_year": 120},
        {"title": "เล่นเกม 30 นาที", "point_cost": 60,
         "max_per_day": 1, "max_per_month": 12, "max_per_year": 100},
        {"title": "นอนพัก 1 ชม. กลางวัน", "point_cost": 20,
         "max_per_day": 1, "max_per_month": 15, "max_per_year": 150},
        {"title": "ช้อปปิ้งของที่อยากได้", "point_cost": 150,
         "max_per_day": 1, "max_per_month": 2, "max_per_year": 20},
        {"title": "ไปเที่ยว/เดินเล่นนอกบ้าน", "point_cost": 200,
         "max_per_day": 1, "max_per_month": 2, "max_per_year": 15},
        {"title": "ซื้อหนังสือเล่มที่อยากอ่าน", "point_cost": 90,
         "max_per_day": 1, "max_per_month": 3, "max_per_year": 24},
        {"title": "แก้วกาแฟ/ชาโปรด", "point_cost": 40,
         "max_per_day": 1, "max_per_month": 10, "max_per_year": 100},
        {"title": "ไถมือถือ/ดูคลิป 30 นาที", "point_cost": 30,
         "max_per_day": 1, "max_per_month": 12, "max_per_year": 100},
    ]
    return pool[:max(1, n)]

"""Calendar service — holidays auto-population + class timetable parser.

แยกจาก main.py เพื่อกันไฟล์งอกยาว (ตามสไตล์ gamification.py)
"""
import datetime
import re
import uuid

from models import Holiday, ClassSchedule, Routine, TimetableCancel


# ---------- วันหยุดราชการไทย ----------

# วันหยุดประจำปี (ซ้ำทุกปี): (เดือน, วัน, ชื่อ, kind)
HOLIDAYS_FIXED = [
    (1, 1, "วันขึ้นปีใหม่", "public"),
    (4, 6, "วันจักรี", "public"),
    (4, 13, "วันสงกรานต์", "public"),
    (4, 14, "วันสงกรานต์", "public"),
    (4, 15, "วันสงกรานต์", "public"),
    (5, 1, "วันแรงงานแห่งชาติ", "public"),
    (5, 4, "วันฉัตรมงคล", "public"),
    (6, 3, "วันเฉลิมพระชนมพรรษา สมเด็จพระนางเจ้าฯ พระบรมราชินี", "public"),
    (7, 28, "วันเฉลิมพระชนมพรรษา ร.10", "public"),
    (8, 12, "วันแม่แห่งชาติ", "public"),
    (10, 13, "วันนวมินทรมหาราช", "public"),
    (10, 23, "วันปิยมหาราช", "public"),
    (12, 5, "วันพ่อแห่งชาติ", "public"),
    (12, 10, "วันรัฐธรรมนูญ", "public"),
    (12, 31, "วันสิ้นปี", "public"),
]

# วันหยุดเฉพาะปี (ตามจันทรคติ + วันชดเชย + วันกรณีพิเศษ) — ต้องอัปเดตเพิ่มทุกปี
HOLIDAYS_YEARLY = {
    2026: [
        (1, 2, "วันหยุดกรณีพิเศษ", "special"),
        (3, 3, "วันมาฆบูชา", "religious"),
        (5, 9, "วันพืชมงคล", "special"),
        (5, 31, "วันวิสาขบูชา", "religious"),
        (6, 1, "ชดเชยวันวิสาขบูชา", "special"),
        (7, 29, "วันอาสาฬหบูชา", "religious"),
        (7, 30, "วันเข้าพรรษา", "religious"),
        (12, 7, "ชดเชยวันพ่อแห่งชาติ", "special"),
    ],
    # ปี 2570 (2027) — มาฆบูชา 21/2 (อา), วิสาขบูชา 20/5 (พฤ), อาสาฬหบูชา 18/7 (อา), เข้าพรรษา 19/7 (จ)
    2027: [
        (2, 21, "วันมาฆบูชา", "religious"),
        (5, 20, "วันวิสาขบูชา", "religious"),
        (7, 18, "วันอาสาฬหบูชา", "religious"),
        (7, 19, "วันเข้าพรรษา", "religious"),
    ],
}


def seed_holidays(db, year):
    """ลงวันหยุดของปีที่กำหนด (idempotent — วันไหนมีแล้วข้าม)
    วันหยุดประจำปี (ซ้ำทุกปี) จะถูกคำนวณจาก HOLIDAYS_FIXED อัตโนมัติ
    """
    existing = {(h.date.month, h.date.day) for h in db.query(Holiday).all()
                if h.date and h.date.year == year}
    entries = [(datetime.date(year, m, d), n, k) for m, d, n, k in HOLIDAYS_FIXED]
    entries += [(datetime.date(year, m, d), n, k) for m, d, n, k in HOLIDAYS_YEARLY.get(year, [])]
    added = 0
    for date, name, kind in entries:
        if (date.month, date.day) in existing:
            continue
        db.add(Holiday(id=str(uuid.uuid4()), date=date, name=name, kind=kind))
        existing.add((date.month, date.day))
        added += 1
    if added:
        db.commit()
    return added


def list_holidays(db, year):
    """รายการวันหยุดของปี เรียงตามวันที่"""
    seed_holidays(db, year)
    rows = db.query(Holiday).filter(Holiday.date >= datetime.date(year, 1, 1),
                                    Holiday.date <= datetime.date(year, 12, 31)).all()
    return [{"date": str(h.date), "name": h.name, "kind": h.kind} for h in rows]


# ---------- Class Timetable import (parse ข้อความที่วาง/พิมพ์มา) ----------

DAY_NAMES = {
    "จันทร์": 1, "อังคาร": 2, "พุธ": 3, "พฤหัสบดี": 4, "พฤหัส": 4, "ศุกร์": 5,
    "เสาร์": 6, "อาทิตย์": 7,
    "mon": 1, "monday": 1, "tue": 2, "tuesday": 2, "tue": 2,
    "wed": 3, "wednesday": 3, "thu": 4, "thur": 4, "thursday": 4,
    "fri": 5, "friday": 5, "sat": 6, "saturday": 6, "sun": 7, "sunday": 7,
}

# รูปแบบเวลา: 09:00-10:30 / 9:00-10:30 / 09:00 ถึง 10:30 / 9:00–10:30
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}):(\d{2})\s*(?:-|–|ถึง|to)\s*(\d{1,2}):(\d{2})"
)

# หาชื่อวันในข้อความ (เรียงตัวยาวก่อน กัน "พฤหัส" ชน prefix ของ "พฤหัสบดี")
_DAY_RE = re.compile(
    r"จันทร์|อังคาร|พุธ|พฤหัสบดี|พฤหัส|ศุกร์|เสาร์|อาทิตย์|monday|mon|tuesday|tue|"
    r"wednesday|wed|thursday|thur|thu|friday|fri|saturday|sat|sunday|sun",
    re.IGNORECASE,
)


def _parse_time(hh, mm):
    h = int(hh)
    m = int(mm)
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return f"{h:02d}:{m:02d}"


def parse_timetable_text(text):
    """parse ข้อความตารางเรียน ทีละบรรทัด กลับ [{day_of_week, start_time, end_time,
    subject, location}]

    รูปแบบที่รองรับ: "จันทร์ 09:00-10:30 คณิตศาสตร์ ห้อง 301"
    ไม่ parse ได้ = ตัดทิ้ง (ไม่มี crash) ตามหลัก §9
    """
    entries = []
    skipped = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # เอาหมายเลขนำหน้าออก เช่น "1. " "2) "
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        # หาวัน: คำแรกต้องตรงกับ DAY_NAMES
        first_word = line.split()[0].lower() if line.split() else ""
        day = None
        for name, d in DAY_NAMES.items():
            if first_word == name:
                day = d
                break
        if day is None:
            skipped.append(raw_line)
            continue
        rest = line[len(first_word):].strip()
        m = _TIME_RANGE_RE.search(rest)
        if not m:
            skipped.append(raw_line)
            continue
        start = _parse_time(m.group(1), m.group(2))
        end = _parse_time(m.group(3), m.group(4))
        if not start or not end or start >= end:
            skipped.append(raw_line)
            continue
        remaining = rest[:m.start()].strip() + " " + rest[m.end():].strip()
        parts = [p for p in remaining.split() if p.strip()]
        if not parts:
            skipped.append(raw_line)
            continue
        subject = parts[0]
        location = " ".join(parts[1:]) if len(parts) > 1 else None
        entries.append({
            "day_of_week": day,
            "start_time": start,
            "end_time": end,
            "subject": subject,
            "location": location,
        })
    return {"entries": entries, "skipped": skipped}


# ---------- Timetable CRUD helpers ----------

def clean_timetable_entries(entries):
    """กรองรายการตารางเรียนที่ใช้ได้: day 1-7, start/end เป็น HH:MM, start < end, มี subject
    ใช้ได้ทั้งตอนบันทึกและตอนแสดง preview — ตัวอะไรข้อมูลไม่ครบตัดทิ้ง ไม่ crash (หลัก §9)"""
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        day = e.get("day_of_week")
        start = e.get("start_time")
        end = e.get("end_time")
        subject = (e.get("subject") or "").strip()
        if not isinstance(day, int) or day < 1 or day > 7:
            continue
        if not isinstance(start, str) or not re.fullmatch(r"\d{2}:\d{2}", start):
            continue
        if not isinstance(end, str) or not re.fullmatch(r"\d{2}:\d{2}", end):
            continue
        if start >= end or not subject:
            continue
        loc = (e.get("location") or "").strip() or None
        out.append({"day_of_week": day, "start_time": start, "end_time": end,
                    "subject": subject, "location": loc})
    return out


def list_schedules(db):
    """ตารางเรียนทั้งหมด เรียงตามวัน แล้วตามเวลาเริ่ม"""
    rows = db.query(ClassSchedule).order_by(
        ClassSchedule.day_of_week, ClassSchedule.start_time).all()
    return [{
        "id": s.id,
        "day_of_week": s.day_of_week,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "subject": s.subject,
        "location": s.location,
    } for s in rows]


def create_schedules(db, entries):
    """สร้างตารางเรียนหลายรายการจากรายการที่ผู้ใช้ยืนยันแล้ว (body JSON array)
    กรองรายการที่ข้อมูลไม่ครบ/เวลาไม่สมเหตุผลออก (clean_timetable_entries)"""
    created = []
    for e in clean_timetable_entries(entries):
        s = ClassSchedule(id=str(uuid.uuid4()), day_of_week=e["day_of_week"],
                          start_time=e["start_time"], end_time=e["end_time"],
                          subject=e["subject"], location=e["location"])
        db.add(s)
        created.append(s)
    db.commit()
    return [{
        "id": s.id,
        "day_of_week": s.day_of_week,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "subject": s.subject,
        "location": s.location,
    } for s in created]


# ---------- Chat: รู้จักตารางเรียน + คำสั่งแก้ตาราง ----------

DAY_NAMES_TH = {1: "จันทร์", 2: "อังคาร", 3: "พุธ", 4: "พฤหัสบดี", 5: "ศุกร์", 6: "เสาร์", 7: "อาทิตย์"}


def detect_timetable(text):
    """เดาแบบ conservative ว่าข้อความนี้คือตารางเรียนไหม (นับบรรทัดที่มีวัน + ช่วงเวลา)
    ใช้ตอนไฟล์ผ่าน /chat เพื่อตัดสินใจว่าจะ extract เป็นตารางหรือแยกงาน
    ระวัง false positive — ถ้าไม่ชัวร์ให้คืน False ไปทางแยกงานปกติ"""
    time_count = 0
    day_count = 0
    low = (text or "").lower()
    for line in low.splitlines():
        if _TIME_RANGE_RE.search(line):
            time_count += 1
        if any(day in line for day in DAY_NAMES):
            day_count += 1
    return (time_count >= 2 and day_count >= 2) or time_count >= 4


def parse_timetable_command(text):
    """ตีความคำสั่งแก้ตารางเรียนในแชท → {kind, subject, day, from_day, to_day,
    start_time, end_time, location}
    kind ∈ add / move / delete / clear / none — ไม่ match ก็ none (ไม่ crash)
    แบบ deterministic ไม่เรียก AI — ผู้ใช้ยืนยันก่อนเสมอก่อนแตะ DB"""
    t = (text or "").strip()
    if not t:
        return {"kind": "none"}
    if any(k in t for k in ["ล้างตาราง", "เคลียร์ตาราง", "ลบตารางทั้งหมด", "ลบตารางเรียนทั้งหมด"]):
        return {"kind": "clear"}

    # เก็บวันตามลำดับที่ปรากฏในข้อความจริง (เรียงยาวก่อนไม่ถูก — จะสลับ from/to)
    days_found = [DAY_NAMES[m.group(0).lower()] for m in _DAY_RE.finditer(t)]
    tm = _TIME_RANGE_RE.search(t)
    start = end = None
    if tm:
        start = _parse_time(tm.group(1), tm.group(2))
        end = _parse_time(tm.group(3), tm.group(4))
    # ห้อง/สถานที่ (เช่น "ห้อง 301")
    loc_m = re.search(r"(?:ห้อง|ชั้น|ตึก|อาคาร)\s*([\w\-./]+)", t)
    location = loc_m.group(1) if loc_m else None

    def _subject_after(kw):
        """ชื่อวิชา = ข้อความระหว่างคำสั่ง กับ เครื่องหมายแรก (วัน/เวลา/ห้อง)"""
        idx = t.find(kw)
        if idx == -1:
            return None
        start_idx = idx + len(kw)
        cut = len(t)
        for m in _DAY_RE.finditer(t):
            if m.start() < start_idx:
                continue
            # ตัดที่คำว่า "วัน" ที่ติดกับชื่อวัน ("...จากวันจันทร์" → วิชา = "...จาก")
            pos = t.rfind("วัน", start_idx, m.start())
            day_cut = pos if pos != -1 and m.start() - pos <= 3 else m.start()
            if day_cut < cut:
                cut = day_cut
        if tm and tm.start() >= start_idx and tm.start() < cut:
            cut = tm.start()
        if loc_m and loc_m.start() >= start_idx and loc_m.start() < cut:
            cut = loc_m.start()
        subject = re.sub(r"\s+", " ", t[start_idx:cut]).strip(" .:-–").strip()
        subject = re.sub(r"^(?:จาก|ไป|ตอน|เวลา|ช่วง|ที่)\s*", "", subject)
        subject = re.sub(r"(?:ไป|ตอน|เวลา|จาก|ถึง|ช่วง|ที่)\s*$", "", subject).strip()
        return subject or None

    for kind, kws in [("add", ["เพิ่มวิชา", "เพิ่มคาบ", "เพิ่มตาราง"]),
                      ("delete", ["ลบวิชา", "ลบคาบ"]),
                      ("move", ["ย้ายวิชา", "ย้ายคาบ"])]:
        for kw in kws:
            if kw in t:
                subject = _subject_after(kw)
                if kind == "add":
                    return {"kind": "add", "subject": subject,
                            "day": days_found[0] if days_found else None,
                            "start_time": start, "end_time": end, "location": location}
                if kind == "delete":
                    return {"kind": "delete", "subject": subject,
                            "day": days_found[0] if days_found else None}
                if kind == "move":
                    # วันแรกในข้อความ = วันต้นทาง, วันถัดมา = ปลายทาง;
                    # ถ้าระบุวันเดียว ถือว่าเป็นปลายทาง (ย้ายไปวันนั้น)
                    if len(days_found) >= 2:
                        return {"kind": "move", "subject": subject,
                                "from_day": days_found[0], "to_day": days_found[1],
                                "start_time": start, "end_time": end}
                    return {"kind": "move", "subject": subject,
                            "from_day": None,
                            "to_day": days_found[0] if days_found else None,
                            "start_time": start, "end_time": end}
    return {"kind": "none"}


def match_schedules(schedules, subject, day=None):
    """หา class schedule ที่ชื่อวิชาตรงกัน (เทียบแบบ contains กันทั้ง 2 ทิศ — ผู้ใช้พิมพ์ย่อได้)
    day ไม่ใช่ None → กรองวันด้วย; คืน [{id, day_of_week, start_time, end_time, subject, location}]"""
    subj = (subject or "").strip().lower()
    if not subj:
        return []
    out = []
    for s in schedules:
        s_subj = (s.get("subject") or "").lower()
        if subj in s_subj or s_subj in subj:
            if day is None or s.get("day_of_week") == day:
                out.append(s)
    return out


def build_timetable_proposal(action, schedules):
    """แปลงคำสั่งที่ parse มาเป็นข้อเสนอให้ผู้ใช้ยืนยัน (ยังไม่แตะ DB — หลัก §9)
    คืน {action, matched[], entry?, ok, summary} ภาษาไทย"""
    kind = action.get("kind")
    if kind == "none":
        return {"action": action, "matched": [], "entry": None, "ok": False,
                "summary": "ยังไม่เข้าใจคำสั่งนี้ ลองแบบนี้: 'เพิ่มวิชาเคมี วันอังคาร 10:00-11:30 ห้อง 201' "
                           "'ย้ายวิชาคณิตศาสตร์ ไปวันพฤหัสบดี' 'ลบวิชาฟิสิกส์' 'ล้างตาราง'"}

    if kind == "clear":
        return {"action": action, "matched": list(schedules), "entry": None, "ok": True,
                "summary": f"จะล้างตารางเรียนทั้งหมด ({len(schedules)} คาบ)"}

    if kind == "add":
        entry = clean_timetable_entries([{
            "day_of_week": action.get("day"), "start_time": action.get("start_time"),
            "end_time": action.get("end_time"), "subject": action.get("subject"),
            "location": action.get("location")}])
        if not entry:
            return {"action": action, "matched": [], "entry": None, "ok": False,
                    "summary": "ข้อมูลยังไม่ครบ — ต้องการ วิชา + วัน + เวลา เช่น 'เพิ่มวิชาเคมี วันอังคาร 10:00-11:30 ห้อง 201'"}
        e = entry[0]
        day_name = DAY_NAMES_TH.get(e["day_of_week"], "?")
        return {"action": action, "matched": [], "entry": e, "ok": True,
                "summary": f"จะเพิ่ม '{e['subject']}' {day_name} {e['start_time']}-{e['end_time']}"
                           + (f" {e['location']}" if e.get("location") else "")}

    matched = match_schedules(schedules, action.get("subject"), action.get("day"))
    if not matched:
        return {"action": action, "matched": [], "entry": None, "ok": False,
                "summary": "ไม่เจอวิชานั้นในตาราง — ลองพิมพ์ชื่อวิชาให้ตรง (เช่น 'คณิต' 'English')"}

    if kind == "delete":
        return {"action": action, "matched": matched, "entry": None, "ok": True,
                "summary": f"จะลบ '{action.get('subject')}' จำนวน {len(matched)} คาบ"}

    if kind == "move":
        to_day = action.get("to_day")
        dest = f"วัน{DAY_NAMES_TH.get(to_day, '?')}" if to_day else "วัน/เวลาที่ระบุ"
        return {"action": action, "matched": matched, "entry": None, "ok": True,
                "summary": f"จะย้าย '{action.get('subject')}' จำนวน {len(matched)} คาบ ไป{dest}"}

    return {"action": action, "matched": [], "entry": None, "ok": False,
            "summary": "ยังไม่เข้าใจคำสั่งนี้ ลองใหม่ได้เลย"}


def apply_timetable_change(db, action):
    """ทำการเปลี่ยนแปลงที่ผู้ใช้ยืนยันแล้วจริง ๆ (ดูจาก action — ไม่อ้างผล proposal ที่ส่งกลับมา)
    คืน {summary, schedules} — add/delete/move/clear; ข้อมูลไม่ครบ/ไม่เจอ = ไม่เปลี่ยน + อธิบาย"""
    schedules = list_schedules(db)
    kind = action.get("kind")

    if kind == "clear":
        for s in db.query(ClassSchedule).all():
            db.delete(s)
        db.commit()
        return {"summary": "ล้างตารางเรียนทั้งหมดแล้ว", "schedules": []}

    if kind == "add":
        created = create_schedules(db, [{
            "day_of_week": action.get("day"),
            "start_time": action.get("start_time"),
            "end_time": action.get("end_time"),
            "subject": action.get("subject"),
            "location": action.get("location"),
        }])
        if not created:
            return {"summary": "ข้อมูลไม่ครบ (ต้องการ วิชา + วัน + เวลา) — ยังไม่ได้บันทึก",
                    "schedules": schedules}
        return {"summary": f"เพิ่ม '{created[0]['subject']}' เข้าตารางแล้ว",
                "schedules": list_schedules(db)}

    matched = match_schedules(schedules, action.get("subject"), action.get("day"))
    if not matched:
        return {"summary": "ไม่เจอวิชานั้นในตาราง — ยังไม่ได้แก้", "schedules": schedules}

    if kind == "delete":
        for s in matched:
            db.query(ClassSchedule).filter(ClassSchedule.id == s["id"]).delete()
        db.commit()
        return {"summary": f"ลบ '{action.get('subject')}' จำนวน {len(matched)} คาบแล้ว",
                "schedules": list_schedules(db)}

    if kind == "move":
        to_day = action.get("to_day")
        start = action.get("start_time")
        end = action.get("end_time")
        moved = 0
        for s in matched:
            obj = db.query(ClassSchedule).filter(ClassSchedule.id == s["id"]).first()
            if not obj:
                continue
            if to_day:
                obj.day_of_week = to_day
            if start and end:
                obj.start_time = start
                obj.end_time = end
            moved += 1
        db.commit()
        return {"summary": f"ย้าย '{action.get('subject')}' จำนวน {moved} คาบแล้ว",
                "schedules": list_schedules(db)}

    return {"summary": "ยังไม่เข้าใจคำสั่งนี้ — ยังไม่ได้แก้", "schedules": schedules}


# ---------- ยกเลิกคาบเรียนเฉพาะวัน (TimetableCancel) ----------

# คำหลักบอกช่วงเวลา: "เช้า" = 00:00-12:00, "บ่าย" = 12:00-18:00, "เย็น/ค่ำ" = 18:00-23:59
CANCEL_PERIODS = [
    (["เช้า", "ช่วงเช้า"], "00:00", "12:00"),
    (["กลางวัน"], "12:00", "13:00"),
    (["บ่าย", "ช่วงบ่าย"], "12:00", "18:00"),
    (["เย็น", "ค่ำ", "ช่วงเย็น"], "18:00", "23:59"),
]

# คำวันสัมพันธ์: "พรุ่งนี้" = +1 วัน, "มะรืนนี้/มะรืน" = +2 วัน, "วันนี้" = 0
RELATIVE_DAY_RE = re.compile(r"พรุ่งนี้|มะรืนนี้|มะรืน|วันนี้", re.IGNORECASE)


def _to_minutes(t):
    """แปลง "HH:MM" → จำนวนนาที (อ่านไม่ได้ → None)"""
    try:
        h, m = (t or "").split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def schedule_overlaps_cancel(schedule, cancel_start="00:00", cancel_end="23:59"):
    """คาบเรียนทับช่วงที่ยกเลิกไหม (เวลาเป็น "HH:MM") — จุดตัดของช่วงสองช่วง
    รับได้ทั้ง dict และ SQLAlchemy object"""
    if not isinstance(schedule, dict):
        schedule = {
            "start_time": schedule.start_time,
            "end_time": schedule.end_time,
        }
    s_start = _to_minutes(schedule.get("start_time"))
    s_end = _to_minutes(schedule.get("end_time"))
    c_start = _to_minutes(cancel_start)
    c_end = _to_minutes(cancel_end)
    if s_start is None or s_end is None or c_start is None or c_end is None:
        return False
    return s_start < c_end and c_start < s_end


def find_classes_to_cancel(db, date, start_time="00:00", end_time="23:59"):
    """คาบเรียนของวันนั้นที่ทับช่วงที่ต้องการยกเลิก (เรียงตามเวลา) —
    ไม่แตะตารางจริง แค่เอาที่ตรงกันมาให้ผู้ใช้ตรวจก่อน"""
    rows = db.query(ClassSchedule).filter(
        ClassSchedule.day_of_week == date.weekday() + 1,
    ).order_by(ClassSchedule.start_time).all()
    return [{
        "id": s.id,
        "day_of_week": s.day_of_week,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "subject": s.subject,
        "location": s.location,
    } for s in rows if schedule_overlaps_cancel(s, start_time, end_time)]


def cancellations_in_range(db, start_date, end_date):
    """รายการยกเลิกคาบเรียนในช่วงวันที่ (สำหรับหน้า calendar)"""
    rows = db.query(TimetableCancel).filter(
        TimetableCancel.date >= start_date,
        TimetableCancel.date <= end_date,
    ).order_by(TimetableCancel.date.desc()).all()
    return [_cancel_dict(c) for c in rows]


def list_cancellations(db):
    """ประวัติการยกเลิกคาบเรียนทั้งหมด (เรียงวันล่าสุดก่อน) — ใช้ดู/ยกเลิกย้อนหลัง"""
    rows = db.query(TimetableCancel).order_by(
        TimetableCancel.date.desc(), TimetableCancel.created_at.desc()).all()
    return [_cancel_dict(c) for c in rows]


def _cancel_dict(c):
    return {
        "id": c.id,
        "date": str(c.date),
        "start_time": c.start_time,
        "end_time": c.end_time,
        "reason": c.reason,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def create_cancellation(db, date, start_time="00:00", end_time="23:59", reason=None):
    """บันทึกการยกเลิกคาบเรียนเฉพาะวัน — เวลาไม่เป็น HH:MM / date ใช้ไม่ได้ → None ไม่ crash
    คืน dict ที่บันทึกแล้ว (บันทึกให้เสมอแม้ไม่มีคาบทับ — ไว้เป็นประวัติ)"""
    if not isinstance(date, datetime.date):
        return None
    if _to_minutes(start_time) is None or _to_minutes(end_time) is None:
        return None
    if start_time >= end_time:
        return None
    c = TimetableCancel(
        id=str(uuid.uuid4()),
        date=date,
        start_time=start_time,
        end_time=end_time,
        reason=(reason or "").strip()[:200] or None,
    )
    db.add(c)
    db.commit()
    return _cancel_dict(c)


def delete_cancellation(db, cancel_id):
    """ลบ/ยกเลิกการยกเว้น — คืน True ถ้าลบจริง, False ถ้าไม่เจอ"""
    c = db.query(TimetableCancel).filter(TimetableCancel.id == cancel_id).first()
    if not c:
        return False
    db.delete(c)
    db.commit()
    return True


def parse_cancel_request(text, today):
    """ตีความข้อความ "เช้าวันจันทร์ไม่มีเรียน" → {date, day_name, start_time, end_time, reason}
    แบบ deterministic ไม่เรียก AI — คำนวณวันจากชื่อวัน/พรุ่งนี้/มะรืนเท่านั้น (gotcha #2)
    ไม่รู้จักวัน/ช่วง → คืน None (ให้ถามผู้ใช้เพิ่ม ไม่ crash)"""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()

    # 1) หาวันที่จะใช้: ชื่อวัน (จันทร์...) หรือคำสัมพันธ์ (พรุ่งนี้/มะรืน/วันนี้)
    target_date = None
    day_name = ""
    m = RELATIVE_DAY_RE.search(low)
    if m:
        word = m.group(0)
        if "พรุ่งนี้" in word:
            target_date = today + datetime.timedelta(days=1)
        elif "มะรืน" in word:
            target_date = today + datetime.timedelta(days=2)
        else:
            target_date = today
    dm = _DAY_RE.search(low)
    if dm:
        day_num = DAY_NAMES.get(dm.group(0).lower())
        if day_num:
            day_name = DAY_NAMES_TH.get(day_num, "")
            target_date = _next_weekday(today, day_num)
    if not target_date:
        return None

    # 2) หาช่วงเวลา: เช้า/บ่าย/เย็น... ไม่มี → ทั้งวัน
    start_time, end_time = "00:00", "23:59"
    for kws, s, e in CANCEL_PERIODS:
        if any(k in low for k in kws):
            start_time, end_time = s, e
            break

    # 3) เหตุผลสั้น ๆ เก็บไว้ดูประวัติ
    reason = re.sub(r"\s+", " ", t).strip()[:200]
    return {
        "date": target_date,
        "day_name": day_name,
        "start_time": start_time,
        "end_time": end_time,
        "reason": reason,
    }


def _next_weekday(today, day_num):
    """วันถัดไปของชื่อวันนั้น (วันนี้ตรงกับวันนั้น → ใช้วันนี้)"""
    delta = (day_num - 1 - today.weekday()) % 7
    return today + datetime.timedelta(days=delta)


# ---------- กิจวัตรประจำวัน (Routines) ----------

DEFAULT_ROUTINES = [
    {"title": "ตื่นนอน", "time": "07:00", "description": "เริ่มวันใหม่"},
    {"title": "อาหารเช้า", "time": "08:00", "description": None},
    {"title": "อาหารกลางวัน", "time": "12:00", "description": None},
    {"title": "อาหารเย็น", "time": "18:00", "description": None},
    {"title": "เข้านอน", "time": "22:00", "description": "พักผ่อนให้เต็มที่"},
]


def _routine_dict(r):
    return {
        "id": r.id,
        "title": r.title,
        "time": r.time,
        "enabled": r.enabled,
        "description": r.description,
    }


def seed_default_routines(db):
    """ลงกิจวัตรพื้นฐานถ้ายังไม่มีเลย (idempotent) — กันหน้าแรกเปิดมา timeline ว่าง"""
    if db.query(Routine).count() == 0:
        for item in DEFAULT_ROUTINES:
            db.add(Routine(
                id=str(uuid.uuid4()),
                title=item["title"],
                time=item["time"],
                enabled=True,
                description=item["description"],
            ))
        db.commit()


def list_routines(db, include_disabled=False):
    """รายการกิจวัตรทั้งหมด เรียงตามเวลา — ถ้ายังไม่เคยมีให้ seed พื้นฐานก่อน
    `include_disabled` = เอารายการที่ปิดไว้มาด้วย (สำหรับหน้าจัดการ)"""
    seed_default_routines(db)
    query = db.query(Routine).order_by(Routine.time)
    if not include_disabled:
        query = query.filter(Routine.enabled.is_(True))
    return [_routine_dict(r) for r in query.all()]


def create_routine(db, title, time, description=None):
    """เพิ่มกิจวัตร — title/time ต้องใช้ได้ (time เป็น HH:MM) ไม่งั้นคืน None ไม่ crash"""
    title = (title or "").strip()
    time = (time or "").strip()
    if not title or not re.fullmatch(r"\d{2}:\d{2}", time):
        return None
    r = Routine(
        id=str(uuid.uuid4()),
        title=title[:100],
        time=time,
        enabled=True,
        description=(description or "").strip()[:200] or None,
    )
    db.add(r)
    db.commit()
    return _routine_dict(r)


def update_routine(db, routine_id, title=None, time=None, enabled=None, description=None):
    """แก้กิจวัตร — ส่งเฉพาะ field ที่ต้องการ; ข้อมูลที่ส่งมาไม่ถูกต้อง = ไม่แก้ field นั้น
    คืน dict ที่แก้แล้ว, หรือ None ถ้าไม่เจอ routine"""
    r = db.query(Routine).filter(Routine.id == routine_id).first()
    if not r:
        return None
    if title is not None:
        t = (title or "").strip()
        if t:
            r.title = t[:100]
    if time is not None:
        t = (time or "").strip()
        if re.fullmatch(r"\d{2}:\d{2}", t):
            r.time = t
    if enabled is not None:
        r.enabled = bool(enabled)
    if description is not None:
        r.description = (description or "").strip()[:200] or None
    db.commit()
    return _routine_dict(r)


def delete_routine(db, routine_id):
    """ลบกิจวัตร — คืน True ถ้าลบจริง, False ถ้าไม่เจอ"""
    r = db.query(Routine).filter(Routine.id == routine_id).first()
    if not r:
        return False
    db.delete(r)
    db.commit()
    return True

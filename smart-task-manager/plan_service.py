"""Daily Plan — จัดแพลนงานรายวันตามตารางเรียน + ระดับพลังงาน

หลักการ:
- ตารางเรียน (ClassSchedule) ของวันนั้นเป็น "บล็อกเวลาที่ติด" ก่อน — งานไปได้แค่ช่วงว่าง
- ระดับพลังงานกำหนด "กำลังคน" ว่าวันนี้มีแรงทำได้กี่นาที (ระดับ 1 = น้อย, 5 = มาก)
- เลือกงาน TODO เรียงตามความเร่งด่วน (deadline ใกล้สุดก่อน) ให้พอดีกับเวลาที่มี
- แนะนำงานที่ควรทำวันถัดไป (งานที่ใส่ไม่ลงวันนี้ + งานใกล้ deadline)

ไม่ใช้ AI — deterministic เพื่อให้ผู้ใช้เห็นผลเหมือนกันตลอด และ test ได้ง่าย
"""
import datetime

from models import Task, ClassSchedule, Goal

# พลังงาน 1-5 -> กำลังทำได้ในวันนี้ (นาที) — ใจดี ไม่กดดัน
ENERGY_CAPACITY = {1: 45, 2: 90, 3: 150, 4: 210, 5: 300}

DAY_START = 8 * 60    # 08:00
DAY_END = 22 * 60     # 22:00


def _parse_hm(s):
    """'09:30' -> 570 (นาที)"""
    try:
        h, m = (s or "00:00").split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _fmt_minutes(mins):
    mins = max(0, int(mins))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _day_schedules(db, date):
    """ตารางเรียนของวันนี้ (1=จันทร์ ... 7=อาทิตย์ ตรงกับ Dart weekday)"""
    dow = date.weekday() + 1
    return db.query(ClassSchedule).filter(
        ClassSchedule.day_of_week == dow
    ).order_by(ClassSchedule.start_time).all()


def _free_blocks(schedules):
    """ช่วงเวลาว่างในวัน = DAY_START..DAY_END ลบช่วงเรียนออก"""
    blocks = [(DAY_START, DAY_END)]
    for s in sorted(schedules, key=lambda x: _parse_hm(x.start_time)):
        start = _parse_hm(s.start_time)
        end = _parse_hm(s.end_time)
        new_blocks = []
        for (bs, be) in blocks:
            if end <= bs or start >= be:
                new_blocks.append((bs, be))  # ไม่ทับกัน
            else:
                if start > bs:
                    new_blocks.append((bs, min(start, be)))
                if end < be:
                    new_blocks.append((max(end, bs), be))
        blocks = new_blocks
    return blocks


def _free_minutes(schedules):
    return sum(be - bs for bs, be in _free_blocks(schedules))


def _task_priority(t):
    """จัดลำดับ: overdue ก่อน, แล้ว deadline ใกล้สุด, งานไม่มี deadline ไปท้าย"""
    now = datetime.datetime.utcnow()
    if t.deadline:
        overdue = 1 if t.deadline < now else 0
        return (overdue, t.deadline, t.created_at or now, t.title)
    return (0, datetime.datetime.max, t.created_at or now, t.title)


def _select_tasks(db, capacity_minutes, exclude_ids=None):
    """เลือกงาน TODO ให้พอดีกับเวลาที่มี (default estimated_time = 30 นาที)"""
    exclude = set(exclude_ids or [])
    tasks = [t for t in db.query(Task).filter(Task.status == "TODO").all()
             if t.id not in exclude]
    tasks.sort(key=_task_priority)

    selected = []
    used = 0
    for t in tasks:
        est = t.estimated_time or 30
        if used + est <= capacity_minutes:
            selected.append(t)
            used += est
    return selected, used


def preview_plan(db, date):
    """ดูก่อนว่าเลือกพลังงานระดับไหนจะได้ทำงานอะไรบ้าง (ใช้ในหน้าเลือกพลังงาน)"""
    schedules = _day_schedules(db, date)
    levels = []
    for level in range(1, 6):
        cap = ENERGY_CAPACITY[level]
        tasks, used = _select_tasks(db, cap)
        levels.append({
            "energy_level": level,
            "capacity_minutes": cap,
            "total_est": used,
            "tasks": [_task_light(t) for t in tasks],
        })
    return {
        "date": str(date),
        "free_minutes": _free_minutes(schedules),
        "class_count": len(schedules),
        "levels": levels,
    }


def _task_light(t):
    return {
        "id": t.id,
        "title": t.title,
        "estimated_time": t.estimated_time,
        "deadline": str(t.deadline.date()) if t.deadline else None,
    }


def build_daily_plan(db, date, energy_level):
    """จัดแพลนวันนี้จริง ๆ:
    - บล็อกเวลาจากตารางเรียน + งานที่เลือกไว้ ลงในช่วงว่าง
    - แนะนำงานวันถัดไป (ที่ใส่ไม่ลงวันนี้ + ใกล้ deadline)
    """
    level = max(1, min(5, int(energy_level)))
    cap = ENERGY_CAPACITY[level]

    schedules = _day_schedules(db, date)
    free_blocks = _free_blocks(schedules)

    selected, used = _select_tasks(db, cap)
    selected_ids = {t.id for t in selected}

    # ใส่งานลงช่วงว่างตามลำดับ
    task_slots = []
    cursor = 0
    for t in selected:
        est = t.estimated_time or 30
        placed = False
        while cursor < len(free_blocks):
            bs, be = free_blocks[cursor]
            avail = be - bs
            if avail <= 0:
                cursor += 1
                continue
            take = min(est, avail)
            task_slots.append({
                "task_id": t.id,
                "title": t.title,
                "estimated_time": est,
                "start_time": _fmt_minutes(bs),
                "end_time": _fmt_minutes(bs + take),
                "deadline": str(t.deadline.date()) if t.deadline else None,
            })
            free_blocks[cursor] = (bs + take, be)
            est -= take
            if est <= 0:
                break
        # ถ้ายังไม่หมด เก็บเอาไว้ (แต่ไม่ทำให้แพลนยืดเกินไป)

    # แนะนำงานวันถัดไป: งานที่ยังไม่ได้เลือก + ใกล้ deadline
    excluded = selected_ids
    remaining = [t for t in db.query(Task).filter(Task.status == "TODO").all()
                 if t.id not in selected_ids]
    remaining.sort(key=_task_priority)

    tomorrow = date + datetime.timedelta(days=1)
    tomorrow_sched = _day_schedules(db, tomorrow)
    next_day_cap = ENERGY_CAPACITY.get(3, 150)  # ใช้ระดับกลางเป็นเกณฑ์แนะนำ
    next_tasks, _ = _select_tasks(db, next_day_cap, exclude_ids=selected_ids)

    return {
        "date": str(date),
        "energy_level": level,
        "capacity_minutes": cap,
        "total_est": used,
        "free_minutes": _free_minutes(schedules),
        "schedules": [{
            "subject": s.subject,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "location": s.location,
        } for s in schedules],
        "task_slots": task_slots,
        "next_day": {
            "date": str(tomorrow),
            "tasks": [_task_light(t) for t in next_tasks],
        },
    }


def build_goal_plan(db, goal, energy_level=3):
    """Study Plan ระยะยาว (Exam-Prep / เป้าหมายที่กำหนดวันเป้าหมาย):
    กระจายงานย่อยของ Goal ไปตามวันที่เหลือก่อนถึง target_date

    หลักการ:
    - งานย่อย (Task.goal_id) ที่ยัง TODO เท่านั้น
    - แต่ละวันจุงานได้ตาม ENERGY_CAPACITY[ระดับพลังงาน] (นาที)
    - งานชิ้นใหญ่เรียงก่อน (estimated_time มากก่อน) จะได้วางก่อน
    - งานชิ้นเดียวที่ใหญ่กว่ากำลังวันจะไม่ถูกผ่าครึ่ง — ถ้าเป็นวันที่ไม่มีงานไหน
      ลงพอดีกำลังวันเลย จะวางงานที่ใหญ่สุดทั้งชิ้นในวันนั้นแทน (จุเกินไปหน่อยก็ยังวาง)
    - deterministic ไม่เรียก AI — ผู้ใช้เห็นผลเหมือนเดิมทุกครั้ง

    คืน None ถ้าไม่มี target_date หรือวันเป้าหมายผ่านไปแล้ว
    """
    level = max(1, min(5, int(energy_level or 3)))
    cap = ENERGY_CAPACITY[level]

    target = goal.target_date
    if target is None:
        return None

    today = datetime.datetime.utcnow().date()
    days_left = (target - today).days
    if days_left <= 0:
        return None

    tasks = db.query(Task).filter(
        Task.goal_id == goal.id,
        Task.status == "TODO",
    ).all()
    tasks.sort(key=lambda t: (-(t.estimated_time or 30), t.title or ""))

    days = []
    current_date = today + datetime.timedelta(days=1)
    while current_date <= target and tasks:
        slots = []
        used = 0
        remaining = []
        for t in tasks:
            est = t.estimated_time or 30
            if used + est <= cap:
                slots.append(_task_light(t))
                used += est
            else:
                remaining.append(t)
        if not slots and remaining:
            # วันนี้ไม่มีงานไหนลงพอดีกำลังวัน → วางงานที่ใหญ่สุดทั้งชิ้น ไม่ผ่าครึ่ง
            big = remaining.pop(0)
            slots.append(_task_light(big))
            used += big.estimated_time or 30
        days.append({
            "date": str(current_date),
            "total_minutes": used,
            "tasks": slots,
        })
        tasks = remaining
        current_date += datetime.timedelta(days=1)

    return {
        "goal_id": goal.id,
        "target_date": str(target),
        "days_left": days_left,
        "energy_level": level,
        "per_day_minutes": cap,
        "days": days,
        "leftover": [_task_light(t) for t in tasks],
    }

"""Gamification module — levels, streaks, achievements, points, nudge.

หลักการ AGENTS.md §9: escape valve ต้องมาก่อน enforcement เสมอ
- streak มี "grace 1 วัน" (ข้ามวันเดียวไม่หลุด) เพื่อไม่กดดัน
- nudge ใจดี: เปิด/ปิดได้, วันละครั้ง, ปิดวันนั้นได้ (dismiss)
- แต้มไม่มีบทลงโทษ (ไม่มีลบแต้มจากพฤติกรรม) — ลบได้แค่ตอนแลกรางวัลเอง
"""
import json
import math
import uuid
import datetime

from models import Task, Goal, EnergyLog, Achievement, UnlockedAchievement, AppSetting, RewardRedemption


# ---------- Levels ----------

def level_info(points):
    """ระดับจากแต้มสะสมตลอดชีพ (lifetime) — cumulative threshold แบบอ่อน ๆ
    ต้องใช้แต้มสะสมรวม: level 2 = 100, 3 = 300, 4 = 600, 5 = 1000, 6 = 1500 ...
    """
    if points <= 0:
        return {"level": 1, "points": 0, "into": 0, "for_next": 100}
    L = max(1, int(math.ceil((1 + math.sqrt(1 + 8 * points / 100.0)) / 2)))
    prev = 100 * (L - 1) * (L - 2) // 2
    threshold = 100 * L * (L - 1) // 2
    return {
        "level": L,
        "points": points,
        "into": points - prev,
        "for_next": max(0, threshold - points),
    }


# ---------- แต้มตามความเหมาะสมของงาน ----------

def compute_task_points(task):
    """คำนวณแต้มที่งานควรได้ ตามความเหมาะสม (ไม่มีบทลงโทษ):
    - base_points (default 10)
    - +โบนัสตามเวลาที่คาดว่าจะใช้ (ทุก 30 นาที +2 สูงสุด +8) — งานใช้เวลานานได้มากกว่า
    - +โบนัส 5 แต้มถ้าทำเสร็จก่อนกำหนดส่ง (ถ้ามี deadline) — ไม่หักถ้าเลย
    """
    base = task.base_points or 10
    points = base

    est = task.estimated_time
    if est and est > 0:
        bonus = min(est // 30, 4) * 2
        points += bonus

    if task.deadline and datetime.datetime.utcnow() <= task.deadline:
        points += 5

    return points


# ---------- Settings helpers (AppSetting key-value) ----------

def get_setting(db, key, default=None):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def set_setting(db, key, value):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = str(value)
    else:
        db.add(AppSetting(key=key, value=str(value)))


def award_points(db, amount):
    """เติมแต้มทั้งสองบัญชี: current_points (ใช้แลกได้) + lifetime_points (สำหรับ level/achievement)"""
    current = int(get_setting(db, "current_points", 0))
    lifetime = int(get_setting(db, "lifetime_points", 0))
    new_current = current + amount
    new_lifetime = lifetime + amount
    set_setting(db, "current_points", new_current)
    set_setting(db, "lifetime_points", new_lifetime)
    db.commit()
    return {"current": new_current, "lifetime": new_lifetime}


def reverse_points(db, amount):
    """หักแต้มคืน (ตอนกดยกเลิกว่าทำเสร็จ) — ลดทั้ง current + lifetime แต่ไม่ติดลบ"""
    current = int(get_setting(db, "current_points", 0))
    lifetime = int(get_setting(db, "lifetime_points", 0))
    new_current = max(0, current - amount)
    new_lifetime = max(0, lifetime - amount)
    set_setting(db, "current_points", new_current)
    set_setting(db, "lifetime_points", new_lifetime)
    db.commit()
    return {"current": new_current, "lifetime": new_lifetime}


# ---------- Streak (ใจดี: มี grace 1 วัน) ----------

def update_streak(db, today):
    """นับวันทำภารกิจติดต่อกัน — ข้ามไป 1 วัน (grace) จะไม่หลุด streak
    คืน streak ปัจจุบัน"""
    count = int(get_setting(db, "streak_count", 0))
    last = get_setting(db, "streak_last_date")

    if last == str(today):
        return count

    yesterday = today - datetime.timedelta(days=1)
    day_before = today - datetime.timedelta(days=2)

    if last == str(yesterday):
        count += 1
    elif last == str(day_before):
        pass  # ให้อภัย 1 วัน — count คงเดิม ไม่เพิ่มไม่หลุด
    else:
        count = 1

    set_setting(db, "streak_count", count)
    set_setting(db, "streak_last_date", str(today))

    best = int(get_setting(db, "streak_best", 0))
    if count > best:
        set_setting(db, "streak_best", count)
    db.commit()
    return count


def recompute_streak(db, today, tz_offset_hours=7.0):
    """คำนวณ streak ใหม่ทั้งหมดจากงานที่ DONE จริง ๆ (completed_at เก็บเป็น UTC)
    ใช้ตอนกด "ยกเลิกว่าทำเสร็จ" เพื่อให้ทุกอย่างกลับไปเหมือนยังไม่ได้ทำ (เกรซ 1 วันคงเดิม)"""
    local_dates = set()
    rows = db.query(Task.completed_at).filter(Task.status == "DONE", Task.completed_at.isnot(None)).all()
    for (completed_at,) in rows:
        local_dt = completed_at + datetime.timedelta(hours=tz_offset_hours)
        if local_dt.date() <= today:
            local_dates.add(local_dt.date())

    count = 0
    last = None
    for d in sorted(local_dates):
        if last is None:
            count = 1
        elif d == last:
            continue  # วันเดียวกัน ไม่นับซ้ำ
        elif d == last + datetime.timedelta(days=1):
            count += 1
        elif d == last + datetime.timedelta(days=2):
            pass  # เกรซ 1 วัน — count คงเดิม ไม่เพิ่มไม่หลุด
        else:
            count = 1
        last = d

    set_setting(db, "streak_count", count)
    if last:
        set_setting(db, "streak_last_date", str(last))
    else:
        set_setting(db, "streak_last_date", None)
    best = int(get_setting(db, "streak_best", 0))
    if count > best:
        set_setting(db, "streak_best", count)
    db.commit()
    return count


# ---------- Achievements ----------

DEFAULT_ACHIEVEMENTS = [
    {"key": "first_task", "title": "ก้าวแรก", "description": "ทำงานแรกสำเร็จ", "icon": "🌱", "points": 20,
     "condition_type": "tasks_done", "condition_value": 1},
    {"key": "tasks_10", "title": "จังหวะดี", "description": "ทำงานครบ 10 งาน", "icon": "🎯", "points": 50,
     "condition_type": "tasks_done", "condition_value": 10},
    {"key": "tasks_50", "title": "เครื่องจักรใจเย็น", "description": "ทำงานครบ 50 งาน", "icon": "🚀", "points": 150,
     "condition_type": "tasks_done", "condition_value": 50},
    {"key": "streak_3", "title": "ติดเครื่อง", "description": "ทำภารกิจติดต่อกัน 3 วัน", "icon": "🔥", "points": 30,
     "condition_type": "streak_days", "condition_value": 3},
    {"key": "streak_7", "title": "หนึ่งสัปดาห์ต่อเนื่อง", "description": "ทำภารกิจติดต่อกัน 7 วัน", "icon": "⭐",
     "points": 100, "condition_type": "streak_days", "condition_value": 7},
    {"key": "points_500", "title": "สะสม 500 แต้ม", "description": "ได้แต้มสะสมรวม 500", "icon": "💎", "points": 100,
     "condition_type": "lifetime_points", "condition_value": 500},
    {"key": "goal_1", "title": "มองไกล", "description": "สร้างเป้าหมายแรก", "icon": "🧭", "points": 25,
     "condition_type": "goals_created", "condition_value": 1},
    {"key": "energy_1", "title": "ฟังตัวเอง", "description": "บันทึกพลังครั้งแรก", "icon": "🔋", "points": 10,
     "condition_type": "energy_logs", "condition_value": 1},
]


def seed_achievements(db):
    """ลง achievement พื้นฐาน ถ้ายังไม่มี (idempotent)"""
    existing = {a.key for a in db.query(Achievement).all()}
    for spec in DEFAULT_ACHIEVEMENTS:
        if spec["key"] in existing:
            continue
        db.add(Achievement(id=str(uuid.uuid4()), **spec))
    db.commit()


def check_achievements(db):
    """ตรวจและปลดล็อก achievement ที่ถึงเงื่อนไขแล้ว (ครั้งเดียวต่อตัว)
    โบนัสแต้มจะเติมให้ทั้ง current + lifetime
    คืน list ของ achievement ที่เพิ่งปลดล็อก [{key,title,icon,description,points}]"""
    seed_achievements(db)
    values = {
        "tasks_done": db.query(Task).filter(Task.status == "DONE").count(),
        "streak_days": int(get_setting(db, "streak_count", 0)),
        "lifetime_points": int(get_setting(db, "lifetime_points", 0)),
        "goals_created": db.query(Goal).count(),
        "energy_logs": db.query(EnergyLog).count(),
    }
    unlocked_keys = {u.achievement_key for u in db.query(UnlockedAchievement).all()}
    newly = []
    for ach in db.query(Achievement).all():
        if ach.key in unlocked_keys:
            continue
        if values.get(ach.condition_type, 0) >= ach.condition_value:
            db.add(UnlockedAchievement(id=str(uuid.uuid4()), achievement_key=ach.key))
            if ach.points and ach.points > 0:
                award_points(db, ach.points)
            newly.append({
                "key": ach.key,
                "title": ach.title,
                "description": ach.description,
                "icon": ach.icon,
                "points": ach.points,
            })
    db.commit()
    return newly


def gamification_status(db):
    """สถานะเต็มรูปแบบสำหรับหน้า gamification"""
    seed_achievements(db)
    current = int(get_setting(db, "current_points", 0))
    lifetime = int(get_setting(db, "lifetime_points", 0))
    unlocked_keys = {u.achievement_key for u in db.query(UnlockedAchievement).all()}
    achievements = []
    for ach in db.query(Achievement).order_by(Achievement.created_at).all():
        achievements.append({
            "key": ach.key,
            "title": ach.title,
            "description": ach.description,
            "icon": ach.icon,
            "points": ach.points,
            "unlocked": ach.key in unlocked_keys,
        })
    return {
        "points": current,
        "lifetime_points": lifetime,
        "level": level_info(lifetime),
        "streak": {
            "current": int(get_setting(db, "streak_count", 0)),
            "best": int(get_setting(db, "streak_best", 0)),
        },
        "achievements": achievements,
    }


# ---------- Nudge Mode (ใจดี ไม่บังคับ) ----------

NUDGE_MESSAGES = [
    "มีงานค้างอยู่ ถ้าว่าง ๆ เลือกทำอย่างหนึ่งเบา ๆ ก็พอ",
    "แค่เริ่มก็ดีแล้ว — เริ่มจากอันที่ง่ายสุดก่อนได้เลย",
    "ไม่ต้องทำทุกอย่างวันนี้ ทำอย่างเดียวที่นึกออกก่อนก็พอ",
]

NUDGE_TIMES_DEFAULT = ["09:00", "15:00", "20:00"]


def get_nudge_settings(db):
    enabled = get_setting(db, "nudge_enabled", "true") == "true"
    try:
        times = json.loads(get_setting(db, "nudge_times", json.dumps(NUDGE_TIMES_DEFAULT)))
    except Exception:
        times = list(NUDGE_TIMES_DEFAULT)
    return {"enabled": enabled, "times": times}


def set_nudge_settings(db, enabled, times):
    set_setting(db, "nudge_enabled", "true" if enabled else "false")
    set_setting(db, "nudge_times", json.dumps(times))
    db.commit()


def nudge_status(db, today, now):
    """ควรแสดง nudge ตอนนี้ไหม — ใจดี: เปิด/ปิดได้, วันละครั้ง, ปิดวันนั้นได้

    today: local date, now: datetime ที่คิดตาม local timezone แล้ว (main.py ส่งมาให้)
    คืน {"should_show": bool, "message": str, "reason": str}
    """
    settings = get_nudge_settings(db)
    if not settings["enabled"]:
        return {"should_show": False, "message": "", "reason": "ปิดอยู่"}

    if get_setting(db, "nudge_last_date", "") == str(today):
        return {"should_show": False, "message": "", "reason": "แสดงแล้ววันนี้"}

    pending = db.query(Task).filter(Task.status == "TODO").count()
    if pending <= 0:
        return {"should_show": False, "message": "", "reason": "ไม่มีงานค้าง"}

    now_hm = now.strftime("%H:%M")
    times = sorted(settings["times"])
    triggered = [t for t in times if now_hm >= t]
    if not triggered:
        return {"should_show": False, "message": "", "reason": "ยังไม่ถึงเวลา"}

    idx = (now.hour * 60 + now.minute) % len(NUDGE_MESSAGES)
    return {
        "should_show": True,
        "message": NUDGE_MESSAGES[idx],
        "reason": f"มีงานค้าง {pending} รายการ",
    }


def dismiss_nudge(db, today):
    set_setting(db, "nudge_last_date", str(today))
    db.commit()


# ---------- Rewards: จำกัดสิทธิ์ใช้ต่อวัน/เดือน/ปี ----------

def reward_usage(db, reward_id, now_local):
    """นับจำนวนครั้งที่แลกรางวัลนี้ไปแล้วภายในรอบวัน/เดือน/ปี (ตาม timezone ผู้ใช้)
    ใช้ now_local (datetime) เป็นช่วงตัดรอบ — ห้ามใช้ UTC ตรง ๆ"""
    def _count(since):
        return db.query(RewardRedemption).filter(
            RewardRedemption.reward_id == reward_id,
            RewardRedemption.redeemed_at >= since,
        ).count()

    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    year_start = day_start.replace(month=1, day=1)
    return {
        "day": _count(day_start),
        "month": _count(month_start),
        "year": _count(year_start),
    }


def reward_available(reward, usage):
    """เช็คว่ารางวัลยังใช้ได้ในรอบนี้หรือไม่ (ตาม max_per_day/month/year ที่ตั้งไว้)
    None = ไม่จำกัด"""
    if reward.max_per_day is not None and usage["day"] >= reward.max_per_day:
        return False, f"วันนี้ใช้ครบ {reward.max_per_day} ครั้งแล้ว"
    if reward.max_per_month is not None and usage["month"] >= reward.max_per_month:
        return False, f"เดือนนี้ใช้ครบ {reward.max_per_month} ครั้งแล้ว"
    if reward.max_per_year is not None and usage["year"] >= reward.max_per_year:
        return False, f"ปีนี้ใช้ครบ {reward.max_per_year} ครั้งแล้ว"
    return True, ""


def record_redemption(db, reward_id, now_local):
    db.add(RewardRedemption(id=str(uuid.uuid4()), reward_id=reward_id, redeemed_at=now_local))
    db.commit()

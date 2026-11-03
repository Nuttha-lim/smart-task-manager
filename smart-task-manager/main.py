from fastapi import FastAPI, Body, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import datetime
import os
import re
import uuid
import json
from models import Base, Task, EnergyLog, AppSetting, Goal, Reward, RewardRedemption, Notification, Device, SpellPref, Holiday, ClassSchedule, TripPlan
from database import engine, SessionLocal
from escalation import compute_urgency, todo_tasks_with_deadline

app = FastAPI()

# CORS — production ตั้ง ALLOWED_ORIGINS เป็น origin ของ frontend (เช่น https://<user>.github.io)
# คั่นหลาย origin ด้วยลูกน้ำ; ไม่ตั้ง = เปิดทุก origin (dev)
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# สร้างตารางถ้ามี DB พร้อม (ถ้า Docker ยังไม่เปิด ไม่ควรทำให้แอป import ไม่ได้)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print("WARNING: ไม่สามารถเชื่อมต่อฐานข้อมูลตอน start:", e)


@app.get("/")
def read_root():
    return {"message": "Hello Smart Task Manager"}


def _task_to_dict(t):
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "status": t.status,
        "estimated_time": t.estimated_time,
        "deadline": str(t.deadline.date()) if t.deadline else None,
        "deadline_time": t.deadline_time,
        "created_at": str(t.created_at),
        "completed_at": str(t.completed_at) if t.completed_at else None,
        "points_award": compute_task_points(t),
        "points_awarded": t.points_awarded,
    }


def _notification_to_dict(n):
    return {
        "id": n.id,
        "task_id": n.task_id,
        "message": n.message,
        "urgency": n.urgency,
        "read": n.read,
        "created_at": str(n.created_at),
    }


def get_tz_offset():
    db = SessionLocal()
    setting = db.query(AppSetting).filter(AppSetting.key == "tz_offset_hours").first()
    db.close()
    return float(setting.value) if setting else 7.0  # default ไทย UTC+7


def get_local_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=get_tz_offset())


def get_local_today():
    return get_local_now().date()


@app.get("/settings/timezone")
def get_timezone():
    return {"offset_hours": get_tz_offset()}


@app.post("/settings/timezone")
def set_timezone(offset_hours: float):
    db = SessionLocal()
    existing = db.query(AppSetting).filter(AppSetting.key == "tz_offset_hours").first()
    if existing:
        existing.value = str(offset_hours)
    else:
        db.add(AppSetting(key="tz_offset_hours", value=str(offset_hours)))
    db.commit()
    db.close()
    return {"offset_hours": offset_hours}


def get_holidays_enabled():
    """วันหยุดในปฏิทินเปิด/ปิดได้ (default เปิด) — วันหยุดแต่ละประเทศไม่เหมือนกัน"""
    db = SessionLocal()
    setting = db.query(AppSetting).filter(AppSetting.key == "show_holidays").first()
    db.close()
    if setting is None:
        return True
    return setting.value != "false" and setting.value != "0"


@app.get("/settings/holidays")
def get_holidays_setting():
    return {"enabled": get_holidays_enabled()}


@app.post("/settings/holidays")
def set_holidays_setting(enabled: bool):
    db = SessionLocal()
    existing = db.query(AppSetting).filter(AppSetting.key == "show_holidays").first()
    if existing:
        existing.value = "1" if enabled else "0"
    else:
        db.add(AppSetting(key="show_holidays", value="1" if enabled else "0"))
    db.commit()
    db.close()
    return {"enabled": enabled}


@app.post("/tasks")
def create_task(title: str, description: str = None, deadline: Optional[str] = None, deadline_time: str = "23:59", estimated_time: Optional[int] = None):
    db = SessionLocal()
    parsed_deadline = None
    if deadline:
        try:
            parsed_deadline = datetime.datetime.strptime(deadline, "%Y-%m-%d")
        except ValueError:
            parsed_deadline = None
    new_task = Task(
        id=str(uuid.uuid4()), title=title, description=description,
        deadline=parsed_deadline, deadline_time=deadline_time,
        estimated_time=estimated_time,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    result = _task_to_dict(new_task)
    db.close()
    return result


@app.get("/tasks")
def list_tasks():
    db = SessionLocal()
    tasks = db.query(Task).all()
    result = [_task_to_dict(t) for t in tasks]
    db.close()
    return result


@app.put("/tasks/{task_id}")
def update_task(task_id: str, title: str = None, description: str = None,
                deadline: Optional[str] = None, deadline_time: str = None,
                estimated_time: Optional[int] = None):
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return {"error": "ไม่พบ task นี้"}
    if title is not None: task.title = title
    if description is not None: task.description = description
    if deadline is not None:
        task.deadline = datetime.datetime.strptime(deadline, "%Y-%m-%d")
    if deadline_time is not None: task.deadline_time = deadline_time
    if estimated_time is not None: task.estimated_time = estimated_time
    db.commit()
    result = _task_to_dict(task)
    db.close()
    return result


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        db.delete(task)
        db.commit()
    db.close()
    return {"deleted": True}


@app.patch("/tasks/{task_id}")
def complete_task(task_id: str):
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return {"error": "ไม่พบ task นี้"}
    if task.status == "DONE":
        db.close()
        return {"error": "งานนี้เสร็จไปแล้ว"}
    task.status = "DONE"
    points_earned = compute_task_points(task)
    task.completed_at = datetime.datetime.utcnow()
    task.points_awarded = points_earned
    db.commit()
    award_points(db, points_earned)
    streak = update_streak(db, get_local_today())
    unlocked = check_achievements(db)
    status = gamification_status(db)
    db.close()
    return {
        "id": task_id,
        "status": "DONE",
        "points_earned": points_earned,
        "total_points": status["points"],
        "lifetime_points": status["lifetime_points"],
        "level": status["level"],
        "streak": status["streak"],
        "unlocked_achievements": unlocked,
    }


@app.post("/tasks/{task_id}/undo")
def undo_complete_task(task_id: str):
    """กดยกเลิกว่ายังทำไม่เสร็จ — กลับเป็น TODO + หักแต้มที่ได้คืน (current + lifetime)
    กันการปั๊มแต้มเพื่อแลกรางวัล; streak คำนวณใหม่จากงานที่ DONE จริง"""
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return {"error": "ไม่พบ task นี้"}
    if task.status != "DONE":
        db.close()
        return {"error": "งานนี้ยังไม่ได้เสร็จ ไม่มีอะไรให้ยกเลิก"}

    awarded = task.points_awarded or compute_task_points(task)
    task.status = "TODO"
    task.completed_at = None
    task.points_awarded = None
    db.commit()
    reverse_points(db, awarded)
    recompute_streak(db, get_local_today(), tz_offset_hours=get_tz_offset())
    status = gamification_status(db)
    db.close()
    return {
        "id": task_id,
        "status": "TODO",
        "points_reversed": awarded,
        "total_points": status["points"],
        "lifetime_points": status["lifetime_points"],
        "level": status["level"],
        "streak": status["streak"],
    }


from ai_service import parse_task_text, parse_tasks_text

@app.post("/parse-task")
def parse_task(text: str):
    """แปลงข้อความ → งาน 1 ตัวหรือหลายตัว (AI แยกให้เอง) — คืน {tasks, ...field แรก compat}"""
    tasks = parse_tasks_text(text, today=get_local_today())
    first = tasks[0] if tasks else {}
    return {
        "tasks": tasks,
        "title": first.get("title"),
        "estimated_time": first.get("estimated_time"),
        "deadline": first.get("deadline"),
        "deadline_time": first.get("deadline_time"),
    }


@app.post("/energy-log")
def create_energy_log(level: int):
    db = SessionLocal()
    new_log = EnergyLog(
        id=str(uuid.uuid4()),
        energy_level=level,
        log_date=get_local_today()
    )
    db.add(new_log)
    db.commit()
    unlocked = check_achievements(db)
    result = {
        "energy_level": level,
        "log_date": str(new_log.log_date),
        "unlocked_achievements": unlocked,
    }
    db.close()
    return result


@app.get("/energy-log/today")
def get_today_energy():
    db = SessionLocal()
    log = db.query(EnergyLog).filter(
        EnergyLog.log_date == get_local_today()
    ).order_by(EnergyLog.created_at.desc()).first()
    db.close()
    if log:
        return {"energy_level": log.energy_level, "log_date": str(log.log_date)}
    return {"energy_level": None}


@app.get("/onboarding/status")
def get_onboarding_status():
    db = SessionLocal()
    setting = db.query(AppSetting).filter(AppSetting.key == "onboarding_done").first()
    db.close()
    return {"done": setting is not None and setting.value == "true"}


@app.post("/onboarding/complete")
def complete_onboarding():
    db = SessionLocal()
    existing = db.query(AppSetting).filter(AppSetting.key == "onboarding_done").first()
    if existing:
        existing.value = "true"
    else:
        db.add(AppSetting(key="onboarding_done", value="true"))
    db.commit()
    db.close()
    return {"done": True}


from ai_service import decompose_goal, assess_breakdown, normalize_subtasks
from gamification import (
    level_info,
    compute_task_points,
    award_points,
    reverse_points,
    update_streak,
    recompute_streak,
    seed_achievements,
    check_achievements,
    gamification_status,
    get_nudge_settings,
    set_nudge_settings,
    nudge_status,
    dismiss_nudge,
    reward_usage,
    reward_available,
    record_redemption,
    get_setting,
)
from calendar_service import (
    seed_holidays,
    list_holidays,
    parse_timetable_text,
    list_schedules,
    create_schedules,
    clean_timetable_entries,
    detect_timetable,
    parse_timetable_command,
    build_timetable_proposal,
    apply_timetable_change,
    seed_default_routines,
    list_routines,
    create_routine,
    update_routine,
    delete_routine,
    parse_cancel_request,
    find_classes_to_cancel,
    cancellations_in_range,
    list_cancellations,
    create_cancellation,
    delete_cancellation,
)

# ลง achievement พื้นฐาน + วันหยุดปีปัจจุบัน (idempotent) — ถ้า DB ยังไม่พร้อม ข้ามไปก่อน
try:
    db = SessionLocal()
    seed_achievements(db)
    seed_holidays(db, get_local_today().year)
    seed_default_routines(db)
    db.close()
except Exception as e:
    print("WARNING: ไม่สามารถ seed ข้อมูลพื้นฐานตอน start:", e)

# Production: ตั้ง env BACKGROUND_WORKER=1 ให้แอปวิ่ง poll งานด่วนในตัว (ไม่ต้องมี Celery/Redis)
from background_worker import start_if_enabled
start_if_enabled()


# ---------- Goals / Life Goal Decompiler ----------

@app.post("/goals/decompose")
def decompose_goal_preview(title: str):
    """แตกเป้าหมายเป็นงานย่อย + ประเมินคุณภาพ (ยังไม่บันทึก)
    ให้ผู้ใช้ตรวจ "พอไหม ตรงไหนต้องแก้" ก่อนยืนยันบันทึกจริง
    คืน tasks เป็น [{title, estimated_time}] — ให้ผู้ใช้แก้เวลาได้ก่อนยืนยัน"""
    try:
        raw = decompose_goal(title)
    except Exception:
        raw = []
    tasks = normalize_subtasks(raw)
    assessment = assess_breakdown([t["title"] for t in tasks])
    return {"title": title, "tasks": tasks, "assessment": assessment}


@app.post("/goals")
def create_goal(title: str, desire_score: int = 3, urgency_score: int = 3,
                target_date: str = None,
                tasks: Optional[list] = Body(None)):
    """สร้างเป้าหมาย + งานย่อย
    ถ้าส่ง tasks (JSON array ใน body) จะใช้รายการที่ผู้ใช้ยืนยัน/แก้แล้ว —
    แต่ละรายการเป็น string หรือ {title, estimated_time} ก็ได้ (กัน 422 ใช้ Optional[list] + กรองเอง)
    ถ้าไม่ส่ง จะให้ AI แตกให้อัตโนมัติ (compat กับเวอร์ชันเก่า)
    target_date (YYYY-MM-DD) = วันเป้าหมาย/วันสอบ — ใช้จัดตารางเตรียม (study plan) ได้
    """
    target = None
    if target_date:
        try:
            target = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
        except Exception:
            target = None  # วันที่อ่านไม่ได้ → ไม่ crash เก็บไว้เป็น null
    db = SessionLocal()
    goal_id = str(uuid.uuid4())
    new_goal = Goal(id=goal_id, title=title, desire_score=desire_score,
                    urgency_score=urgency_score, target_date=target)
    db.add(new_goal)
    db.commit()

    if tasks is None:
        try:
            tasks = decompose_goal(title)
        except Exception:
            tasks = []

    created_tasks = []
    for item in normalize_subtasks(tasks):
        t = Task(id=str(uuid.uuid4()), title=item["title"],
                 goal_id=goal_id, estimated_time=item["estimated_time"])
        db.add(t)
        created_tasks.append(t)
    db.commit()

    unlocked = check_achievements(db)
    result = {
        "id": goal_id,
        "title": title,
        "tasks": [_task_to_dict(t) for t in created_tasks],
        "unlocked_achievements": unlocked,
    }
    db.close()
    return result


@app.get("/goals")
def list_goals():
    db = SessionLocal()
    goals = db.query(Goal).all()
    result = []
    for g in goals:
        tasks = db.query(Task).filter(Task.goal_id == g.id).all()
        result.append({
            "id": g.id, "title": g.title,
            "desire_score": g.desire_score, "urgency_score": g.urgency_score,
            "target_date": str(g.target_date) if g.target_date else None,
            "tasks": [_task_to_dict(t) for t in tasks],
        })
    db.close()
    return result


@app.get("/goals/{goal_id}/study-plan")
def goal_study_plan(goal_id: str, energy_level: int = 3):
    """Study Plan ระยะยาว (Exam-Prep): กระจายงานย่อยของเป้าหมายไปตามวันที่เหลือ
    ก่อนถึง target_date — deterministic ไม่เรียก AI (ดู plan_service.build_goal_plan)"""
    db = SessionLocal()
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        db.close()
        return JSONResponse(status_code=404, content={"detail": "ไม่พบเป้าหมายนี้"})
    if not goal.target_date:
        db.close()
        return JSONResponse(status_code=400, content={"detail": "ยังไม่ได้ตั้งวันเป้าหมาย"})
    plan = build_goal_plan(db, goal, energy_level)
    db.close()
    if plan is None:
        return JSONResponse(status_code=400, content={"detail": "วันเป้าหมายผ่านไปแล้ว — เลื่อนวันหรือตั้งใหม่"})
    return plan


# ---------- Gamification: Points ----------

def get_current_points():
    db = SessionLocal()
    setting = db.query(AppSetting).filter(AppSetting.key == "current_points").first()
    db.close()
    return int(setting.value) if setting else 0


def add_points(amount: int):
    db = SessionLocal()
    setting = db.query(AppSetting).filter(AppSetting.key == "current_points").first()
    current = int(setting.value) if setting else 0
    new_value = current + amount
    if setting:
        setting.value = str(new_value)
    else:
        db.add(AppSetting(key="current_points", value=str(new_value)))
    db.commit()
    db.close()
    return new_value


@app.get("/points")
def get_points():
    status = gamification_status(SessionLocal())
    return {
        "points": status["points"],
        "lifetime_points": status["lifetime_points"],
        "level": status["level"],
        "streak": status["streak"],
    }


# ---------- Gamification: Rewards ----------

from ai_service import suggest_reward_cost, generate_reward_ideas


def _reward_to_dict(r, db, now_local=None):
    d = {
        "id": r.id, "title": r.title, "point_cost": r.point_cost, "locked": r.locked,
        "source": r.source,
        "max_per_day": r.max_per_day, "max_per_month": r.max_per_month,
        "max_per_year": r.max_per_year,
    }
    if now_local is not None:
        usage = reward_usage(db, r.id, now_local)
        ok, msg = reward_available(r, usage)
        d["usage"] = usage
        d["available"] = ok
        d["unavailable_reason"] = msg
    return d


@app.post("/rewards")
def create_reward(title: str, max_per_day: Optional[int] = None,
                  max_per_month: Optional[int] = None, max_per_year: Optional[int] = None):
    """สร้างรางวัล — แต้มกำหนดโดย AI จากชื่อรางวัล (ผู้ใช้ตั้งเองไม่ได้)"""
    db = SessionLocal()
    new_id = str(uuid.uuid4())
    point_cost = suggest_reward_cost(title)
    new_reward = Reward(id=new_id, title=title, point_cost=point_cost,
                        locked=False, source="user",
                        max_per_day=max_per_day, max_per_month=max_per_month,
                        max_per_year=max_per_year)
    db.add(new_reward)
    db.commit()
    result = _reward_to_dict(new_reward, db)
    db.close()
    return result


@app.post("/rewards/ideas")
def add_reward_from_ideas(title: str):
    """เพิ่มรางวัลจากไอเดียที่ AI เสนอมา (แต้ม + จำกัดสิทธิ์ตามที่ AI คิดให้ ผู้ใช้ตั้งเองไม่ได้)"""
    db = SessionLocal()
    new_id = str(uuid.uuid4())
    idea = next((i for i in generate_reward_ideas(10) if i["title"] == title), None)
    if idea:
        new_reward = Reward(id=new_id, title=idea["title"], point_cost=idea["point_cost"],
                            locked=False, source="ai",
                            max_per_day=idea["max_per_day"], max_per_month=idea["max_per_month"],
                            max_per_year=idea["max_per_year"])
    else:
        cost = suggest_reward_cost(title)
        new_reward = Reward(id=new_id, title=title, point_cost=cost,
                            locked=False, source="ai",
                            max_per_day=1, max_per_month=8, max_per_year=80)
    db.add(new_reward)
    db.commit()
    result = _reward_to_dict(new_reward, db)
    db.close()
    return result


@app.get("/rewards")
def list_rewards():
    db = SessionLocal()
    now_local = get_local_now()
    rewards = db.query(Reward).order_by(Reward.created_at).all()
    result = [_reward_to_dict(r, db, now_local) for r in rewards]
    db.close()
    return result


@app.get("/rewards/ideas")
def get_reward_ideas(n: int = 5):
    """AI คิดไอเดียรางวัลให้อย่างน้อย n ช่อง (พร้อมแต้ม + จำกัดสิทธิ์) — ยังไม่บันทึก"""
    return {"ideas": generate_reward_ideas(n)}


@app.post("/rewards/{reward_id}/redeem")
def redeem_reward(reward_id: str):
    db = SessionLocal()
    reward = db.query(Reward).filter(Reward.id == reward_id).first()
    if not reward:
        db.close()
        return {"error": "ไม่พบรางวัลนี้"}
    now_local = get_local_now()
    usage = reward_usage(db, reward_id, now_local)
    available, reason = reward_available(reward, usage)
    if not available:
        db.close()
        return {"error": f"รางวัลนี้ใช้ไม่ได้ช่วงนี้ — {reason}",
                "current_points": int(get_setting(db, "current_points", 0)),
                "needed": reward.point_cost}
    current = get_current_points()
    if current < reward.point_cost:
        db.close()
        return {"error": "แต้มไม่พอ", "current_points": current, "needed": reward.point_cost}
    new_points = add_points(-reward.point_cost)
    record_redemption(db, reward_id, now_local)
    db.close()
    return {"redeemed": True, "reward": reward.title, "remaining_points": new_points}


@app.delete("/rewards/{reward_id}")
def delete_reward(reward_id: str):
    db = SessionLocal()
    reward = db.query(Reward).filter(Reward.id == reward_id).first()
    if not reward:
        db.close()
        return {"error": "ไม่พบรางวัลนี้"}
    db.delete(reward)
    db.commit()
    db.close()
    return {"deleted": True, "id": reward_id}


# ---------- Gamification: หน้าสถานะเต็มรูปแบบ ----------

@app.get("/gamification")
def get_gamification():
    db = SessionLocal()
    try:
        return gamification_status(db)
    finally:
        db.close()


# ---------- Nudge Mode (ใจดี ไม่บังคับ — escape valve เสมอ) ----------

@app.get("/settings/nudge")
def read_nudge_settings():
    db = SessionLocal()
    try:
        return get_nudge_settings(db)
    finally:
        db.close()


@app.post("/settings/nudge")
def write_nudge_settings(enabled: bool, times: str):
    """times = JSON array ของ "HH:MM" เช่น '["09:00","15:00"]'"""
    import json
    try:
        times_list = json.loads(times)
        times_list = [t for t in times_list if isinstance(t, str) and len(t) == 5 and ":" in t]
    except Exception:
        times_list = []
    db = SessionLocal()
    try:
        set_nudge_settings(db, enabled, times_list)
    finally:
        db.close()
    return {"enabled": enabled, "times": times_list}


@app.get("/nudge")
def get_nudge():
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=get_tz_offset())
        return nudge_status(db, get_local_today(), now)
    finally:
        db.close()


@app.post("/nudge/dismiss")
def dismiss_nudge_today():
    db = SessionLocal()
    try:
        dismiss_nudge(db, get_local_today())
    finally:
        db.close()
    return {"dismissed": True}


# ---------- Dynamic Break Generator ----------

BREAK_ACTIVITIES = {
    "low": ["นอนอืดไถโทรศัพท์", "หลับตาพัก 5 นาที", "ฟังเพลงเบาๆ"],
    "mid": ["เดินไปเซเว่น", "ยืดเส้นยืดสาย", "ชงกาแฟ/ชา"],
    "high": ["เดินเล่นนอกบ้าน", "วาดรูปจิบิเล่นๆ", "ทำกิจกรรมที่ชอบสั้นๆ"],
}

@app.get("/break-suggestion")
def get_break_suggestion(estimated_time: Optional[int] = None):
    db = SessionLocal()
    log = db.query(EnergyLog).filter(
        EnergyLog.log_date == get_local_today()
    ).order_by(EnergyLog.created_at.desc()).first()
    db.close()
    energy_level = log.energy_level if log else 3

    if estimated_time and estimated_time > 0:
        break_minutes = max(5, min(30, round(estimated_time * 0.2)))
    else:
        break_minutes = 10

    if energy_level <= 2:
        pool = BREAK_ACTIVITIES["low"]
    elif energy_level == 3:
        pool = BREAK_ACTIVITIES["mid"]
    else:
        pool = BREAK_ACTIVITIES["high"]

    import random
    activity = random.choice(pool)

    return {"break_minutes": break_minutes, "activity": activity, "energy_level": energy_level}


@app.get("/tasks/needs-deadline-check")
def get_tasks_needing_check():
    db = SessionLocal()
    tasks = db.query(Task).filter(
        Task.status == "TODO",
        Task.deadline.is_(None)
    ).order_by(Task.created_at.asc()).all()  # งานเก่าสุดก่อน

    now = datetime.datetime.utcnow()
    result = []
    for t in tasks:
        if t.last_deadline_check is None or (now - t.last_deadline_check).days >= 7:
            result.append(_task_to_dict(t))
    db.close()
    return result


@app.post("/tasks/{task_id}/deadline-check")
def respond_deadline_check(task_id: str, skip: bool = False, deadline: Optional[str] = None, deadline_time: str = "23:59"):
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return {"error": "ไม่พบ task นี้"}

    task.last_deadline_check = datetime.datetime.utcnow()
    if not skip and deadline:
        task.deadline = datetime.datetime.strptime(deadline, "%Y-%m-%d")
        task.deadline_time = deadline_time

    db.commit()
    result = _task_to_dict(task)
    db.close()
    return result


# ---------- Escalation Logic ----------
# Latest Start Time = Deadline - (Estimated Time + Buffer)
# compute_urgency ย้ายไปอยู่ที่ escalation.py (จุดเดียว) — worker/celery import จากที่เดียวกัน

@app.get("/tasks/escalations")
def get_escalations(buffer_minutes: int = 60):
    db = SessionLocal()
    tasks = todo_tasks_with_deadline(db)
    now = get_local_now()
    result = []
    for t in tasks:
        latest_start, seconds_to_latest, seconds_to_deadline, urgency = compute_urgency(t, buffer_minutes, now)
        d = _task_to_dict(t)
        d.update({
            "latest_start": latest_start.isoformat(),
            "urgency": urgency,
            "seconds_to_latest_start": round(seconds_to_latest),
            "seconds_to_deadline": round(seconds_to_deadline),
        })
        result.append(d)
    db.close()
    return result


# ---------- Notifications ----------

@app.get("/notifications")
def list_notifications():
    db = SessionLocal()
    notes = db.query(Notification).order_by(Notification.created_at.desc()).all()
    result = [_notification_to_dict(n) for n in notes]
    db.close()
    return result


@app.post("/notifications/{notification_id}/ack")
def ack_notification(notification_id: str):
    db = SessionLocal()
    note = db.query(Notification).filter(Notification.id == notification_id).first()
    if not note:
        db.close()
        return {"error": "ไม่พบการแจ้งเตือนนี้"}
    note.read = True
    db.commit()
    db.close()
    return {"ack": True}


# ---------- Devices (push notification) ----------

@app.get("/push/vapid-public-key")
def get_vapid_public_key_endpoint():
    """คืน VAPID public key (base64url) ให้ browser ใช้ subscribe ผ่าน PushManager
    (Web Push API — ไม่ต้องมี Firebase)"""
    from push_service import get_vapid_public_key
    db = SessionLocal()
    try:
        return {"public_key": get_vapid_public_key(db)}
    finally:
        db.close()


@app.post("/devices")
def register_device(device_token: str = Body(...), platform: str = Body(...)):
    db = SessionLocal()
    # upsert — device ตัวเดิม (token+platform ซ้ำ) ไม่งอกแถวใหม่ทุกครั้งที่แอปเปิด
    existing = db.query(Device).filter(
        Device.platform == platform, Device.device_token == device_token).first()
    if existing:
        db.close()
        return {"id": existing.id, "device_token": existing.device_token,
                "platform": existing.platform, "duplicate": True}
    new_id = str(uuid.uuid4())
    device = Device(id=new_id, device_token=device_token, platform=platform)
    db.add(device)
    db.commit()
    db.close()
    return {"id": new_id, "device_token": device_token, "platform": platform}


# ---------- Smart Typo Correction ----------

from spellcheck_service import resolve_text, clean_tokens


def get_spell_prefs(db):
    """คำที่ผู้ใช้เลือกไว้ชัดเจน: word -> corrected (ว่าง/None = คงคำเดิม)"""
    prefs = {}
    for p in db.query(SpellPref).all():
        prefs[p.word] = p.corrected
    return prefs


def get_trusted_words(db):
    """คำศัพท์ของผู้ใช้จากงาน/เป้าหมายที่เคยสร้างจริง (จำนิสัย)"""
    words = set()
    for (title,) in db.query(Task.title).all():
        words.update(clean_tokens(title or ""))
    for (desc,) in db.query(Task.description).filter(Task.description.isnot(None)).all():
        words.update(clean_tokens(desc or ""))
    for (title,) in db.query(Goal.title).all():
        words.update(clean_tokens(title or ""))
    return words


@app.post("/spellcheck/auto-resolve")
def auto_resolve_spellcheck(text: str = ""):
    db = SessionLocal()
    try:
        pref_map = get_spell_prefs(db)
        trusted = get_trusted_words(db)
    finally:
        db.close()
    return resolve_text(text, pref_map, trusted)


@app.post("/spellcheck/pref")
def set_spell_pref(word: str, corrected: str = None):
    db = SessionLocal()
    existing = db.query(SpellPref).filter(SpellPref.word == word).first()
    if existing:
        existing.corrected = corrected
    else:
        db.add(SpellPref(id=str(uuid.uuid4()), word=word, corrected=corrected))
    db.commit()
    db.close()
    return {"word": word, "corrected": corrected}


# ---------- Calendar: วันหยุด (Holiday Auto-Population) ----------

@app.get("/holidays")
def get_holidays(year: Optional[int] = None):
    """วันหยุดของปี — ไม่ส่ง year = ปีปัจจุบัน (ตาม timezone ที่ตั้งไว้)"""
    db = SessionLocal()
    try:
        if year is None:
            year = get_local_today().year
        return list_holidays(db, year)
    finally:
        db.close()


# ---------- Calendar: Class Timetable Import ----------

@app.post("/timetable/parse")
def parse_timetable(text: str = Body("", embed=True)):
    """parse ข้อความตารางเรียนที่ผู้ใช้วางมา → ผู้ใช้ตรวจก่อนบันทึก (ยังไม่เซฟ)"""
    return parse_timetable_text(text)


@app.post("/timetable")
def save_timetable(tasks: Optional[list] = Body(None), replace: bool = False):
    """สร้างตารางเรียนจากรายการที่ผู้ใช้ยืนยันแล้ว (body = JSON array ของรายการ)
    replace=true → ล้างตารางเดิมก่อน (ใช้ตอนอัปโหลดตารางทั้งชุดจากแชท)
    รับ list เปล่า ๆ (ไม่บังคับ schema — ตัวกรองจะคัดรายการที่ใช้ไม่ได้ออกเอง)"""
    db = SessionLocal()
    try:
        if replace:
            for s in db.query(ClassSchedule).all():
                db.delete(s)
            db.commit()
        entries = tasks if tasks is not None else []
        created = create_schedules(db, entries)
    finally:
        db.close()
    return {"created": created, "count": len(created)}


@app.post("/timetable/apply-change")
def apply_timetable_change_endpoint(action: Optional[dict] = Body(None)):
    """ทำการแก้ตารางเรียนที่ผู้ใช้ยืนยันแล้วจากแชท (action จาก /chat intent update_timetable)
    เช่น {"kind": "add", ...} / {"kind": "delete", "subject": "คณิต"} / {"kind": "move", ...} / {"kind": "clear"}"""
    db = SessionLocal()
    try:
        return apply_timetable_change(db, action or {})
    finally:
        db.close()


@app.get("/timetable")
def get_timetable():
    db = SessionLocal()
    try:
        return list_schedules(db)
    finally:
        db.close()


@app.delete("/timetable/{schedule_id}")
def delete_schedule(schedule_id: str):
    db = SessionLocal()
    schedule = db.query(ClassSchedule).filter(ClassSchedule.id == schedule_id).first()
    if not schedule:
        db.close()
        return {"error": "ไม่พบรายการนี้"}
    db.delete(schedule)
    db.commit()
    db.close()
    return {"deleted": True, "id": schedule_id}


@app.post("/timetable/cancel")
def cancel_classes_endpoint(date: str, start_time: str = "00:00",
                            end_time: str = "23:59", reason: str = None):
    """ยกเลิกคาบเรียนเฉพาะวัน (ไม่แตะตารางรายสัปดาห์) — date = YYYY-MM-DD
    บันทึกเป็นประวัติเสมอ (แม้ไม่มีคาบทับ) แล้วคืนคาบที่โดนยกเลิกไปด้วย"""
    db = SessionLocal()
    try:
        try:
            d = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except Exception:
            return {"ok": False, "error": "date ต้องเป็น YYYY-MM-DD"}
        c = create_cancellation(db, d, start_time, end_time, reason)
        if not c:
            return {"ok": False, "error": "เวลาไม่ถูกต้อง (HH:MM และ start ต้องก่อน end)"}
        affected = find_classes_to_cancel(db, d, start_time, end_time)
        return {"ok": True, "cancellation": c, "affected": affected}
    finally:
        db.close()


@app.get("/timetable/cancellations")
def get_cancellations():
    """ประวัติการยกเลิกคาบเรียนเฉพาะวัน (เรียงวันล่าสุดก่อน)"""
    db = SessionLocal()
    try:
        return {"cancellations": list_cancellations(db)}
    finally:
        db.close()


@app.delete("/timetable/cancellations/{cancel_id}")
def delete_cancellation_endpoint(cancel_id: str):
    """ยกเลิกการยกเว้น (คืนคาบเรียนวันนั้นกลับมา)"""
    db = SessionLocal()
    try:
        if not delete_cancellation(db, cancel_id):
            return {"ok": False, "error": "ไม่เจอรายการนี้"}
        return {"ok": True, "deleted": True}
    finally:
        db.close()


# ---------- Calendar Overview (รวมทุกอย่างของเดือน) ----------

@app.get("/calendar")
def get_calendar(month: str = None):
    """ข้อมูลทั้งเดือนสำหรับหน้า calendar: งาน + พลังงาน + วันหยุด + ตารางเรียน
    month = "YYYY-MM" — ไม่ส่ง = เดือนปัจจุบัน (ตาม timezone ที่ตั้งไว้)"""
    db = SessionLocal()
    try:
        if month:
            try:
                year, mon = month.split("-")
                start = datetime.datetime(int(year), int(mon), 1)
            except Exception:
                today = get_local_today()
                start = datetime.datetime(today.year, today.month, 1)
        else:
            today = get_local_today()
            start = datetime.datetime(today.year, today.month, 1)
        end = (start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)

        tasks = db.query(Task).filter(Task.deadline.isnot(None),
                                      Task.deadline >= start,
                                      Task.deadline <= end).all()
        energy_logs = db.query(EnergyLog).filter(
            EnergyLog.log_date >= start.date(),
            EnergyLog.log_date <= end.date()).all()
        seed_holidays(db, start.year)  # auto-populate วันหยุดของปีนั้น (idempotent)
        holidays = db.query(Holiday).filter(
            Holiday.date >= start.date(),
            Holiday.date <= end.date()).all()
        holidays_enabled = get_holidays_enabled()

        return {
            "month": start.strftime("%Y-%m"),
            "tasks": [{
                "id": t.id,
                "title": t.title,
                "date": str(t.deadline.date()),
                "deadline_time": t.deadline_time,
                "status": t.status,
                "estimated_time": t.estimated_time,
            } for t in tasks],
            "energy_logs": [{
                "date": str(e.log_date),
                "energy_level": e.energy_level,
            } for e in energy_logs],
            "holidays": [{
                "date": str(h.date),
                "name": h.name,
                "kind": h.kind,
            } for h in holidays] if holidays_enabled else [],
            "holidays_enabled": holidays_enabled,
            "schedules": list_schedules(db),
            "routines": list_routines(db),
            "cancellations": cancellations_in_range(db, start.date(), end.date()),
        }
    finally:
        db.close()


# ---------- กิจวัตรประจำวัน (Routines) ----------

@app.get("/calendar/routines")
def get_routines():
    """รายการกิจวัตรที่เปิดใช้อยู่ (เรียงตามเวลา) — ถ้ายังไม่เคยตั้งไว้ให้ seed พื้นฐานก่อน"""
    db = SessionLocal()
    try:
        return {"routines": list_routines(db)}
    finally:
        db.close()


@app.get("/routines")
def get_routines_all():
    """รายการกิจวัตรทั้งหมดรวมที่ปิดไว้ (สำหรับหน้าจัดการ)"""
    db = SessionLocal()
    try:
        return {"routines": list_routines(db, include_disabled=True)}
    finally:
        db.close()


@app.post("/routines")
def create_routine_endpoint(title: str, time: str, description: str = None):
    """เพิ่มกิจวัตรใหม่ (title + time "HH:MM" บังคับ; description ว่างได้)"""
    db = SessionLocal()
    try:
        r = create_routine(db, title, time, description)
        if not r:
            return {"ok": False, "error": "title/time ไม่ถูกต้อง (time ต้องเป็น HH:MM)"}
        return {"ok": True, "routine": r}
    finally:
        db.close()


@app.put("/routines/{routine_id}")
def update_routine_endpoint(routine_id: str, title: str = None, time: str = None,
                            enabled: bool = None, description: str = None):
    """แก้กิจวัตร — ส่งเฉพาะ field ที่อยากเปลี่ยน"""
    db = SessionLocal()
    try:
        r = update_routine(db, routine_id, title, time, enabled, description)
        if not r:
            return {"ok": False, "error": "ไม่เจอกิจวัตรนี้"}
        return {"ok": True, "routine": r}
    finally:
        db.close()


@app.delete("/routines/{routine_id}")
def delete_routine_endpoint(routine_id: str):
    """ลบกิจวัตร"""
    db = SessionLocal()
    try:
        if not delete_routine(db, routine_id):
            return {"ok": False, "error": "ไม่เจอกิจวัตรนี้"}
        return {"ok": True, "deleted": True}
    finally:
        db.close()


# ---------- File Upload & AI Content Analysis ----------

from ai_service import analyze_file_text, analyze_image_file, plan_trip
from file_service import extract_text_from_file, is_image_file, is_supported

TEXT_EXCERPT_LIMIT = 3000


def _task_from_analysis(item):
    """แปลงงานจาก AI analysis เป็น dict ที่ /tasks/bulk รับได้ (กันของเสีย ไม่ crash ตาม §9)"""
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or "").strip()
    if not title:
        return None
    result = {"title": title}
    desc = (item.get("description") or "").strip()
    notes = (item.get("notes") or "").strip()
    combined = "\n".join(x for x in [desc, notes] if x)
    if combined:
        result["description"] = combined
    est = item.get("estimated_time")
    if isinstance(est, (int, float)) and est and est > 0:
        result["estimated_time"] = int(est)
    deadline = item.get("deadline")
    if isinstance(deadline, str) and deadline:
        try:
            datetime.datetime.strptime(deadline, "%Y-%m-%d")
            result["deadline"] = deadline
            dt = item.get("deadline_time")
            result["deadline_time"] = dt if isinstance(dt, str) and len(dt) == 5 else "23:59"
        except ValueError:
            pass
    return result


@app.post("/upload/analyze")
async def upload_analyze(file: UploadFile = File(...)):
    """อัปโหลดไฟล์ (pdf/docx/txt/รูปภาพ) → AI วิเคราะห์หางานในเอกสาร
    (ยังไม่บันทึก — ให้ผู้ใช้ตรวจก่อน ตามหลัก confirmation §9)"""
    filename = file.filename or "file"
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        return {"error": "ไฟล์ใหญ่เกินไป (จำกัด 15 MB)", "tasks": []}

    if not is_supported(filename):
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "?"
        return {"error": f"ไฟล์ .{ext} ยังอ่านไม่ได้ — ลองแปลงเป็น PDF/Word/ข้อความ หรือรูปภาพก่อน", "tasks": []}

    try:
        if is_image_file(filename):
            result = analyze_image_file(data, filename, get_local_today())
        else:
            text = extract_text_from_file(filename, data)
            result = analyze_file_text(text, get_local_today())
    except Exception as e:
        print("upload/analyze failed:", e)
        text = ""
        try:
            text = extract_text_from_file(filename, data)
        except Exception:
            pass
        return {
            "filename": filename,
            "warning": f"AI วิเคราะห์ไม่สำเร็จ — ลองอีกครั้งหรือลองไฟล์อื่น ({e})",
            "summary": None,
            "tasks": [],
            "text_excerpt": text[:TEXT_EXCERPT_LIMIT],
        }

    tasks = []
    for item in result.get("tasks") or []:
        t = _task_from_analysis(item)
        if t:
            tasks.append(t)
    return {
        "filename": filename,
        "summary": result.get("summary"),
        "tasks": tasks,
        "text_excerpt": None,
    }


@app.post("/tasks/bulk")
def bulk_create_tasks(tasks: Optional[list] = Body(None)):
    """สร้างงานหลายตัวพร้อมกัน (รายการที่ผู้ใช้ยืนยันแล้วจากไฟล์/ทริป)
    รับ list เปล่า ๆ (ไม่บังคับ schema — ตัวกรองจะคัดรายการที่ใช้ไม่ได้ออกเอง ไม่ 422)"""
    db = SessionLocal()
    created = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        deadline = None
        d = item.get("deadline")
        if isinstance(d, str) and d:
            try:
                deadline = datetime.datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                deadline = None
        est = item.get("estimated_time")
        try:
            est = int(est) if est else None
        except (TypeError, ValueError):
            est = None
        t = Task(
            id=str(uuid.uuid4()), title=title,
            description=(item.get("description") or None),
            deadline=deadline,
            deadline_time=(item.get("deadline_time") or "23:59"),
            estimated_time=est,
        )
        db.add(t)
        created.append(t)
    db.commit()
    result = [_task_to_dict(t) for t in created]
    db.close()
    return {"created": result, "count": len(result)}


# ---------- Travel Planning ----------

def _trip_to_dict(plan):
    return {
        "id": plan.id,
        "destination": plan.destination,
        "start_date": str(plan.start_date) if plan.start_date else None,
        "end_date": str(plan.end_date) if plan.end_date else None,
        "notes": plan.notes,
        "days": json.loads(plan.days_json) if plan.days_json else [],
        "prep_tasks": json.loads(plan.prep_tasks_json) if plan.prep_tasks_json else [],
        "created_at": str(plan.created_at),
    }


@app.post("/travel/plan")
def preview_travel_plan(destination: str, start_date: str, end_date: str, notes: str = None):
    """AI วางแผนทริป (ยังไม่บันทึก — ให้ผู้ใช้ตรวจก่อน)"""
    try:
        start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD"}
    try:
        result = plan_trip(destination, start, end, notes, get_local_today())
    except Exception as e:
        print("travel/plan failed:", e)
        return {"error": f"วางแผนไม่สำเร็จ — ลองอีกครั้ง", "days": [], "prep_tasks": []}
    return {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "notes": notes,
        "days": result.get("days", []),
        "prep_tasks": result.get("prep_tasks", []),
    }


@app.post("/travel")
def save_travel_plan(destination: str, start_date: str, end_date: str,
                     notes: str = None, days: Optional[list] = Body(None),
                     prep_tasks: Optional[list] = Body(None)):
    """บันทึกแผนทริปที่ผู้ใช้ยืนยันแล้ว + สร้างงานเตรียมตัวจาก prep_tasks เป็นงานจริง"""
    db = SessionLocal()
    try:
        start = None
        end = None
        try:
            start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            pass
        plan = TripPlan(
            id=str(uuid.uuid4()), destination=destination,
            start_date=start, end_date=end, notes=notes,
            days_json=json.dumps(days or [], ensure_ascii=False),
            prep_tasks_json=json.dumps(prep_tasks or [], ensure_ascii=False),
        )
        db.add(plan)

        created = []
        for item in (prep_tasks or []):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            deadline = None
            d = item.get("deadline")
            if isinstance(d, str) and d:
                try:
                    deadline = datetime.datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    deadline = None
            est = item.get("estimated_time")
            try:
                est = int(est) if est else None
            except (TypeError, ValueError):
                est = None
            t = Task(
                id=str(uuid.uuid4()), title=title,
                deadline=deadline,
                deadline_time=(item.get("deadline_time") or "23:59"),
                estimated_time=est,
            )
            db.add(t)
            created.append(t)
        db.commit()
        result = _trip_to_dict(plan)
        result["created_tasks"] = [_task_to_dict(t) for t in created]
    finally:
        db.close()
    return result


@app.get("/travel")
def list_travel_plans():
    db = SessionLocal()
    try:
        plans = db.query(TripPlan).order_by(TripPlan.created_at.desc()).all()
        return [_trip_to_dict(p) for p in plans]
    finally:
        db.close()


@app.delete("/travel/{plan_id}")
def delete_travel_plan(plan_id: str):
    db = SessionLocal()
    try:
        plan = db.query(TripPlan).filter(TripPlan.id == plan_id).first()
        if not plan:
            return {"error": "ไม่พบแผนทริปนี้"}
        db.delete(plan)
        db.commit()
        return {"deleted": True, "id": plan_id}
    finally:
        db.close()


# ---------- Daily Plan (จัดแพลนวันนี้ตามพลังงาน + ตารางเรียน) ----------

from plan_service import preview_plan, build_daily_plan, build_goal_plan


@app.get("/plan/preview")
def get_plan_preview(date: Optional[str] = None):
    """ดูตัวเลือกพลังงาน 1-5 ว่าจะทำงานอะไรได้บ้างวันนี้ (ยังไม่บันทึก)
    ใช้ในหน้าเลือกพลังงานก่อนจัดแพลนจริง"""
    db = SessionLocal()
    try:
        target = datetime.datetime.strptime(date, "%Y-%m-%d").date() if date else get_local_today()
        return preview_plan(db, target)
    except ValueError:
        return {"error": "รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD"}
    finally:
        db.close()


@app.post("/plan/daily")
def create_daily_plan(date: Optional[str] = None, energy_level: int = 3):
    """จัดแพลนวันนี้จริง: งานลงในช่วงว่างของตารางเรียนตามระดับพลังงาน
    แพลนคำนวณใหม่ทุกครั้งจากตารางเรียนปัจจุบัน — ถ้าตารางเปลี่ยน/มีงานแทรก
    งานจะย้ายไปช่วงว่างถัดไปให้อัตโนมัติ"""
    db = SessionLocal()
    try:
        target = datetime.datetime.strptime(date, "%Y-%m-%d").date() if date else get_local_today()
        return build_daily_plan(db, target, energy_level)
    except ValueError:
        return {"error": "รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD"}
    finally:
        db.close()


# ---------- Dashboard สรุปวันนี้ (ทำไปแล้ว + ควรทำอะไรต่อตามพลังงาน) ----------

@app.get("/dashboard/today")
def get_dashboard_today():
    """สรุปสำหรับหน้าแรกวันนี้:
    - done_today: งานที่ทำเสร็จวันนี้ (completed_at อยู่ในช่วงวันตาม timezone ผู้ใช้)
    - todo_today: งาน TODO ที่ครบกำหนดวันนี้หรือเลยกำหนด
    - plan: แพลนของวันตามระดับพลังงานที่เช็คอินไว้ (ถ้ามี) — ว่าควรทำอะไรบ้าง
    """
    db = SessionLocal()
    try:
        offset = get_tz_offset()
        today = get_local_today()
        # ช่วงวันนี้ในเวลา UTC (completed_at เก็บเป็น utcnow)
        start_utc = datetime.datetime(today.year, today.month, today.day) - datetime.timedelta(hours=offset)
        end_utc = start_utc + datetime.timedelta(days=1)

        done_today = [
            t for t in db.query(Task).filter(Task.status == "DONE").all()
            if t.completed_at and start_utc <= t.completed_at < end_utc
        ]
        done_today.sort(key=lambda t: t.completed_at)

        todo_today = [
            t for t in db.query(Task).filter(Task.status == "TODO").all()
            if t.deadline and t.deadline.date() <= today
        ]
        todo_today.sort(key=lambda t: (t.deadline, t.title))

        log = db.query(EnergyLog).filter(EnergyLog.log_date == today).order_by(
            EnergyLog.created_at.desc()).first()
        energy_level = log.energy_level if log else None

        plan = build_daily_plan(db, today, energy_level) if energy_level else None

        return {
            "date": str(today),
            "energy_level": energy_level,
            "done_today": [_task_to_dict(t) for t in done_today],
            "todo_today": [_task_to_dict(t) for t in todo_today],
            "plan": plan,
        }
    finally:
        db.close()


# ---------- Chat (แยกแยะเจตนาเอง: งาน / ไฟล์ / แพลนวันนี้ / ทริป / ทักทาย) ----------

from fastapi import Form
from ai_service import classify_chat, parse_task_text, analyze_file_text, analyze_image_file, plan_trip, extract_timetable, extract_timetable_image
from file_service import extract_text_from_file, is_image_file, is_supported

# คำที่ใช้ในคำสั่ง "ยกเลิกงาน" (ไม่เอาไปจับคู่กับชื่องาน) — กันจับคู่เพี้ยนจากคำสั่งเอง
CANCEL_STOPWORDS = {
    "ยกเลิก", "ลบ", "งาน", "การบ้าน", "เอา", "ออก", "ช่วย", "หน่อย", "ให้", "ด้วย",
    "ของ", "เรื่อง", "ครับ", "ค่ะ", "นะ", "ที่", "อยาก", "จะ", "ขอ", "ช้อป", "แล้ว",
}


def _find_tasks_to_cancel(db, text, limit=5):
    """หางาน TODO ที่ผู้ใช้อยากยกเลิก: เอา 'คำสั่ง' ออก เหลือคำหลักที่เรียกชื่องาน แล้วจับคู่กับชื่องาน
    - ภาษาไทยไม่มีเว้นวรรค → ใช้การตัด stopword แล้ว match แบบ substring (ทั้งชื่องานในข้อความ และคำในข้อความในชื่องาน)
    - ไม่มีคำเฉพาะเจาะจง (พิมพ์แค่ "ยกเลิกงาน") → คืนงานค้างอยู่ล่าสุดให้เลือก (มากสุด limit)
    - คืน [] ถ้าไม่มีงานค้างเลย"""
    low = (text or "").lower()
    content = low
    for w in sorted(CANCEL_STOPWORDS, key=len, reverse=True):
        content = content.replace(w, " ")
    content = re.sub(r"\s+", " ", content).strip()
    tokens = [w for w in content.split(" ") if len(w) >= 2]

    tasks = (db.query(Task)
             .filter(Task.status == "TODO")
             .order_by(Task.deadline.is_(None), Task.deadline.asc())
             .all())
    if not tasks:
        return []
    if not tokens:
        return [_task_to_dict(t) for t in tasks[:limit]]

    matches = []
    for t in tasks:
        title = (t.title or "").lower()
        title_words = [w for w in title.split(" ") if len(w) >= 2]
        # ตรงเมื่อ: คำหลักปรากฏในชื่องาน หรือ ชื่องาน (บางส่วน) ปรากฏในข้อความ
        if any(w in title for w in tokens) or any(tw in low for tw in title_words):
            matches.append(t)
    matches.sort(key=lambda x: (x.deadline is None, x.deadline))
    return [_task_to_dict(t) for t in matches[:limit]]


@app.post("/chat")
async def chat_message(text: Optional[str] = Form(None), file: Optional[UploadFile] = File(None),
                       files: Optional[List[UploadFile]] = File(None)):
    """คุยกับแอปฟรีฟอร์ม — แอปแยกแยะเองว่าข้อความนี้คืออะไร:
    - งานใหม่ (create_task) → parse + คืน task ให้ตรวจก่อนบันทึก
    - ไฟล์แนบ (1+ ไฟล์) → AI ดึงงานจากเอกสาร/รูปภาพ ให้ตรวจก่อนบันทึก
    - "แพลนวันนี้" → คืน preview ให้เลือกพลังงาน (ไปหน้า Daily Plan)
    - "ไปเที่ยว..." → ไปหน้า Travel Planning
    - ทักทาย/ช่วยเหลือ → คุยใจดี ๆ
    """
    # 1) มีไฟล์แนบ (field เดิม `file` หรือ field ใหม่ `files` = หลายไฟล์) → วิเคราะห์ก่อน
    uploads = []
    if file is not None and file.filename:
        uploads.append(file)
    if files:
        uploads.extend(f for f in files if f is not None and f.filename)
    if uploads:
        return await _process_chat_files(uploads)

    # 2) ไม่มีไฟล์ → แยกแยะเจตนาจากข้อความ
    user_text = (text or "").strip()
    if not user_text:
        return {"intent": "chat", "reply": "พิมพ์งานที่จะทำ หรือส่งไฟล์มาให้ช่วยวิเคราะห์ก็ได้"}

    intent = classify_chat(user_text)

    if intent == "plan_trip":
        return {
            "intent": "plan_trip",
            "reply": "จัดทริปให้เลย — กรอกปลายทาง/วันเดินทางในหน้าเดินทางได้",
        }

    if intent == "plan_daily":
        db = SessionLocal()
        try:
            preview = preview_plan(db, get_local_today())
        finally:
            db.close()
        return {
            "intent": "plan_daily",
            "reply": "จัดแพลนวันนี้ให้เลย — เลือกระดับพลังงานแล้วแอปจะจัดตารางให้",
            "plan_preview": preview,
        }

    if intent == "update_timetable":
        db = SessionLocal()
        try:
            action = parse_timetable_command(user_text)
            proposal = build_timetable_proposal(action, list_schedules(db))
        finally:
            db.close()
        return {
            "intent": "update_timetable",
            "reply": proposal["summary"],
            "action": action,
            "matched": proposal["matched"],
            "entry": proposal["entry"],
            "ok": proposal["ok"],
        }

    if intent == "set_timetable":
        # ข้อความแบบตารางเรียน → พยายาม parse แบบ deterministic ก่อน
        entries = clean_timetable_entries(parse_timetable_text(user_text).get("entries", []))
        skipped = []
        if len(entries) < 2:
            try:
                tt = extract_timetable(user_text, get_local_today())
                entries = clean_timetable_entries(tt.get("entries", []))
                skipped = [s for s in tt.get("skipped", []) if isinstance(s, str)]
            except Exception as e:
                print("chat/timetable extract failed:", e)
        if not entries:
            return {
                "intent": "chat",
                "reply": "พิมพ์ตารางเรียนมาแบบ 'จันทร์ 09:00-10:30 คณิตศาสตร์ ห้อง 301' (บรรทัดละคาบ) "
                         "หรือส่งไฟล์/รูปตารางเรียนมาให้ช่วยอ่านก็ได้",
            }
        return {
            "intent": "set_timetable",
            "reply": f"อ่านตารางเรียนได้ {len(entries)} คาบ — ตรวจก่อนบันทึก (บันทึกจะแทนที่ตารางเดิม)",
            "entries": entries,
            "skipped": skipped,
            "suggested_actions": ["apply_timetable"],
        }

    if intent == "cancel_classes":
        # "เช้าวันจันทร์ไม่มีเรียน" → หาวัน/ช่วงจากข้อความ → เอาคาบที่ทับช่วงนั้นมาให้ตรวจก่อน
        db = SessionLocal()
        try:
            req = parse_cancel_request(user_text, get_local_today())
            if not req:
                return {
                    "intent": "chat",
                    "reply": "บอกวันให้ชัดขึ้นหน่อย เช่น 'เช้าวันจันทร์ไม่มีเรียน' หรือ 'พรุ่งนี้บ่ายหยุดเรียน' — "
                             "แอปจะยกเลิกเฉพาะวันนั้น ไม่แตะตารางประจำสัปดาห์",
                }
            classes = find_classes_to_cancel(db, req["date"],
                                             req["start_time"], req["end_time"])
        finally:
            db.close()
        if not classes:
            return {
                "intent": "chat",
                "reply": f"ไม่พบคาบเรียนของ{req['day_name'] or 'วันนั้น'} "
                         f"({req['date']}) ในช่วง{'เช้า' if req['start_time'] == '00:00' else 'บ่าย'} — "
                         f"ดูตารางเรียนในปฏิทินได้เลย (การยกเว้นนี้ไม่จำเป็นเพราะไม่มีคาบทับ)",
            }
        period_label = ("เช้า" if req["start_time"] == "00:00"
                        else "บ่าย" if req["start_time"] == "12:00"
                        else f"{req['start_time']}-{req['end_time']}")
        subject_list = " · ".join(c["subject"] for c in classes[:3])
        if len(classes) > 3:
            subject_list += f" และอีก {len(classes) - 3} คาบ"
        return {
            "intent": "cancel_classes",
            "reply": f"เจอ {len(classes)} คาบช่วง{period_label}ของ{req['day_name']} "
                     f"({req['date']}): {subject_list} — ยกเลิกเฉพาะวันนี้ (ตารางประจำสัปดาห์ไม่เปลี่ยน)",
            "date": str(req["date"]),
            "start_time": req["start_time"],
            "end_time": req["end_time"],
            "reason": req["reason"],
            "classes": classes,
            "suggested_actions": ["cancel_classes_confirm"],
        }

    if intent == "cancel_task":
        db = SessionLocal()
        try:
            candidates = _find_tasks_to_cancel(db, user_text)
        finally:
            db.close()
        if not candidates:
            return {
                "intent": "chat",
                "reply": "หาไม่เจองานค้างที่ตรงกับที่บอก — พิมพ์ชื่องานให้ชัดขึ้น เช่น "
                         "'ยกเลิกงานล้างจาน' หรือดูในประวัติก็ได้",
            }
        reply = (f"เจอ {len(candidates)} งานที่ตรงกัน — เลือกงานที่อยากยกเลิก "
                 "(ยืนยันแล้วจะลบออกจากรายการ)")
        return {
            "intent": "cancel_task",
            "reply": reply,
            "tasks": candidates,
        }

    if intent == "chat":
        return {
            "intent": "chat",
            "reply": "ฟังอยู่จ้า — พิมพ์งานที่อยากทำ (เช่น 'ล้างจานพรุ่งนี้เช้า 30 นาที') "
                     "หรือส่งไฟล์/รูปมาให้ช่วยดึงงานออกให้ได้เลย",
        }

    # create_task (default): parse งานจากข้อความ (ข้อความเดียวอาจมีหลายงาน) → ให้ตรวจก่อนบันทึก
    try:
        parsed_list = parse_tasks_text(user_text, get_local_today())
    except Exception as e:
        print("chat/parse failed:", e)
        return {"intent": "create_task", "reply": "อ่านงานไม่ทัน ลองพิมพ์ใหม่ได้เลย", "task": None, "tasks": []}
    tasks = [
        {
            "title": p.get("title", ""),
            "estimated_time": p.get("estimated_time"),
            "deadline": p.get("deadline"),
            "deadline_time": p.get("deadline_time"),
        }
        for p in parsed_list if isinstance(p, dict) and p.get("title")
    ]
    if not tasks:
        return {"intent": "create_task", "reply": "อ่านงานไม่ทัน ลองพิมพ์ใหม่ได้เลย", "task": None, "tasks": []}
    reply = (f"เจอ {len(tasks)} งาน — ตรวจความถูกต้องก่อนบันทึกได้เลย"
             if len(tasks) > 1 else "จดให้แล้ว — ตรวจความถูกต้องก่อนบันทึกได้เลย")
    return {
        "intent": "create_task",
        "reply": reply,
        "task": tasks[0],  # compat เดิม
        "tasks": tasks,
    }


async def _process_chat_files(uploads):
    """วิเคราะห์ไฟล์หลายไฟล์พร้อมกัน — ไฟล์ไหนอ่านไม่ได้ก็ไม่ฆ่ากันทั้งชุด (หลัก §9)
    - ไฟล์/รูปที่เป็น "ตารางเรียน" → extract เป็นคาบเรียน (intent set_timetable ให้ตรวจก่อน)
    - ไฟล์ทั่วไป → AI ดึงงาน (intent analyze_file พร้อม tasks + suggested_actions ให้ frontend เลือก)
    """
    today = get_local_today()
    all_tasks = []
    files_meta = []
    summaries = []
    failed = []
    ok_count = 0
    timetable_entries = []
    timetable_skipped = []

    def _file_is_timetable(filename, data):
        """ลอง extract ตารางเรียนจากไฟล์ → คืน entries (list) ถ้าใช่, [] ถ้าไม่ใช่"""
        try:
            if is_image_file(filename):
                # รูป: ดูว่าเป็นตารางเรียนไหม (AI vision) — กันเบิ้ล 2 รอบ เรียกเฉพาะตอน analyze_file ไม่เจองาน
                return []
            text_content = extract_text_from_file(filename, data)
            if not detect_timetable(text_content):
                return []
            entries = clean_timetable_entries(parse_timetable_text(text_content).get("entries", []))
            if len(entries) < 2:
                tt = extract_timetable(text_content, today)
                entries = clean_timetable_entries(tt.get("entries", []))
                timetable_skipped.extend(s for s in tt.get("skipped", []) if isinstance(s, str))
            return entries
        except Exception as e:
            print("chat/file timetable detect failed:", filename, e)
            return []

    for uf in uploads:
        data = await uf.read()
        filename = uf.filename or "ไฟล์ไม่มีชื่อ"
        if not is_supported(filename):
            files_meta.append({"name": filename, "ok": False, "error": "ไฟล์ประเภทนี้ยังอ่านไม่ได้ (ลอง txt/pdf/docx/rtf หรือรูปภาพ)"})
            failed.append(f"{filename} (ประเภทไฟล์ยังไม่รองรับ)")
            continue
        try:
            if is_image_file(filename):
                # รูป: ลองอ่านเป็นตารางเรียนก่อน — กัน analyze_image_file อ่านตารางเป็น "งาน" ผิดทาง
                # (สกรีนช็อตตารางเรียนมีวิชา+เวลา → มองเป็นงานได้ง่าย); ถ้าไม่ใช่ตารางค่อยหางานจริง
                tt = None
                try:
                    tt = extract_timetable_image(data, filename, today)
                    entries = clean_timetable_entries(tt.get("entries", []))
                except Exception:
                    entries = []
                if len(entries) >= 2:
                    timetable_entries.extend(entries)
                    if tt:
                        timetable_skipped.extend(s for s in tt.get("skipped", []) if isinstance(s, str))
                    files_meta.append({"name": filename, "ok": True, "kind": "timetable",
                                       "entries": len(entries)})
                    ok_count += 1
                    continue
                analysis = analyze_image_file(data, filename, today)
                tasks = analysis.get("tasks", [])
                if not tasks and tt:
                    timetable_skipped.extend(s for s in tt.get("skipped", []) if isinstance(s, str))
            else:
                text_content = extract_text_from_file(filename, data)
                entries = _file_is_timetable(filename, data)
                if entries:
                    timetable_entries.extend(entries)
                    files_meta.append({"name": filename, "ok": True, "kind": "timetable",
                                       "entries": len(entries)})
                    ok_count += 1
                    continue
                analysis = analyze_file_text(text_content, today)
        except Exception as e:
            print("chat/file failed:", filename, e)
            err = str(e) or "อ่านข้อมูลในไฟล์ไม่ได้"
            files_meta.append({"name": filename, "ok": False, "error": err})
            failed.append(f"{filename} ({err})")
            continue
        ok_count += 1
        files_meta.append({"name": filename, "ok": True, "summary": analysis.get("summary", "")})
        tasks = analysis.get("tasks", [])
        if isinstance(tasks, list):
            all_tasks.extend(t for t in tasks if isinstance(t, dict) and t.get("title"))
        if analysis.get("summary"):
            summaries.append(f"{filename}: {analysis['summary']}")

    # ไฟล์ไหนเป็นตารางเรียน → ให้ตรวจ/บันทึกตารางก่อน (ยังเอา tasks ที่เจอในไฟล์อื่นมาด้วยได้)
    if timetable_entries:
        reply_parts = [f"อ่านตารางเรียนได้ {len(timetable_entries)} คาบ จาก {len(timetable_entries)} รายการ"]
        if failed:
            reply_parts.append("ไฟล์ที่อ่านไม่ได้: " + " | ".join(failed))
        result = {
            "intent": "set_timetable",
            "reply": " | ".join(reply_parts) + " — ตรวจก่อนบันทึก (บันทึกจะแทนที่ตารางเดิม)",
            "entries": timetable_entries[:60],
            "skipped": timetable_skipped[:20],
            "files": files_meta,
            "suggested_actions": ["apply_timetable"],
        }
        if all_tasks:
            result["tasks"] = all_tasks[:40]
            result["suggested_actions"].append("add_tasks")
        return result

    all_tasks = all_tasks[:40]  # กัน payload ยักษ์
    combined_summary = " ".join(summaries)

    if ok_count == 0:
        return {
            "intent": "chat",
            "reply": "อ่านไฟล์ไม่ได้เลย: " + " | ".join(failed),
            "files": files_meta,
            "tasks": [],
        }

    reply_parts = [f"อ่านไฟล์แล้ว เจองาน {len(all_tasks)} อย่าง จาก {ok_count} ไฟล์"]
    if failed:
        reply_parts.append("ไฟล์ที่อ่านไม่ได้: " + " | ".join(failed))
    suggested_actions = ["add_tasks"] if all_tasks else []
    if combined_summary:
        suggested_actions.append("summarize")
    return {
        "intent": "analyze_file",
        "reply": " | ".join(reply_parts),
        "files": files_meta,
        "tasks": all_tasks,
        "summary": combined_summary,
        "suggested_actions": suggested_actions,
        "filename": (files_meta[0]["name"] if files_meta else ""),  # compat เดิม
    }

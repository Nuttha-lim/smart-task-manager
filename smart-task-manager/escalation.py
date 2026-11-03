"""Escalation logic — Latest Start Time = Deadline - (Estimated Time + Buffer)

เคยแยก compute_urgency ไว้ 3 ที่ (main.py, celery_tasks.py,
workers/notification_worker.py) — แก้ threshold ที่หนึ่งแล้วที่อื่นไม่ตาม
เลยย้ายมารวมจุดเดียว (ดู AGENTS.md §8 หมายเหตุ)

เกณฑ์ urgency:
  overdue  = กำหนดส่งผ่านแล้ว
  critical = เลยเวลาต้องเริ่ม (deadline - (est + buffer)) แล้ว
  high     = เหลือถึงเวลาต้องเริ่ม <= 1 ชม.
  medium   = เหลือ <= 24 ชม.
  low      = ที่เหลือ

สำคัญ: deadline เก็บเป็น "เที่ยงคืนเวลาท้องถิ่น" (naive) — ตอนเรียก compute_urgency
ต้องส่ง `now` เป็น local-naive เช่น get_local_now() ไม่ใช่ utcnow() ตรง ๆ
(ดู AGENTS.md §6 ข้อ 3)
"""
import datetime

from models import Task, Notification

# ระดับที่ควรสร้าง notification (worker + celery ใช้ร่วมกัน)
NOTIFY_URGENCIES = ('critical', 'high', 'overdue')
# ไม่เตือนซ้ำ งาน+ระดับเดิม ภายใน 6 ชม. (กันสแปม)
RE_NOTIFY_SECONDS = 3600 * 6


def task_deadline_datetime(t):
    """คืน moment จริงที่งานต้องส่ง = วันที่ (deadline) + เวลา (deadline_time)

    deadline เก็บเป็น DateTime (เที่ยงคืนของวันส่ง) ส่วน deadline_time เก็บแยก "HH:MM"
    (default "23:59") — ต้องรวมกันก่อนคำนวณ latest_start ไม่งั้นถือว่า deadline คือเที่ยงคืน
    ซึ่งเร็วไป 23 ชม. 59 นาที (งานเลยดูเร่งด่วนผิด)
    """
    base = t.deadline
    if base is None:
        return None
    time_str = t.deadline_time or "23:59"
    try:
        parts = (time_str.split(":") + ["0"])[:2]
        return base.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
    except Exception:
        # เวลาเพี้ยน/อ่านไม่ได้ → ใช้ deadline เดิม (ไม่ crash ตามหลัก §9)
        return base


def compute_urgency(t, buffer_minutes: int, now):
    """คืน (latest_start, seconds_to_latest, seconds_to_deadline, urgency)"""
    est = t.estimated_time if t.estimated_time is not None else 30
    deadline = task_deadline_datetime(t)
    latest_start = deadline - datetime.timedelta(minutes=(est + buffer_minutes))
    seconds_to_latest = (latest_start - now).total_seconds()
    seconds_to_deadline = (deadline - now).total_seconds()

    if seconds_to_deadline <= 0:
        urgency = "overdue"
    elif seconds_to_latest <= 0:
        urgency = "critical"
    elif seconds_to_latest <= 3600:
        urgency = "high"
    elif seconds_to_latest <= 86400:
        urgency = "medium"
    else:
        urgency = "low"
    return latest_start, seconds_to_latest, seconds_to_deadline, urgency


def todo_tasks_with_deadline(db):
    """งาน TODO ที่มี deadline — ใช้ร่วมกันทั้ง endpoint, celery และ worker"""
    return db.query(Task).filter(
        Task.status == "TODO",
        Task.deadline.isnot(None),
    ).all()


def was_notified_recently(db, task, urgency, now=None):
    """งาน+ระดับเดิมเพิ่งถูกเตือนไปภายใน RE_NOTIFY_SECONDS หรือยัง
    (True = ข้าม ไม่สร้าง notification ซ้ำ)

    สำคัญ: `recent.created_at` เก็บเป็น UTC — ต้องเทียบกับ utcnow() ไม่ใช่ `now`
    (local) ไม่งั้นเอาค่า offset มาบวกเข้าไป ทำให้ดูเหมือน "ผ่านไปนานกว่า" จริง
    → worker จะเตือนซ้ำถี่เกินไป (เช่น UTC+7 เตือนซ้ำทุก ~23 ชม. ทั้งที่ตั้งไว้ 6 ชม.)"""
    recent = db.query(Notification).filter(
        Notification.task_id == task.id,
        Notification.urgency == urgency,
    ).order_by(Notification.created_at.desc()).first()
    if recent is None:
        return False
    try:
        return (datetime.datetime.utcnow() - recent.created_at).total_seconds() < RE_NOTIFY_SECONDS
    except Exception:
        return False

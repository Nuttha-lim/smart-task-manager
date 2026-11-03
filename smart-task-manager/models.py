from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()


class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)
    title = Column(String)
    description = Column(String, nullable=True)
    status = Column(String, default="TODO")
    base_points = Column(Integer, default=10)
    estimated_time = Column(Integer, nullable=True)
    deadline = Column(DateTime, nullable=True)
    deadline_time = Column(String, default="23:59")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    goal_id = Column(String, nullable=True)
    last_deadline_check = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)      # เวลาที่ทำเสร็จ (ใช้ undo/streak ใหม่)
    points_awarded = Column(Integer, nullable=True)     # แต้มที่ให้ตอนเสร็จ (ใช้ undo หักคืน)


class EnergyLog(Base):
    __tablename__ = "energy_logs"
    id = Column(String, primary_key=True)
    energy_level = Column(Integer)
    log_date = Column(Date, default=datetime.date.today)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String, primary_key=True)
    value = Column(String)


class Goal(Base):
    __tablename__ = "goals"
    id = Column(String, primary_key=True)
    title = Column(String)
    desire_score = Column(Integer, default=3)
    urgency_score = Column(Integer, default=3)
    target_date = Column(Date, nullable=True)  # วันเป้าหมาย/วันสอบ — ใช้จัดตารางเตรียม (study plan)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Reward(Base):
    __tablename__ = "rewards"
    id = Column(String, primary_key=True)
    title = Column(String)
    point_cost = Column(Integer)
    locked = Column(Boolean, default=False)
    max_per_day = Column(Integer, nullable=True)     # จำกัดสิทธิ์ใช้ต่อวัน (None = ไม่จำกัด)
    max_per_month = Column(Integer, nullable=True)   # จำกัดสิทธิ์ใช้ต่อเดือน
    max_per_year = Column(Integer, nullable=True)    # จำกัดสิทธิ์ใช้ต่อปี
    source = Column(String, default="user")          # "user" = ผู้ใช้สร้าง, "ai" = AI แนะนำ
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RewardRedemption(Base):
    __tablename__ = "reward_redemptions"
    id = Column(String, primary_key=True)
    reward_id = Column(String)
    redeemed_at = Column(DateTime, default=datetime.datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True)
    task_id = Column(String, nullable=True)
    message = Column(String)
    urgency = Column(String)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Device(Base):
    __tablename__ = "devices"
    id = Column(String, primary_key=True)
    device_token = Column(String)
    platform = Column(String)
    user_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)


class SpellPref(Base):
    __tablename__ = "spell_prefs"
    id = Column(String, primary_key=True)
    word = Column(String)
    corrected = Column(String, nullable=True)  # ค่าว่าง/None = ผู้ใช้อยากได้คำเดิม
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Achievement(Base):
    __tablename__ = "achievements"
    id = Column(String, primary_key=True)
    key = Column(String, unique=True)
    title = Column(String)
    description = Column(String)
    icon = Column(String)
    points = Column(Integer, default=0)  # โบนัสแต้มเมื่อปลดล็อก
    condition_type = Column(String)  # tasks_done | streak_days | lifetime_points | goals_created | energy_logs
    condition_value = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class UnlockedAchievement(Base):
    __tablename__ = "unlocked_achievements"
    id = Column(String, primary_key=True)
    achievement_key = Column(String)
    unlocked_at = Column(DateTime, default=datetime.datetime.utcnow)


class Holiday(Base):
    __tablename__ = "holidays"
    id = Column(String, primary_key=True)
    date = Column(Date)
    name = Column(String)
    kind = Column(String, default="public")  # public | religious | special
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ClassSchedule(Base):
    __tablename__ = "class_schedules"
    id = Column(String, primary_key=True)
    day_of_week = Column(Integer)  # 1=จันทร์ ... 7=อาทิตย์ (ตรงกับ Dart DateTime.weekday)
    start_time = Column(String)    # "HH:MM"
    end_time = Column(String)      # "HH:MM"
    subject = Column(String)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class TimetableCancel(Base):
    """ยกเลิกคาบเรียนเฉพาะวัน (ไม่แตะตารางรายสัปดาห์) — เก็บไว้ดูประวัติ/ยกเลิกได้
    เช่น "เช้าวันจันทร์ไม่มีเรียน" → date=วันจันทร์นั้น start="00:00" end="12:00"
    คาบที่ทับช่วงนี้ของวันนั้นจะถูกมองว่า "ยกเลิก" ใน Calendar/ไทม์ไลน์"""
    __tablename__ = "timetable_cancels"
    id = Column(String, primary_key=True)
    date = Column(Date, nullable=False)               # วันที่ยกเลิก (เฉพาะวันนี้)
    start_time = Column(String(5), nullable=False, default="00:00")
    end_time = Column(String(5), nullable=False, default="23:59")
    reason = Column(String(200), nullable=True)       # เช่น "เช้าไม่มีเรียน"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class TripPlan(Base):
    __tablename__ = "trip_plans"
    id = Column(String, primary_key=True)
    destination = Column(String)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    notes = Column(String, nullable=True)
    days_json = Column(String, nullable=True)       # JSON array ของ day-by-day itinerary
    prep_tasks_json = Column(String, nullable=True)  # JSON array ของงานเตรียมตัวที่ยืนยันแล้ว
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Routine(Base):
    __tablename__ = "routines"
    id = Column(String, primary_key=True)
    title = Column(String(100), nullable=False)   # ชื่อกิจวัตร เช่น "ตื่นนอน", "ออกกำลังกาย"
    time = Column(String(5), nullable=False)      # "HH:MM" — ช่วงเวลาที่ทำ
    enabled = Column(Boolean, default=True)       # ปิด = ไม่โชว์ใน timeline (ยังเก็บไว้)
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

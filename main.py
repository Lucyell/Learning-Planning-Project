# FastAPI backend starter based on your project1.py logic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from project1 import DatabaseManager, GeneratorAgent, ProgressTracker, FocusManager, WeeklyReportGenerator

app = FastAPI()

# CORS setup for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()
generator = GeneratorAgent()
progress_tracker = ProgressTracker(db)
focus_manager = FocusManager(db)
report_generator = WeeklyReportGenerator(db, focus_manager)

# ----------------------- Models -----------------------
class RegisterUser(BaseModel):
    username: str
    email: str
    learning_style: Optional[str] = None
    proficiency_level: Optional[str] = None

class GeneratePlan(BaseModel):
    user_id: int
    subject: str
    duration_days: int
    target_level: str

class FocusStart(BaseModel):
    plan_id: int
    day_number: int
    task_name: str

class ProgressUpdate(BaseModel):
    plan_id: int
    day_number: int
    completed: bool
    notes: Optional[str] = ""

# ----------------------- Routes -----------------------
@app.post("/api/user/register")
def register_user(user: RegisterUser):
    try:
        user_id = db.add_user(user.username, user.email, user.learning_style, user.proficiency_level)
        return {"user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/plan/generate")
def generate_study_plan(data: GeneratePlan):
    try:
        content = generator.generate_plan(data.subject, data.duration_days, data.target_level)
        plan_id = db.add_study_plan(data.user_id, data.subject, data.duration_days, data.target_level, content)
        return {"plan_id": plan_id, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/plan/{plan_id}")
def get_study_plan(plan_id: int):
    plan = db.get_study_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@app.post("/api/focus/start")
def start_focus(data: FocusStart):
    try:
        session = focus_manager.start_focus(data.plan_id, data.day_number, data.task_name)
        return session
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/focus/end")
def end_focus():
    try:
        return focus_manager.end_focus()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/report/weekly")
def get_weekly_report(user_id: int, plan_id: int):
    try:
        return {"report": report_generator.generate_weekly_report(user_id, plan_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/progress/update")
def update_progress(data: ProgressUpdate):
    success = progress_tracker.update_progress(data.plan_id, data.day_number, data.completed, data.notes)
    if not success:
        raise HTTPException(status_code=400, detail="Update failed")
    return {"success": True}

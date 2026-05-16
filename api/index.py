from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from supabase import create_client
import os
import bcrypt
from datetime import datetime, timedelta, timezone
import jwt

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "https://kara-suu-tazalyk.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]
# Allow extra origins via env (n8n, preview deploys)
_extra = os.environ.get("EXTRA_CORS_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS += [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https://.*\.vercel\.app$",  # preview deploys
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

SECRET_KEY = os.environ.get("JWT_SECRET", "tazalyk-secret-2024")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return url, key

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# --- Pydantic Models ---

class MessageCreate(BaseModel):
    application_id: str
    text: str
    user_id: Optional[str] = None
    type: Optional[str] = "text"

class ApplicationCreate(BaseModel):
    phone: str                          # номер WhatsApp (обязательно)
    address: str                        # адрес (обязательно)
    description: Optional[str] = None  # описание проблемы
    waste_type: Optional[str] = None   # тип мусора
    media_url: Optional[str] = None    # ссылка на фото
    source: Optional[str] = "whatsapp"
    status: Optional[str] = "new"
    priority: Optional[str] = "medium"

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    operator_id: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    vehicle_id: Optional[str] = None

class InstitutionCreate(BaseModel):
    name: str
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None

class InstitutionUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    is_active: Optional[bool] = None

class WasteTypeCreate(BaseModel):
    name: str
    color: Optional[str] = None

class ScheduleCreate(BaseModel):
    institution_id: str
    vehicle_id: Optional[str] = None
    waste_type_id: Optional[str] = None
    interval_days: Optional[int] = 7
    next_run_at: Optional[str] = None  # date string

class ScheduleUpdate(BaseModel):
    institution_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    waste_type_id: Optional[str] = None
    interval_days: Optional[int] = None
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None

class TransportCreate(BaseModel):
    name: str
    plate: str
    type: Optional[str] = "truck"
    status: Optional[str] = "available"
    route: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    fuel_level: Optional[int] = 100
    mileage: Optional[int] = 0
    last_service: Optional[str] = None
    next_service: Optional[str] = None

class TransportUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    route: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    fuel_level: Optional[int] = None
    mileage: Optional[int] = None
    last_service: Optional[str] = None
    next_service: Optional[str] = None

class ExpenseCreate(BaseModel):
    transport_id: str
    description: str
    amount: float
    created_by: str

class VehicleCreate(BaseModel):
    """Deprecated — kept only for backward-compat with any legacy callers."""
    brand: str
    plate: str
    type: str
    status: str = "бош"
    current_task: Optional[str] = None
    notes: Optional[str] = None

class VehicleUpdate(BaseModel):
    """Deprecated."""
    brand: Optional[str] = None
    plate: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    current_task: Optional[str] = None
    notes: Optional[str] = None

class TelegramNotify(BaseModel):
    chat_id: str
    message: str

class MarkReadBody(BaseModel):
    ids: Optional[list[str]] = None
    all: Optional[bool] = False

class RefusalCreate(BaseModel):
    """Operator initiates client refusal — requires notes."""
    refusal_notes: str
    operator_id: Optional[str] = None

class RefusalSignature(BaseModel):
    """Driver attaches signature from mini-app."""
    signature_url: str
    lat: Optional[float] = None
    lng: Optional[float] = None

class RefusalDecision(BaseModel):
    """Admin approves or returns refusal."""
    approver_id: Optional[str] = None
    admin_note: Optional[str] = None
    return_to_status: Optional[str] = "in_progress"  # used only on return

@app.get("/")
def read_root():
    url, key = get_supabase()
    return {
        "status": "running",
        "version": "1.1.0",
        "debug": {
            "has_url": bool(url and len(url) > 5),
            "has_key": bool(key and len(key) > 5)
        }
    }


@app.post("/api/applications")
async def create_application_api(body: ApplicationCreate):
    """Entry point for n8n/WhatsApp. Saves application to Supabase."""
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {
            "phone":       body.phone,
            "address":     body.address,
            "description": body.description or "",
            "waste_type":  body.waste_type or "",
            "media_url":   body.media_url or "",
            "source":      body.source or "whatsapp",
            "status":      body.status or "new",
            "priority":    body.priority or "medium",
        }
        result = supabase.table("applications").insert(data).execute()
        return {"success": True, "data": result.data[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/applications/by-phone/{phone}")
async def get_applications_by_phone(phone: str):
    """WhatsApp bot: get last 3 applications by phone number."""
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        result = supabase.table("applications") \
            .select("id, created_at, address, waste_type, status, media_url") \
            .eq("phone", phone) \
            .order("created_at", desc=True) \
            .limit(3) \
            .execute()
        return {"success": True, "applications": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── APPLICATIONS ──────────────────────────

@app.get("/api/applications")
async def get_applications(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    source: Optional[str] = None,
    unread_only: Optional[bool] = None,
    limit: Optional[int] = None,
):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        query = supabase.table("applications") \
            .select("*") \
            .order("created_at", desc=True)

        if status:   query = query.eq("status", status)
        if priority: query = query.eq("priority", priority)
        if source:   query = query.eq("source", source)
        if unread_only is True: query = query.eq("is_read", False)
        if limit:    query = query.limit(limit)

        result = query.execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/applications/mark-read")
async def mark_applications_read(body: MarkReadBody):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        query = supabase.table("applications").update({"is_read": True})
        
        if body.all:
            query = query.eq("is_read", False)
        elif body.ids:
            query = query.in_("id", body.ids)
        else:
            return {"success": True, "updated": 0}

        result = query.execute()
        return {"success": True, "updated": len(result.data)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/applications/{id}")
async def get_application_by_id(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        result = supabase.table("applications") \
            .select("*, transport:transport(name, plate)") \
            .eq("id", id) \
            .single() \
            .execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/applications/{id}")
async def update_application_api(id: str, body: ApplicationUpdate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("applications").update(data).eq("id", id).execute()
        return {"success": True, "data": result.data[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/applications/{id}")
async def delete_application_api(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        supabase.table("applications").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── MESSAGES (CHAT) ────────────────────────

@app.get("/api/applications/{id}/messages")
async def get_app_messages(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        result = supabase.table("messages").select("*, user:users(id, name)").eq("application_id", id).order("created_at", desc=False).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/applications/{id}/messages")
async def post_app_message(id: str, body: MessageCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = body.dict()
        data["application_id"] = id
        result = supabase.table("messages").insert(data).execute()
        
        # Logic: If operator replies, move to waiting_user
        if body.user_id:
            supabase.table("applications").update({"status": "waiting_user"}).eq("id", id).execute()
            
        return {"success": True, "data": result.data[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── DIRECTORIES ────────────────────────────

@app.get("/api/institutions")
async def get_inst(include_inactive: Optional[bool] = False):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        q = supabase.table("institutions").select("*").order("name")
        if not include_inactive:
            q = q.eq("is_active", True)
        return {"success": True, "data": q.execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/institutions")
async def create_inst(body: InstitutionCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("institutions").insert(data).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

@app.patch("/api/institutions/{id}")
async def update_inst(id: str, body: InstitutionUpdate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("institutions").update(data).eq("id", id).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e: return {"success": False, "error": str(e)}

@app.delete("/api/institutions/{id}")
async def delete_inst(id: str):
    """Soft delete — set is_active=false. Use ?hard=true to actually DELETE."""
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        supabase.table("institutions").update({"is_active": False}).eq("id", id).execute()
        return {"success": True}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/institutions/{id}/restore")
async def restore_inst(id: str):
    """Reactivate soft-deleted institution."""
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        supabase.table("institutions").update({"is_active": True}).eq("id", id).execute()
        return {"success": True}
    except Exception as e: return {"success": False, "error": str(e)}

@app.get("/api/waste_types")
async def get_wt():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("waste_types").select("*").order("name").execute().data}
    except Exception as e: return {"success": False, "error": str(e)}



# ── SCHEDULES ─────────────────────────────

@app.get("/api/schedules")
async def get_sched():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("schedules").select("*, institution:institutions(name, address, contact_phone), transport:transport(name, plate, type), waste_type:waste_types(name)").execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.get("/api/schedules/tomorrow")
async def get_sched_tomorrow():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        return {"success": True, "data": supabase.table("schedules").select("*, institution:institutions(name, address, contact_phone), transport:transport(name, plate, type), waste_type:waste_types(name)").eq("next_run_at", tomorrow).execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/schedules")
async def create_sched(body: ScheduleCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("schedules").insert(data).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

@app.patch("/api/schedules/{id}")
async def patch_sched(id: str, body: ScheduleUpdate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("schedules").update(data).eq("id", id).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

# ── VEHICLES (DEPRECATED) ─────────────────────────
# /api/vehicles/* endpoints removed — use /api/transport/* instead.
# The legacy 'vehicles' table is no longer used by the dashboard.

# ── REPORTS ─────────────────────────────

@app.get("/api/reports/applications")
async def get_reports_applications(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None
):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        query = supabase.table("applications").select("*, institution:institutions(name)")
        if status: query = query.eq("status", status)
        if source: query = query.eq("source", source)
        if date_from: query = query.gte("created_at", date_from)
        if date_to: query = query.lte("created_at", f"{date_to}T23:59:59.999Z")
        return {"success": True, "data": query.execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.get("/api/reports/summary")
async def get_reports_summary(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        query = supabase.table("applications").select("*")
        if date_from: query = query.gte("created_at", date_from)
        if date_to: query = query.lte("created_at", f"{date_to}T23:59:59.999Z")
        apps = query.execute().data or []
        
        trans_query = supabase.table("transport").select("*, transport_history(*)")
        trans = trans_query.execute().data or []
        
        status_counts = {}
        source_counts = {}
        waste_counts = {}
        user_type_counts = {}
        
        for a in apps:
            st = a.get("status") or "new"
            status_counts[st] = status_counts.get(st, 0) + 1
            
            src = a.get("source") or "whatsapp"
            source_counts[src] = source_counts.get(src, 0) + 1
            
            wt = a.get("waste_type") or "unknown"
            waste_counts[wt] = waste_counts.get(wt, 0) + 1
            
            ut = a.get("user_type") or "resident"
            user_type_counts[ut] = user_type_counts.get(ut, 0) + 1
            
        transport_usage = []
        for t in trans:
            hist = t.get("transport_history", [])
            if date_from or date_to:
                c_hist = []
                for h in hist:
                    h_date = h.get("created_at", "")
                    if date_from and h_date < date_from: continue
                    if date_to and h_date > f"{date_to}T23:59:59.999Z": continue
                    c_hist.append(h)
                trips = len(c_hist)
            else:
                trips = len(hist)
            transport_usage.append({"name": t.get("name"), "plate": t.get("plate"), "trips": trips})

        return {"success": True, "data": {
            "total": len(apps),
            "by_status": status_counts,
            "by_source": source_counts,
            "by_waste_type": waste_counts,
            "by_user_type": user_type_counts,
            "transport_usage": transport_usage
        }}
    except Exception as e: return {"success": False, "error": str(e)}

@app.get("/api/reports/schedule")
async def get_reports_schedule():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("schedules").select("*").execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

# ── TELEGRAM ─────────────────────────────
import urllib.request
import json

@app.post("/api/notify/telegram")
async def notify_telegram(body: TelegramNotify):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"success": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": body.chat_id, "text": body.message}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as res:
            res_data = json.loads(res.read().decode())
            return {"success": res_data.get("ok", False)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── TRANSPORT ──────────────────────────────

@app.get("/api/transport")
async def get_transport_list(include_inactive: Optional[bool] = False):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        q = supabase.table("transport").select("*").order("name")
        if not include_inactive:
            q = q.eq("is_active", True)
        return {"success": True, "data": q.execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/transport")
async def create_transport(body: TransportCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("transport").insert(data).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

@app.delete("/api/transport/{id}")
async def delete_transport(id: str):
    """Soft delete — set is_active=false. Preserves FKs from applications/schedules."""
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        supabase.table("transport").update({"is_active": False}).eq("id", id).execute()
        return {"success": True}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/transport/{id}/restore")
async def restore_transport(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        supabase.table("transport").update({"is_active": True}).eq("id", id).execute()
        return {"success": True}
    except Exception as e: return {"success": False, "error": str(e)}

@app.get("/api/transport/{id}")
async def get_transport_info(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        res = supabase.table("transport").select("*").eq("id", id).single().execute()
        hist = supabase.table("transport_history").select("*").eq("transport_id", id).order("created_at", desc=True).limit(5).execute()
        return {"success": True, "data": {**res.data, "history": hist.data}}
    except Exception as e: return {"success": False, "error": str(e)}

@app.patch("/api/transport/{id}")
async def patch_transport(id: str, body: TransportUpdate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("transport").update(data).eq("id", id).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

# ── TRANSPORT EXPENSES ─────────────────────

@app.get("/api/transport/{id}/expenses")
async def get_transport_expenses(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        result = supabase.table("transport_expenses").select("*").eq("transport_id", id).order("created_at", desc=True).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/transport/expenses")
async def create_transport_expense(body: ExpenseCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        result = supabase.table("transport_expenses").insert(body.dict()).execute()
        return {"success": True, "data": result.data[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── OPERATORS (DEPRECATED) ────────────────────────
# /api/operators/* endpoints removed — use /api/users/* instead.
# Operators live in the 'users' table with role='operator'.

# ── ANALYTICS ─────────────────────────────────────────────

@app.get("/api/analytics")
async def get_analytics():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        all_apps = supabase.table("applications").select("id, status, source, priority, created_at, waste_type").execute()
        data = all_apps.data or []

        total = len(data)
        new_count = len([a for a in data if a.get("status") == "new"])
        in_progress = len([a for a in data if a.get("status") == "in_progress"])
        closed = len([a for a in data if a.get("status") == "closed"])
        urgent = len([a for a in data if a.get("priority", 0) >= 1])

        # By source
        sources = {}
        for a in data:
            s = a.get("source") or "unknown"
            sources[s] = sources.get(s, 0) + 1

        # By date (last 30 days)
        from datetime import datetime, timedelta, timezone
        today = datetime.now(timezone.utc).date()
        by_date = {}
        for i in range(30):
            day = today - timedelta(days=i)
            key_day = day.isoformat()
            by_date[key_day] = len([
                a for a in data
                if a.get("created_at", "").startswith(key_day)
            ])
            
        apps_history = [{"date": k, "count": v} for k, v in reversed(by_date.items())]

        transport_result = supabase.table("transport").select("id, status").execute()
        transport = transport_result.data or []
        
        sched_result = supabase.table("schedules").select("id, next_pickup").execute()
        sched_data = sched_result.data or []
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_pickups = len([s for s in sched_data if s.get("next_pickup") == tomorrow])

        return {
            "success": True,
            "data": {
                "applications": {
                    "total": total,
                    "new": new_count,
                    "in_progress": in_progress,
                    "closed": closed,
                    "urgent": urgent,
                    "by_source": sources,
                    "by_date": by_date,
                },
                "applications_history": apps_history,
                "transport": {
                    "total": len(transport),
                    "working": len([t for t in transport if t.get("status") == "working"]),
                    "available": len([t for t in transport if t.get("status") == "available"]),
                    "repair": len([t for t in transport if t.get("status") == "repair"]),
                },
                "schedule": {
                    "total_objects": len(sched_data),
                    "tomorrow_pickups": tomorrow_pickups,
                }
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
# ── SERVICE ZONES ─────────────────────────

class ZoneCreate(BaseModel):
    name: str # required
    description: Optional[str] = None
    color: Optional[str] = '#3B82F6'
    is_active: Optional[bool] = True

class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

@app.get("/api/zones")
async def get_zones():
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("service_zones").select("*").execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/zones")
async def create_zone(body: ZoneCreate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("service_zones").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/zones/{id}")
async def update_zone(id: str, body: ZoneUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("service_zones").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/zones/{id}")
async def delete_zone(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("service_zones").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── CONTACTS ──────────────────────────────

class ContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    institution_id: Optional[str] = None
    notes: Optional[str] = None

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None

@app.get("/api/contacts")
async def get_contacts():
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("contacts").select(
            "*, institution:institutions(id, name)"
        ).order("name").execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/contacts")
async def create_contact(body: ContactCreate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("contacts").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/contacts/{id}")
async def update_contact(id: str, body: ContactUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("contacts").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/contacts/{id}")
async def delete_contact(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("contacts").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── ORGANIZATION PROFILE ──────────────────

class OrgUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    working_hours: Optional[str] = None

@app.get("/api/organization")
async def get_organization():
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("organization").select("*").limit(1).execute()
        return {"success": True, "data": result.data[0] if result.data else {}}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/organization/{id}")
async def update_organization(id: str, body: OrgUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("organization").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── REFUSAL WORKFLOW (operator → admin approval) ───────────────────────────

@app.post("/api/applications/{id}/reject")
async def reject_application(id: str, body: RefusalCreate):
    """Operator initiates client refusal. Status -> pending_admin_approval.
    Releases assigned transport (if any) back to 'available'."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        # Fetch current app to know vehicle_id
        cur = supabase.table("applications").select("vehicle_id").eq("id", id).single().execute()
        vehicle_id = cur.data.get("vehicle_id") if cur.data else None
        updates = {
            "status": "pending_admin_approval",
            "refusal_notes": body.refusal_notes,
            "refused_at": datetime.now(timezone.utc).isoformat(),
        }
        if body.operator_id:
            updates["refused_by_operator_id"] = body.operator_id
        result = supabase.table("applications").update(updates).eq("id", id).execute()
        # Release transport
        if vehicle_id:
            try:
                supabase.table("transport").update({
                    "status": "available",
                    "current_task": None
                }).eq("id", vehicle_id).execute()
            except Exception:
                pass
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/applications/{id}/signature")
async def attach_refusal_signature(id: str, body: RefusalSignature):
    """Driver attaches refusal signature from mini-app. Doesn't change status —
    signature is just metadata that admin can review before approving."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {"refusal_signature_url": body.signature_url}
        if body.lat is not None:
            updates["refused_lat"] = body.lat
        if body.lng is not None:
            updates["refused_lng"] = body.lng
        result = supabase.table("applications").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/applications/{id}/refusal/approve")
async def approve_refusal(id: str, body: RefusalDecision):
    """Admin approves the refusal. Final status -> cancelled."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {
            "status": "cancelled",
            "refusal_approved_at": datetime.now(timezone.utc).isoformat(),
        }
        if body.approver_id:
            updates["refusal_approved_by"] = body.approver_id
        if body.admin_note:
            # Append admin note to refusal_notes
            cur = supabase.table("applications").select("refusal_notes").eq("id", id).single().execute()
            prev = (cur.data or {}).get("refusal_notes") or ""
            updates["refusal_notes"] = f"{prev}\n\n[Админ] {body.admin_note}".strip()
        result = supabase.table("applications").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/applications/{id}/refusal/return")
async def return_refusal(id: str, body: RefusalDecision):
    """Admin returns the refusal to the operator (rejects the refusal)."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        target_status = body.return_to_status or "in_progress"
        updates = {"status": target_status}
        if body.admin_note:
            cur = supabase.table("applications").select("refusal_notes").eq("id", id).single().execute()
            prev = (cur.data or {}).get("refusal_notes") or ""
            updates["refusal_notes"] = f"{prev}\n\n[Админ возврат] {body.admin_note}".strip()
        result = supabase.table("applications").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── SCHEDULE COMPLETE ─────────────────────────────

@app.patch("/api/schedules/{id}/complete")
async def complete_schedule(id: str):
    """Mark a scheduled pickup as completed today.
    Sets last_completed + last_run_at = now, and advances next_run_at
    by interval_days (if interval_days > 0)."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        cur = supabase.table("schedules").select("interval_days, next_run_at").eq("id", id).single().execute()
        row = cur.data or {}
        now_dt = datetime.now(timezone.utc)
        today_date = now_dt.date().isoformat()
        updates = {
            "last_completed": now_dt.isoformat(),
            "last_run_at": today_date,
        }
        # Advance next_run_at if interval is set
        try:
            days = int(row.get("interval_days") or 0)
        except (TypeError, ValueError):
            days = 0
        if days > 0:
            updates["next_run_at"] = (now_dt + timedelta(days=days)).date().isoformat()
        result = supabase.table("schedules").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data[0] if result.data else None}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── AUTH MODELS ───────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    email: str
    password: str

class RegisterBody(BaseModel):
    name: str
    email: str
    password: str
    role: Optional[str] = "operator"
    phone: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class RoleUpdate(BaseModel):
    role: str

class NotifPrefsUpdate(BaseModel):
    new_application: Optional[bool] = None
    status_changed: Optional[bool] = None
    urgent_application: Optional[bool] = None
    system_update: Optional[bool] = None

# ── AUTH ENDPOINTS ────────────────────────────────────────────────────────────

@app.post("/api/auth/register")
async def register(body: RegisterBody):
    """Public registration. Self-signup is always pending+operator.
    When called by an admin (with role/phone), creates immediately with given role (still pending until approved)."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        existing = supabase.table("users").select("id").eq("email", body.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email уже занят")
        hashed = hash_password(body.password)
        role = body.role if body.role in ("operator", "admin", "super_admin") else "operator"
        new_user = {
            "name": body.name,
            "email": body.email,
            "password_hash": hashed,
            "role": role,
            "status": "pending",
        }
        if body.phone:
            new_user["phone"] = body.phone
        result = supabase.table("users").insert(new_user).execute()
        created = result.data[0] if result.data else None
        return {
            "success": True,
            "status": "pending",
            "user": {
                "id": created["id"] if created else None,
                "name": created["name"] if created else body.name,
                "email": created["email"] if created else body.email,
                "role": created["role"] if created else role,
            } if created else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/auth/login")
async def login(body: LoginBody):
    """Login — only approved users can login. Pending/rejected get error message."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("users").select("*").eq("email", body.email).execute()
        if not result.data:
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        user = result.data[0]
        if not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        # Check approval status
        status = user.get("status", "approved")
        if status == "pending":
            return {"success": False, "status": "pending",
                    "message": "Ваша регистрация ожидает подтверждения администратора"}
        if status == "rejected":
            return {"success": False, "status": "rejected",
                    "message": "Ваша регистрация отклонена. Свяжитесь с администратором."}
        # Approved — issue token
        supabase.table("users").update({
            "last_login": datetime.now(timezone.utc).isoformat()
        }).eq("id", user["id"]).execute()
        token = create_token(user["id"], user["email"], user["role"])
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/auth/me")
async def get_me(request: Request):
    try:
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "")
        if not token:
            return {"success": False, "error": "No token"}
        payload = verify_token(token)
        user_id = payload["sub"]
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("users").select(
            "id, name, email, role, status, last_login, created_at"
        ).eq("id", user_id).single().execute()
        try:
            prefs = supabase.table("notification_prefs").select("*").eq("user_id", user_id).execute()
            notif_prefs = prefs.data[0] if prefs.data else {}
        except Exception:
            notif_prefs = {}
        return {
            "success": True,
            "user": result.data,
            "notification_prefs": notif_prefs
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── USER MANAGEMENT ───────────────────────────────────────────────────────────

@app.get("/api/users")
async def get_users(include_inactive: Optional[bool] = False):
    """Admin: get all users with status. By default excludes soft-deleted."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        q = supabase.table("users").select(
            "id, name, email, role, status, phone, is_active, last_login, created_at"
        ).order("created_at", desc=True)
        if not include_inactive:
            q = q.eq("is_active", True)
        result = q.execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/users/{id}")
async def update_user(id: str, body: UserUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("users").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/users/{id}/approve")
async def approve_user(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"status": "approved"}).eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/users/{id}/reject")
async def reject_user(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"status": "rejected"}).eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/users/{id}/role")
async def change_role(id: str, body: RoleUpdate):
    try:
        if body.role not in ("operator", "admin", "super_admin"):
            raise HTTPException(status_code=400, detail="Недопустимая роль")
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"role": body.role}).eq("id", id).execute()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/users/{id}/password")
async def change_password(id: str, body: PasswordChange):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        user = supabase.table("users").select("password_hash").eq("id", id).single().execute()
        if not verify_password(body.old_password, user.data["password_hash"]):
            raise HTTPException(status_code=400, detail="Неверный текущий пароль")
        new_hash = hash_password(body.new_password)
        supabase.table("users").update({"password_hash": new_hash}).eq("id", id).execute()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/users/{id}")
async def delete_user(id: str):
    """Soft delete — set is_active=false. Preserves foreign keys from
    historical applications / messages."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"is_active": False}).eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/users/{id}/restore")
async def restore_user(id: str):
    """Reactivate soft-deleted user."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"is_active": True}).eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/users/{id}/notif-prefs")
async def update_notif_prefs(id: str, body: NotifPrefsUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        existing = supabase.table("notification_prefs").select("id").eq("user_id", id).execute()
        if existing.data:
            result = supabase.table("notification_prefs").update(updates).eq("user_id", id).execute()
        else:
            result = supabase.table("notification_prefs").insert({"user_id": id, **updates}).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# DRIVER WORKFLOW (iter3)
# ═══════════════════════════════════════════════════════════════════════════
# Three endpoints that mediate between admin UI / n8n Telegram bot / DB:
#  1. POST /api/transport/register        — driver binds Telegram chat_id by phone
#  2. POST /api/applications/{id}/assign  — operator assigns vehicle, fires webhook
#  3. POST /api/applications/{id}/driver-action — driver accepts/refuses/completes
#
# Architecture: API is the single source of truth.
# n8n never writes to Supabase directly; it only calls these endpoints.

import re as _re

def _normalize_phone_kg(raw):
    """Return canonical 996XXXXXXXXX or None."""
    if not raw:
        return None
    digits = _re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if len(digits) == 12 and digits.startswith("996"):
        return digits
    if len(digits) == 10 and digits[0] in ("0", "8"):
        return "996" + digits[1:]
    if len(digits) == 9:
        return "996" + digits
    return None


def _trigger_n8n_webhook(payload):
    """Fire-and-forget POST to n8n driver-assign webhook.
    Returns (ok: bool, err: Optional[str]). Does not raise.
    """
    url = os.environ.get("N8N_DRIVER_ASSIGN_WEBHOOK_URL")
    if not url:
        return False, "N8N_DRIVER_ASSIGN_WEBHOOK_URL not configured"
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()  # drain
        return True, None
    except Exception as e:
        return False, str(e)


# ── 1. Driver registration ─────────────────────────────────────────────────

class DriverRegister(BaseModel):
    phone: str
    telegram_chat_id: int
    telegram_username: Optional[str] = None


@app.post("/api/transport/register")
async def driver_register(body: DriverRegister):
    """Bind a Telegram chat_id to a transport record by matching driver_phone.

    Called by n8n when driver sends `/start <phone>` to the bot.
    """
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        phone = _normalize_phone_kg(body.phone)
        if not phone:
            return {"success": False, "error": "invalid_phone"}

        match = (
            supabase.table("transport")
            .select("id, name, plate, driver_name, driver_phone, is_active")
            .eq("driver_phone", phone)
            .execute()
        )
        rows = match.data or []
        rows = [r for r in rows if r.get("is_active") in (True, None)]
        if not rows:
            return {"success": False, "error": "phone_not_found"}

        t = rows[0]
        updates = {
            "telegram_chat_id": str(body.telegram_chat_id),
            "telegram_username": body.telegram_username,
            "telegram_linked_at": datetime.now(timezone.utc).isoformat(),
        }
        supabase.table("transport").update(updates).eq("id", t["id"]).execute()
        return {
            "success": True,
            "data": {
                "id": t["id"],
                "name": t.get("name"),
                "plate": t.get("plate"),
                "driver_name": t.get("driver_name"),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 2. Assign vehicle to application ───────────────────────────────────────

class AssignVehicle(BaseModel):
    vehicle_id: str


@app.post("/api/applications/{id}/assign")
async def assign_vehicle(id: str, body: AssignVehicle):
    """Operator assigns a vehicle to an application.

    Side effects: sets status='assigned', records assigned_at,
    fires webhook to n8n which will notify the driver in Telegram.
    """
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        # Verify transport exists and is active
        t = (
            supabase.table("transport")
            .select("id, name, plate, telegram_chat_id, driver_name, is_active")
            .eq("id", body.vehicle_id)
            .single()
            .execute()
        )
        if not t.data:
            return {"success": False, "error": "vehicle_not_found"}
        if t.data.get("is_active") is False:
            return {"success": False, "error": "vehicle_inactive"}

        # Update application
        now_iso = datetime.now(timezone.utc).isoformat()
        result = (
            supabase.table("applications")
            .update({
                "vehicle_id": body.vehicle_id,
                "status": "assigned",
                "assigned_at": now_iso,
            })
            .eq("id", id)
            .execute()
        )
        if not result.data:
            return {"success": False, "error": "application_not_found"}

        # Fire webhook to n8n (non-blocking semantics — we don't fail the assign
        # if webhook is down; the driver can be reached by phone in that case)
        webhook_ok, webhook_err = _trigger_n8n_webhook({
            "application_id": id,
            "vehicle_id": body.vehicle_id,
            "has_telegram": bool(t.data.get("telegram_chat_id")),
        })

        return {
            "success": True,
            "data": result.data[0] if result.data else None,
            "webhook": {"ok": webhook_ok, "error": webhook_err},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 3. Driver action (accept / refuse / complete) ──────────────────────────

class DriverAction(BaseModel):
    action: str  # 'accept' | 'refuse' | 'complete'
    telegram_chat_id: int


@app.post("/api/applications/{id}/driver-action")
async def driver_action(id: str, body: DriverAction):
    """Driver presses a button in Telegram. Validates that the chat_id
    matches the transport assigned to this application, then transitions
    status accordingly.

    accept   : assigned  → accepted
    refuse   : assigned  → new (returns to operators' queue, vehicle_id cleared)
    complete : accepted  → completed (also shifts schedule.next_run_at)
    """
    if body.action not in ("accept", "refuse", "complete"):
        return {"success": False, "error": "invalid_action"}

    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        # Fetch application + its assigned transport
        app_row = (
            supabase.table("applications")
            .select("id, status, vehicle_id, institution_id")
            .eq("id", id)
            .single()
            .execute()
        )
        if not app_row.data:
            return {"success": False, "error": "application_not_found"}
        a = app_row.data
        if not a.get("vehicle_id"):
            return {"success": False, "error": "no_vehicle_assigned"}

        # Verify the driver pressing the button owns the assigned vehicle
        t = (
            supabase.table("transport")
            .select("id, telegram_chat_id, name, plate")
            .eq("id", a["vehicle_id"])
            .single()
            .execute()
        )
        if not t.data:
            return {"success": False, "error": "vehicle_not_found"}
        expected_chat = t.data.get("telegram_chat_id")
        if not expected_chat or str(expected_chat) != str(body.telegram_chat_id):
            return {"success": False, "error": "chat_id_mismatch"}

        # Compute state transition
        now_iso = datetime.now(timezone.utc).isoformat()
        if body.action == "accept":
            if a["status"] != "assigned":
                return {"success": False, "error": "invalid_state", "current_status": a["status"]}
            updates = {"status": "accepted", "accepted_at": now_iso}
        elif body.action == "refuse":
            if a["status"] not in ("assigned", "accepted"):
                return {"success": False, "error": "invalid_state", "current_status": a["status"]}
            updates = {
                "status": "new",
                "vehicle_id": None,
                "assigned_at": None,
                "accepted_at": None,
            }
        else:  # complete
            if a["status"] not in ("accepted", "assigned"):
                return {"success": False, "error": "invalid_state", "current_status": a["status"]}
            updates = {"status": "completed", "completed_at": now_iso}

        upd_result = (
            supabase.table("applications").update(updates).eq("id", id).execute()
        )

        # If completed and application is tied to an institution, advance the schedule
        schedule_advanced = None
        if body.action == "complete" and a.get("institution_id"):
            sch = (
                supabase.table("schedules")
                .select("id, next_run_at, interval_days")
                .eq("institution_id", a["institution_id"])
                .execute()
            )
            if sch.data:
                # Advance every schedule for this institution that's due on/before today
                today = datetime.now(timezone.utc).date()
                advanced_ids = []
                for s in sch.data:
                    nxt = s.get("next_run_at")
                    ival = s.get("interval_days") or 7
                    if not nxt:
                        continue
                    try:
                        cur = datetime.fromisoformat(nxt.replace("Z", "+00:00")).date()
                    except Exception:
                        continue
                    if cur <= today:
                        new_next = cur + timedelta(days=int(ival))
                        supabase.table("schedules").update({
                            "next_run_at": new_next.isoformat(),
                            "last_completed": now_iso,
                            "last_run_at": now_iso,
                        }).eq("id", s["id"]).execute()
                        advanced_ids.append(s["id"])
                schedule_advanced = advanced_ids or None

        return {
            "success": True,
            "data": upd_result.data[0] if upd_result.data else None,
            "schedule_advanced": schedule_advanced,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    phone: str
    address: str
    description: Optional[str] = None
    waste_type: Optional[str] = None
    source: Optional[str] = "whatsapp"
    status: Optional[str] = "new"
    institution_name: Optional[str] = None
    user_type: Optional[str] = None
    priority: Optional[str] = "medium"

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    operator_id: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None

class InstitutionCreate(BaseModel):
    name: str
    address: Optional[str] = None
    type: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None

class WasteTypeCreate(BaseModel):
    name: str
    color: Optional[str] = None

class ScheduleCreate(BaseModel):
    institution_id: Optional[str] = None
    transport_id: Optional[str] = None
    day_of_week: Optional[int] = None
    time_slot: Optional[str] = None
    object_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    next_pickup: Optional[str] = None
    interval_type: Optional[str] = None
    interval_value: Optional[str] = None
    last_pickup: Optional[str] = None
    notes: Optional[str] = None

class ScheduleUpdate(BaseModel):
    institution_id: Optional[str] = None
    transport_id: Optional[str] = None
    day_of_week: Optional[int] = None
    time_slot: Optional[str] = None
    object_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    next_pickup: Optional[str] = None
    interval_type: Optional[str] = None
    interval_value: Optional[str] = None
    last_pickup: Optional[str] = None
    notes: Optional[str] = None

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
    brand: str
    plate: str
    type: str
    status: str = "бош"
    current_task: Optional[str] = None
    notes: Optional[str] = None

class VehicleUpdate(BaseModel):
    brand: Optional[str] = None
    plate: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    current_task: Optional[str] = None
    notes: Optional[str] = None

class TelegramNotify(BaseModel):
    chat_id: str
    message: str

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
    """Entry point for n8n/WhatsApp/Public forms. Default status: pending_review"""
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = body.dict()
        if not data.get("status"):
            data["status"] = "pending_review"
        if not data.get("priority"):
            data["priority"] = "medium"
            
        result = supabase.table("applications").insert(data).execute()
        return {"success": True, "data": result.data[0]}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── APPLICATIONS ──────────────────────────

@app.get("/api/applications")
async def get_applications(
    status: Optional[str] = None,
    waste_type_id: Optional[str] = None,
    institution_id: Optional[str] = None,
    priority: Optional[str] = None,
    source: Optional[str] = None,
):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        query = supabase.table("applications").select(
            "*, institution:institutions(id, name, address), waste_type:waste_types(id, name)"
        ).order("created_at", desc=True)

        if status:         query = query.eq("status", status)
        if waste_type_id:  query = query.eq("waste_type_id", waste_type_id)
        if institution_id: query = query.eq("institution_id", institution_id)
        if priority:       query = query.eq("priority", priority)
        if source:         query = query.eq("source", source)

        result = query.execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/applications/{id}")
async def get_application_by_id(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        result = supabase.table("applications").select(
            "*, institution:institutions(*), waste_type:waste_types(*)"
        ).eq("id", id).single().execute()
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
async def get_inst():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("institutions").select("*").order("name").execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/institutions")
async def create_inst(body: InstitutionCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("institutions").insert(body.dict()).execute().data[0]}
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
        return {"success": True, "data": supabase.table("schedules").select("*, institution:institutions(name), transport:transport(name, plate)").execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.get("/api/schedules/tomorrow")
async def get_sched_tomorrow():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        return {"success": True, "data": supabase.table("schedules").select("*, institution:institutions(name), transport:transport(name, plate)").eq("next_pickup", tomorrow).execute().data}
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

# ── VEHICLES ─────────────────────────────

@app.get("/api/vehicles")
async def get_vehicles():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("vehicles").select("*").order("plate").execute().data}
    except Exception as e: return {"success": False, "error": str(e)}

@app.post("/api/vehicles")
async def create_vehicle(body: VehicleCreate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("vehicles").insert(data).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

@app.patch("/api/vehicles/{id}")
async def update_vehicle(id: str, body: VehicleUpdate):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        data = {k: v for k, v in body.dict().items() if v is not None}
        return {"success": True, "data": supabase.table("vehicles").update(data).eq("id", id).execute().data[0]}
    except Exception as e: return {"success": False, "error": str(e)}

@app.delete("/api/vehicles/{id}")
async def delete_vehicle(id: str):
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        supabase.table("vehicles").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e: return {"success": False, "error": str(e)}

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
        query = supabase.table("applications").select("*, institution:institutions(name), waste_type:waste_types(name)")
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
        return {"success": True, "data": supabase.table("schedules").select("*, institution:institutions(name), transport:transport(name, plate)").execute().data}
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
async def get_transport_list():
    url, key = get_supabase()
    supabase = create_client(url, key)
    try:
        return {"success": True, "data": supabase.table("transport").select("*").order("name").execute().data}
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

# ── OPERATORS CRUD ────────────────────────

class OperatorCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = "operator"

class OperatorUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

@app.get("/api/operators")
async def get_operators():
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("operators").select("*").execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/operators")
async def create_operator(body: OperatorCreate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("operators").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/operators/{id}")
async def update_operator(id: str, body: OperatorUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("operators").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/operators/{id}")
async def delete_operator(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("operators").update({"is_active": False}).eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── ANALYTICS ─────────────────────────────────────────────

@app.get("/api/analytics")
async def get_analytics():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        all_apps = supabase.table("applications").select("id, status, source, priority, created_at, waste_type_id").execute()
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

# ── AUTH MODELS ───────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    email: str
    password: str

class RegisterBody(BaseModel):
    name: str
    email: str
    password: str

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
    """Public registration — creates user with status=pending. Admin must approve."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        existing = supabase.table("users").select("id").eq("email", body.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email уже занят")
        hashed = hash_password(body.password)
        supabase.table("users").insert({
            "name": body.name,
            "email": body.email,
            "password_hash": hashed,
            "role": "operator",
            "status": "pending",
        }).execute()
        return {"success": True, "status": "pending"}
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
async def get_users():
    """Admin: get all users with status."""
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("users").select(
            "id, name, email, role, status, last_login, created_at"
        ).order("created_at", desc=True).execute()
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
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"role": body.role}).eq("id", id).execute()
        return {"success": True}
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
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").delete().eq("id", id).execute()
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


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
    sender_role: str  # "operator" or "client"

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    operator_id: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None

class ScheduleCreate(BaseModel):
    transport_id: Optional[str] = None
    route: Optional[str] = None
    scheduled_date: Optional[str] = None
    institution_id: Optional[str] = None

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

@app.get("/")
def read_root():
    url, key = get_supabase()
    return {
        "status": "running",
        "debug": {
            # Проверяем не просто наличие, а длину, чтобы исключить пустые строки
            "has_url": bool(url and len(url) > 5),
            "has_key": bool(key and len(key) > 5)
        }
    }

@app.post("/api/applications")
async def create_application(data: dict):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        response = supabase.table("applications").insert(data).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── APPLICATIONS ──────────────────────────

@app.get("/api/applications")
async def get_applications(
    status: Optional[str] = None,
    waste_type_id: Optional[str] = None,
    institution_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    source: Optional[str] = None,
):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        query = supabase.table("applications").select(
            "*, institution:institutions(id, name, address), waste_type:waste_types(id, name)"
        ).order("created_at", desc=True)

        if status:         query = query.eq("status", status)
        if waste_type_id:  query = query.eq("waste_type_id", waste_type_id)
        if institution_id: query = query.eq("institution_id", institution_id)
        if date_from:      query = query.gte("created_at", date_from)
        if date_to:        query = query.lte("created_at", date_to)
        if source:         query = query.eq("source", source)

        result = query.execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/applications/{id}")
async def get_application(id: str):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("applications").select(
            "*, institution:institutions(*), waste_type:waste_types(*)"
        ).eq("id", id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/applications/{id}")
async def update_application(id: str, body: ApplicationUpdate):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        updates = {k: v for k, v in body.dict().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = supabase.table("applications").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/applications/{id}")
async def delete_application(id: str):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("applications").delete().eq("id", id).execute()
        return {"success": True, "data": {"deleted": True, "id": id}}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── MESSAGES ──────────────────────────────

@app.get("/api/messages")
async def get_messages(application_id: str):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("messages").select("*").eq(
            "application_id", application_id
        ).order("created_at", desc=False).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/messages")
async def create_message(body: MessageCreate):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("messages").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── INSTITUTIONS ──────────────────────────

@app.get("/api/institutions")
async def get_institutions():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("institutions").select("*").execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── WASTE TYPES ───────────────────────────

@app.get("/api/waste_types")
async def get_waste_types():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("waste_types").select("*").execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── SCHEDULES (full CRUD) ─────────────────

class ScheduleCreate(BaseModel):
    transport_id: Optional[str] = None
    driver_name: Optional[str] = None
    route: Optional[str] = None
    scheduled_date: Optional[str] = None
    start_time: Optional[str] = None
    status: Optional[str] = "planned"
    notes: Optional[str] = None

class ScheduleUpdate(BaseModel):
    transport_id: Optional[str] = None
    driver_name: Optional[str] = None
    route: Optional[str] = None
    scheduled_date: Optional[str] = None
    start_time: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

@app.get("/api/schedules")
async def get_schedules(date: Optional[str] = None):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        query = supabase.table("schedules").select(
            "*, transport:transport(id, name, plate)"
        ).order("scheduled_date", desc=False)
        if date:
            query = query.eq("scheduled_date", date)
        result = query.execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/schedules")
async def create_schedule(body: ScheduleCreate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("schedules").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/schedules/{id}")
async def update_schedule(id: str, body: ScheduleUpdate):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("schedules").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/schedules/{id}")
async def delete_schedule(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("schedules").delete().eq("id", id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── TRANSPORT ─────────────────────────────────────────────

@app.get("/api/transport")
async def get_transport():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("transport").select("*").order("created_at", desc=False).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/transport/{id}")
async def get_transport_by_id(id: str):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("transport").select("*").eq("id", id).single().execute()
        history = supabase.table("transport_history").select("*").eq("transport_id", id).order("created_at", desc=True).limit(10).execute()
        return {"success": True, "data": {**result.data, "history": history.data}}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/transport")
async def create_transport(body: TransportCreate):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("transport").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.patch("/api/transport/{id}")
async def update_transport(id: str, body: TransportUpdate):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        updates = {k: v for k, v in body.dict().items() if v is not None}
        result = supabase.table("transport").update(updates).eq("id", id).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/transport/{id}")
async def delete_transport(id: str):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        supabase.table("transport").delete().eq("id", id).execute()
        return {"success": True}
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

        # By date (last 7 days)
        from datetime import datetime, timedelta, timezone
        today = datetime.now(timezone.utc).date()
        by_date = {}
        for i in range(7):
            day = today - timedelta(days=i)
            key_day = day.isoformat()
            by_date[key_day] = len([
                a for a in data
                if a.get("created_at", "").startswith(key_day)
            ])

        transport_result = supabase.table("transport").select("id, status").execute()
        transport = transport_result.data or []

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
                "transport": {
                    "total": len(transport),
                    "working": len([t for t in transport if t.get("status") == "working"]),
                    "available": len([t for t in transport if t.get("status") == "available"]),
                    "repair": len([t for t in transport if t.get("status") == "repair"]),
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
    role: Optional[str] = "operator"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class NotifPrefsUpdate(BaseModel):
    new_application: Optional[bool] = None
    status_changed: Optional[bool] = None
    urgent_application: Optional[bool] = None
    system_update: Optional[bool] = None

# ── AUTH ENDPOINTS ────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(body: LoginBody):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("users").select("*").eq("email", body.email).eq("is_active", True).execute()
        if not result.data:
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        user = result.data[0]
        if not verify_password(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")
        supabase.table("users").update({"last_login": datetime.now(timezone.utc).isoformat()}).eq("id", user["id"]).execute()
        token = create_token(user["id"], user["email"], user["role"])
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
                "avatar_url": user.get("avatar_url"),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/auth/register")
async def register(body: RegisterBody):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        existing = supabase.table("users").select("id").eq("email", body.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email уже занят")
        hashed = hash_password(body.password)
        result = supabase.table("users").insert({
            "name": body.name,
            "email": body.email,
            "password_hash": hashed,
            "role": body.role,
        }).execute()
        user = result.data[0]
        try:
            supabase.table("notification_prefs").insert({"user_id": user["id"]}).execute()
        except Exception:
            pass
        return {"success": True, "data": {
            "id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"],
        }}
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
            "id, name, email, role, avatar_url, last_login, created_at"
        ).eq("id", user_id).single().execute()
        prefs = supabase.table("notification_prefs").select("*").eq("user_id", user_id).execute()
        return {
            "success": True,
            "user": result.data,
            "notification_prefs": prefs.data[0] if prefs.data else {}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── USER MANAGEMENT ───────────────────────────────────────────────────────────

@app.get("/api/users")
async def get_users():
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        result = supabase.table("users").select(
            "id, name, email, role, is_active, last_login, created_at"
        ).order("created_at", desc=False).execute()
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

@app.patch("/api/users/{id}/toggle")
async def toggle_user(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        user = supabase.table("users").select("is_active").eq("id", id).single().execute()
        new_status = not user.data["is_active"]
        supabase.table("users").update({"is_active": new_status}).eq("id", id).execute()
        return {"success": True, "is_active": new_status}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/users/{id}")
async def delete_user(id: str):
    try:
        url, key = get_supabase()
        supabase = create_client(url, key)
        supabase.table("users").update({"is_active": False}).eq("id", id).execute()
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


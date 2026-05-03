from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from supabase import create_client
import os

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return url, key

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


# ── SCHEDULES ─────────────────────────────

@app.get("/api/schedules")
async def get_schedules():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("schedules").select("*").order(
            "scheduled_date", desc=False
        ).execute()
        return {"success": True, "data": result.data}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/schedules")
async def create_schedule(body: ScheduleCreate):
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("schedules").insert(body.dict()).execute()
        return {"success": True, "data": result.data}
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

# ── OPERATORS ─────────────────────────────────────────────

@app.get("/api/operators")
async def get_operators():
    url, key = get_supabase()
    if not url or not key:
        return {"success": False, "error": "Credentials missing"}
    
    supabase = create_client(url, key)
    try:
        result = supabase.table("operators").select("*").eq("is_active", True).execute()
        return {"success": True, "data": result.data}
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
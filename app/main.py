import hashlib
import hmac
import json
import mimetypes
import os
import secrets
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path

import jdatetime
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app import auth, models
from app.auth import utcnow as closure_now
from app.database import Base, SessionLocal, engine, get_db
from app.migrations import migrate_schema

BASE_DIR = Path(__file__).parent
STATUS_LABELS = {"new": "جدید", "in_progress": "در حال بررسی", "waiting": "منتظر", "resolved": "حل‌شده", "closed": "بسته"}
STATUSES = list(STATUS_LABELS)
CATEGORIES = {"hardware": "سخت‌افزار", "software": "نرم‌افزار", "network": "شبکه", "access": "دسترسی", "other": "سایر"}
PRIORITIES = ["low", "normal", "high", "urgent"]
SLA_HOURS = {"low": 72, "normal": 48, "high": 24, "urgent": 4}
SEED_USERS = [
    ("admin", "Admin", "admin"),
    ("agent1", "Agent 1", "agent"),
    ("agent2", "Agent 2", "agent"),
    ("user1", "User 1", "user"),
]
VALID_ROLES = {"user", "agent", "admin"}
ASSET_STATUSES = {"in_use", "storage", "repair", "retired"}

migrate_schema(engine)
Base.metadata.create_all(engine)

with SessionLocal() as db:
    for username, full_name, role in SEED_USERS:
        user = db.scalar(select(models.User).where(models.User.username == username))
        if not user:
            user = models.User(username=username, full_name=full_name, role=role)
            db.add(user)
            db.flush()
        if db.get(models.Credential, user.id) is None:
            password = "admin" if username == "admin" else secrets.token_urlsafe(9)
            db.add(
                models.Credential(
                    user_id=user.id, password_hash=auth.hash_password(password)
                )
            )
            print(f"INITIAL PASSWORD  {username}: {password}", flush=True)
    db.commit()

_csrf_secret_hex = os.getenv("CSRF_SECRET_HEX", "")
if _csrf_secret_hex:
    try:
        CSRF_SECRET = bytes.fromhex(_csrf_secret_hex)
    except ValueError as exc:
        raise RuntimeError("CSRF_SECRET_HEX must contain hexadecimal bytes") from exc
    if len(CSRF_SECRET) < 32:
        raise RuntimeError("CSRF_SECRET_HEX must contain at least 32 bytes")
else:
    CSRF_SECRET = secrets.token_bytes(32)


def sign_csrf(token: str) -> str:
    return hmac.new(CSRF_SECRET, token.encode(), hashlib.sha256).hexdigest()


async def csrf_guard(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie = request.cookies.get("itdesk_csrf", "")
    token, separator, signature = cookie.partition(".")
    form = await request.form()
    submitted = str(form.get("csrf_token", ""))
    if not separator or not token or not hmac.compare_digest(signature.encode(), sign_csrf(token).encode()) or not hmac.compare_digest(submitted.encode(), token.encode()):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

mimetypes.add_type("font/woff2", ".woff2")
app = FastAPI(title="IT Desk", dependencies=[Depends(csrf_guard)])
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
_allowed_hosts = [value.strip() for value in os.getenv("ALLOWED_HOSTS", "").split(",") if value.strip()]
if _allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)

@app.middleware("http")
async def csrf_cookie(request: Request, call_next):
    cookie = request.cookies.get("itdesk_csrf", "")
    token, separator, signature = cookie.partition(".")
    if not separator or not token or not hmac.compare_digest(signature.encode(), sign_csrf(token).encode()):
        token = secrets.token_urlsafe(32)
        cookie = f"{token}.{sign_csrf(token)}"
        new_cookie = True
    else:
        new_cookie = False
    request.state.csrf_token = token
    response = await call_next(request)
    if new_cookie:
        response.set_cookie("itdesk_csrf", cookie, httponly=True, samesite="strict", secure=os.getenv("COOKIE_SECURE") == "1")
    return response
templates = Jinja2Templates(directory=BASE_DIR / "templates")


templates.env.globals.update(status_fa=STATUS_LABELS, categories=CATEGORIES)


def shamsi(dt):
    local = dt + timedelta(hours=3, minutes=30)  # UTC -> Tehran
    return jdatetime.datetime.fromgregorian(datetime=local).strftime("%Y/%m/%d %H:%M")


def fromjson(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


templates.env.filters["shamsi"] = shamsi
templates.env.filters["fromjson"] = fromjson


def ticket_is_overdue(ticket: models.Ticket, now: datetime | None = None) -> bool:
    return bool(ticket.due_at and ticket.status not in {"resolved", "closed"} and ticket.due_at < (now or datetime.utcnow()))


templates.env.filters["overdue"] = ticket_is_overdue


@app.exception_handler(auth.LoginRequired)
async def login_required_handler(request: Request, exc: auth.LoginRequired):
    return RedirectResponse("/login", status_code=303)


def is_staff(user: models.User) -> bool:
    return user.role in ("agent", "admin")


def audit(db, actor_id, action, entity, entity_id, detail=""):
    db.add(
        models.AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
        )
    )


def get_ticket_for(db: Session, ticket_id: int, user: models.User) -> models.Ticket:
    ticket = db.get(models.Ticket, ticket_id)
    if ticket is None or (not is_staff(user) and ticket.requester_id != user.id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    key = username.strip().lower()[:50]
    if auth.is_locked(key):
        return templates.TemplateResponse(
            request, "login.html", {"error": "locked"}, status_code=429
        )
    user = db.scalar(select(models.User).where(models.User.username == key))
    cred = db.get(models.Credential, user.id) if user else None
    ok = bool(
        user
        and user.is_active
        and cred
        and auth.verify_password(password, cred.password_hash)
    )
    if not ok:
        auth.register_failure(key)
        audit(db, user.id if user else None, "login_failed", "user",
              user.id if user else None, key)
        db.commit()
        return templates.TemplateResponse(
            request, "login.html", {"error": "invalid"}, status_code=401
        )
    auth.clear_failures(key)
    token = auth.create_session(db, user)
    audit(db, user.id, "login", "user", user.id)
    db.commit()
    response = RedirectResponse("/tickets", status_code=303)
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE") == "1",  # set to 1 once HTTPS is on
        max_age=auth.SESSION_HOURS * 3600,
    )
    return response


@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        auth.destroy_session(db, token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


@app.get("/account/password")
def change_password_page(
    request: Request,
    user: models.User = Depends(auth.get_current_user),
):
    return templates.TemplateResponse(request, "change_password.html", {"user": user})


@app.post("/account/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    credential = db.get(models.Credential, user.id)
    if credential is None or not auth.verify_password(current_password, credential.password_hash):
        return templates.TemplateResponse(request, "change_password.html", {"user": user, "error": "current"}, status_code=400, headers={"Cache-Control": "no-store"})
    if not 12 <= len(new_password) <= 128 or new_password != confirm_password:
        return templates.TemplateResponse(request, "change_password.html", {"user": user, "error": "new"}, status_code=400, headers={"Cache-Control": "no-store"})
    credential.password_hash = auth.hash_password(new_password)
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id == user.id))
    audit(db, user.id, "change_password", "user", user.id)
    db.commit()
    response = RedirectResponse("/login", status_code=303, headers={"Cache-Control": "no-store"})
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


@app.get("/admin/users")
def admin_users(
    request: Request,
    user: models.User = Depends(auth.require_roles("admin")),
    db: Session = Depends(get_db),
):
    users = db.scalars(select(models.User).order_by(models.User.id)).all()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"users": users, "user": user, "generated_password": None},
    )


@app.post("/admin/users")
def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    role: str = Form("user"),
    password: str = Form(""),
    user: models.User = Depends(auth.require_roles("admin")),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    full_name = full_name.strip()
    if not username or len(username) > 50 or not username.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid username")
    if not full_name or len(full_name) > 100:
        raise HTTPException(status_code=400, detail="Invalid full name")
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if db.scalar(select(models.User).where(models.User.username == username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    if password and (len(password) < 12 or len(password) > 128):
        raise HTTPException(status_code=400, detail="Password must be between 12 and 128 characters")
    generated_password = password or secrets.token_urlsafe(9)
    new_user = models.User(username=username, full_name=full_name, role=role)
    db.add(new_user)
    db.flush()
    db.add(models.Credential(user_id=new_user.id, password_hash=auth.hash_password(generated_password)))
    audit(db, user.id, "create", "user", new_user.id, username)
    db.commit()
    users = db.scalars(select(models.User).order_by(models.User.id)).all()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"users": users, "user": user, "generated_password": generated_password if not password else None},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/admin/users/{user_id}/update")
def update_user(
    user_id: int,
    full_name: str = Form(...),
    role: str = Form(...),
    is_active: str = Form("0"),
    user: models.User = Depends(auth.require_roles("admin")),
    db: Session = Depends(get_db),
):
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if role not in VALID_ROLES or not full_name.strip() or len(full_name.strip()) > 100:
        raise HTTPException(status_code=400, detail="Invalid user data")
    active = is_active == "1"
    if target.id == user.id and not active:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")
    if target.role == "admin" and (role != "admin" or not active):
        remaining = db.scalar(
            select(models.User).where(
                models.User.role == "admin",
                models.User.is_active.is_(True),
                models.User.id != target.id,
            )
        )
        if remaining is None:
            raise HTTPException(status_code=400, detail="At least one active admin is required")
    target.full_name = full_name.strip()
    target.role = role
    target.is_active = active
    if not active:
        db.execute(delete(models.LoginSession).where(models.LoginSession.user_id == target.id))
    audit(db, user.id, "update", "user", target.id, f"role={role}; active={active}")
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/reset-password")
def reset_user_password(
    request: Request,
    user_id: int,
    user: models.User = Depends(auth.require_roles("admin")),
    db: Session = Depends(get_db),
):
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    generated_password = secrets.token_urlsafe(9)
    credential = db.get(models.Credential, target.id)
    if credential is None:
        credential = models.Credential(user_id=target.id, password_hash=auth.hash_password(generated_password))
        db.add(credential)
    else:
        credential.password_hash = auth.hash_password(generated_password)
    db.execute(delete(models.LoginSession).where(models.LoginSession.user_id == target.id))
    audit(db, user.id, "reset_password", "user", target.id)
    db.commit()
    users = db.scalars(select(models.User).order_by(models.User.id)).all()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"users": users, "user": user, "generated_password": generated_password},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/assets")
def assets_page(
    request: Request,
    imported: int = 0,
    q: str = "",
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    q = q.strip()
    query = select(models.Asset)
    if q:
        query = query.where(models.Asset.name.icontains(q, autoescape=True) |
                            models.Asset.tag.icontains(q, autoescape=True) |
                            models.Asset.location.icontains(q, autoescape=True))
    assets = db.scalars(query.order_by(models.Asset.id.desc())).all()
    users = db.scalars(select(models.User).where(models.User.is_active.is_(True)).order_by(models.User.full_name)).all()
    return templates.TemplateResponse(request, "assets.html", {"assets": assets, "users": users, "user": user, "imported": imported, "q": q})


@app.get("/assets/{asset_id}")
def asset_detail(
    asset_id: int,
    request: Request,
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    tickets = db.scalars(
        select(models.Ticket).where(models.Ticket.asset_id == asset_id).order_by(models.Ticket.id.desc())
    ).all()
    return templates.TemplateResponse(
        request, "asset_detail.html", {"asset": asset, "tickets": tickets, "user": user}
    )


@app.post("/assets/{asset_id}/location")
def set_location(asset_id: int, location: str = Form("", max_length=120),
                 user: models.User = Depends(auth.require_roles("agent", "admin")),
                 db: Session = Depends(get_db)):
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found")
    value = location.strip() or None
    if asset.location != value:
        audit(db, user.id, "update", "asset", asset.id,
              json.dumps({"location": [asset.location, value]}, ensure_ascii=False))
        asset.location = value
        db.commit()
    return RedirectResponse(f"/assets/{asset_id}", status_code=303)


@app.post("/assets")
def create_asset(
    tag: str = Form(...),
    name: str = Form(...),
    asset_type: str = Form(...),
    serial: str = Form(""),
    location: str = Form("", max_length=120),
    status: str = Form("in_use"),
    assigned_to_id: str = Form(""),
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    tag, name, asset_type = tag.strip(), name.strip(), asset_type.strip()
    if not tag or not name or not asset_type or len(tag) > 50 or len(name) > 100 or len(asset_type) > 50:
        raise HTTPException(status_code=400, detail="Invalid asset data")
    if status not in ASSET_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid asset status")
    if db.scalar(select(models.Asset).where(models.Asset.tag == tag)):
        raise HTTPException(status_code=409, detail="Asset tag already exists")
    try:
        assignee = int(assigned_to_id) if assigned_to_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid assigned user")
    if assignee is not None and db.scalar(select(models.User).where(models.User.id == assignee, models.User.is_active.is_(True))) is None:
        raise HTTPException(status_code=400, detail="Invalid assigned user")
    asset = models.Asset(tag=tag, name=name, location=location.strip() or None, asset_type=asset_type, serial=serial.strip() or None, status=status, assigned_to_id=assignee)
    db.add(asset)
    db.flush()
    audit(db, user.id, "create", "asset", asset.id, tag)
    db.commit()
    return RedirectResponse("/assets", status_code=303)


@app.post("/assets/import")
async def import_assets(
    file: UploadFile = File(...),
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is too large")
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        rows = list(workbook.active.iter_rows(values_only=True))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Excel file") from exc
    if not rows:
        raise HTTPException(status_code=400, detail="Excel file is empty")
    headers = [str(value or "").strip() for value in rows[0]]
    expected = ["شماره اموال", "نام", "نوع", "سریال", "وضعیت", "نام کاربری تحویل‌گیرنده"]
    if headers not in (expected, expected + ["محل"]):
        raise HTTPException(status_code=400, detail="Invalid Excel headers")
    existing_tags = set(db.scalars(select(models.Asset.tag)).all())
    seen_tags = set()
    prepared = []
    for line, row in enumerate(rows[1:], start=2):
        values = list(row) + [None] * len(expected)
        tag, name, asset_type, serial, status, assignee_username = [str(values[i] or "").strip() for i in range(6)]
        location = str(values[6] or "").strip() if len(headers) == 7 else ""
        if len(location) > 120:
            raise HTTPException(400, detail=f"Invalid location at row {line}")
        if not any((tag, name, asset_type, serial, status, assignee_username, location)):
            continue
        if not tag or not name or not asset_type or len(tag) > 50 or len(name) > 100 or len(asset_type) > 50 or len(serial) > 100:
            raise HTTPException(status_code=400, detail=f"Invalid asset data at row {line}")
        if status not in ASSET_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid asset status at row {line}")
        if tag in existing_tags or tag in seen_tags:
            raise HTTPException(status_code=409, detail=f"Duplicate asset tag at row {line}: {tag}")
        assignee = None
        if assignee_username:
            assignee = db.scalar(select(models.User).where(models.User.username == assignee_username, models.User.is_active.is_(True)))
            if assignee is None:
                raise HTTPException(status_code=400, detail=f"Invalid assignee at row {line}")
        seen_tags.add(tag)
        prepared.append((tag, name, asset_type, serial or None, status, assignee.id if assignee else None, location or None))
    if not prepared:
        raise HTTPException(status_code=400, detail="No asset rows found")
    for tag, name, asset_type, serial, status, assignee_id, location in prepared:
        asset = models.Asset(tag=tag, name=name, asset_type=asset_type, serial=serial, status=status, assigned_to_id=assignee_id, location=location)
        db.add(asset)
        db.flush()
        audit(db, user.id, "create", "asset", asset.id, f"import:{tag}")
    db.commit()
    return RedirectResponse(f"/assets?imported={len(prepared)}", status_code=303)


@app.get("/dashboard")
def dashboard(
    request: Request,
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    ticket_counts = dict(db.execute(select(models.Ticket.status, func.count(models.Ticket.id)).group_by(models.Ticket.status)).all())
    priority_counts = dict(db.execute(select(models.Ticket.priority, func.count(models.Ticket.id)).group_by(models.Ticket.priority)).all())
    asset_counts = dict(db.execute(select(models.Asset.status, func.count(models.Asset.id)).group_by(models.Asset.status)).all())
    recent_tickets = db.scalars(select(models.Ticket).order_by(models.Ticket.created_at.desc()).limit(10)).all()
    avg_hours = db.scalar(select(func.avg(
        (func.julianday(models.Ticket.closed_at) - func.julianday(models.Ticket.created_at)) * 24
    )).where(models.Ticket.status == "closed", models.Ticket.closed_at.is_not(None)))
    avg_resolution_hours = round(avg_hours, 1) if avg_hours is not None else None
    category_counts = dict(db.execute(select(models.Ticket.category, func.count(models.Ticket.id)).group_by(models.Ticket.category).order_by(func.count(models.Ticket.id).desc())).all())
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "ticket_counts": ticket_counts,
        "priority_counts": priority_counts,
        "asset_counts": asset_counts,
        "recent_tickets": recent_tickets,
        "category_counts": category_counts,
        "avg_resolution_hours": avg_resolution_hours,
    })


@app.get("/reports/data.xlsx")
def export_data(
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    workbook = Workbook()
    tickets_sheet = workbook.active
    tickets_sheet.title = "تیکت‌ها"
    assets_sheet = workbook.create_sheet("دارایی‌ها")
    for sheet in (tickets_sheet, assets_sheet):
        sheet.sheet_view.rightToLeft = True
        sheet.freeze_panes = "A2"

    tickets_sheet.append(["شناسه", "عنوان", "شرح", "وضعیت", "اولویت", "شناسه درخواست‌کننده", "شناسه کارشناس", "شناسه دارایی", "تاریخ ایجاد UTC", "آخرین تغییر UTC", "دسته", "نوع ثبت", "تاریخ بسته‌شدن UTC"])
    for item in db.scalars(select(models.Ticket).order_by(models.Ticket.id)):
        tickets_sheet.append([item.id, item.title, item.description, item.status, item.priority, item.requester_id, item.assignee_id, item.asset_id, item.created_at.isoformat(), item.updated_at.isoformat(), CATEGORIES[item.category], "تماس تلفنی" if item.intake == "phone" else "فرم", item.closed_at.isoformat() if item.closed_at else None])

    assets_sheet.append(["شناسه", "شماره اموال", "نام", "نوع", "سریال", "وضعیت", "شناسه تحویل‌گیرنده", "تاریخ ایجاد UTC", "محل"])
    for item in db.scalars(select(models.Asset).order_by(models.Asset.id)):
        assets_sheet.append([item.id, item.tag, item.name, item.asset_type, item.serial, item.status, item.assigned_to_id, item.created_at.isoformat(), item.location])

    for sheet in (tickets_sheet, assets_sheet):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="itdesk-data.xlsx"', "Cache-Control": "no-store"})


@app.get("/")
def index():
    return RedirectResponse("/tickets")


@app.get("/tickets")
def list_tickets(
    request: Request,
    q: str = "",
    status: str = "",
    priority: str = "",
    overdue: str = "",
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = select(models.Ticket).order_by(models.Ticket.id.desc())
    if not is_staff(user):
        query = query.where(models.Ticket.requester_id == user.id)
    q = q.strip()
    if q:
        query = query.where(models.Ticket.title.ilike(f"%{q}%"))
    if status in STATUSES:
        query = query.where(models.Ticket.status == status)
    if priority in PRIORITIES:
        query = query.where(models.Ticket.priority == priority)
    tickets = db.scalars(query).all()
    if overdue == "1":
        tickets = [ticket for ticket in tickets if ticket_is_overdue(ticket)]
    assets = db.scalars(select(models.Asset).order_by(models.Asset.tag)).all() if is_staff(user) else []
    return templates.TemplateResponse(
        request, "tickets.html", {"tickets": tickets, "user": user, "assets": assets,
                                    "q": q, "status": status, "priority": priority,
                                    "overdue": overdue, "callers": db.scalars(select(models.User).where(models.User.is_active.is_(True)).order_by(models.User.full_name)).all() if is_staff(user) else []}
    )


@app.post("/tickets")
def create_ticket(
    title: str = Form(...),
    category: str = Form("other"),
    caller_id: str = Form(""),
    description: str = Form(""),
    priority: str = Form("normal"),
    asset_id: str = Form(""),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    title = title.strip()
    if not title or len(title) > 200:
        raise HTTPException(status_code=400, detail="Invalid ticket title")
    if priority not in PRIORITIES:
        priority = "normal"
    try:
        selected_asset = int(asset_id) if asset_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset")
    if selected_asset is not None and db.get(models.Asset, selected_asset) is None:
        raise HTTPException(status_code=400, detail="Invalid asset")
    if selected_asset is not None and not is_staff(user):
        raise HTTPException(status_code=403, detail="Only staff can link assets")
    if category not in CATEGORIES:
        raise HTTPException(400, "Invalid ticket category")
    requester = user
    if caller_id:
        if not is_staff(user):
            raise HTTPException(403, "Only staff can record calls")
        if not caller_id.isascii() or not caller_id.isdigit() or len(caller_id) > 18:
            raise HTTPException(400, "Invalid caller")
        requester = db.get(models.User, int(caller_id))
        if not requester or not requester.is_active:
            raise HTTPException(400, "Invalid caller")
    ticket = models.Ticket(
        title=title,
        description=description.strip(),
        priority=priority,
        requester_id=requester.id,
        category=category,
        intake="phone" if caller_id else "form",
        asset_id=selected_asset,
        due_at=datetime.utcnow() + timedelta(hours=SLA_HOURS[priority]),
    )
    db.add(ticket)
    db.flush()
    audit(db, user.id, "create", "ticket", ticket.id, ticket.title)
    db.commit()
    return RedirectResponse(f"/tickets/{ticket.id}", status_code=303)


@app.get("/tickets/{ticket_id}")
def ticket_detail(
    ticket_id: int,
    request: Request,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ticket = get_ticket_for(db, ticket_id, user)
    notes = db.scalars(
        select(models.TicketNote)
        .where(models.TicketNote.ticket_id == ticket_id)
        .order_by(models.TicketNote.id)
    ).all()
    history = db.scalars(
        select(models.AuditLog)
        .where(models.AuditLog.entity == "ticket", models.AuditLog.entity_id == ticket_id)
        .order_by(models.AuditLog.id.desc())
    ).all()
    users = {u.id: u for u in db.scalars(select(models.User))}
    agents = [u for u in users.values() if is_staff(u) and u.is_active]
    assets = db.scalars(select(models.Asset).order_by(models.Asset.tag)).all()
    return templates.TemplateResponse(
        request,
        "ticket_detail.html",
        {
            "ticket": ticket,
            "notes": notes,
            "history": history,
            "users": users,
            "agents": agents,
            "user": user,
            "assets": assets,
        },
    )


@app.post("/tickets/{ticket_id}/update")
def update_ticket(
    ticket_id: int,
    request: Request,
    status: str = Form(...),
    assignee_id: str = Form(""),
    asset_id: str | None = Form(None),
    user: models.User = Depends(auth.require_roles("agent", "admin")),
    db: Session = Depends(get_db),
):
    ticket = get_ticket_for(db, ticket_id, user)
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    try:
        new_assignee = int(assignee_id) if assignee_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid assignee")
    if new_assignee is not None:
        target = db.get(models.User, new_assignee)
        if target is None or not is_staff(target) or not target.is_active:
            raise HTTPException(status_code=400, detail="Invalid assignee")
    try:
        new_asset = ticket.asset_id if asset_id is None else (int(asset_id) if asset_id else None)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset")
    if new_asset is not None and db.get(models.Asset, new_asset) is None:
        raise HTTPException(status_code=400, detail="Invalid asset")

    names = {u.id: u.full_name for u in db.scalars(select(models.User))}
    changes = {}
    if ticket.status != status:
        changes["status"] = [ticket.status, status]
        ticket.closed_at = closure_now() if status == "closed" else None
        ticket.status = status
    if ticket.assignee_id != new_assignee:
        changes["assignee"] = [
            names.get(ticket.assignee_id, "-"),
            names.get(new_assignee, "-"),
        ]
        ticket.assignee_id = new_assignee
    if ticket.asset_id != new_asset:
        changes["asset"] = [ticket.asset_id, new_asset]
        ticket.asset_id = new_asset
    if changes:
        audit(db, user.id, "update", "ticket", ticket.id,
              json.dumps(changes, ensure_ascii=False))
        db.commit()
    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request, "ticket_summary.html", {"ticket": ticket, "users": {u.id: u for u in db.scalars(select(models.User))}})
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/notes")
def add_note(
    ticket_id: int,
    body: str = Form(...),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ticket = get_ticket_for(db, ticket_id, user)
    body = body.strip()
    if body:
        db.add(models.TicketNote(ticket_id=ticket.id, author_id=user.id, body=body))
        audit(db, user.id, "note", "ticket", ticket.id)
        db.commit()
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)

"""FastAPI app: watch management pages, the LCD display API, and the price scheduler."""
import asyncio
import contextlib
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import db, refresh
from .config import Settings
from .display import build_screens, format_price, time_ago
from .pricing import PriceProvider

log = logging.getLogger("watchbox.app")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
SLOTS = range(1, 9)
FormStr = Annotated[str, Form()]


def parse_slot(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if not raw.isdigit() or not 1 <= int(raw) <= 8:
        raise ValueError("Slot must be between 1 and 8")
    return int(raw)


def validate_reference(reference: str) -> None:
    if not re.sub(r"[^a-z0-9]", "", reference.lower()):
        raise ValueError("Reference number must contain letters or digits")


def validate_required(brand: str, model: str) -> None:
    if not brand.strip() or not model.strip():
        raise ValueError("Brand and model are required")


def redirect(path: str, error: str | None = None) -> RedirectResponse:
    url = f"{path}?error={quote(error)}" if error else path
    return RedirectResponse(url, status_code=303)


async def run_scheduled(fn) -> None:
    """Runs a scheduled job in a thread; any failure is logged, never raised, so the loop keeps going."""
    try:
        await asyncio.to_thread(fn)
    except Exception:
        log.exception("scheduled refresh failed")


def create_app(settings: Settings, provider: PriceProvider | None, run_scheduler: bool = True) -> FastAPI:
    def get_conn():
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[object, Depends(get_conn)]

    def refresh_one(watch_id: int) -> None:
        if provider is None:
            return
        conn = db.connect(settings.db_path)
        try:
            watch = db.get_watch(conn, watch_id)
            if watch:
                refresh.refresh_watch(conn, provider, watch)
        finally:
            conn.close()

    def refresh_everything() -> None:
        if provider is None:
            return
        conn = db.connect(settings.db_path)
        try:
            refresh.refresh_all(conn, provider)
        finally:
            conn.close()

    def check_and_refresh_if_stale() -> None:
        conn = db.connect(settings.db_path)
        try:
            stale = refresh.needs_refresh(db.latest_fetch_time(conn), settings.refresh_hours, datetime.now(timezone.utc))
        finally:
            conn.close()
        if stale:
            refresh_everything()

    async def scheduler() -> None:
        await run_scheduled(check_and_refresh_if_stale)
        while True:
            await asyncio.sleep(settings.refresh_hours * 3600)
            await run_scheduled(refresh_everything)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(scheduler()) if run_scheduler and provider else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="WatchBox v0", lifespan=lifespan)

    def render(request: Request, name: str, **context) -> HTMLResponse:
        context |= {"format_price": format_price, "time_ago": time_ago, "slots": SLOTS,
                    "has_provider": provider is not None}
        return templates.TemplateResponse(request, name, context)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, conn: Conn, error: str | None = None):
        watches = db.list_watches(conn)
        priced = [w for w in watches if w.price_usd is not None]
        return render(request, "index.html", watches=watches, total=sum(w.price_usd for w in priced),
                      priced_count=len(priced), error=error, fw=None, action="/watches", submit_label="Add watch")

    @app.post("/watches")
    def create_watch(background: BackgroundTasks, conn: Conn, brand: FormStr, model: FormStr, reference: FormStr,
                     slot: FormStr = "", nickname: FormStr = ""):
        try:
            validate_required(brand, model)
            validate_reference(reference)
            watch_id = db.add_watch(conn, brand.strip(), model.strip(), reference.strip(), parse_slot(slot),
                                    nickname.strip() or None)
        except (ValueError, db.SlotTakenError) as e:
            return redirect("/", str(e))
        background.add_task(refresh_one, watch_id)
        return redirect("/")

    @app.get("/watches/{watch_id}/edit", response_class=HTMLResponse)
    def edit_watch(request: Request, watch_id: int, conn: Conn, error: str | None = None):
        watch = db.get_watch(conn, watch_id)
        if watch is None:
            raise HTTPException(404, "Watch not found")
        return render(request, "edit.html", watch=watch, error=error, fw=watch,
                      action=f"/watches/{watch_id}", submit_label="Save")

    @app.post("/watches/{watch_id}")
    def update_watch(watch_id: int, background: BackgroundTasks, conn: Conn, brand: FormStr, model: FormStr,
                     reference: FormStr, slot: FormStr = "", nickname: FormStr = ""):
        if db.get_watch(conn, watch_id) is None:
            raise HTTPException(404, "Watch not found")
        try:
            validate_required(brand, model)
            validate_reference(reference)
            db.update_watch(conn, watch_id, brand.strip(), model.strip(), reference.strip(), parse_slot(slot),
                            nickname.strip() or None)
        except (ValueError, db.SlotTakenError) as e:
            return redirect(f"/watches/{watch_id}/edit", str(e))
        background.add_task(refresh_one, watch_id)
        return redirect("/")

    @app.post("/watches/{watch_id}/delete")
    def delete_watch(watch_id: int, conn: Conn):
        db.delete_watch(conn, watch_id)
        return redirect("/")

    @app.post("/refresh")
    def refresh_now(background: BackgroundTasks):
        background.add_task(refresh_everything)
        return redirect("/")

    @app.get("/api/display")
    def display(conn: Conn):
        return {"generated_at": db.now_iso(), "screens": build_screens(db.list_watches(conn))}

    return app

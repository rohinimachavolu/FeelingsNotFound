"""FastAPI app: participant API, admin API, and the built React frontend.

Run:  uvicorn backend.app.main:app --reload
"""
from __future__ import annotations

import base64
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import exports, retention, study
from . import settings as settings_mod
from .db import init_engine
from .survey import get_survey

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_engine()
    get_survey()  # fail fast if the config is broken
    yield


app = FastAPI(title="Changing How Setbacks Feel", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.exception_handler(study.StudyError)
def _study_error(_: Request, exc: study.StudyError):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "errors": exc.errors})


# ----------------------------------------------------------------------------- participant API
class StartBody(BaseModel):
    pid: str | None = None
    source: str | None = None


class SubmitBody(BaseModel):
    step: str
    answers: dict[str, Any]


@app.get("/api/health")
def health():
    s = settings_mod.settings
    return {"ok": True, "survey_version": get_survey().version, "provider": s.llm_provider}


@app.post("/api/start")
def start(body: StartBody, request: Request):
    token = study.start_participant(source="human", pid=body.pid, recruit_source=body.source,
                                    user_agent=request.headers.get("user-agent"))
    return {"token": token, "state": study.get_state(token)}


@app.get("/api/session/{token}")
def state(token: str):
    return study.get_state(token)


@app.post("/api/session/{token}/submit")
def submit(token: str, body: SubmitBody):
    return study.submit(token, body.step, body.answers)


@app.post("/api/session/{token}/generate")
def generate(token: str):
    return study.run_generation(token)


# ----------------------------------------------------------------------------- admin API
def require_admin(request: Request) -> None:
    pw = settings_mod.settings.admin_password
    if not pw:
        raise HTTPException(503, "Admin is disabled: set ADMIN_PASSWORD")
    header = request.headers.get("authorization", "")
    supplied = ""
    if header.lower().startswith("basic "):
        try:
            supplied = base64.b64decode(header[6:]).decode().split(":", 1)[-1]
        except Exception:
            supplied = ""
    if not hmac.compare_digest(supplied.encode(), pw.encode()):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": 'Basic realm="admin"'})


@app.get("/api/admin/summary", dependencies=[Depends(require_admin)])
def admin_summary():
    return exports.summary()


@app.get("/api/admin/flags", dependencies=[Depends(require_admin)])
def admin_flags():
    return exports.flag_rows()


@app.get("/api/admin/export/{kind}.csv", dependencies=[Depends(require_admin)])
def admin_export(kind: str, completed_only: bool = False, source: str | None = None):
    if kind not in exports.EXPORTS:
        raise HTTPException(404, f"unknown export {kind}")
    if source not in (None, "", "human", "persona"):
        raise HTTPException(400, "source must be human or persona")
    csv_text = exports.export_csv(kind, completed_only=completed_only, source=source or None)
    return PlainTextResponse(csv_text, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})


class DeleteBody(BaseModel):
    confirm: str


@app.post("/api/admin/delete-all", dependencies=[Depends(require_admin)])
def admin_delete_all(body: DeleteBody):
    if body.confirm != retention.CONFIRM_PHRASE:
        raise HTTPException(400, f'Type "{retention.CONFIRM_PHRASE}" to confirm')
    deleted = retention.delete_all_data()
    logging.getLogger("admin").warning("All study data deleted: %s", deleted)
    return {"deleted": deleted}


# ----------------------------------------------------------------------------- frontend
_dist = settings_mod.settings.frontend_dist
if (_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    f = _dist / full_path
    if full_path and f.is_file() and _dist in f.resolve().parents:
        return FileResponse(f)
    index = _dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return PlainTextResponse("Frontend not built. Run: cd frontend && npm install && npm run build", status_code=503)

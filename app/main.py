from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_bearer
from app.database import init_db
from app.routes import calls, devices, voice

app = FastAPI(title="Clinical Call Triage Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# Twilio webhooks authenticate via request-signature validation (see voice.py),
# NOT the bearer token. Everything else requires the bearer token.
app.include_router(voice.router)
app.include_router(calls.router, dependencies=[Depends(require_bearer)])
app.include_router(devices.router, dependencies=[Depends(require_bearer)])


@app.get("/")
def root() -> dict:
    return {"status": "ok", "service": "clinical-call-triage-demo"}

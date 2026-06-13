from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routes import calls, voice

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


app.include_router(voice.router)
app.include_router(calls.router)


@app.get("/")
def root() -> dict:
    return {"status": "ok", "service": "clinical-call-triage-demo"}

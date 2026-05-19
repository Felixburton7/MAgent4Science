from __future__ import annotations

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.pipeline import run_pipeline

app = FastAPI(title="Idea Hater API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    hypothesis: str
    information_cutoff_year: int | None = None


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/run")
async def run(req: RunRequest) -> dict:
    state = await run_pipeline(
        req.hypothesis,
        information_cutoff_year=req.information_cutoff_year,
    )
    return jsonable_encoder(state)

"""
FastAPI application entry point for AgentReliabilityLab.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.routers import runs, traces, evals, policy, replay, leaderboard, hitl

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise storage on startup."""
    import sys
    import pathlib
    # Ensure packages/ is importable when running from apps/api/
    root = pathlib.Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.makedirs("data", exist_ok=True)
    from packages.tracing.storage import get_storage
    get_storage()  # initialise DB tables
    logger.info("AgentReliabilityLab API started")
    yield
    logger.info("AgentReliabilityLab API shutdown")


app = FastAPI(
    title="AgentReliabilityLab API",
    description="Evaluation & observability platform for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(runs.router,        prefix="/api/runs",        tags=["runs"])
app.include_router(traces.router,      prefix="/api/traces",      tags=["traces"])
app.include_router(evals.router,       prefix="/api/evals",       tags=["evals"])
app.include_router(policy.router,      prefix="/api/policy",      tags=["policy"])
app.include_router(replay.router,      prefix="/api/replay",      tags=["replay"])
app.include_router(leaderboard.router, prefix="/api/leaderboard", tags=["leaderboard"])
app.include_router(hitl.router,        prefix="/api/hitl",        tags=["hitl"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "agent-reliability-lab"}


@app.get("/api/stats")
async def stats():
    """Quick dashboard stats."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    total = storage.count_runs()
    return {"total_runs": total}

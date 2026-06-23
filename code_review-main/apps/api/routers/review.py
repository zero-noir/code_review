from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from core.config import settings
from repositories.review_store import ReviewStore
from services.repository_service import RepositoryService
from services.analysis_service import AnalysisService, AGENT_LABELS
from schemas.review import HealthResponse, UploadedRepository, FileListResponse, ReviewRequest, ReviewResponse, SessionSummary, SkillCard

router = APIRouter(prefix="/api/v1/review", tags=["agentic code reviewer"])
store = ReviewStore(settings.database_path)
repo_service = RepositoryService(store)
analysis_service = AnalysisService(store, repo_service)

@router.get("/health", response_model=HealthResponse)
def health():
    uploads, reviews = store.counts()
    return {
        "ok": True,
        "app_name": settings.app_name,
        "storage": str(settings.storage_dir),
        "uploads": uploads,
        "reviews": reviews,
        "ai_enabled": analysis_service.llm_enabled(),
        "provider": analysis_service.ai_mode(),
        "agents": list(AGENT_LABELS.keys()),
    }

@router.post("/upload", response_model=UploadedRepository)
async def upload_repository(file: UploadFile = File(...)):
    data = await file.read()
    return repo_service.upload_zip(data, file.filename or "repository.zip")

@router.get("/files/{session_id}", response_model=FileListResponse)
def files(session_id: str):
    session = store.get_session(session_id)
    rows = repo_service.file_list(session_id)
    defaults = session.get("default_targets") if session else []
    return {"session_id": session_id, "files": [{**r, "selected": r["path"] in defaults} for r in rows], "default_targets": defaults}

@router.post("/run", response_model=ReviewResponse)
def run_review(payload: ReviewRequest):
    return analysis_service.run_review(payload.session_id, payload.objective, payload.target_files, payload.focus_areas, payload.use_llm)

@router.get("/sessions", response_model=list[SessionSummary])
def sessions():
    return store.list_sessions()

@router.get("/skills", response_model=list[SkillCard])
def skills():
    return analysis_service.skills()

@router.get("/memory/{session_id}")
def memory(session_id: str):
    return {"session_id": session_id, "memory": store.memory(session_id)}

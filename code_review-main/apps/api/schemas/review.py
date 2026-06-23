from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Any

Severity = Literal["blocker", "warning", "suggestion", "nit", "praise"]
AgentName = Literal[
    "repository_mapper",
    "api_contract_reviewer",
    "frontend_quality_reviewer",
    "backend_architect",
    "security_reviewer",
    "database_optimizer",
    "devops_automator",
    "ui_designer",
    "git_workflow_reviewer",
    "mcp_builder",
    "patch_planner",
]

class HealthResponse(BaseModel):
    ok: bool
    app_name: str
    storage: str
    uploads: int
    reviews: int
    ai_enabled: bool
    provider: str
    agents: list[str]

class UploadedRepository(BaseModel):
    session_id: str
    repo_name: str
    uploaded_filename: str
    file_count: int
    default_targets: list[str]
    detected_stack: list[str]
    warnings: list[str] = []

class RepoFile(BaseModel):
    path: str
    size: int
    kind: str
    selected: bool = False

class FileListResponse(BaseModel):
    session_id: str
    files: list[RepoFile]
    default_targets: list[str]

class ReviewRequest(BaseModel):
    session_id: str
    objective: str = "Review this repository for production readiness."
    target_files: list[str] = []
    focus_areas: list[str] = Field(default_factory=lambda: ["api_contract", "frontend", "backend", "security", "devops"])
    use_llm: bool = True

class Finding(BaseModel):
    id: str
    severity: Severity
    agent: AgentName
    title: str
    file: str | None = None
    line: int | None = None
    evidence: str
    why_it_matters: str
    recommendation: str
    patch_hint: str | None = None
    confidence: float = Field(ge=0, le=1, default=0.85)

class AgentTrace(BaseModel):
    agent: AgentName
    status: Literal["complete", "skipped", "error"]
    summary: str
    findings: int = 0

class ReviewResponse(BaseModel):
    review_id: str
    session_id: str
    repo_name: str
    ai_mode: str
    summary: str
    score: int
    findings: list[Finding]
    traces: list[AgentTrace]
    patch_checklist: list[str]
    markdown_report: str
    json_export: dict[str, Any]

class SessionSummary(BaseModel):
    session_id: str
    repo_name: str
    created_at: str
    file_count: int
    review_count: int

class SkillCard(BaseModel):
    name: str
    role: str
    incorporated_as: str
    source_file: str

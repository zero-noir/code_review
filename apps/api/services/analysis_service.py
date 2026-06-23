from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any
import requests

from core.config import settings
from core.errors import bad_request
from repositories.review_store import ReviewStore
from services.repository_service import RepositoryService

FASTAPI_DECORATOR_RE = re.compile(r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]")
APIR_PREFIX_RE = re.compile(r"APIRouter\(.*?prefix\s*=\s*['\"]([^'\"]+)['\"]", re.S)
FETCH_PATH_RE = re.compile(r"(?:fetch|request<[^>]+>|request)\(\s*[`'\"]([^`'\"]*/api/[^`'\"]*)")
VITE_BASE_RE = re.compile(r"VITE_[A-Z0-9_]+\s*=\s*['\"]?([^'\"\n]+)")
SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-./]{12,}['\"]")

AGENT_LABELS = {
    "repository_mapper": "Repository Mapper",
    "api_contract_reviewer": "API Contract Reviewer",
    "frontend_quality_reviewer": "Frontend Quality Reviewer",
    "backend_architect": "Backend Architect",
    "security_reviewer": "Security Reviewer",
    "database_optimizer": "Database Optimizer",
    "devops_automator": "DevOps Automator",
    "ui_designer": "UI Designer",
    "git_workflow_reviewer": "Git Workflow Reviewer",
    "mcp_builder": "MCP Builder",
    "patch_planner": "Patch Planner",
}

ALLOWED_SEVERITIES = {"blocker", "warning", "suggestion", "nit", "praise"}
ALLOWED_AGENTS = set(AGENT_LABELS.keys())

SEVERITY_ALIASES = {
    "critical": "blocker",
    "fatal": "blocker",
    "error": "blocker",
    "must_fix": "blocker",
    "must-fix": "blocker",
    "high": "warning",
    "major": "warning",
    "medium": "suggestion",
    "moderate": "suggestion",
    "low": "nit",
    "minor": "nit",
    "info": "nit",
    "informational": "nit",
    "positive": "praise",
    "good": "praise",
}

AGENT_ALIASES = {
    "code_reviewer": "patch_planner",
    "reviewer": "patch_planner",
    "senior_code_reviewer": "patch_planner",
    "security_auditor": "security_reviewer",
    "security": "security_reviewer",
    "security_engineer": "security_reviewer",
    "frontend_reviewer": "frontend_quality_reviewer",
    "frontend_developer": "frontend_quality_reviewer",
    "backend_reviewer": "backend_architect",
    "backend": "backend_architect",
    "database_reviewer": "database_optimizer",
    "db_optimizer": "database_optimizer",
    "devops": "devops_automator",
    "devops_reviewer": "devops_automator",
    "ui_reviewer": "ui_designer",
    "ux_reviewer": "ui_designer",
    "git_reviewer": "git_workflow_reviewer",
    "git_workflow_master": "git_workflow_reviewer",
    "mcp_reviewer": "mcp_builder",
}

class AnalysisService:
    def __init__(self, store: ReviewStore, repo: RepositoryService):
        self.store = store
        self.repo = repo

    def llm_enabled(self) -> bool:
        provider = (settings.llm_provider or "offline").lower().strip()
        return (provider == "deepseek" and bool(settings.deepseek_api_key)) or (provider == "gemini" and bool(settings.gemini_api_key))

    def ai_mode(self) -> str:
        provider = (settings.llm_provider or "offline").lower().strip()
        if provider == "deepseek" and settings.deepseek_api_key:
            return f"deepseek:{settings.deepseek_model}"
        if provider == "gemini" and settings.gemini_api_key:
            return f"gemini:{settings.gemini_model}"
        return "offline_static_review"

    def _normalize_severity(self, value: Any) -> str:
        raw = str(value or "suggestion").strip().lower().replace(" ", "_")
        raw = SEVERITY_ALIASES.get(raw, raw)
        return raw if raw in ALLOWED_SEVERITIES else "suggestion"

    def _normalize_agent(self, value: Any) -> str:
        raw = str(value or "patch_planner").strip().lower().replace(" ", "_").replace("-", "_")
        raw = AGENT_ALIASES.get(raw, raw)
        return raw if raw in ALLOWED_AGENTS else "patch_planner"

    def _finding(self, severity: str, agent: str, title: str, evidence: str, recommendation: str, file: str | None = None, why: str | None = None, patch: str | None = None, line: int | None = None, confidence: float = .86) -> dict[str, Any]:
        return {
            "id": f"F-{uuid.uuid4().hex[:8]}",
            "severity": self._normalize_severity(severity),
            "agent": self._normalize_agent(agent),
            "title": str(title or "Review finding").strip(),
            "file": file,
            "line": line,
            "evidence": str(evidence or "Review evidence not provided.")[:1200],
            "why_it_matters": why or "This can reduce correctness, maintainability, security, performance, or production readiness.",
            "recommendation": str(recommendation or "Review manually and patch as needed.").strip(),
            "patch_hint": patch,
            "confidence": max(0.0, min(1.0, float(confidence or .86))),
        }

    def _read_selected(self, session_id: str, target_files: list[str]) -> dict[str, str]:
        all_files = self.repo.file_list(session_id)
        valid = {f["path"] for f in all_files}
        if not target_files:
            session = self.store.get_session(session_id)
            target_files = session.get("default_targets") if session else []
        chosen = [p for p in target_files if p in valid]
        # Include extra contract files even if user selected README only.
        must = [p for p in valid if p.endswith(("client.ts", "main.py", "package.json", "requirements.txt", "vite.config.ts", "svelte.config.js", "app.html")) or "/routers/" in p or "/schemas/" in p]
        for p in must[:70]:
            if p not in chosen:
                chosen.append(p)
        return {p: self.repo.read_text(session_id, p) for p in chosen[:120]}

    def _map_repository(self, files: list[dict[str, Any]], contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        if not any(f["path"].lower().endswith("readme.md") for f in files):
            findings.append(self._finding("suggestion", "repository_mapper", "README is missing", "No README.md found in inspected repository.", "Add a concise README with setup, architecture, env variables, API routes, and test commands.", why="A production repository needs a reliable entry point for reviewers, teammates, and deployment operators."))
        if not any(f["path"].lower() in {".env.example", "env.example"} for f in files):
            findings.append(self._finding("warning", "repository_mapper", ".env.example is missing", "No environment template detected.", "Add .env.example with safe placeholder values and document required variables.", why="Missing environment documentation causes failed local setup and accidental secret exposure."))
        if any("package-lock.json" == Path(f["path"]).name for f in files):
            for p,t in contents.items():
                if p.endswith("package-lock.json") and "applied-caas-gateway" in t:
                    findings.append(self._finding("blocker", "repository_mapper", "Lockfile contains non-public registry URLs", "package-lock.json references an internal registry.", "Regenerate the lockfile against https://registry.npmjs.org or do not ship the lockfile.", file=p, why="Developers outside the original environment will get ETIMEDOUT or install failures."))
        return findings

    def _api_contract(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        backend=[]
        prefixes={}
        for p,t in contents.items():
            if p.endswith(".py"):
                pref = ""
                m = APIR_PREFIX_RE.search(t)
                if m: pref = m.group(1).rstrip("/")
                for method,path in FASTAPI_DECORATOR_RE.findall(t):
                    full = (pref + "/" + path.lstrip("/")).replace("//","/")
                    backend.append((method.upper(), full, p))
        frontend=[]
        for p,t in contents.items():
            if p.endswith((".ts", ".svelte", ".js")):
                for raw in FETCH_PATH_RE.findall(t):
                    clean = raw.replace("${API_BASE}", "").split("?")[0]
                    if clean.startswith("http"):
                        idx = clean.find("/api/")
                        clean = clean[idx:] if idx >= 0 else clean
                    frontend.append((clean, p))
        backend_paths = {b[1] for b in backend}
        for path, file in frontend:
            if "/api/" in path and path not in backend_paths and not any(self._path_compatible(path, bp) for bp in backend_paths):
                findings.append(self._finding("blocker", "api_contract_reviewer", "Frontend calls a route not found in backend", f"Frontend call: {path}. Backend routes detected: {', '.join(sorted(list(backend_paths))[:12])}", "Align the frontend client path with the mounted FastAPI router path, or add the missing backend route.", file=file, why="This causes runtime 404s even when the frontend compiles."))
        if backend and not frontend:
            findings.append(self._finding("suggestion", "api_contract_reviewer", "Backend routes found but no frontend API client detected", f"Detected {len(backend)} FastAPI routes.", "Add a typed client.ts wrapper so frontend calls remain centralized and reviewable.", why="Centralized API clients reduce route drift and make port/base URL changes safer."))
        return findings

    def _path_compatible(self, frontend: str, backend: str) -> bool:
        # treat path params as compatible
        fp = frontend.strip("/").split("/")
        bp = backend.strip("/").split("/")
        if len(fp) != len(bp): return False
        for a,b in zip(fp,bp):
            if b.startswith("{") and b.endswith("}"): continue
            if a != b: return False
        return True

    def _frontend(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        app_html = next(((p,t) for p,t in contents.items() if p.endswith("app.html")), None)
        if app_html and "%sveltekit.head%" not in app_html[1]:
            findings.append(self._finding("blocker", "frontend_quality_reviewer", "Svelte app.html is missing %sveltekit.head%", "app.html contains %sveltekit.body% but not %sveltekit.head%.", "Add %sveltekit.head% inside the <head> element.", file=app_html[0], why="SvelteKit dev server warns and head-managed metadata/styles may fail."))
        pkg = next(((p,t) for p,t in contents.items() if p.endswith("package.json")), None)
        vite = any(p.endswith("vite.config.ts") for p in contents)
        if pkg:
            try:
                data = json.loads(pkg[1])
                if vite and data.get("type") != "module":
                    findings.append(self._finding("blocker", "frontend_quality_reviewer", "package.json is missing type=module", "Vite/SvelteKit config imports ESM-only @sveltejs/kit/vite.", "Set \"type\": \"module\" in package.json.", file=pkg[0], why="Without it, Vite can try loading ESM packages through CommonJS and fail at startup."))
            except Exception:
                findings.append(self._finding("warning", "frontend_quality_reviewer", "package.json could not be parsed", "Invalid JSON or malformed package manifest.", "Validate package.json and reinstall dependencies.", file=pkg[0]))
        for p,t in contents.items():
            if p.endswith(".svelte"):
                if re.search(r"<a(?![^>]*href=)[^>]*>", t):
                    findings.append(self._finding("warning", "frontend_quality_reviewer", "Anchor without href", "A <a> element without href was detected.", "Use <button type=\"button\"> for actions, or add a real href for navigation.", file=p, why="This triggers accessibility warnings and poor keyboard/screen-reader behavior."))
                if re.search(r"<label(?![^>]*for=)[^>]*>", t) and not re.search(r"<label[^>]*>\s*<(input|textarea|select)", t):
                    findings.append(self._finding("warning", "frontend_quality_reviewer", "Label may not be associated with a control", "A label without a for attribute was detected.", "Add matching id/for attributes or wrap the control inside the label.", file=p, why="Form labels must be programmatically associated for accessibility."))
                if re.search(r"<article[^>]*(onclick|on:click)=", t):
                    findings.append(self._finding("warning", "frontend_quality_reviewer", "Non-interactive article has click handler", "An <article> element handles clicks.", "Use a button or anchor for interactive cards.", file=p, why="Svelte accessibility checks require keyboard-operable interactive elements."))
                if "[object Object]" in t or re.search(r"{\s*[^}\n]+\s*}\s*</", t):
                    # low-confidence but useful hint
                    pass
        return findings

    def _backend(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        req = next(((p,t) for p,t in contents.items() if p.endswith("requirements.txt")), None)
        imports_pyd_settings = any("pydantic_settings" in t for p,t in contents.items() if p.endswith(".py"))
        if imports_pyd_settings and req and "pydantic-settings" not in req[1].lower():
            findings.append(self._finding("blocker", "backend_architect", "pydantic-settings dependency missing", "Python imports pydantic_settings, but requirements.txt does not include pydantic-settings.", "Add pydantic-settings>=2.0.0 to requirements.txt.", file=req[0], why="Fresh installs will fail with ModuleNotFoundError or Pylance missing import warnings."))
        if any("zipfile" in t and "extractall" in t for p,t in contents.items() if p.endswith(".py")):
            unsafe = [p for p,t in contents.items() if p.endswith(".py") and "extractall" in t and "resolve" not in t[max(0,t.find("extractall")-800):t.find("extractall")+800]]
            for p in unsafe:
                findings.append(self._finding("blocker", "security_reviewer", "ZIP extraction may be vulnerable to path traversal", "extractall() detected without nearby path traversal validation.", "Validate each archive member resolves inside the destination directory before extraction.", file=p, why="Malicious ZIP entries like ../../.env can overwrite files outside the intended folder."))
        for p,t in contents.items():
            if p.endswith(".py"):
                if "allow_origins=['*']" in t or 'allow_origins=["*"]' in t:
                    findings.append(self._finding("warning", "security_reviewer", "CORS allows all origins", "allow_origins includes '*'.", "Restrict CORS to configured frontend origins in production.", file=p, why="Wildcard CORS can expose APIs unexpectedly when credentials or tokens are introduced."))
                if re.search(r"except\s+Exception\s*:\s*pass", t):
                    findings.append(self._finding("suggestion", "backend_architect", "Exception is silently swallowed", "except Exception: pass detected.", "Log the exception or return structured error context where appropriate.", file=p, why="Silent failures make debugging production issues harder."))
        return findings

    def _security(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        for p,t in contents.items():
            if p.endswith((".py", ".ts", ".js", ".svelte", ".env", ".json", ".yml", ".yaml")):
                for m in SECRET_RE.finditer(t):
                    findings.append(self._finding("blocker", "security_reviewer", "Possible hardcoded secret", m.group(0)[:160], "Move secrets to environment variables and rotate the exposed value if it is real.", file=p, line=t[:m.start()].count("\n")+1, why="Secrets in source code can leak through repos, logs, screenshots, or client bundles."))
                if "NEXT_PUBLIC_" in t and re.search(r"NEXT_PUBLIC_.*(SECRET|SERVICE|TOKEN|KEY)", t, re.I):
                    findings.append(self._finding("blocker", "security_reviewer", "Potential secret exposed through public frontend env variable", "NEXT_PUBLIC_ variable name includes secret/key/token language.", "Only expose truly public values to browser bundles; keep private keys server-side.", file=p, why="Public-prefixed variables are visible to users in client bundles."))
        return findings

    def _database(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        for p,t in contents.items():
            if p.endswith(".py"):
                if re.search(r"for\s+\w+\s+in\s+.*:\s*\n\s+.*execute\(", t):
                    findings.append(self._finding("suggestion", "database_optimizer", "Possible N+1 or looped query pattern", "Database execute call appears inside a loop.", "Batch queries, use joins, or use executemany when writing multiple rows.", file=p, why="Looped database calls can become severe latency bottlenecks under real workloads."))
                if "sqlite3.connect" in t and "PRAGMA journal_mode" not in t:
                    findings.append(self._finding("suggestion", "database_optimizer", "SQLite connection lacks explicit durability/concurrency pragmas", "sqlite3.connect detected without WAL/busy_timeout pragmas.", "Consider WAL mode and busy_timeout for local production-style session storage.", file=p, why="SQLite defaults can lock under concurrent API requests."))
        return findings

    def _devops(self, files: list[dict[str, Any]], contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        paths={f["path"].lower() for f in files}
        if not any(p.startswith(".github/workflows/") for p in paths):
            findings.append(self._finding("suggestion", "devops_automator", "No CI workflow detected", "No .github/workflows files found.", "Add CI for dependency install, lint/check, tests, backend import smoke, and frontend build.", why="Production code review should fail fast before manual testing."))
        if not any(Path(p).name.lower()=="dockerfile" for p in paths):
            findings.append(self._finding("nit", "devops_automator", "No Dockerfile detected", "No Dockerfile found.", "Add Dockerfile if the service needs repeatable deployment or review environments.", why="A container recipe reduces environment drift."))
        return findings

    def _ui(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        for p,t in contents.items():
            if p.endswith(".svelte") or p.endswith(".css"):
                if re.search(r"font-size\s*:\s*(4[0-9]|5[0-9]|6[0-9])px", t):
                    findings.append(self._finding("suggestion", "ui_designer", "Oversized typography detected", "Very large font size found in UI styles.", "Use a restrained type scale and reserve large display text for landing-page moments only.", file=p, why="Enterprise/workspace UIs become harder to scan when text is overbearing."))
                if "linear-gradient" in t and ("#0f" in t or "blue" in t.lower() or "cyan" in t.lower()):
                    findings.append(self._finding("suggestion", "ui_designer", "Generic AI-dashboard visual treatment", "Gradient/blue-cyan styling detected.", "Use a product-specific neutral palette, semantic tokens, and smaller workspace typography.", file=p, why="Generic AI visual patterns make the product look less credible."))
        return findings

    def _git(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        findings=[]
        paths={f["path"].lower() for f in files}
        if "contributing.md" not in paths and ".github/pull_request_template.md" not in paths:
            findings.append(self._finding("nit", "git_workflow_reviewer", "No contribution or PR review guide detected", "No CONTRIBUTING.md or PR template found.", "Add a small PR checklist covering tests, env changes, API contract changes, and screenshots.", why="Clean Git workflows reduce review ambiguity and repeated feedback."))
        return findings

    def _mcp(self, contents: dict[str, str]) -> list[dict[str, Any]]:
        findings=[]
        if any("McpServer" in t or "FastMCP" in t or "@modelcontextprotocol" in t for t in contents.values()):
            for p,t in contents.items():
                if "McpServer" in t or "FastMCP" in t:
                    if "description" not in t.lower():
                        findings.append(self._finding("warning", "mcp_builder", "MCP tool descriptions may be missing", "MCP server code detected but no obvious tool descriptions found.", "Give every tool a precise verb_noun name, typed params, and a when-to-use description.", file=p, why="Agents choose MCP tools based on names and descriptions."))
                    if "os.environ" not in t and "process.env" not in t and ("token" in t.lower() or "key" in t.lower()):
                        findings.append(self._finding("warning", "mcp_builder", "MCP server may not use environment-based secrets", "Auth-like language detected but no env access pattern found.", "Read credentials from env vars and document them in .env.example.", file=p, why="MCP tools may be run by agents in shared developer environments."))
        return findings

    def _call_llm(self, objective: str, contents: dict[str, str], findings: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not self.llm_enabled():
            return None
        sample = "\n\n".join([f"--- {p} ---\n{txt[:2500]}" for p,txt in list(contents.items())[:12]])[:14000]
        static = json.dumps([{k:f[k] for k in ["severity","agent","title","file","evidence"]} for f in findings[:25]], indent=2)
        system = (
            "You are a senior code review panel. Return strict JSON with keys summary, additional_findings, patch_checklist. "
            "additional_findings must be an array of objects with severity, agent, title, file, evidence, why_it_matters, recommendation, patch_hint. "
            "Use only these severity values: blocker, warning, suggestion, nit, praise. "
            "Use only these agent values: repository_mapper, api_contract_reviewer, frontend_quality_reviewer, backend_architect, security_reviewer, database_optimizer, devops_automator, ui_designer, git_workflow_reviewer, mcp_builder, patch_planner. "
            "Map critical/high to blocker or warning; map medium to suggestion; map low to nit. "
            "Map security_auditor to security_reviewer and code_reviewer to patch_planner. "
            "Be concrete. Do not invent files."
        )
        user = f"Objective: {objective}\n\nStatic findings:\n{static}\n\nSelected repository context:\n{sample}"
        provider = (settings.llm_provider or "offline").lower().strip()
        try:
            if provider == "deepseek":
                resp = requests.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type":"application/json"}, json={"model": settings.deepseek_model, "messages":[{"role":"system","content":system},{"role":"user","content":user}], "temperature":0.15, "response_format":{"type":"json_object"}}, timeout=60)
                resp.raise_for_status(); text=resp.json()["choices"][0]["message"]["content"]
            else:
                url=f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
                resp=requests.post(url,json={"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":user}]}],"generationConfig":{"temperature":0.15,"responseMimeType":"application/json"}},timeout=60)
                resp.raise_for_status(); text=resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text[text.find('{'):text.rfind('}')+1])
        except Exception as exc:
            return {"summary": f"LLM review failed; deterministic review was used. Error: {exc}", "additional_findings": [], "patch_checklist": []}

    def run_review(self, session_id: str, objective: str, target_files: list[str], focus_areas: list[str], use_llm: bool=True) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if not session: bad_request("Unknown session_id")
        files = self.repo.file_list(session_id)
        contents = self._read_selected(session_id, target_files)
        findings=[]
        traces=[]
        groups=[
            ("repository_mapper", lambda: self._map_repository(files, contents)),
            ("api_contract_reviewer", lambda: self._api_contract(contents)),
            ("frontend_quality_reviewer", lambda: self._frontend(contents)),
            ("backend_architect", lambda: self._backend(contents)),
            ("security_reviewer", lambda: self._security(contents)),
            ("database_optimizer", lambda: self._database(contents)),
            ("devops_automator", lambda: self._devops(files, contents)),
            ("ui_designer", lambda: self._ui(contents)),
            ("git_workflow_reviewer", lambda: self._git(files)),
            ("mcp_builder", lambda: self._mcp(contents)),
        ]
        focus_map={"api_contract":"api_contract_reviewer","frontend":"frontend_quality_reviewer","backend":"backend_architect","security":"security_reviewer","database":"database_optimizer","devops":"devops_automator","ui":"ui_designer","git":"git_workflow_reviewer","mcp":"mcp_builder"}
        wanted={focus_map.get(f, f) for f in focus_areas} | {"repository_mapper"}
        for agent, fn in groups:
            if agent not in wanted:
                traces.append({"agent":agent,"status":"skipped","summary":"Skipped by focus area selection.","findings":0}); continue
            try:
                fs=fn(); findings.extend(fs)
                traces.append({"agent":agent,"status":"complete","summary":f"{AGENT_LABELS[agent]} completed deterministic checks.","findings":len(fs)})
            except Exception as exc:
                traces.append({"agent":agent,"status":"error","summary":str(exc),"findings":0})
        llm_data = self._call_llm(objective, contents, findings) if use_llm else None
        if llm_data:
            llm_findings = llm_data.get("additional_findings") or []
            if isinstance(llm_findings, dict):
                llm_findings = [llm_findings]
            if not isinstance(llm_findings, list):
                llm_findings = []

            accepted_llm_findings = 0
            for f in llm_findings:
                if isinstance(f, dict) and f.get("title"):
                    findings.append(
                        self._finding(
                            f.get("severity") or "suggestion",
                            f.get("agent") or "patch_planner",
                            f.get("title"),
                            f.get("evidence") or "LLM review",
                            f.get("recommendation") or "Review manually.",
                            f.get("file"),
                            f.get("why_it_matters"),
                            f.get("patch_hint"),
                            confidence=.72,
                        )
                    )
                    accepted_llm_findings += 1
            traces.append({"agent":"patch_planner","status":"complete","summary":"LLM-assisted synthesis completed." if not str(llm_data.get("summary","")).startswith("LLM review failed") else llm_data.get("summary"),"findings":accepted_llm_findings})
        else:
            traces.append({"agent":"patch_planner","status":"complete","summary":"Offline patch planner synthesized deterministic findings.","findings":0})
        severity_weight={"blocker":16,"warning":8,"suggestion":4,"nit":1,"praise":0}
        penalty=sum(severity_weight.get(f["severity"],3) for f in findings)
        score=max(0, min(100, 100-penalty))
        patch_checklist=[]
        for f in findings:
            if f["severity"] in {"blocker","warning","suggestion"}:
                file_prefix = f"[{f['file']}] " if f.get("file") else ""
                patch_checklist.append(file_prefix + f["recommendation"])
        if llm_data:
            llm_patch_items = llm_data.get("patch_checklist") or []
            if isinstance(llm_patch_items, str):
                llm_patch_items = [line.strip(" -•	") for line in llm_patch_items.splitlines() if line.strip(" -•	")]
            if isinstance(llm_patch_items, list):
                patch_checklist.extend([str(x) for x in llm_patch_items if str(x).strip()])
        summary = self._summary(score, findings, session["repo_name"])
        review_id=str(uuid.uuid4())
        result={"review_id":review_id,"session_id":session_id,"repo_name":session["repo_name"],"ai_mode":self.ai_mode(),"summary":summary,"score":score,"findings":findings,"traces":traces,"patch_checklist":patch_checklist[:40],"markdown_report":"","json_export":{}}
        result["markdown_report"]=self._markdown(result)
        result["json_export"]={"review_id":review_id,"repo":session["repo_name"],"score":score,"findings":findings,"patch_checklist":result["patch_checklist"]}
        self.store.save_review(session_id, objective, result)
        return result

    def _summary(self, score: int, findings: list[dict[str, Any]], repo: str) -> str:
        counts={s:sum(1 for f in findings if f["severity"]==s) for s in ["blocker","warning","suggestion","nit"]}
        return f"{repo} scored {score}/100 with {counts['blocker']} blockers, {counts['warning']} warnings, {counts['suggestion']} suggestions, and {counts['nit']} nits. Prioritize blockers before treating the repository as production-ready."

    def _markdown(self, result: dict[str, Any]) -> str:
        lines=[f"# Code Review Report — {result['repo_name']}","",f"**Score:** {result['score']}/100",f"**Mode:** {result['ai_mode']}","",result["summary"],""]
        for severity in ["blocker","warning","suggestion","nit","praise"]:
            group=[f for f in result["findings"] if f["severity"]==severity]
            if not group: continue
            lines.extend([f"## {severity.title()} findings",""])
            for f in group:
                loc=f" — `{f['file']}`" if f.get("file") else ""
                lines.extend([f"### {f['title']}{loc}","",f"**Agent:** {AGENT_LABELS.get(f['agent'], f['agent'])}","",f"**Evidence:** {f['evidence']}","",f"**Why it matters:** {f['why_it_matters']}","",f"**Recommendation:** {f['recommendation']}",""])
        if result.get("patch_checklist"):
            lines.extend(["## Patch checklist",""])
            lines.extend([f"- {x}" for x in result["patch_checklist"]])
        return "\n".join(lines).strip()+"\n"

    def skills(self) -> list[dict[str, str]]:
        return [
            {"name":"Code Reviewer","role":"Correctness, security, maintainability, performance, and testing review.","incorporated_as":"Severity model, findings format, mentor-style recommendations.","source_file":"engineering-code-reviewer.md"},
            {"name":"Backend Architect","role":"FastAPI/API architecture and reliability review.","incorporated_as":"Backend route, config, error handling, and dependency checks.","source_file":"engineering-backend-architect.md"},
            {"name":"Frontend Developer","role":"Svelte/frontend implementation, accessibility, and performance review.","incorporated_as":"SvelteKit startup, a11y, app.html, package and client checks.","source_file":"engineering-frontend-developer.md"},
            {"name":"DevOps Automator","role":"CI/CD, deployment, monitoring, and environment readiness.","incorporated_as":"CI, Docker, env, and production workflow checks.","source_file":"engineering-devops-automator.md"},
            {"name":"Database Optimizer","role":"Database schema and query performance review.","incorporated_as":"N+1, SQLite persistence, connection/durability recommendations.","source_file":"engineering-database-optimizer.md"},
            {"name":"UI Designer","role":"Visual system and accessibility review.","incorporated_as":"UI theme, large typography, generic AI-dashboard checks.","source_file":"design-ui-designer.md"},
            {"name":"MCP Builder","role":"MCP server tool interface, validation, and config safety.","incorporated_as":"MCP-specific server/tool description and secret handling checks.","source_file":"specialized-mcp-builder.md"},
            {"name":"Git Workflow Master","role":"Clean commits, PR hygiene, and branch strategy.","incorporated_as":"PR template and contribution readiness checks.","source_file":"engineering-git-workflow-master.md"},
        ]

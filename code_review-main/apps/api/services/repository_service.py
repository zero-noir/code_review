from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any
from core.config import settings
from core.errors import bad_request
from repositories.review_store import ReviewStore

TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".env", ".css", ".html", ".sql", ".sh", ".dockerfile"}
DEFAULT_NAME_RE = re.compile(r"(^|/)(readme\.md|package\.json|requirements\.txt|pyproject\.toml|vite\.config\.ts|svelte\.config\.js|src/app\.html|src/routes/\+page\.svelte|main\.py|.*client\.ts)$", re.I)

class RepositoryService:
    def __init__(self, store: ReviewStore):
        self.store = store

    def _safe_extract(self, zip_path: Path, dest: Path) -> None:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                target = dest / member.filename
                if not str(target.resolve()).startswith(str(dest.resolve())):
                    bad_request(f"Unsafe ZIP path blocked: {member.filename}")
            zf.extractall(dest)

    def _flatten_root(self, dest: Path) -> Path:
        children = [p for p in dest.iterdir() if p.name not in {"__MACOSX"}]
        if len(children) == 1 and children[0].is_dir():
            return children[0]
        return dest

    def _kind(self, path: Path) -> str:
        name = path.name.lower()
        suffix = path.suffix.lower()
        if name in {"package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock"}: return "node-manifest"
        if name in {"requirements.txt", "pyproject.toml", "poetry.lock"}: return "python-manifest"
        if suffix == ".svelte": return "svelte"
        if suffix in {".ts", ".tsx", ".js", ".jsx"}: return "frontend-code"
        if suffix == ".py": return "python-code"
        if suffix in {".md", ".txt"}: return "document"
        if suffix in {".yml", ".yaml", ".toml", ".json"}: return "config"
        return "other"

    def list_repo_files(self, root: Path) -> list[dict[str, Any]]:
        rows=[]
        skip_dirs={".git","node_modules",".venv","venv","__pycache__","dist","build",".svelte-kit",".next","target","coverage"}
        for p in root.rglob("*"):
            if p.is_dir():
                continue
            if any(part in skip_dirs for part in p.relative_to(root).parts):
                continue
            rel = p.relative_to(root).as_posix()
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > settings.max_file_kb * 1024 and p.suffix.lower() not in {".json", ".md"}:
                continue
            if p.suffix.lower() in TEXT_EXT or p.name.lower() in {"dockerfile", "makefile"}:
                rows.append({"path": rel, "size": size, "kind": self._kind(p)})
        rows.sort(key=lambda r: r["path"])
        return rows

    def detect_stack(self, files: list[dict[str, Any]]) -> list[str]:
        paths = {f["path"].lower() for f in files}
        stack=[]
        if "package.json" in paths: stack.append("node")
        if "vite.config.ts" in paths or "svelte.config.js" in paths: stack.append("sveltekit")
        if any(p.endswith(".svelte") for p in paths): stack.append("svelte")
        if "requirements.txt" in paths or "pyproject.toml" in paths: stack.append("python")
        if "main.py" in paths or any("routers/" in p and p.endswith(".py") for p in paths): stack.append("fastapi")
        if any("dockerfile" == Path(p).name.lower() for p in paths): stack.append("docker")
        if any(p.startswith(".github/workflows/") for p in paths): stack.append("github-actions")
        return stack or ["generic-repository"]

    def default_targets(self, files: list[dict[str, Any]]) -> list[str]:
        picked = [f["path"] for f in files if DEFAULT_NAME_RE.search(f["path"])]
        if not picked:
            picked = [f["path"] for f in files if f["path"].lower().endswith("readme.md")]
        return picked[:40]

    def upload_zip(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        if len(file_bytes) > settings.max_zip_mb * 1024 * 1024:
            bad_request(f"ZIP too large. Limit is {settings.max_zip_mb} MB.")
        repo_name = Path(filename).stem.replace(" ", "_")
        zip_id = re.sub(r"[^A-Za-z0-9_.-]", "_", repo_name) + "_upload.zip"
        upload_path = settings.upload_dir / zip_id
        upload_path.write_bytes(file_bytes)
        extract_base = settings.extracted_dir / (repo_name + "_" + os.urandom(4).hex())
        extract_base.mkdir(parents=True, exist_ok=True)
        self._safe_extract(upload_path, extract_base)
        repo_root = self._flatten_root(extract_base)
        files = self.list_repo_files(repo_root)
        detected = self.detect_stack(files)
        defaults = self.default_targets(files)
        warnings=[]
        if len(files) == 0: warnings.append("No text/code files were detected in the ZIP.")
        session_id = self.store.create_session(repo_name, filename, repo_root, files, defaults, detected)
        return {"session_id": session_id, "repo_name": repo_name, "uploaded_filename": filename, "file_count": len(files), "default_targets": defaults, "detected_stack": detected, "warnings": warnings}

    def read_text(self, session_id: str, rel_path: str) -> str:
        session = self.store.get_session(session_id)
        if not session:
            bad_request("Unknown session_id")
        root = Path(session["extracted_path"])
        target = root / rel_path
        if not str(target.resolve()).startswith(str(root.resolve())) or not target.exists() or not target.is_file():
            bad_request(f"Invalid target file: {rel_path}")
        data = target.read_bytes()
        if len(data) > settings.max_file_kb * 1024:
            data = data[:settings.max_file_kb * 1024]
        return data.decode("utf-8", errors="replace")

    def file_list(self, session_id: str) -> list[dict[str, Any]]:
        return self.store.list_files(session_id)

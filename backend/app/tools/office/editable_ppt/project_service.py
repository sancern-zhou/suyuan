from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Iterable

from app.tools.office.editable_ppt.contracts import ChangeRecord, ProjectState
from app.utils.path_config import get_data_registry
from app.utils.path_config import resolve_agent_path


class RevisionConflictError(RuntimeError):
    pass


class EditablePptProjectService:
    """Owns editable source projects; generated preview/PPTX files are never authoritative."""

    def __init__(self, storage_root: str | Path | None = None):
        base = Path(storage_root) if storage_root is not None else get_data_registry()
        self.projects_root = (base / "editable_ppt_projects").resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def create_project(self, title: str, theme: str = "business") -> ProjectState:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "presentation"
        root = self.projects_root / f"{slug}-{uuid.uuid4().hex[:8]}"
        (root / "slides").mkdir(parents=True)
        (root / "assets").mkdir()
        (root / "templates").mkdir()
        (root / ".editable-ppt" / "snapshots").mkdir(parents=True)
        deck = {
            "schemaVersion": "1.0", "id": slug, "title": title,
            "theme": "theme.json", "slides": ["cover"],
        }
        themes = {
            "government": {"primary": "#8B1E1E", "secondary": "#B98B2F"},
            "business": {"primary": "#174A7C", "secondary": "#0F766E"},
            "data-analysis": {"primary": "#1D4ED8", "secondary": "#7C3AED"},
        }
        colors = themes.get(theme, themes["business"])
        theme_doc = {
            "name": theme, **colors, "accent": "#E8A317", "canvas": "#F7F9FC",
            "surface": "#FFFFFF", "text": "#1F2937", "muted": "#64748B",
            "line": "#CBD5E1", "fontTitle": "Noto Sans CJK SC",
            "fontBody": "Noto Sans CJK SC", "pptFontTitle": "Microsoft YaHei",
            "pptFontBody": "Microsoft YaHei",
        }
        safe_title = html.escape(title).replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        intent = json.dumps(f"introduce {title}", ensure_ascii=False)
        slide = f'''window.slideDataMap.set(1, {{
  schemaVersion: "1.0", id: "cover", type: "cover", intent: {intent},
  layoutMode: "freeform", html: `<section class="relative w-[1440px] h-[810px] bg-[var(--canvas)]" data-pptx-id="slide-root"><h1 class="absolute left-[100px] top-[280px] text-[58px] font-bold" data-pptx-id="title">{safe_title}</h1></section>`,
  nativeElements: [], speakerNotes: []
}});
'''
        self._write(root / "deck.json", json.dumps(deck, ensure_ascii=False, indent=2))
        self._write(root / "theme.json", json.dumps(theme_doc, ensure_ascii=False, indent=2))
        self._write(root / "slides" / "slide-001.js", slide)
        state = ProjectState(str(root), 1, ["cover"], self._hashes(root), [])
        self._save_state(root, state)
        self._snapshot(root, 1)
        return state

    def inspect(self, project_dir: str | Path) -> ProjectState:
        root = self._project_root(project_dir)
        return self.reconcile_external_edits(root)

    def read_source(self, project_dir: str | Path, relative_path: str) -> str:
        path = self._source_path(self._project_root(project_dir), relative_path)
        return path.read_text(encoding="utf-8")

    def edit_source(
        self, project_dir: str | Path, relative_path: str,
        content: str | bytes, base_revision: int,
    ) -> ProjectState:
        root = self._project_root(project_dir)
        current = self.reconcile_external_edits(root)
        if current.revision != base_revision:
            raise RevisionConflictError(
                f"stale revision {base_revision}; current revision is {current.revision}"
            )
        path = self._source_path(root, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = content if isinstance(content, bytes) else content.encode("utf-8")
        self._validate_candidate(root, relative_path, payload)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(payload)
        tmp.replace(path)
        return self._record_change(root, current, [relative_path], "managed_edit")

    def edit_sources(
        self,
        project_dir: str | Path,
        edits: list[dict[str, str | bytes]],
        base_revision: int,
    ) -> ProjectState:
        root = self._project_root(project_dir)
        current = self.reconcile_external_edits(root)
        if current.revision != base_revision:
            raise RevisionConflictError(
                f"stale revision {base_revision}; current revision is {current.revision}"
            )
        if not edits:
            raise ValueError("edits 不能为空")
        candidates: list[tuple[str, bytes]] = []
        seen: set[str] = set()
        for edit in edits:
            relative_path = str(edit["relative_path"]).replace("\\", "/")
            if relative_path in seen:
                raise ValueError(f"edits 包含重复路径: {relative_path}")
            seen.add(relative_path)
            self._source_path(root, relative_path)
            content = edit["content"]
            payload = content if isinstance(content, bytes) else str(content).encode("utf-8")
            candidates.append((relative_path, payload))

        self._validate_candidates(root, candidates)
        staged_files: list[tuple[Path, Path]] = []
        try:
            for relative_path, payload in candidates:
                target = self._source_path(root, relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                staged = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                staged.write_bytes(payload)
                staged_files.append((staged, target))
            for staged, target in staged_files:
                staged.replace(target)
        finally:
            for staged, _target in staged_files:
                if staged.exists():
                    staged.unlink()
        return self._record_change(
            root,
            current,
            [relative_path for relative_path, _payload in candidates],
            "managed_batch_edit",
        )

    def _validate_candidate(self, root: Path, relative_path: str, payload: bytes):
        self._validate_candidates(root, [(relative_path, payload)])

    def _validate_candidates(self, root: Path, candidates: list[tuple[str, bytes]]):
        if all(relative_path.startswith(("assets/", "templates/")) for relative_path, _ in candidates):
            return
        with tempfile.TemporaryDirectory(prefix="editable-ppt-validate-") as temp:
            staged = Path(temp) / "project"
            shutil.copytree(root, staged, ignore=shutil.ignore_patterns(".editable-ppt", "build"))
            for relative_path, payload in candidates:
                target = staged / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            cli = Path(__file__).resolve().parent.parent / "editable_ppt_runtime" / "src" / "cli.mjs"
            request = json.dumps({"command": "inspect", "projectDir": str(staged)}).encode()
            try:
                run = subprocess.run(["node", str(cli)], input=request, capture_output=True, timeout=5)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise ValueError(f"source validation unavailable: {exc}") from exc
            if run.returncode != 0:
                message = run.stderr.decode("utf-8", errors="replace").strip()
                raise ValueError(f"source validation failed: {message}")

    def reconcile_external_edits(self, project_dir: str | Path) -> ProjectState:
        root = self._project_root(project_dir)
        state = self._load_state(root)
        hashes = self._hashes(root)
        changed = sorted(
            key for key in set(hashes) | set(state.hashes)
            if hashes.get(key) != state.hashes.get(key)
        )
        if not changed:
            return state
        return self._record_change(root, state, changed, "direct_document_edit", hashes=hashes)

    def restore_revision(
        self, project_dir: str | Path, revision: int, base_revision: int
    ) -> ProjectState:
        root = self._project_root(project_dir)
        current = self.reconcile_external_edits(root)
        if current.revision != base_revision:
            raise RevisionConflictError(
                f"stale revision {base_revision}; current revision is {current.revision}"
            )
        snapshot = root / ".editable-ppt" / "snapshots" / str(revision)
        if not snapshot.is_dir():
            raise ValueError(f"snapshot revision not found: {revision}")
        before = set(self._hashes(root))
        for relative in before:
            target = root / relative
            if target.exists():
                target.unlink()
        for source in snapshot.rglob("*"):
            if source.is_file():
                target = root / source.relative_to(snapshot)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        changed = sorted(before | set(self._hashes(root)))
        return self._record_change(root, current, changed, "restore")

    def mark_clean(self, project_dir: str | Path, slide_ids: Iterable[str] | None = None) -> ProjectState:
        root = self._project_root(project_dir)
        state = self.reconcile_external_edits(root)
        clean = set(slide_ids or state.dirty_slides)
        updated = ProjectState(
            state.project_dir, state.revision,
            [item for item in state.dirty_slides if item not in clean],
            state.hashes, state.changes,
        )
        self._save_state(root, updated)
        return updated

    def _record_change(self, root, state, paths, source, hashes=None):
        hashes = hashes or self._hashes(root)
        dirty = sorted(set(state.dirty_slides) | set(self._dirty_slides(root, paths)))
        revision = state.revision + 1
        change = ChangeRecord(revision, source, sorted(paths), dirty)
        updated = ProjectState(str(root), revision, dirty, hashes, [*state.changes, change])
        self._save_state(root, updated)
        self._snapshot(root, revision)
        return updated

    def _dirty_slides(self, root: Path, changed: Iterable[str]) -> list[str]:
        deck = json.loads((root / "deck.json").read_text(encoding="utf-8"))
        ordered_ids = deck.get("slides", [])
        slide_ids = []
        sources = {}
        for index, path in enumerate(sorted((root / "slides").glob("slide-*.js")), 1):
            relative = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
            match = re.search(r'\bid\s*:\s*["\']([^"\']+)', text)
            slide_id = match.group(1) if match else f"slide-{index}"
            slide_ids.append(slide_id)
            sources[relative] = (slide_id, text)
        if ordered_ids:
            slide_ids = [item for item in ordered_ids if item in slide_ids]
        dirty = set()
        for relative in changed:
            if relative in {"deck.json", "theme.json"} or relative.startswith("templates/"):
                dirty.update(slide_ids)
            elif relative in sources:
                dirty.add(sources[relative][0])
            elif relative.startswith("assets/"):
                for slide_id, source in sources.values():
                    if relative in source or Path(relative).name in source:
                        dirty.add(slide_id)
        return sorted(dirty)

    def _project_root(self, project_dir: str | Path) -> Path:
        root = resolve_agent_path(project_dir)
        try:
            root.relative_to(self.projects_root)
        except ValueError as exc:
            raise ValueError("project is outside editable PPT projects root") from exc
        if not (root / ".editable-ppt" / "state.json").is_file():
            raise ValueError("not an editable PPT project")
        return root

    @staticmethod
    def _source_path(root: Path, relative_path: str) -> Path:
        normalized = str(relative_path).replace("\\", "/")
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("path is outside project root") from exc
        allowed = normalized in {"deck.json", "theme.json"} or normalized.startswith(("slides/", "templates/", "assets/"))
        if not allowed:
            raise ValueError("path is outside editable source scope")
        if path == root:
            raise ValueError("path is outside editable source scope")
        return path

    @staticmethod
    def _hashes(root: Path) -> dict[str, str]:
        result = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and not relative.startswith(".editable-ppt/") and not relative.startswith("build/"):
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    @staticmethod
    def _write(path: Path, content: str):
        path.write_text(content, encoding="utf-8")

    def _load_state(self, root: Path) -> ProjectState:
        raw = json.loads((root / ".editable-ppt" / "state.json").read_text(encoding="utf-8"))
        changes = [ChangeRecord(**item) for item in raw.get("changes", [])]
        return ProjectState(raw["project_dir"], raw["revision"], raw.get("dirty_slides", []), raw.get("hashes", {}), changes)

    @staticmethod
    def _save_state(root: Path, state: ProjectState):
        target = root / ".editable-ppt" / "state.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    def _snapshot(self, root: Path, revision: int):
        target = root / ".editable-ppt" / "snapshots" / str(revision)
        if target.exists():
            shutil.rmtree(target)
        for relative in self._hashes(root):
            source = root / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

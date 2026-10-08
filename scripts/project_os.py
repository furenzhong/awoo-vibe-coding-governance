#!/usr/bin/env python3
"""Adopt lightweight project governance without replacing an existing project.

Python 3.10+ and the standard library are sufficient. Git is used read-only when
available. No command in this tool downloads files, executes task commands,
changes remotes, commits changes, or contacts an agent service.
"""

# MIT License
#
# Copyright (c) 2026 furenzhong
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit


VERSION = "1.6.0"
SCHEMA_VERSION = 1
MANIFEST = "project-os.json"
ADOPTION = ".project-os-adoption.json"
KIT_ORIGIN = "github.com/furenzhong/awoo-vibe-coding-governance"
# Retain the former URL for clones and provenance recorded before the rename.
KIT_ORIGINS = {KIT_ORIGIN, "github.com/furenzhong/ai_codex_project_os_starter_kit"}
SOURCE_KEYS = ("rules", "status", "handoff", "decisions")
DEFAULT_SOURCES = {key: f"project-os/{key.upper()}.md" for key in SOURCE_KEYS}
BEGIN = b"<!-- project-os:begin -->"
END = b"<!-- project-os:end -->"
TASK_STATUSES = {"planned", "running", "submitted", "accepted", "returned", "blocked"}
LIMITS = (
    "Checks validate local structure, Git object references, declared results, and evidence paths. "
    "Opted-in task context checks compare snapshot hashes, declared revisions, checkpoints, and correction evidence. "
    "Legacy tasks have no context coverage. Hashes are editable consistency records, not tamper-proof attestations. "
    "Checks do not execute commands, contact or stop agents, establish identity or understanding, "
    "verify live process state, or prove evidence claims and product correctness."
)
INVENTORY_EXTENSIONS = {".md", ".markdown", ".txt", ".rst"}
INVENTORY_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "vendor",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache",
    ".tox", ".venv", "venv", "coverage", ".next", ".nuxt",
}
INVENTORY_ARCHIVE_PREFIXES = {"docs/06_archive", "archive", "archives"}
INVENTORY_METADATA_KEYS = {"lifecycle", "topic", "created", "superseded_by", "archived_reason"}
INVENTORY_RETIRED = {"archived", "superseded", "obsolete"}
INVENTORY_LIMITS = (
    "Categories use declared mappings, document front matter, and paths; they do not measure actual agent context. "
    "Only the reported file extensions and reading entrypoints are scanned, excluding the reported directories and links. "
    "Exact duplicates are review candidates; unclassified documents are not garbage. "
    "No files are moved, rewritten, or deleted. Truth, freshness, semantic duplication, and deletion eligibility require review."
)


class ProjectOSError(Exception):
    """A concise, actionable validation failure."""


def git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=15,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def normalize_origin(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().replace("\\", "/")
    if "://" in value:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        value = (parsed.hostname or "") + parsed.path
    else:
        value = re.sub(r"^[^/@]+@", "", value)
        value = re.sub(r"^([^/]+):(?=[^/])", r"\1/", value)
        value = re.split(r"[?#]", value, maxsplit=1)[0]
    value = value.rstrip("/")
    if value.lower().endswith(".git"):
        value = value[:-4]
    return value.lower()


def identity(root: Path) -> dict[str, Any]:
    top = git(root, "rev-parse", "--show-toplevel")
    common = git(root, "rev-parse", "--git-common-dir") if top else None
    common_path = (root / common).resolve() if common else None
    return {
        "root": root,
        "git_root": Path(top).resolve() if top else None,
        "common_dir": common_path,
        "origin": normalize_origin(git(root, "remote", "get-url", "origin")) if top else None,
    }


def fingerprint(path: Path | None) -> str | None:
    return hashlib.sha256(os.path.normcase(str(path)).encode("utf-8")).hexdigest() if path else None


def target_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ProjectOSError(f"Target must be an existing project directory: {value}")
    info = identity(root)
    if info["git_root"] and info["git_root"] != root:
        raise ProjectOSError("--target must name the Git working tree root, not one of its subdirectories.")
    return root


def safe_path(root: Path, relative: Any, *, inspect_filesystem: bool = True) -> Path:
    root = root.resolve()
    if not isinstance(relative, str) or not relative.strip():
        raise ProjectOSError("Managed paths must be nonempty relative strings.")
    windows = PureWindowsPath(relative)
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if windows.drive or windows.is_absolute() or relative.startswith("/"):
        raise ProjectOSError(f"Absolute paths are not allowed: {relative}")
    if not parts or any(p.casefold() in {"..", ".git"} for p in parts):
        raise ProjectOSError(f"Path traversal and .git paths are not allowed: {relative}")
    if any(":" in p for p in parts):
        raise ProjectOSError(f"Drive and alternate-stream paths are not allowed: {relative}")
    if any(p.endswith((" ", ".")) or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts):
        raise ProjectOSError(f"Ambiguous or reserved filesystem names are not allowed: {relative}")
    path = root.joinpath(*parts)
    if not inspect_filesystem:
        return path
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ProjectOSError(f"Symlink or junction paths are not managed: {relative}")
    if not path.resolve().is_relative_to(root):
        raise ProjectOSError(f"Path escapes the project: {relative}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectOSError(f"Cannot read JSON from {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectOSError(f"{path.name} must contain a JSON object.")
    return data


def json_bytes(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def manifest_shape(root: Path, data: dict[str, Any]) -> None:
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ProjectOSError(f"Unsupported schema_version; expected {SCHEMA_VERSION}.")
    if data.get("role") not in ("starter-kit", "project"):
        raise ProjectOSError("Manifest role must be starter-kit or project.")
    if not isinstance(data.get("kit_version"), str) or not data["kit_version"]:
        raise ProjectOSError("Manifest requires kit_version.")
    sources = data.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(SOURCE_KEYS):
        raise ProjectOSError("sources must map exactly rules, status, handoff, and decisions.")
    names = list(sources.values()) + [data.get("tasks_dir"), data.get("evidence_dir")]
    paths = [safe_path(root, name) for name in names]
    reserved = {root / MANIFEST, root / ADOPTION, root / "AGENTS.md", root / "CLAUDE.md", root / "scripts/project_os.py"}
    for index, path in enumerate(paths):
        rules_entry = names[index] == sources["rules"] and path == root / "AGENTS.md"
        if path in reserved and not rules_entry:
            raise ProjectOSError("Governance paths must not replace the manifest, agent entries, or tool.")
    for i, path in enumerate(paths):
        for other in paths[i + 1:]:
            if path == other or path.is_relative_to(other) or other.is_relative_to(path):
                raise ProjectOSError("Source files, tasks_dir, and evidence_dir must be distinct, non-nested paths.")
    source_identity = data.get("source_identity")
    if source_identity is not None:
        if not isinstance(source_identity, dict):
            raise ProjectOSError("source_identity must be an object.")
        for key in ("origin", "revision", "kit_version", "common_dir_fingerprint"):
            if source_identity.get(key) is not None and not isinstance(source_identity[key], str):
                raise ProjectOSError(f"source_identity.{key} must be a string or null.")


def install_identity(source: Path, target: Path, current: dict[str, Any] | None) -> dict[str, Any]:
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise ProjectOSError("Source and target must be separate, non-overlapping directories.")
    source_manifest = safe_path(source, MANIFEST)
    if source_manifest.exists() and read_json(source_manifest).get("role") != "starter-kit":
        raise ProjectOSError("Install from a starter-kit checkout; an installed copy is for check and snapshot.")
    if current and current.get("role") != "project":
        raise ProjectOSError("Target identifies as starter-kit. Choose the existing child project instead.")
    src, dst = identity(source), identity(target)
    if src["common_dir"] and src["common_dir"] == dst["common_dir"]:
        raise ProjectOSError("Target shares the starter kit's Git common directory (including worktrees).")
    if dst["origin"] and dst["origin"] in KIT_ORIGINS | {src["origin"]}:
        raise ProjectOSError("Target origin identifies the starter kit. Do not deploy into a clone of the mother repository.")
    origin = src["origin"]
    # Local remotes are useful for the live identity comparison but should not
    # publish machine-specific paths in a committed child-project manifest.
    public_origin = origin if origin and "." in origin.split("/", 1)[0] else None
    return {
        "origin": public_origin,
        "revision": git(source, "rev-parse", "HEAD"),
        "kit_version": VERSION,
        "dirty_source": bool(git(source, "status", "--porcelain=v1")),
        "common_dir_fingerprint": fingerprint(src["common_dir"]),
    }


def default_document(key: str) -> bytes:
    documents = {
        "rules": """# 项目规则 / Project rules

Record the project's goal, scope boundaries, and lasting constraints here.
Use existing code, tests, and observed behavior to check claims about reality.
Keep one authoritative source for each fact; link to task evidence instead of
copying task state into multiple documents. Add detail only when it prevents a
specific recurring mistake.

Backlogs keep task status, the next action and a topic link, rather than copying
the topic's requirements, constraints or pending choices. When the current work
touches a duplicate entry, replace that duplicate with a reference only after
confirming the topic preserves the full content. Do not start unrelated cleanup.

Only on an explicit user request for document inventory or cleanup, consolidate
within the requested scope (all project documents or specified files/topics).
Preserve
the current conclusion, constraints, unresolved questions, rejected options
and their rationale, evidence, and conditions for reopening the decision.
Keep canonical source paths stable. Working notes and archives are read on
demand, not preloaded as current instructions. Mark replaced standalone notes
with lifecycle: superseded and a replacement link in top-of-file front matter;
update incoming references before moving them. Uncertain or unfinished material
stays working/candidate. Adoption, task closure, replaced decisions, handoffs,
context conflicts, and new sessions do not start or prompt a cleanup. Normal
fact maintenance and task-related questions continue as before.
For an explicitly requested inventory or cleanup, use
`python scripts/project_os.py inventory --target . --json` as needed; it scans
the project, but cleanup stays within the requested scope. Unclassified
and exact duplicate candidates are not deletion lists.
Investigate uncertainty in existing requirements, decisions, code, and evidence
first. Ask the user only when the answer changes intent, retention, or authority
and cannot be established there: conflicting requirements, a possibly unique
constraint, or deletion outside existing authorization. State the concrete
conflict, evidence, recommendation, and consequence. Preserve unresolved material
and pause only dependent actions while awaiting an answer; silence is not consent.
Routine reversible organization within authorization does not need reapproval.
Delete only within existing user/project authorization after checking unique
content, references, active tasks, and retention needs; age alone is insufficient.

## 跨会话任务 / Cross-session tasks

Save consequential user confirmations, corrections, rejected choices and reasons,
evidence, and unfinished state while they are still verifiable. Update the existing
responsible source before dependent action, or before ending the turn otherwise.
Do not wait for a reminder, compaction, or an explicit handoff request. No meaningful
change means no new summary or repeated rewrite of every entrypoint.

After compaction or recovery, compare available summaries and relevant user input
with current authority and unfinished operations. Save missing consequential
information to its existing source. Native summaries remain source-labelled
historical evidence, retained only through an adopted recording mechanism. When
native text or coverage is unavailable, save verifiable continuation information
and state the gap; model-written notes are not native summaries or proof of full
recovery. Verify that each executor loads the shared rules; writing them does not
establish adoption. Shared rule maintenance, native capture, and verified
continuation are separate outcomes, and none initiates document cleanup.

When the user asks to prepare a new conversation or update the handoff, save
unsaved decisions, corrections, verification results and necessary operation
details to their existing sources. Preserve information whose absence would
cause repeated questions, repeated trial and error, use of the wrong environment,
or duplicate external actions. Keep durable access and operating knowledge in an
existing runbook: environment and entrypoint, account role, credential location
(never values), known working steps, verification evidence/time and limitations.
Keep the current stop point, operation/session IDs, observed state and next step
in the existing task/checkpoint; HANDOFF links to it. Use only applicable details,
not a mandatory server form. Do not invent tasks for discussion or create a new
document for every conversation. Saved, checked for handoff, and actually resumed
are separate claims. Report the resume entry, missing information and checks
actually performed. A past successful login is not current access evidence.
This is ordinary handoff maintenance, not document cleanup or a new auto-trigger.

If this project explicitly enables project-os-context.json, follow
project-os/CONTEXT_CAPTURE.md for event reconciliation and recovery. Native
summaries are historical evidence. Check relevant pending inputs and current
sources before dependent work; capture alone proves neither semantic accuracy
nor delivery. Ordinary installation does not enable capture. Discussion does
not invent an execution task, and these events never initiate document cleanup.

For delegated or recoverable work, keep the existing task record as the sole
lifecycle source. Retain a versioned dispatch snapshot of the goal, constraints
and accessible sources, rejected choices and reasons, assumptions, non-goals,
and acceptance basis. Confirm the executor can access the actual version in its
own workspace; a link to uncommitted files elsewhere is not delivery. For a
consequential interpretation, inspect an early key choice or representative
result. Routine implementation needs no added approval ceremony.

Each active execution identity, including the coordinator, owns a separate task
checkpoint. Save meaningful changes, corrections and handoffs: last observed
action and evidence, unresolved assumptions, ongoing operations and locators,
next action, and adopted context version. Do not save every message or depend
on a pre-compaction hook. Keep project HANDOFF as navigation to these records.
Recheck current authority, revisions, pending corrections, actual Git and runtime
state before resuming or redispatching. Last observed running is not live truth;
unknown does not mean stopped. Query external operations before retrying them.

Corrections are recorded, delivered, then adopted, with evidence tied to the
specific session. Editing a shared file does not establish delivery or adoption.
Keep old dispatch snapshots; advance the revision for changed requirements.
Reconcile stale results and affected work before acceptance. A one-shot worker
may only receive corrections on return; documents cannot stop its active writes.
Separate user decisions, observed facts, and assumptions; revisit original
sources instead of repeatedly compressing old summaries into new authority.
Ask only about substantive intent/authority that available evidence cannot
resolve; preserve disputed material and continue independent authorized work.
These task records are normal fact maintenance, not a request for document
inventory, consolidation, archive, or deletion. No lossless memory is promised.

For machine checking, use the optional task.context contract and examples:
https://github.com/furenzhong/awoo-vibe-coding-governance/blob/main/docs/02_TECH/TASK_CONTEXT.md
https://github.com/furenzhong/awoo-vibe-coding-governance/tree/main/examples/context
Use the kit revision recorded in project-os.json when comparing versions.
Existing tasks remain valid without this extension; the report shows the gap.

## 当前约束 / Current constraints

- Not yet recorded. The project owner or agent must reconcile these rules with
  the existing project before treating adoption as operational validation.
""",
        "status": """# 当前项目状态 / Current project status

Governance files have been installed. The project's implementation and product
behavior have not been inspected or validated by this installer.

## 当前目标 / Current objective

- Not yet recorded.

## 已验证事实 / Verified state

- No implementation claims yet. Link each material completion claim to its
  revision, verification command, and evidence.

## 正在进行 / Active work

- Link to task records instead of maintaining a second task lifecycle here.
""",
        "handoff": """# 当前交接 / Current handoff

Link to the existing current task/checkpoint and any runbook needed to continue.
For an explicit conversation handoff, preserve unsaved decisions and corrections,
actual results, required access/operating knowledge, and unfinished operations.
Keep stable operating steps in their existing source; keep temporary state in
the task/checkpoint. Record credential locations only, never secrets. Distinguish
saved information, reviewed sufficiency, and actual resumption tests; list gaps.
No extra task or document is required for discussion, and handoff is not cleanup.

## 接续位置 / Resume point

- Reconcile the current project state with code and existing documentation.

## 下一步 / Next useful action

- Record the immediate objective and the smallest check that demonstrates it.

## 中断的工作 / Interrupted work

- No execution sessions have been recorded by this installer. Before resuming
  an interrupted delegated task, inspect its executor, worktree, and session.
  Silence or a timeout does not establish that its previous writer has stopped.
  Link each active task's coordinator/executor checkpoint and current context
  revision here; do not copy their lifecycle or let all actors overwrite a
  shared summary. Reconcile pending corrections and actual runtime on recovery.
""",
        "decisions": """# 项目决策 / Project decisions

Record consequential decisions with their reason, scope, assumptions, and the
condition that would reopen them. Link to the affected contract or source.
Routine edits do not require a decision entry.

No project-specific decisions have been recorded by this installer.
""",
    }
    return documents[key].encode("utf-8")


def entry_block(data: dict[str, Any], claude: bool = False) -> bytes:
    if claude:
        body = "@AGENTS.md"
    else:
        lines = ["Project governance index: `project-os.json`."]
        lines.extend(f"- {key}: `{data['sources'][key]}`" for key in SOURCE_KEYS)
        lines.extend([
            f"- Task state: `{data['tasks_dir']}`; evidence: `{data['evidence_dir']}`.",
            "Read the relevant sources before substantial work. Preserve existing project rules.",
            "Installer checks are structural; project claims still require verification.",
        ])
        body = "\n".join(lines)
    return BEGIN + b"\n" + body.encode("utf-8") + b"\n" + END


def append_entry(original: bytes, block: bytes, name: str) -> bytes:
    if BEGIN in original or END in original:
        if original.count(BEGIN) != 1 or original.count(END) != 1:
            raise ProjectOSError(f"{name} has malformed or duplicate managed blocks; reconcile it manually.")
        actual = original.split(BEGIN, 1)[1].split(END, 1)[0]
        expected = block.split(BEGIN, 1)[1].split(END, 1)[0]
        if actual.replace(b"\r\n", b"\n") != expected:
            raise ProjectOSError(f"{name} has a different managed block; existing content will not be overwritten.")
        return original
    separator = b"\r\n" if b"\r\n" in original else b"\n"
    suffix = block.replace(b"\n", separator) + separator
    return original + (separator * 2 if original else b"") + suffix


def build_plan(source: Path, target: Path, mapping_file: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source, target = source.resolve(), target.resolve()
    manifest_path = safe_path(target, MANIFEST)
    current = read_json(manifest_path) if manifest_path.exists() else None
    source_identity = install_identity(source, target, current)
    mapping = read_json(Path(mapping_file).expanduser().resolve()) if mapping_file else {}
    if set(mapping) - {"sources", "tasks_dir", "evidence_dir"}:
        raise ProjectOSError("Mapping accepts only sources, tasks_dir, and evidence_dir.")
    mapped_sources = mapping.get("sources", {})
    if not isinstance(mapped_sources, dict) or set(mapped_sources) - set(SOURCE_KEYS):
        raise ProjectOSError("Mapping sources accepts only rules, status, handoff, and decisions.")
    if current:
        manifest_shape(target, current)
        data = current
        for key, value in mapping.items():
            if key == "sources":
                if any(current["sources"][k] != v for k, v in value.items()):
                    raise ProjectOSError("Mapping differs from installed sources. Reconcile the manifest manually; no files changed.")
            elif current[key] != value:
                raise ProjectOSError("Mapping differs from the installed manifest; no files changed.")
    else:
        data = {
            "schema_version": SCHEMA_VERSION, "kit_version": VERSION, "role": "project",
            "sources": {**DEFAULT_SOURCES, **mapped_sources},
            "tasks_dir": mapping.get("tasks_dir", "project-os/tasks"),
            "evidence_dir": mapping.get("evidence_dir", "project-os/evidence"),
            "source_identity": source_identity,
        }
        manifest_shape(target, data)
    operations: list[dict[str, Any]] = []

    def add_file(relative: str, content: bytes | None, purpose: str, adopt: bool = False) -> None:
        path = safe_path(target, relative)
        if path.exists() and not path.is_file():
            raise ProjectOSError(f"Expected a file, found another path type: {relative}")
        for parent in path.parents:
            if parent == target:
                break
            if parent.exists() and not parent.is_dir():
                raise ProjectOSError(f"A parent directory is occupied by a file: {relative}")
        before = path.read_bytes() if path.exists() else None
        if before is not None and adopt:
            after, action = before, "reuse"
        elif before is not None and before != content:
            raise ProjectOSError(f"Path conflict: {relative}. Use --mapping to adopt existing governance documents or choose unused paths; files are never overwritten.")
        else:
            after, action = content, "reuse" if before is not None else "create"
        operations.append({"path": relative, "action": action, "purpose": purpose, "before": before, "after": after})

    for key, relative in data["sources"].items():
        existing = safe_path(target, relative).exists()
        if current and not existing:
            raise ProjectOSError(f"Installed source is missing: {relative}. Restore it explicitly; apply will not recreate user documents.")
        if key == "rules" and safe_path(target, relative) == target / "AGENTS.md":
            continue  # The single entry operation below preserves and indexes it.
        add_file(relative, default_document(key), key, adopt=bool(current) or key in mapped_sources)
    for key in ("tasks_dir", "evidence_dir"):
        relative = data[key]
        path = safe_path(target, relative)
        if path.exists() and not path.is_dir():
            raise ProjectOSError(f"Directory conflicts with an existing file: {relative}")
        for parent in path.parents:
            if parent == target:
                break
            if parent.exists() and not parent.is_dir():
                raise ProjectOSError(f"A parent directory is occupied by a file: {relative}")
        operations.append({"path": relative, "action": "reuse" if path.exists() else "mkdir", "purpose": key, "directory": True})
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = safe_path(target, name)
        if path.exists() and not path.is_file():
            raise ProjectOSError(f"Expected a file: {name}")
        before = path.read_bytes() if path.exists() else b""
        initial = before
        if name == "AGENTS.md" and not path.exists() and safe_path(target, data["sources"]["rules"]) == path:
            initial = default_document("rules")
        after = append_entry(initial, entry_block(data, name == "CLAUDE.md"), name)
        if path.exists() and path.stat().st_nlink > 1 and before != after:
            raise ProjectOSError(f"Cannot append to hardlinked agent entry: {name}")
        operations.append({"path": name, "action": "reuse" if before == after else ("append" if path.exists() else "create"), "purpose": "agent entry", "before": before if path.exists() else None, "after": after})
    add_file("scripts/project_os.py", Path(__file__).read_bytes(), "offline checker", adopt=bool(current))
    if not current:
        # Inert tools only. Native hooks require a separate explicit setup plan.
        for name in ("project_os_context.py", "project_os_context_hooks.py"):
            asset = Path(__file__).with_name(name)
            if asset.is_file():
                add_file("scripts/" + name, asset.read_bytes(), "optional context tool")
        guide = Path(__file__).resolve().parent.parent / "docs/02_TECH/CONTEXT_CAPTURE.md"
        if guide.is_file():
            add_file("project-os/CONTEXT_CAPTURE.md", guide.read_bytes(), "optional context guide")
    add_file(MANIFEST, json_bytes(data), "governance mapping", adopt=bool(current))
    if not current:
        adopted = {
            "schema_version": 1, "kind": "governance-adoption", "source": source_identity,
            "source_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "files": [
                {"path": op["path"], "purpose": op["purpose"], "action": op["action"],
                 "origin": "reused-project" if op["action"] == "reuse" else
                           "entry-appended" if op["action"] == "append" else "kit-created",
                 "adopted": upgrade_image(op["after"])}
                for op in operations if not op.get("directory")
            ],
            "limits": "Actual installation bytes, not proof that reused project rules came from the kit or that semantics were validated.",
        }
        add_file(ADOPTION, json_bytes(adopted), "immutable adoption evidence")
    report = {
        "command": "plan", "ok": True, "target": str(target), "kit_version": VERSION,
        "operations": [{k: v for k, v in op.items() if k not in {"before", "after", "directory"}} for op in operations],
        "changes": sum(op["action"] != "reuse" for op in operations),
        "limits": LIMITS,
        "notes": ["Existing project files and Git metadata are preserved.", "Adopted documents require semantic review; installation does not verify their contents."],
    }
    if current and current["kit_version"] != VERSION:
        report["notes"].append("An older installed version was retained. Automatic content migration is not supported; review an explicit upgrade diff.")
    if current and not safe_path(target, ADOPTION).exists():
        report["notes"].append("Original adoption baseline is unknown; apply does not fabricate it. Use an explicit upgrade plan to record the next actual adoption.")
    tool_path = safe_path(target, "scripts/project_os.py")
    if current and tool_path.is_file() and tool_path.read_bytes() != Path(__file__).read_bytes():
        report["notes"].append("Installed scripts/project_os.py differs from this kit and was retained. Apply is adoption, not an upgrade; reconcile the tool with an explicit reviewed diff.")
    return report, operations


def apply_plan(target: Path, operations: list[dict[str, Any]]) -> None:
    target = target.resolve()
    # Recheck the whole write set before starting. This protects against ordinary
    # concurrent edits; it is not a filesystem transaction or a hostile-race lock.
    for op in operations:
        path = safe_path(target, op["path"])
        if op.get("directory"):
            if path.exists() and not path.is_dir():
                raise ProjectOSError(f"Target directory changed after planning: {op['path']}; retry plan.")
        else:
            before = path.read_bytes() if path.exists() else None
            if before != op["before"]:
                raise ProjectOSError(f"Target changed after planning: {op['path']}; retry plan.")
    for op in operations:
        if op["action"] == "reuse":
            continue
        path = safe_path(target, op["path"])
        if op.get("directory"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if op["action"] == "create":
                with path.open("xb") as stream:
                    stream.write(op["after"])
            else:
                # Append only the governed suffix; do not rewrite original bytes.
                with path.open("ab") as stream:
                    stream.write(op["after"][len(op["before"]):])


UPGRADE_LIMITS = (
    "Explicit candidates require semantic review. Missing original adoption remains unknown. "
    "The journal retains exact content and declared provenance, not authenticated intent. "
    "Checks and atomic file replacement are not a cross-file transaction or protection from "
    "arbitrary external concurrent writers. Coordinate affected writers. No cleanup, network, "
    "agent control, automatic version promotion, Git reset or business commands are performed."
)
UPGRADE_LOCK = ".project-os-upgrade.lock"


def upgrade_image(raw: bytes | None) -> dict[str, str] | None:
    if raw is None:
        return None
    return {"content_b64": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest()}


def upgrade_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"content_b64", "sha256"}:
        raise ProjectOSError("Invalid content image in upgrade record.")
    try:
        raw = base64.b64decode(value["content_b64"], validate=True)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ProjectOSError("Invalid base64 content in upgrade record.") from exc
    if hashlib.sha256(raw).hexdigest() != value["sha256"]:
        raise ProjectOSError("Upgrade content digest does not match retained bytes.")
    return raw


def upgrade_regular(path: Path, missing: bool = True) -> bytes | None:
    # lstat all existing ancestors: Python 3.10 has no Path.is_junction().
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProjectOSError(f"Upgrade paths must not contain links or reparse points: {part.name}")
    if not path.exists():
        if missing:
            return None
        raise ProjectOSError(f"Required upgrade input is missing: {path}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
        raise ProjectOSError(f"Upgrade requires a regular, non-hardlinked file: {path.name}")
    return path.read_bytes()


def upgrade_path(target: Path, relative: Any) -> Path:
    path = safe_path(target, relative)
    if path == target / ADOPTION or path == target / UPGRADE_LOCK:
        raise ProjectOSError("Adoption evidence and the upgrade lock are not upgrade components.")
    upgrade_regular(path)
    return path


def upgrade_identity(target: Path) -> dict[str, Any]:
    info = identity(target)
    return {"root": str(target.resolve()), "git_root": str(info["git_root"]) if info["git_root"] else None,
            "git_common_dir": str(info["common_dir"]) if info["common_dir"] else None,
            "origin": info["origin"]}


def upgrade_external(target: Path, value: str | Path, exists: bool = False) -> Path:
    # Check before resolve so links cannot disappear through canonicalization.
    path = Path(os.path.abspath(Path(value).expanduser()))
    upgrade_regular(path, missing=not exists)
    path = path.resolve()
    if path.is_relative_to(target):
        raise ProjectOSError("Upgrade plans and journals must stay outside the target project.")
    return path


def upgrade_digest(data: dict[str, Any]) -> str:
    payload = {k: v for k, v in data.items() if k != "sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def upgrade_atomic(path: Path, raw: bytes, expected: bytes | None) -> None:
    if upgrade_regular(path) != expected:
        raise ProjectOSError(f"File changed before write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if expected is not None else None
    fd, temporary = tempfile.mkstemp(prefix=".project-os-write-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        if upgrade_regular(path) != expected:
            raise ProjectOSError(f"File changed during write preparation: {path}")
        if expected is None:
            # Link an already flushed file into a previously absent name. Unlike
            # replace(), this cannot overwrite a concurrent creator.
            os.link(temp, path)
        else:
            os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def upgrade_save(path: Path, data: dict[str, Any], expected: bytes | None) -> bytes:
    raw = json_bytes(data)
    upgrade_atomic(path, raw, expected)
    return raw


def build_upgrade_plan(source: Path, target: Path, proposal_file: str, output: str) -> dict[str, Any]:
    source, target = source.resolve(), target.resolve()
    proposal_path = Path(os.path.abspath(Path(proposal_file).expanduser()))
    upgrade_regular(proposal_path, missing=False)
    proposal = read_json(proposal_path)
    out = upgrade_external(target, output)
    if out.exists():
        raise ProjectOSError("Upgrade plan output already exists; choose a new file.")
    current_path = safe_path(target, MANIFEST)
    current = read_json(current_path) if current_path.exists() else None
    provenance = install_identity(source, target, current)
    provenance["tool_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if proposal.get("schema_version") != 1 or set(proposal) != {"schema_version", "components"}:
        raise ProjectOSError("Proposal requires schema_version=1 and components.")
    components = proposal["components"]
    if not isinstance(components, list) or not components:
        raise ProjectOSError("Proposal components must be a nonempty list.")
    ops, inputs, seen = [], {str(proposal_path.resolve())}, []
    allowed = {"component", "path", "reason", "candidate", "base", "upstream", "mode", "merge_reason"}
    for item in components:
        if not isinstance(item, dict) or set(item) - allowed:
            raise ProjectOSError("Unknown proposal component fields.")
        for key in ("component", "path", "reason", "candidate"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ProjectOSError(f"Each proposal component requires {key}.")
        path = upgrade_path(target, item["path"])
        relative = path.relative_to(target).as_posix()
        folded = relative.casefold()
        if any(folded == old or folded.startswith(old + "/") or old.startswith(folded + "/") for old in seen):
            raise ProjectOSError("Duplicate or overlapping upgrade component paths.")
        seen.append(folded)
        before = upgrade_regular(path)

        def material(key: str) -> bytes:
            name = item.get(key)
            if not isinstance(name, str) or not name.strip():
                raise ProjectOSError(f"Invalid {key} input path.")
            candidate = Path(name).expanduser()
            if not candidate.is_absolute():
                candidate = proposal_path.parent / candidate
            candidate = Path(os.path.abspath(candidate))
            raw = upgrade_regular(candidate, missing=False)
            inputs.add(str(candidate.resolve()))
            return raw  # type: ignore[return-value]

        after = material("candidate")
        have_base = "base" in item
        if have_base != ("upstream" in item):
            raise ProjectOSError("base and upstream must be supplied together.")
        base = material("base") if have_base else None
        upstream = material("upstream") if have_base else None
        mode = item.get("mode", "candidate" if have_base else "current_only")
        if not isinstance(mode, str) or mode not in ({"candidate", "merged"} if have_base else {"current_only"}):
            raise ProjectOSError("Unknown comparison mode for available baseline.")
        conflict = have_base and before != base and upstream != base and before != upstream
        merge_reason = item.get("merge_reason", "")
        if not isinstance(merge_reason, str):
            raise ProjectOSError("merge_reason must be a string.")
        if (conflict or mode == "merged") and (mode != "merged" or not merge_reason.strip()):
            raise ProjectOSError(f"Local and upstream changes require an explicit merged candidate and merge_reason: {relative}")
        try:
            diff = "".join(difflib.unified_diff((before or b"").decode("utf-8").splitlines(keepends=True),
                                               after.decode("utf-8").splitlines(keepends=True),
                                               fromfile="before/" + relative, tofile="after/" + relative))
        except UnicodeDecodeError:
            diff = "Non-UTF-8 content; compare retained bytes and hashes."
        ops.append({"component": item["component"], "path": relative, "reason": item["reason"],
                    "mode": mode, "old_baseline_unknown": not have_base, "merge_reason": merge_reason,
                    "before": upgrade_image(before), "after": upgrade_image(after),
                    "base": upgrade_image(base), "upstream": upgrade_image(upstream), "diff": diff})
    if str(out) in inputs:
        raise ProjectOSError("Plan output conflicts with an input file.")
    plan = {"schema_version": 1, "kind": "governance-upgrade-plan", "target": upgrade_identity(target),
            "observed_head": git(target, "rev-parse", "HEAD"), "source": provenance,
            "created_at": datetime.now().astimezone().isoformat(), "inputs": sorted(inputs),
            "operations": ops, "limits": UPGRADE_LIMITS}
    plan["sha256"] = upgrade_digest(plan)
    upgrade_save(out, plan, None)
    return {"command": "upgrade-plan", "ok": True, "plan": str(out),
            "changes": sum(op["before"] != op["after"] for op in ops),
            "operations": [{"path": op["path"], "action": op["mode"]} for op in ops], "limits": UPGRADE_LIMITS}


def validate_upgrade_plan(target: Path, plan: dict[str, Any], *, recovery: bool = False) -> list[dict[str, Any]]:
    target = target.resolve()
    if plan.get("schema_version") != 1 or plan.get("kind") != "governance-upgrade-plan":
        raise ProjectOSError("Unsupported upgrade plan.")
    if plan.get("sha256") != upgrade_digest(plan):
        raise ProjectOSError("Plan changed or is incomplete; regenerate it rather than editing retained content.")
    if plan.get("target") != upgrade_identity(target):
        raise ProjectOSError("Upgrade target identity differs from the planned project.")
    ops = plan.get("operations")
    if not isinstance(ops, list) or not ops:
        raise ProjectOSError("Upgrade plan has no operations.")
    paths = []
    for op in ops:
        if not isinstance(op, dict):
            raise ProjectOSError("Invalid upgrade operation.")
        path = safe_path(target, op.get("path"), inspect_filesystem=False) if recovery else upgrade_path(target, op.get("path"))
        if path in {target / ADOPTION, target / UPGRADE_LOCK}:
            raise ProjectOSError("Reserved upgrade component path.")
        folded = path.relative_to(target).as_posix().casefold()
        if any(folded == p or folded.startswith(p + "/") or p.startswith(folded + "/") for p in paths):
            raise ProjectOSError("Duplicate or overlapping upgrade paths.")
        paths.append(folded)
        upgrade_bytes(op.get("before"))
        if upgrade_bytes(op.get("after")) is None:
            raise ProjectOSError("Upgrade plans do not delete components.")
        upgrade_bytes(op.get("base"))
        upgrade_bytes(op.get("upstream"))
    return ops


def upgrade_lock(target: Path) -> Path:
    path = safe_path(target, UPGRADE_LOCK)
    try:
        with path.open("xb") as stream:
            stream.write(json_bytes({"pid": os.getpid(), "created_at": datetime.now().astimezone().isoformat()}))
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ProjectOSError("An upgrade lock exists. Inspect its owner and journal before removing a stale lock; do not assume the previous writer stopped.") from exc
    return path


def apply_upgrade(target: Path, plan_file: str, journal_file: str) -> dict[str, Any]:
    target = target.resolve()
    plan_path = upgrade_external(target, plan_file, exists=True)
    plan = read_json(plan_path)
    ops = validate_upgrade_plan(target, plan)
    journal_path = upgrade_external(target, journal_file)
    if journal_path.exists() or str(journal_path) in {str(plan_path), *plan.get("inputs", [])}:
        raise ProjectOSError("Journal must be a new path distinct from plan and input files.")
    lock = upgrade_lock(target)
    try:
        for op in ops:
            if upgrade_regular(upgrade_path(target, op["path"])) != upgrade_bytes(op["before"]):
                raise ProjectOSError(f"Target changed after planning: {op['path']}; replan affected changes.")
        journal = {"schema_version": 1, "kind": "governance-upgrade-journal", "plan": plan,
                   "status": "applying", "entries": [{"path": op["path"], "state": "pending"} for op in ops]}
        saved = upgrade_save(journal_path, journal, None)
        for op, entry in zip(ops, journal["entries"]):
            try:
                path = upgrade_path(target, op["path"])
                before, after = upgrade_bytes(op["before"]), upgrade_bytes(op["after"])
                if upgrade_regular(path) != before:
                    raise ProjectOSError(f"Target changed before component write: {op['path']}")
                if before == after:
                    entry["state"] = "unchanged"
                    saved = upgrade_save(journal_path, journal, saved)
                    continue
                entry["state"] = "intent"
                saved = upgrade_save(journal_path, journal, saved)
                upgrade_atomic(path, after, before)  # type: ignore[arg-type]
                entry["state"] = "applied"
                saved = upgrade_save(journal_path, journal, saved)
            except (OSError, ProjectOSError) as exc:
                # On a journal write failure the durable intent still contains
                # both byte images. Recovery must inspect actual content.
                entry["error"] = str(exc)
                journal["status"] = "partial_failure"
                try:
                    saved = upgrade_save(journal_path, journal, saved)
                except (OSError, ProjectOSError):
                    pass
                return {"command": "upgrade-apply", "ok": False, "journal": str(journal_path),
                        "applied": [e["path"] for e in journal["entries"] if e["state"] == "applied"],
                        "errors": [{"path": op["path"], "message": str(exc)}], "limits": UPGRADE_LIMITS}
        journal["status"] = "applied"
        upgrade_save(journal_path, journal, saved)
        return {"command": "upgrade-apply", "ok": True, "journal": str(journal_path),
                "applied": [e["path"] for e in journal["entries"] if e["state"] == "applied"], "limits": UPGRADE_LIMITS}
    finally:
        lock.unlink(missing_ok=True)


def rollback_upgrade(target: Path, journal_file: str) -> dict[str, Any]:
    target = target.resolve()
    journal_path = upgrade_external(target, journal_file, exists=True)
    saved = upgrade_regular(journal_path, missing=False)
    journal = read_json(journal_path)
    if journal.get("schema_version") != 1 or journal.get("kind") != "governance-upgrade-journal":
        raise ProjectOSError("Unsupported upgrade journal.")
    plan = journal.get("plan")
    if not isinstance(plan, dict):
        raise ProjectOSError("Journal is missing its self-contained plan.")
    ops = validate_upgrade_plan(target, plan, recovery=True)
    entries = journal.get("entries")
    if not isinstance(entries, list) or len(entries) != len(ops):
        raise ProjectOSError("Journal entries do not match the plan.")
    allowed = {"pending", "intent", "applied", "unchanged", "rollback_intent", "rolled_back", "conflict"}
    for op, entry in zip(ops, entries):
        if (not isinstance(entry, dict) or entry.get("path") != op["path"]
                or not isinstance(entry.get("state"), str) or entry["state"] not in allowed):
            raise ProjectOSError("Invalid journal entry; inspect retained evidence before recovery.")
    conflicts, restored = [], []
    lock = upgrade_lock(target)
    try:
        for op, entry in reversed(list(zip(ops, entries))):
            if entry["state"] in {"pending", "unchanged", "rolled_back"}:
                continue  # Never claim writes merely because someone made a plan.
            try:
                path = upgrade_path(target, op["path"])
                before, after = upgrade_bytes(op["before"]), upgrade_bytes(op["after"])
                actual = upgrade_regular(path)
                if actual == before:
                    entry["state"] = "rolled_back"
                elif actual == after:
                    entry["state"] = "rollback_intent"
                    saved = upgrade_save(journal_path, journal, saved)
                    if before is None:
                        if upgrade_regular(path) != after:
                            raise ProjectOSError("File changed before removal of this upgrade's new file.")
                        path.unlink()
                    else:
                        upgrade_atomic(path, before, after)
                    entry["state"] = "rolled_back"
                    restored.append(op["path"])
                else:
                    raise ProjectOSError("Later content differs; preserve it and review an inverse patch.")
                entry.pop("error", None)
            except (OSError, ProjectOSError) as exc:
                entry["state"] = "conflict"
                entry["error"] = str(exc)
                conflicts.append({"path": op["path"], "message": str(exc)})
            saved = upgrade_save(journal_path, journal, saved)
        journal["status"] = "rollback_conflicts" if conflicts else "rolled_back"
        upgrade_save(journal_path, journal, saved)
        return {"command": "upgrade-rollback", "ok": not conflicts, "journal": str(journal_path),
                "restored": restored, "errors": conflicts, "limits": UPGRADE_LIMITS}
    finally:
        lock.unlink(missing_ok=True)


def context_path(root: Path, relative: Any) -> Path:
    """Read context only inside the project, excluding links/reparse points on 3.10+."""
    if isinstance(relative, str) and "\x00" in relative:
        raise ProjectOSError("Context path contains invalid characters.")
    try:
        path = safe_path(root, relative)
    except ValueError as exc:
        raise ProjectOSError("Context path contains invalid characters.") from exc
    cursor = root.resolve()
    for part in path.relative_to(cursor).parts:
        cursor = cursor / part
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ProjectOSError(f"Context paths must not use links or reparse points: {relative}")
    if not path.is_file() or not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size == 0:
        raise ProjectOSError(f"Context/evidence must name an existing, nonempty regular file: {relative}")
    return path


def context_snapshot_sha256(path: Path) -> str:
    """Hash UTF-8 snapshot text with CRLF normalized to LF; keep all other bytes."""
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeError as exc:
        raise ProjectOSError("Context snapshot must contain UTF-8 text.") from exc
    if not content.strip():
        raise ProjectOSError("Context snapshot must contain nonempty text.")
    return hashlib.sha256(content.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def check_task_context(root: Path, task: dict[str, Any], relative: str) -> dict[str, Any]:
    """Validate opted-in context records, without running or contacting executors."""
    result: dict[str, Any] = {"tracked": "context" in task, "errors": [], "warnings": []}
    if not result["tracked"]:
        return result

    def issue(code: str, message: str, path: str = relative, warning: bool = False) -> None:
        result["warnings" if warning else "errors"].append({"code": code, "path": path, "message": message})

    def nonempty(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ProjectOSError(f"{label} must be a nonempty string.")
        return value

    def array(value: Any, label: str) -> list[Any]:
        if not isinstance(value, list):
            raise ProjectOSError(f"{label} must be an array.")
        return value

    def enum(value: Any, choices: set[str], label: str) -> str:
        value = nonempty(value, label)
        if value not in choices:
            raise ProjectOSError(f"Unknown {label}: {value}.")
        return value

    def evidence(value: Any, label: str, required: bool = False, forbidden: set[Path] | None = None) -> None:
        refs = array(value, label)
        if required and not refs:
            raise ProjectOSError(f"{label} requires nonempty evidence.")
        for ref in refs:
            path = context_path(root, ref)
            if forbidden and any(path == other or path.samefile(other) for other in forbidden):
                raise ProjectOSError(f"{label} must reference preserved evidence, not a mutable active checkpoint.")

    paths: set[Path] = set()

    def record_path(ref: Any) -> Path:
        path = context_path(root, ref)
        if any(path == other or path.samefile(other) for other in paths):
            raise ProjectOSError(f"Context record paths must identify unique files, including hardlink aliases: {ref}")
        paths.add(path)
        return path

    try:
        context = task["context"]
        if not isinstance(context, dict):
            raise ProjectOSError("Task context must be an object.")
        if type(context.get("schema_version")) is not int or context["schema_version"] != 1:
            raise ProjectOSError("Unsupported context.schema_version; expected integer 1.")
        current = nonempty(context.get("current_revision"), "context.current_revision")
        snapshots = array(context.get("snapshots"), "context.snapshots")
        checkpoint_refs = array(context.get("checkpoints"), "context.checkpoints")
        correction_refs = array(context.get("corrections"), "context.corrections")
        if not snapshots:
            raise ProjectOSError("context.snapshots must not be empty.")
    except ProjectOSError as exc:
        issue("context_schema", str(exc))
        return result

    revisions: dict[str, int] = {}
    for index, snapshot_record in enumerate(snapshots):
        try:
            if not isinstance(snapshot_record, dict):
                raise ProjectOSError("Each context snapshot must be an object.")
            rev = nonempty(snapshot_record.get("revision"), "Snapshot revision")
            if rev in revisions:
                raise ProjectOSError(f"Duplicate context revision: {rev}")
            revisions[rev] = index
            digest = snapshot_record.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise ProjectOSError("Snapshot sha256 must contain 64 hexadecimal characters.")
            path = record_path(snapshot_record.get("path"))
            if context_snapshot_sha256(path) != digest.lower():
                raise ProjectOSError(f"Context snapshot hash mismatch: {snapshot_record['path']}")
        except (ProjectOSError, OSError) as exc:
            issue("context_snapshot", str(exc))
    if revisions.get(current) != len(snapshots) - 1:
        issue("context_revision", "current_revision must identify the last snapshot in the ordered snapshots array.")

    checkpoints: dict[Path, dict[str, Any]] = {}
    checkpoint_paths: set[Path] = set()
    checkpoint_sessions: set[tuple[str, str]] = set()
    for ref in checkpoint_refs:
        try:
            path = record_path(ref)
            checkpoint_paths.add(path)
            checkpoint = read_json(path)
            if checkpoint.get("task_id") != task["id"]:
                raise ProjectOSError("Checkpoint task_id does not match its task.")
            for field in ("actor", "session_id", "context_revision", "last_action", "next_action"):
                nonempty(checkpoint.get(field), f"Checkpoint {field}")
            role = enum(checkpoint.get("role"), {"coordinator", "executor"}, "checkpoint role")
            key = (role, checkpoint["session_id"])
            if key in checkpoint_sessions:
                raise ProjectOSError("Only one active checkpoint per role/session_id is allowed.")
            checkpoint_sessions.add(key)
            observed = nonempty(checkpoint.get("observed_at"), "Checkpoint observed_at")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", observed):
                raise ProjectOSError("Checkpoint observed_at must be ISO 8601 with seconds and a timezone.")
            try:
                datetime.fromisoformat(observed.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ProjectOSError("Checkpoint observed_at is not a valid timestamp.") from exc
            rev = checkpoint["context_revision"]
            if rev not in revisions:
                raise ProjectOSError("Checkpoint refers to an unknown context revision.")
            for item in array(checkpoint.get("unresolved"), "Checkpoint unresolved"):
                nonempty(item, "Checkpoint unresolved item")
            operations = array(checkpoint.get("operations"), "Checkpoint operations")
            for operation in operations:
                if not isinstance(operation, dict):
                    raise ProjectOSError("Each checkpoint operation must be an object.")
                nonempty(operation.get("description"), "Operation description")
                nonempty(operation.get("locator"), "Operation locator")
                state = enum(operation.get("state"), {"running", "completed", "unknown"}, "operation state")
                if state in {"running", "unknown"}:
                    issue("context_operation", "Recorded operation may still be active; inspect its actual locator before resuming or redispatching. No process state was verified.", ref, True)
            evidence(checkpoint.get("evidence"), "Checkpoint evidence")
            checkpoints[path] = checkpoint
            if rev != current:
                issue("context_stale_checkpoint", "Checkpoint uses an older context revision; it does not cover the current execution state.", ref, True)
        except (ProjectOSError, OSError) as exc:
            issue("context_checkpoint", str(exc), str(ref))
    if task.get("status") == "running" and not any(
        cp["role"] == "executor" and cp["session_id"] == task.get("session_id") and cp["context_revision"] == current
        for cp in checkpoints.values()
    ):
        issue("context_missing_checkpoint", "Running task has no current executor checkpoint for its session; inspect the writer before redispatching.", warning=True)
    if task.get("status") in {"running", "submitted", "accepted"} and not any(
        cp["role"] == "coordinator" for cp in checkpoints.values()
    ):
        issue("context_missing_coordinator", "Task has no coordinator checkpoint; preserve the coordinator's review and continuation state. Presence does not identify the currently active coordinator.", warning=True)

    correction_ids: set[str] = set()
    covered_revisions: set[str] = set()
    for ref in correction_refs:
        try:
            correction = read_json(record_path(ref))
            if correction.get("task_id") != task["id"]:
                raise ProjectOSError("Correction task_id does not match its task.")
            for field in ("id", "from_revision", "to_revision", "reason", "impact", "target_session_id"):
                nonempty(correction.get(field), f"Correction {field}")
            if correction["id"] in correction_ids:
                raise ProjectOSError("Correction id must be unique within the task.")
            correction_ids.add(correction["id"])
            enum(correction.get("cause"), {"handoff_omission", "execution_deviation", "requirement_change", "acceptance_gap"}, "correction cause")
            before, after = correction["from_revision"], correction["to_revision"]
            if before not in revisions or after not in revisions or revisions[before] >= revisions[after]:
                raise ProjectOSError("Correction revisions must be known and ordered from an earlier to a later snapshot.")
            delivery = enum(correction.get("delivery"), {"recorded", "delivered", "adopted"}, "correction delivery")
            evidence(correction.get("delivery_evidence"), "Correction delivery_evidence", delivery in {"delivered", "adopted"})
            evidence(correction.get("adoption_evidence"), "Correction adoption_evidence", delivery == "adopted", checkpoint_paths)
            covered_revisions.add(after)
            if delivery != "adopted":
                current_session = correction["target_session_id"] == task.get("session_id")
                issue("context_pending_correction", "Correction adoption is not recorded for its target session; changing a file does not deliver or apply it.", ref,
                      warning=not (current_session and task.get("status") == "accepted"))
        except (ProjectOSError, OSError) as exc:
            issue("context_correction", str(exc), str(ref))
    for rev, index in revisions.items():
        if index and rev not in covered_revisions:
            issue("context_missing_correction", f"Later snapshot {rev} requires a correction record describing its change.")

    receipt_ref = task.get("receipt")
    if not receipt_ref and task.get("status") in {"submitted", "accepted"}:
        issue("context_receipt", "Submitted or accepted context task requires a receipt with its revision and executor checkpoint.")
    if receipt_ref:
        try:
            receipt = read_json(context_path(root, receipt_ref))
            receipt_rev = nonempty(receipt.get("context_revision"), "Receipt context_revision")
            if receipt_rev not in revisions:
                raise ProjectOSError("Receipt refers to an unknown context revision.")
            receipt_checkpoint = context_path(root, receipt.get("checkpoint"))
            checkpoint = checkpoints.get(receipt_checkpoint)
            if checkpoint is None:
                raise ProjectOSError("Receipt checkpoint must name a valid active context.checkpoints entry.")
            session_id = nonempty(task.get("session_id"), "Task session_id for context receipt")
            if checkpoint["role"] != "executor" or checkpoint["session_id"] != session_id:
                raise ProjectOSError("Receipt checkpoint must belong to this task's current executor session.")
            if checkpoint["context_revision"] != receipt_rev:
                raise ProjectOSError("Receipt and checkpoint context revisions must match.")
            if receipt_rev != current:
                issue("context_stale_receipt", "Receipt was produced against an older context revision; inspect affected work before acceptance.", str(receipt_ref), task.get("status") != "accepted")
        except (ProjectOSError, OSError) as exc:
            issue("context_receipt", str(exc), str(receipt_ref))
    return result


def capture_report(root: Path) -> dict[str, Any]:
    """Read optional capture evidence without loading payloads into the report."""
    config_path = safe_path(root, "project-os-context.json")
    store_path = safe_path(root, ".project-os-local/context")
    if not config_path.exists() and not store_path.exists():
        return {"state": "not_configured", "bindings": []}
    module_path = Path(__file__).with_name("project_os_context.py")
    if not module_path.is_file():
        return {"state": "tool_unavailable", "bindings": [], "limits": "Optional capture tool is not installed; no coverage was checked."}
    spec = importlib.util.spec_from_file_location("_awoo_context_capture", module_path)
    module = importlib.util.module_from_spec(spec)
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_bytecode
    try:
        result = module.context_status(root)
        config = read_json(config_path) if config_path.exists() else {}
        if config and (config.get("schema_version") != 1 or type(config.get("enabled")) is not bool):
            raise ProjectOSError("Invalid optional context capture configuration.")
        result["enabled"] = config.get("enabled", False)
        result["adapters"] = config.get("adapters", {})
        if result["state"] == "not_configured" and config:
            result["state"] = "configured_unverified"
        return result
    except module.ContextError as exc:
        raise ProjectOSError(str(exc)) from None


def check_project(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def issue(code: str, message: str, path: str = "", warning: bool = False) -> None:
        (warnings if warning else errors).append({"code": code, "path": path, "message": message})

    report: dict[str, Any] = {"command": "check", "ok": False, "target": str(root), "errors": errors, "warnings": warnings, "harness": {"tasks": 0, "accepted": 0, "state": "not_exercised"}, "context": {"tracked": 0, "legacy": 0, "state": "not_exercised"}, "limits": LIMITS}
    try:
        data = read_json(safe_path(root, MANIFEST))
        manifest_shape(root, data)
    except ProjectOSError as exc:
        issue("manifest", str(exc), MANIFEST)
        return report
    report["role"] = data["role"]
    report["kit_version"] = data["kit_version"]
    if data["kit_version"] != VERSION:
        issue("version", f"Installed manifest is {data['kit_version']}; checker is {VERSION}. No migration was performed.", MANIFEST, True)
    info = identity(root)
    if data["role"] == "project":
        src = data.get("source_identity", {})
        if not isinstance(src, dict):
            issue("identity", "source_identity must be an object.", MANIFEST)
            src = {}
        same_origin = info["origin"] and info["origin"] in KIT_ORIGINS | {src.get("origin")}
        same_common = fingerprint(info["common_dir"]) and fingerprint(info["common_dir"]) == src.get("common_dir_fingerprint")
        if same_origin or same_common:
            issue("identity", "Project manifest is installed in a repository identifying as its starter kit.", MANIFEST)
    if not info["git_root"]:
        issue("git_unavailable", "No Git working tree was found; revision evidence cannot be verified.", warning=True)
    for key, relative in data["sources"].items():
        path = safe_path(root, relative)
        if not path.is_file():
            issue("missing_source", f"Missing {key} source.", relative)
    try:
        if not safe_path(root, "scripts/project_os.py").is_file():
            issue("missing_checker", "Offline project checker is missing.", "scripts/project_os.py")
    except ProjectOSError as exc:
        issue("checker", str(exc), "scripts/project_os.py")
    for name in ("AGENTS.md", "CLAUDE.md"):
        try:
            path = safe_path(root, name)
            if not path.is_file():
                if data["role"] == "project" or name == "AGENTS.md":
                    issue("missing_entry", "Agent entry is missing.", name)
                continue
            content = path.read_bytes()
            if len(content) > 24_000:
                issue("large_entry", "Entry exceeds 24 KB; move detailed material behind focused links.", name, True)
            if data["role"] == "project":
                if BEGIN not in content:
                    issue("entry_index", "Managed governance index is missing.", name)
                else:
                    append_entry(content, entry_block(data, name == "CLAUDE.md"), name)
        except (ProjectOSError, OSError) as exc:
            issue("entry_index", str(exc), name)
    task_dir = safe_path(root, data["tasks_dir"])
    evidence_dir = safe_path(root, data["evidence_dir"])
    for path in (task_dir, evidence_dir):
        if not path.is_dir():
            issue("missing_directory", "Governance directory is missing.", path.relative_to(root).as_posix())
    task_files = sorted(task_dir.glob("*.json")) if task_dir.is_dir() else []
    report["harness"]["tasks"] = len(task_files)

    def evidence_file(relative: Any, label: str) -> bool:
        try:
            path = safe_path(root, relative)
            if not path.is_file() or path.stat().st_size == 0:
                raise ProjectOSError("Evidence must name an existing, nonempty file.")
        except (ProjectOSError, OSError) as exc:
            issue("evidence", f"{label}: {exc}", str(relative))
            return False
        return True

    def revision(value: Any, label: str, relative: str) -> str | None:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value):
            issue("revision", f"{label} must be a full commit ID, not a moving branch name.", relative)
            return None
        resolved = git(root, "rev-parse", "--verify", f"{value}^{{commit}}")
        if not resolved:
            issue("revision", f"{label} is not a locally available Git commit.", relative)
        return resolved

    seen: set[str] = set()
    for task_path in task_files:
        relative = task_path.relative_to(root).as_posix()
        try:
            safe_path(root, relative)
            task = read_json(task_path)
            for field in ("id", "objective", "base_revision", "status"):
                if not isinstance(task.get(field), str) or not task[field].strip():
                    raise ProjectOSError(f"Task requires nonempty {field}.")
            if task["id"] in seen:
                raise ProjectOSError(f"Duplicate task id: {task['id']}")
            seen.add(task["id"])
            if task["status"] not in TASK_STATUSES:
                raise ProjectOSError("Unknown task status.")
            context_report = check_task_context(root, task, relative)
            report["context"]["tracked" if context_report["tracked"] else "legacy"] += 1
            errors.extend(context_report["errors"])
            warnings.extend(context_report["warnings"])
            for field in ("writable_paths", "acceptance_commands"):
                if not isinstance(task.get(field), list) or not task[field] or not all(isinstance(x, str) and x.strip() for x in task[field]):
                    raise ProjectOSError(f"Task requires a nonempty {field} list.")
            scopes = [safe_path(root, value) for value in task["writable_paths"]]
            base = revision(task["base_revision"], "Task base_revision", relative)
            if task["status"] == "running":
                for field in ("executor", "worktree", "session_id"):
                    if not isinstance(task.get(field), str) or not task[field].strip():
                        issue("resume_locator", f"Running task lacks {field}; inspect the existing writer before reassigning it.", relative, True)
            if task["status"] == "accepted":
                report["harness"]["accepted"] += 1
            receipt_ref = task.get("receipt")
            if not receipt_ref:
                if task["status"] in {"submitted", "accepted"}:
                    raise ProjectOSError("Submitted or accepted task requires a receipt path.")
                continue
            receipt_path = context_path(root, receipt_ref) if "context" in task else safe_path(root, receipt_ref)
            receipt = read_json(receipt_path)
            if receipt.get("task_id") != task["id"]:
                raise ProjectOSError("Receipt task_id does not match the task.")
            receipt_base = revision(receipt.get("base_revision"), "Receipt base_revision", receipt_ref)
            result = revision(receipt.get("result_revision"), "Receipt result_revision", receipt_ref)
            if receipt_base != base or not isinstance(receipt.get("base_revision"), str) or receipt["base_revision"].lower() != task["base_revision"].lower():
                issue("receipt_baseline", "Receipt was produced for a different task baseline.", receipt_ref)
            if base and result and git(root, "merge-base", "--is-ancestor", base, result) is None:
                issue("receipt_ancestry", "Result revision is not a descendant of the task baseline.", receipt_ref)
            changed = receipt.get("changed_files")
            if not isinstance(changed, list) or not all(isinstance(x, str) for x in changed):
                raise ProjectOSError("Receipt requires changed_files as a list of project-relative paths.")
            for changed_file in changed:
                path = safe_path(root, changed_file)
                if not any(path == scope or path.is_relative_to(scope) for scope in scopes):
                    issue("write_scope", "Receipt declares a change outside writable_paths.", changed_file)
            if base and result:
                actual = git(root, "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames", base, result)
                if actual is None:
                    issue("receipt_diff_unavailable", "Git could not compare the base and result revisions; changed_files could not be verified.", receipt_ref)
                elif set(actual.splitlines()) != set(changed):
                    issue("receipt_diff", "changed_files does not match the committed diff between base and result.", receipt_ref)
            checks = receipt.get("checks")
            if not isinstance(checks, list) or not checks:
                raise ProjectOSError("Receipt requires a nonempty checks list.")
            declared_commands: set[str] = set()
            for check in checks:
                if not isinstance(check, dict) or not isinstance(check.get("command"), str) or not check["command"].strip():
                    raise ProjectOSError("Each receipt check requires command, exit_code, and evidence.")
                declared_commands.add(check["command"])
                if type(check.get("exit_code")) is not int:
                    raise ProjectOSError("Receipt check exit_code must be an integer.")
                if task["status"] == "accepted" and check["exit_code"] != 0:
                    issue("failed_check", "Accepted task declares a failed check.", receipt_ref)
                evidence_file(check.get("evidence"), "Check output")
            if not set(task["acceptance_commands"]).issubset(declared_commands):
                issue("missing_check", "Receipt does not include all acceptance_commands.", receipt_ref)
            evidence = receipt.get("evidence")
            if not isinstance(evidence, list):
                raise ProjectOSError("Receipt requires an evidence list; use [] when checks contain all delivery evidence.")
            for reference in evidence:
                evidence_file(reference, "Delivery evidence")
            if task["status"] == "accepted":
                if not isinstance(receipt.get("verified_by"), str) or not receipt["verified_by"].strip():
                    issue("verification", "Accepted task requires verified_by; execution success alone is not acceptance.", receipt_ref)
                verification = receipt.get("verification_evidence")
                if not isinstance(verification, list) or not verification:
                    issue("verification", "Accepted task requires nonempty verification_evidence.", receipt_ref)
                else:
                    for reference in verification:
                        evidence_file(reference, "Acceptance verification")
        except (ProjectOSError, OSError) as exc:
            issue("task", str(exc), relative)
    if task_files:
        report["harness"]["state"] = "records_invalid" if errors else ("accepted_records_checked" if report["harness"]["accepted"] else "records_checked_no_acceptance")
    if report["context"]["tracked"]:
        report["context"]["state"] = "records_invalid" if any(item["code"].startswith("context_") for item in errors) else ("partially_covered" if report["context"]["legacy"] else "tracked_records_checked")
    elif report["context"]["legacy"]:
        report["context"]["state"] = "legacy_only"
    try:
        report["context_capture"] = capture_report(root)
    except (ProjectOSError, OSError) as exc:
        report["context_capture"] = {"state": "records_invalid"}
        issue("context_capture", str(exc), "project-os-context.json")
    report["ok"] = not errors
    return report


def snapshot(root: Path) -> dict[str, Any]:
    root = root.resolve()
    report = check_project(root)
    report["command"] = "snapshot"
    report["git"] = {"head": git(root, "rev-parse", "HEAD"), "branch": git(root, "branch", "--show-current"), "status": git(root, "status", "--porcelain=v1")}
    try:
        data = read_json(safe_path(root, MANIFEST))
        report["sources"] = {key: {"path": relative, "sha256": hashlib.sha256(safe_path(root, relative).read_bytes()).hexdigest() if safe_path(root, relative).is_file() else None} for key, relative in data["sources"].items()}
    except (ProjectOSError, OSError, KeyError, TypeError):
        pass
    return report


def inventory_metadata(text: str) -> tuple[dict[str, str], list[str]]:
    """Read only simple, top-level scalar keys in closed leading front matter.

    This deliberately is not a YAML parser. Body text, indented keys, fenced
    examples, collections, and multiline YAML values do not provide metadata.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return {}, []
    closing = next((i for i, line in enumerate(lines[1:], 1) if line.rstrip() == "---"), None)
    if closing is None:
        return {}, ["Leading front matter is not closed; no lifecycle metadata was used."]
    metadata: dict[str, str] = {}
    invalid: set[str] = set()
    messages: list[str] = []
    for line in lines[1:closing]:
        match = re.fullmatch(r"([a-z_]+):[ \t]*(.*)", line)
        if not match or match[1] not in INVENTORY_METADATA_KEYS:
            continue
        key, raw = match[1], match[2].strip()
        if key in metadata or key in invalid:
            metadata.pop(key, None)
            invalid.add(key)
            messages.append(f"Duplicate front-matter key {key}; its value was ignored.")
            continue
        if raw.startswith(('"', "'")):
            # Quoted scalars may contain #; a comment may follow the closing quote.
            quoted = re.fullmatch(r'''"([^"\\]*)"(?:\s+#.*)?|'([^']*)'(?:\s+#.*)?''', raw)
            value = next((part for part in quoted.groups() if part is not None), "") if quoted else None
        else:
            value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
            if value.startswith(("#", "[", "{", "|", ">", "&", "*", "!")):
                value = None
        if value is None:
            invalid.add(key)
            messages.append(f"Unsupported front-matter value for {key}; use a simple single-line scalar.")
        elif value:
            metadata[key] = value
    return metadata, messages


def inventory_link(path: Path) -> bool:
    """Exclude Windows reparse points too, including junctions on Python 3.10."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def inventory(root: Path) -> dict[str, Any]:
    """Report document lifecycle signals without moving, rewriting, or deleting files."""
    root = root.resolve()
    report: dict[str, Any] = {
        "command": "inventory", "ok": False, "target": str(root),
        "documents": [], "reading_entrypoints": [], "working_documents": [],
        "evidence_documents": [], "archive_documents": [], "unclassified": [],
        "duplicate_candidates": [], "warnings": [], "skipped_paths": [],
        "scope": {
            "extensions": sorted(INVENTORY_EXTENSIONS),
            "ignored_directory_names": sorted(INVENTORY_SKIP_DIRS),
            "archive_directory_prefixes": sorted(INVENTORY_ARCHIVE_PREFIXES),
            "metadata_keys": sorted(INVENTORY_METADATA_KEYS),
            "follows_links": False,
        },
        "limits": INVENTORY_LIMITS,
    }

    def warning(code: str, relative: str, message: str) -> None:
        report["warnings"].append({"code": code, "path": relative, "message": message})

    def skipped(path: Path, reason: str) -> None:
        report["skipped_paths"].append({"path": path.relative_to(root).as_posix(), "reason": reason})

    try:
        data = read_json(safe_path(root, MANIFEST))
        manifest_shape(root, data)
    except ProjectOSError as exc:
        warning("manifest", MANIFEST, str(exc))
        return report
    mapped_sources = {safe_path(root, value).relative_to(root).as_posix() for value in data["sources"].values()}
    entries = {"AGENTS.md", "CLAUDE.md"}
    expected_entrypoints = mapped_sources | entries
    evidence_dir = safe_path(root, data["evidence_dir"])
    by_hash: dict[str, list[str]] = {}

    def walk_error(error: OSError) -> None:
        path = Path(error.filename) if error.filename else root
        skipped(path, "unreadable_directory")
        warning("unreadable", path.relative_to(root).as_posix(), str(error))

    for directory, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        retained = []
        for name in sorted(dirs):
            path = parent / name
            try:
                if inventory_link(path):
                    skipped(path, "link_or_reparse_point")
                elif name.casefold() in INVENTORY_SKIP_DIRS:
                    skipped(path, "ignored_directory")
                else:
                    retained.append(name)
            except OSError as exc:
                skipped(path, "unreadable_directory")
                warning("unreadable", path.relative_to(root).as_posix(), str(exc))
        dirs[:] = retained  # Prune before traversal, including directory junctions.
        for name in sorted(files):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            try:
                if inventory_link(path):
                    skipped(path, "link_or_reparse_point")
                    continue
                if path.suffix.lower() not in INVENTORY_EXTENSIONS and relative not in expected_entrypoints:
                    continue
                if not stat.S_ISREG(path.lstat().st_mode):
                    skipped(path, "not_regular_file")
                    continue
                content = path.read_bytes()
            except OSError as exc:
                skipped(path, "unreadable_file")
                warning("unreadable", relative, str(exc))
                continue
            metadata, messages = inventory_metadata(content.decode("utf-8-sig", errors="replace"))
            for message in messages:
                warning("metadata", relative, message)
            lifecycle = metadata.get("lifecycle", "").lower() or None
            if lifecycle and lifecycle not in INVENTORY_RETIRED | {"active", "working", "candidate"}:
                warning("unknown_lifecycle", relative, f"Unknown lifecycle value: {lifecycle}.")
            in_archive = any(relative.casefold().startswith(prefix + "/") for prefix in INVENTORY_ARCHIVE_PREFIXES)
            retired = lifecycle in INVENTORY_RETIRED
            if relative in mapped_sources:
                category = "mapped_source"
            elif relative in entries:
                category = "entry"
            elif in_archive or retired:
                category = "archive"
            elif path.is_relative_to(evidence_dir):
                category = "evidence"
            elif lifecycle in {"working", "candidate"}:
                category = "working"
            else:
                category = "unclassified"
            digest = hashlib.sha256(content).hexdigest()
            report["documents"].append({
                "path": relative, "bytes": len(content), "sha256": digest,
                "category": category, "lifecycle": lifecycle, "metadata": metadata,
                "in_archive_directory": in_archive,
            })
            by_hash.setdefault(digest, []).append(relative)
            collection = {
                "mapped_source": "reading_entrypoints", "entry": "reading_entrypoints",
                "archive": "archive_documents", "evidence": "evidence_documents",
                "working": "working_documents", "unclassified": "unclassified",
            }[category]
            report[collection].append(relative)
            if relative in expected_entrypoints and (retired or in_archive):
                warning("retired_reading_entrypoint", relative, "A declared reading entrypoint is marked retired or located in an archive. Reconcile the mapping and replacement before changing it.")
            # Archive directory guides describe the container, not a retired decision.
            archive_guide = path.name.casefold() in {"readme.md", "readme.markdown", "readme.txt", "readme.rst"}
            if (in_archive or retired) and not (archive_guide and not retired):
                if not lifecycle:
                    warning("archive_without_lifecycle", relative, "Archive material has no explicit lifecycle in leading front matter.")
                elif not retired:
                    warning("archive_lifecycle_conflict", relative, "Archive path conflicts with its declared lifecycle.")
                if not metadata.get("archived_reason"):
                    warning("archive_without_reason", relative, "Archive material should state archived_reason in leading front matter.")
            if len(content) > 24_000 and relative in entries:
                warning("large_entry", relative, "Entry is large; keep durable rules short and link detail behind focused sources.")
    scanned = {item["path"] for item in report["documents"]}
    for relative in sorted(mapped_sources - scanned):
        warning("unscanned_source", relative, "Mapped source was missing or outside the readable scan scope; inspect it explicitly.")
    report["duplicate_candidates"] = sorted(sorted(group) for group in by_hash.values() if len(group) > 1)
    report["documents"].sort(key=lambda item: item["path"])
    for key in ("reading_entrypoints", "working_documents", "evidence_documents", "archive_documents", "unclassified"):
        report[key].sort()
    report["skipped_paths"].sort(key=lambda item: item["path"])
    report["ok"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "check", "snapshot", "inventory", "upgrade-plan", "upgrade-apply", "upgrade-rollback"))
    parser.add_argument("--target", required=True, help="Existing project root; never a destination to clone or overwrite.")
    parser.add_argument("--mapping", help="JSON file relative to the current working directory. Its sources/tasks_dir/evidence_dir paths are relative to --target; existing mapped documents are adopted.")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable report.")
    parser.add_argument("--proposal", help="Explicit component candidates for upgrade-plan.")
    parser.add_argument("--out", help="New self-contained plan outside the target.")
    parser.add_argument("--plan", help="Existing self-contained upgrade plan.")
    parser.add_argument("--journal", help="External adoption/rollback journal; new for upgrade-apply.")
    args = parser.parse_args(argv)
    try:
        target = target_root(args.target)
        if args.mapping and args.command not in {"plan", "apply"}:
            raise ProjectOSError("--mapping is only valid for plan and apply.")
        permitted = {"upgrade-plan": {"proposal", "out"}, "upgrade-apply": {"plan", "journal"}, "upgrade-rollback": {"journal"}}
        supplied = {key for key in ("proposal", "out", "plan", "journal") if getattr(args, key)}
        if supplied != permitted.get(args.command, set()):
            raise ProjectOSError("Upgrade command arguments are missing or not applicable to this command.")
        if args.command == "upgrade-plan":
            report = build_upgrade_plan(Path(__file__).resolve().parents[1], target, args.proposal, args.out)
        elif args.command == "upgrade-apply":
            report = apply_upgrade(target, args.plan, args.journal)
        elif args.command == "upgrade-rollback":
            report = rollback_upgrade(target, args.journal)
        elif args.command in {"plan", "apply"}:
            source = Path(__file__).resolve().parents[1]
            report, operations = build_plan(source, target, args.mapping)
            if args.command == "apply":
                apply_plan(target, operations)
                report["command"] = "apply"
        else:
            report = check_project(target) if args.command == "check" else snapshot(target) if args.command == "snapshot" else inventory(target)
    except (ProjectOSError, OSError) as exc:
        report = {"command": args.command, "ok": False, "errors": [{"code": "preflight", "message": str(exc)}], "limits": LIMITS}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        qualifier = "explicit candidate and file-state checks" if args.command.startswith("upgrade-") else "read-only document signals" if args.command == "inventory" else "structural checks only"
        print(f"{args.command}: {'PASS' if report['ok'] else 'FAIL'} ({qualifier})")
        if args.command == "inventory" and "documents" in report:
            print(f"Documents: {len(report['documents'])}; reading entrypoints: {len(report['reading_entrypoints'])}; working: {len(report['working_documents'])}; evidence: {len(report['evidence_documents'])}; archive: {len(report['archive_documents'])}; unclassified: {len(report['unclassified'])}")
            print(f"Exact duplicate groups: {len(report['duplicate_candidates'])}; skipped paths: {len(report['skipped_paths'])}. Use --json for paths, metadata, and scan scope.")
        if "changes" in report:
            print(f"Planned changes: {report['changes']}")
        for key in ("plan", "journal"):
            if key in report:
                print(f"{key}: {report[key]}")
        for key in ("applied", "restored"):
            for path in report.get(key, []):
                print(f"  {key}: {path}")
        for operation in report.get("operations", []):
            print(f"  {operation['action']}: {operation['path']}")
        for note in report.get("notes", []):
            print(f"  note: {note}")
        for kind in ("errors", "warnings"):
            for item in report.get(kind, []):
                print(f"  {kind[:-1]}: {item.get('path', '')} {item['message']}")
        if "harness" in report:
            print(f"Harness: {report['harness']['state']}")
            print(f"Context: {report['context']['state']}; tracked={report['context']['tracked']}; legacy={report['context']['legacy']}")
        print(report.get("limits", LIMITS))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

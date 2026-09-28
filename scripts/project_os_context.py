#!/usr/bin/env python3
"""Offline, private context evidence. No model calls, transcript scans or cleanup.

MIT License; copyright (c) 2026 furenzhong. Distributed under the repository's
MIT license. Python 3.10+ and the standard library are sufficient.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

SCHEMA_VERSION = 1
STORE = ".project-os-local/context"
MAX_INPUT = 1_048_576
KINDS = {"user_input", "pre_compact", "post_compact", "dispatch", "result", "handoff", "resume", "session_start"}
POLICIES = {"metadata_only", "redacted", "private_original"}
LIMITS = (
    "Evidence records observations and declared reconciliation, not semantic correctness, "
    "execution completion, delivery or adoption. Source coverage is unknown without explicit "
    "continuity evidence. Redaction is heuristic. Private records are never automatically cleaned."
)


class ContextError(Exception):
    """A controlled error whose message contains no captured payload."""


def controlled(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ContextError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
            raise ContextError("Context operation failed schema validation or private storage access; existing evidence was preserved.") from exc
    return call


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def packed(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ContextError("Input is not supported JSON data.") from exc


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                timeout=10, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def inspect_path(path: Path, file: bool = False, required: bool = True) -> None:
    for parent in [*reversed(path.parents), path]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ContextError("Context paths cannot traverse symbolic links or reparse points.")
        if parent != path and not stat.S_ISDIR(info.st_mode):
            raise ContextError("A context path parent is not a directory.")
    if not path.exists():
        if required:
            raise ContextError("Required context path is missing.")
        return
    info = path.stat()
    if file and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise ContextError("Context inputs must be regular files without hard links.")


def relative_path(root: Path, value: Any, required: bool = True) -> Path:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ContextError("A relative file path is required.")
    win = PureWindowsPath(value)
    parts = PurePosixPath(value.replace("\\", "/")).parts
    if win.drive or win.is_absolute() or value.startswith("/") or not parts:
        raise ContextError("Absolute paths are not allowed in context references.")
    for part in parts:
        if part.casefold() in {"..", ".git"} or ":" in part or part.endswith((" ", ".")):
            raise ContextError("Unsafe relative context path.")
        if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part):
            raise ContextError("Reserved filesystem names are not valid references.")
    path = root.joinpath(*parts)
    inspect_path(path, file=True, required=required)
    if not path.resolve().is_relative_to(root):
        raise ContextError("Context reference escapes the workspace.")
    return path


def project_root(value: str | Path) -> Path:
    path = Path(os.path.abspath(Path(value).expanduser()))
    inspect_path(path)
    if not path.is_dir():
        raise ContextError("Target must be an existing workspace directory.")
    path = path.resolve()
    top = git(path, "rev-parse", "--show-toplevel")
    if top and Path(top).resolve() != path:
        raise ContextError("Target must be the Git workspace root.")
    return path


def project_identity(root: Path) -> dict[str, Any]:
    common = git(root, "rev-parse", "--git-common-dir")
    return {"workspace": str(root), "git_common_dir": str((root / common).resolve()) if common else None}


def private_store(root: Path, create: bool = False) -> Path:
    path = root / STORE
    inspect_path(path, required=False)
    if path.exists() and not path.is_dir():
        raise ContextError("Private context storage must be a directory.")
    probe = STORE + "/privacy-probe.json"
    if git(root, "check-ignore", "--no-index", "--", probe) is None:
        raise ContextError("Private context storage must be Git-ignored before binding; configure .project-os-local/ during setup.")
    tracked = git(root, "ls-files", "--", ".project-os-local")
    if tracked:
        raise ContextError("Private context storage has tracked files; resolve privacy configuration before capturing.")
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        inspect_path(path)
    return path


def read_record(path: Path) -> dict[str, Any]:
    inspect_path(path, file=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContextError("A stored context record is invalid JSON.") from exc
    if not isinstance(data, dict):
        raise ContextError("A context record must be a JSON object.")
    return data


def atomic_record(path: Path, data: dict[str, Any]) -> None:
    inspect_path(path, file=True, required=False)
    if path.exists():
        raise ContextError("Immutable context record already exists.")
    private_parent = next((parent for parent in path.parents if parent.name == ".project-os-local"), None)
    if private_parent is None or git(private_parent.parent, "check-ignore", "--no-index", "--", path.relative_to(private_parent.parent).as_posix()) is None:
        raise ContextError("The actual context record path is not Git-ignored; no record was saved.")
    raw = packed(data)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    inspect_path(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".context-write-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        inspect_path(path, file=True, required=False)
        if path.exists():
            raise ContextError("Context record appeared during write preparation.")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def writer_lock(store: Path):
    lock = store / ".writer.lock"
    inspect_path(lock, file=True, required=False)
    deadline = time.monotonic() + 1.0
    while True:
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ContextError("Context writer is busy or interrupted; inspect the lock owner before retrying or removing a stale lock.") from exc
            time.sleep(0.05)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(packed({"pid": os.getpid(), "created_at": now()}))
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        lock.unlink(missing_ok=True)


def identifier(value: Any, name: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
        raise ContextError(name + " must be a nonempty bounded string.")
    if redact(value)[1]:
        raise ContextError(name + " appears to contain sensitive material.")
    return value


def stored_id(value: Any, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(prefix + r"-[0-9a-f]{32}", value):
        raise ContextError("Invalid context record identifier.")
    return value


def records(folder: Path) -> list[dict[str, Any]]:
    inspect_path(folder, required=False)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise ContextError("Context record collection is not a directory.")
    return [read_record(path) for path in sorted(folder.glob("*.json"))]


def manifest(root: Path) -> dict[str, Any]:
    path = relative_path(root, "project-os.json", required=False)
    return read_record(path) if path.exists() else {}


def current_authority(root: Path, binding: dict[str, Any]) -> list[str]:
    mapping = manifest(root)
    sources = mapping.get("sources", {})
    if not isinstance(sources, dict):
        raise ContextError("Governance sources mapping is invalid.")
    refs = list(binding.get("topic_refs", []))
    for key in ("rules", "status", "handoff", "decisions"):
        if key in sources:
            refs.append(sources[key])
    return sorted({relative_path(root, ref).relative_to(root).as_posix() for ref in refs})


def checkpoint_paths(root: Path, binding: dict[str, Any]) -> list[str]:
    if binding.get("mode") != "execution":
        return []
    mapping = manifest(root)
    tasks_dir = mapping.get("tasks_dir")
    if not isinstance(tasks_dir, str):
        raise ContextError("Execution binding requires an existing tasks mapping.")
    task_id = binding.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", task_id):
        raise ContextError("Execution binding requires a valid task id.")
    path = relative_path(root, tasks_dir.rstrip("/") + "/" + task_id + ".json")
    task = read_record(path)
    if task.get("id") != task_id:
        raise ContextError("Execution task identity does not match the binding.")
    context = task.get("context", {})
    if not isinstance(context, dict) or not isinstance(context.get("checkpoints", []), list):
        raise ContextError("Task checkpoint mapping is invalid.")
    return [relative_path(root, ref).relative_to(root).as_posix() for ref in context.get("checkpoints", [])]


def snapshots(root: Path, binding: dict[str, Any]) -> list[dict[str, str]]:
    return [{"path": ref, "sha256": sha(relative_path(root, ref).read_bytes())}
            for ref in sorted(set(current_authority(root, binding) + checkpoint_paths(root, binding)))]


def load_binding(root: Path, store: Path, binding_id: str) -> dict[str, Any]:
    stored_id(binding_id, "binding")
    binding = read_record(store / "bindings" / (binding_id + ".json"))
    if binding.get("binding_id") != binding_id or binding.get("project") != project_identity(root):
        raise ContextError("Binding does not identify this workspace.")
    stored_id(binding.get("stream_id"), "stream")
    if binding.get("payload_policy") not in POLICIES:
        raise ContextError("Stored payload policy is invalid.")
    return binding


@controlled
def bind_context(target: str | Path, adapter: str, session_id: str, mode: str = "discussion",
                 topic_refs: list[str] | None = None, task_id: str | None = None,
                 payload_policy: str = "redacted", supersedes: str | None = None) -> dict[str, Any]:
    root = project_root(target)
    if not isinstance(adapter, str) or adapter not in {"claude", "codex", "generic"}:
        raise ContextError("Unsupported context adapter.")
    identifier(session_id, "session_id")
    if mode not in {"discussion", "execution"} or payload_policy not in POLICIES:
        raise ContextError("Invalid binding mode or payload policy.")
    if topic_refs is None:
        topic_refs = []
    if not isinstance(topic_refs, list):
        raise ContextError("topic_refs must be a list of existing relative paths.")
    topics = sorted({relative_path(root, ref).relative_to(root).as_posix() for ref in topic_refs})
    if mode == "discussion" and task_id is not None:
        raise ContextError("A discussion binding cannot invent or adopt an execution task.")
    binding = {"schema_version": 1, "project": project_identity(root), "adapter": adapter,
               "session_id": session_id, "mode": mode, "topic_refs": topics,
               "task_id": task_id, "payload_policy": payload_policy}
    checkpoint_paths(root, binding)
    current_authority(root, binding)
    store = private_store(root, create=True)
    with writer_lock(store):
        existing_bindings = records(store / "bindings")
        superseded = {item.get("previous_binding") for item in existing_bindings if item.get("previous_binding")}
        if supersedes is not None:
            old = load_binding(root, store, supersedes)
            if supersedes in superseded or old.get("adapter") != adapter or old.get("session_id") != session_id:
                raise ContextError("Only the active binding of this exact adapter/session/workspace can be superseded.")
        for existing in existing_bindings:
            if existing.get("adapter") == adapter and existing.get("session_id") == session_id:
                if existing.get("binding_id") in superseded:
                    continue
                if supersedes is not None:
                    if existing.get("binding_id") != supersedes:
                        raise ContextError("Superseded binding is not the current session binding.")
                    continue
                if any(existing.get(key) != value for key, value in binding.items()):
                    raise ContextError("This session already has a different binding; do not silently change its ownership or policy.")
                return {"ok": True, "binding_id": existing["binding_id"], "binding": existing, "deduplicated": True}
        binding.update(binding_id="binding-" + uuid.uuid4().hex, stream_id="stream-" + uuid.uuid4().hex,
                       created_at=now(), capabilities="unverified", previous_binding=supersedes)
        atomic_record(store / "bindings" / (binding["binding_id"] + ".json"), binding)
    return {"ok": True, "binding_id": binding["binding_id"], "binding": binding, "deduplicated": False}


SECRET_KEY = re.compile(r"(?i)(?:^|[_-])(?:password|passwd|secret|token|api[_-]?key|authorization|credential|private[_-]?key)(?:$|[_-])")
SECRET_TEXT = [
    re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r'''(?i)\b(?:[A-Za-z0-9]+[_-])*(?:password|passwd|token|secret|api[_-]?key|authorization)(?:[_-][A-Za-z0-9]+)*\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;"'}]+)'''),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)"),
    re.compile(r"(?i)(?:https?://)[^\s/@:]+:[^\s/@]+@[^\s]+"),
]


def redact(value: Any, depth: int = 0) -> tuple[Any, bool]:
    if depth > 30:
        raise ContextError("Context data nesting is too deep.")
    changed = False
    if isinstance(value, str):
        for pattern in SECRET_TEXT:
            value, count = pattern.subn("[REDACTED]", value)
            changed = changed or bool(count)
        return value, changed
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContextError("Context object keys must be strings.")
            clean_key, key_changed = redact(key, depth + 1)
            if SECRET_KEY.search(key):
                result[clean_key] = "[REDACTED]"
                changed = True
            else:
                result[clean_key], did_change = redact(item, depth + 1)
                changed = changed or did_change or key_changed
        return result, changed
    if isinstance(value, list):
        result = []
        for item in value:
            cleaned, did_change = redact(item, depth + 1)
            result.append(cleaned)
            changed = changed or did_change
        return result, changed
    if value is None or type(value) in {int, float, bool}:
        packed(value)
        return value, False
    raise ContextError("Unsupported context payload type.")


@controlled
def capture_event(target: str | Path, binding_id: str, data: dict[str, Any]) -> dict[str, Any]:
    root = project_root(target)
    store = private_store(root)
    binding = load_binding(root, store, binding_id)
    fields = {"kind", "native_event_id", "native_cursor", "source_sequence", "sequence_start", "source_complete", "payload", "text", "metadata"}
    if not isinstance(data, dict) or set(data) - fields:
        raise ContextError("Capture input contains unsupported fields.")
    if not isinstance(data.get("kind"), str) or data["kind"] not in KINDS:
        raise ContextError("Unsupported capture event kind.")
    normalized = {"kind": data["kind"], "native_event_id": data.get("native_event_id"),
                  "native_cursor": data.get("native_cursor"), "source_sequence": data.get("source_sequence"),
                  "sequence_start": data.get("sequence_start"), "source_complete": data.get("source_complete", False),
                  "payload": data.get("payload"), "text": data.get("text"), "metadata": data.get("metadata", {})}
    for key in ("native_event_id", "native_cursor"):
        identifier(normalized[key], key, nullable=True)
    for key in ("source_sequence", "sequence_start"):
        value = normalized[key]
        if value is not None and (type(value) is not int or value < 0 or value > 2**53):
            raise ContextError(key + " must be a nonnegative integer or null.")
    if type(normalized["source_complete"]) is not bool or not isinstance(normalized["metadata"], dict):
        raise ContextError("Invalid source_complete or metadata type.")
    if normalized["text"] is not None and not isinstance(normalized["text"], str):
        raise ContextError("Capture text must be a string or null.")
    raw = packed(normalized)
    if len(raw) > MAX_INPUT:
        raise ContextError("Capture input exceeds the one-megabyte limit; no event was saved.")
    signature = sha(raw)
    clean, redacted = redact(normalized)
    policy = binding["payload_policy"]
    has_body = normalized["payload"] is not None or normalized["text"] is not None
    payload_state = ("redacted" if redacted else "original") if has_body else "unavailable"
    if policy == "metadata_only":
        clean["payload"], clean["text"] = None, None
        payload_state = "omitted_by_policy"
    elif policy == "redacted" and len(packed({"text": clean["text"], "payload": clean["payload"]})) > 32768:
        clean["text"] = (clean["text"] or "")[:12000] or None
        clean["payload"] = None
        payload_state = "truncated_redacted" if redacted else "truncated"
    with writer_lock(store):
        folder = store / "sessions" / binding["stream_id"] / "events"
        events = records(folder)
        native = normalized["native_event_id"]
        if native is not None:
            for event in events:
                if event.get("native_event_id") == native:
                    if event.get("input_sha256") != signature:
                        raise ContextError("Native event identity was reused with different content; existing evidence was preserved.")
                    return {"ok": True, "capture_id": event["capture_id"], "event_path": str((folder / (event["capture_id"] + ".json")).relative_to(root)), "deduplicated": True}
        capture_id = "capture-" + uuid.uuid4().hex
        event = {"schema_version": 1, "binding_id": binding_id, "stream_id": binding["stream_id"],
                 "capture_id": capture_id, "received_at": now(), "receive_sequence": len(events) + 1,
                 "input_sha256": signature, "payload_policy": policy, "payload_state": payload_state,
                 "original_payload_sha256": sha(packed({"payload": normalized["payload"], "text": normalized["text"]})) if has_body else None,
                 "stored_payload_sha256": sha(packed({"payload": clean["payload"], "text": clean["text"]})) if clean["payload"] is not None or clean["text"] is not None else None,
                 "redaction_applied": redacted, "body_available": clean["payload"] is not None or clean["text"] is not None,
                 "source_refs": snapshots(root, binding), **clean}
        path = folder / (capture_id + ".json")
        atomic_record(path, event)
    return {"ok": True, "capture_id": capture_id, "event_path": path.relative_to(root).as_posix(),
            "deduplicated": False, "payload_state": payload_state}


def hash_value(value: Any, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContextError("A lowercase SHA-256 value is required.")
    return value


@controlled
def reconcile_context(target: str | Path, binding_id: str, data: dict[str, Any]) -> dict[str, Any]:
    root = project_root(target)
    store = private_store(root)
    binding = load_binding(root, store, binding_id)
    allowed = {"event_ids", "outcome", "reason", "source_refs", "writes", "checkpoint_ref", "next_action", "unresolved"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ContextError("Reconciliation contains unsupported fields.")
    outcome = data.get("outcome")
    if not isinstance(outcome, str) or outcome not in {"changed", "no_change", "unresolved"}:
        raise ContextError("Invalid reconciliation outcome.")
    for key in ("reason", "next_action"):
        if not isinstance(data.get(key), str) or not data[key].strip() or len(data[key]) > 8000:
            raise ContextError(key + " must contain a bounded explanation.")
    event_ids, source_refs, writes, unresolved = (data.get(key, []) for key in ("event_ids", "source_refs", "writes", "unresolved"))
    if any(not isinstance(value, list) for value in (event_ids, source_refs, writes, unresolved)):
        raise ContextError("Reconciliation event/source/write/unresolved fields must be arrays.")
    if not event_ids or not source_refs or any(not isinstance(item, str) or not item.strip() for item in unresolved):
        raise ContextError("Reconciliation needs event ids, actual source references and valid unresolved items.")
    if len(set(stored_id(item, "capture") for item in event_ids)) != len(event_ids):
        raise ContextError("Duplicate reconciliation event ids.")
    if outcome == "unresolved" and not unresolved:
        raise ContextError("Unresolved reconciliation requires an explicit unresolved reason.")
    if outcome != "unresolved" and unresolved:
        raise ContextError("Outstanding issues require outcome unresolved.")
    if outcome == "no_change" and writes:
        raise ContextError("no_change cannot declare document writes.")
    with writer_lock(store):
        session = store / "sessions" / binding["stream_id"]
        events = {event["capture_id"]: event for event in records(session / "events")}
        if any(event_id not in events for event_id in event_ids):
            raise ContextError("Reconciliation refers to events outside this binding.")
        allowed_paths = set(current_authority(root, binding) + checkpoint_paths(root, binding))
        observed = {(ref["path"], ref["sha256"]) for event_id in event_ids for ref in events[event_id].get("source_refs", [])}
        checked_writes = {}
        for write in writes:
            if not isinstance(write, dict) or set(write) != {"path", "before_sha256", "after_sha256"}:
                raise ContextError("Each write needs path, before_sha256 and after_sha256.")
            path = relative_path(root, write["path"])
            rel = path.relative_to(root).as_posix()
            before, after = hash_value(write["before_sha256"]), hash_value(write["after_sha256"])
            if rel not in allowed_paths or rel in checked_writes:
                raise ContextError("Write is outside bound authority or duplicated.")
            if (rel, before) not in observed or sha(path.read_bytes()) != after:
                raise ContextError("Write evidence does not match captured source and current content; no reconciliation was saved.")
            checked_writes[rel] = write
        checked_refs = []
        verified_current = {rel: write["after_sha256"] for rel, write in checked_writes.items()}
        for ref in source_refs:
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
                raise ContextError("Each source reference needs path and sha256.")
            path = relative_path(root, ref["path"])
            rel, digest = path.relative_to(root).as_posix(), hash_value(ref["sha256"])
            current = sha(path.read_bytes())
            historic_write = checked_writes.get(rel)
            if digest != current and not (historic_write and digest == historic_write["before_sha256"] and (rel, digest) in observed):
                raise ContextError("Source reference is stale; reread current authority before reconciling.")
            checked_refs.append({"path": rel, "sha256": digest})
            verified_current[rel] = current
        checkpoint = data.get("checkpoint_ref")
        if checkpoint is not None:
            checkpoint = relative_path(root, checkpoint).relative_to(root).as_posix()
            if checkpoint not in checkpoint_paths(root, binding):
                raise ContextError("Checkpoint is not an existing checkpoint of the bound task.")
            verified_current[checkpoint] = sha(relative_path(root, checkpoint).read_bytes())
        if outcome == "changed" and not checked_writes and checkpoint is None and not any(ref["path"] in allowed_paths for ref in checked_refs):
            raise ContextError("changed needs verified writes or an existing authority/checkpoint reference.")
        receipt, redacted = redact({"schema_version": 1, "binding_id": binding_id, "event_ids": event_ids,
                                   "outcome": outcome, "reason": data["reason"], "source_refs": checked_refs,
                                   "writes": list(checked_writes.values()), "checkpoint_ref": checkpoint,
                                   "next_action": data["next_action"], "unresolved": unresolved})
        receipt.update(reconciliation_id="reconciliation-" + uuid.uuid4().hex, received_at=now(),
                       receive_sequence=len(records(session / "reconciliations")) + 1,
                       redaction_applied=redacted, adopted=False)
        for rel, digest in verified_current.items():
            if sha(relative_path(root, rel).read_bytes()) != digest:
                raise ContextError("Referenced content changed during reconciliation; reread affected sources.")
        atomic_record(session / "reconciliations" / (receipt["reconciliation_id"] + ".json"), receipt)
    return {"ok": True, "reconciliation_id": receipt["reconciliation_id"], "outcome": outcome, "adopted": False}


def coverage_for(store: Path, binding: dict[str, Any]) -> dict[str, Any]:
    root = store.parents[1]
    session = store / "sessions" / binding["stream_id"]
    events = sorted(records(session / "events"), key=lambda event: event["receive_sequence"])
    receipts = sorted(records(session / "reconciliations"), key=lambda receipt: receipt["receive_sequence"])
    latest = {}
    for receipt in receipts:
        for event_id in receipt.get("event_ids", []):
            latest[event_id] = receipt
    stale_receipts = set()
    changed_sources = set()
    active_receipts = {receipt["reconciliation_id"] for receipt in latest.values()}
    for receipt in receipts:
        if receipt["reconciliation_id"] not in active_receipts:
            continue
        written = {item["path"]: item["after_sha256"] for item in receipt.get("writes", [])}
        for ref in receipt.get("source_refs", []):
            try:
                actual = sha(relative_path(root, ref["path"]).read_bytes())
            except (ContextError, OSError):
                actual = None
            if actual != written.get(ref["path"], ref["sha256"]):
                stale_receipts.add(receipt["reconciliation_id"])
                changed_sources.add(ref["path"])
    observed = [event["capture_id"] for event in events]
    reconciled = [eid for eid in observed if eid in latest and latest[eid]["outcome"] in {"changed", "no_change"}
                  and latest[eid]["reconciliation_id"] not in stale_receipts]
    unresolved = [eid for eid in observed if eid in latest and latest[eid]["outcome"] == "unresolved"]
    pending = [eid for eid in observed if eid not in reconciled]
    starts = {event["sequence_start"] for event in events if event.get("source_complete") and event.get("sequence_start") is not None}
    complete_positions = [event["source_sequence"] for event in events if event.get("source_complete") and event.get("source_sequence") is not None]
    through, missing, ambiguous, unknown = None, [], [], []
    positions: dict[int, list[str]] = {}
    for event in events:
        if event.get("source_sequence") is not None:
            positions.setdefault(event["source_sequence"], []).append(event["capture_id"])
    if len(starts) == 1 and complete_positions:
        start, end = next(iter(starts)), max(complete_positions)
        if end < start or end - start > 100000:
            unknown.append("Declared source interval is invalid or exceeds the bounded coverage scan.")
        else:
            for sequence in range(start, end + 1):
                ids = positions.get(sequence, [])
                if not ids:
                    missing.append(sequence)
                elif len(ids) != 1:
                    ambiguous.append(sequence)
            for sequence in range(start, end + 1):
                ids = positions.get(sequence, [])
                if len(ids) != 1 or ids[0] not in reconciled:
                    break
                through = sequence
            unknown.append("Continuity applies only to the explicitly declared source interval; earlier and later history is unknown.")
    else:
        unknown.append("No unambiguous explicit source start and completeness evidence; receive order is not source order.")
    if any(event.get("source_sequence") is None for event in events):
        unknown.append("Some observed events have no source sequence and remain outside any source watermark.")
    compaction_gaps = []
    post_cycles = {event.get("metadata", {}).get("compaction_id") for event in events
                   if event["kind"] == "post_compact" and isinstance(event.get("metadata", {}).get("compaction_id"), str)}
    for event in events:
        metadata = event.get("metadata", {})
        signals_compaction = event["kind"] == "pre_compact" or (
            event["kind"] in {"session_start", "resume"} and metadata.get("source", metadata.get("start_source")) == "compact")
        if signals_compaction:
            cycle = metadata.get("compaction_id")
            if not isinstance(cycle, str) or cycle not in post_cycles:
                compaction_gaps.append({"capture_id": event["capture_id"], "state": "pending_or_unknown",
                                        "reason": "Matching post-compaction capture is not durably observed; hook receive order alone cannot close this gap."})
        if event["kind"] == "post_compact" and not event.get("body_available"):
            compaction_gaps.append({"capture_id": event["capture_id"], "state": "body_unavailable",
                                    "reason": "Post-compaction event is saved; readable native summary was not saved."})
    unknown.append("Unobserved asynchronous events and executor adoption are unknown.")
    if changed_sources:
        unknown.append("Sources changed after reconciliation; prior classification does not settle their current meaning.")
    return {"observed_capture_ids": observed, "reconciled_capture_ids": reconciled,
            "pending_capture_ids": pending, "unresolved_capture_ids": unresolved,
            "reconciled_through": through, "missing_source_sequences": missing[:1000],
            "missing_source_sequence_count": len(missing), "ambiguous_source_sequences": ambiguous[:1000],
            "unknown_ranges": unknown, "reconciliation_ids": [r["reconciliation_id"] for r in receipts],
            "changed_source_refs": sorted(changed_sources), "stale_reconciliation_ids": sorted(stale_receipts),
            "compaction_gaps": compaction_gaps,
            "observed_kinds": sorted({e["kind"] for e in events}), "semantic_correctness": "unverified"}


@controlled
def context_status(target: str | Path, binding_id: str | None = None) -> dict[str, Any]:
    root = project_root(target)
    raw_store = root / STORE
    inspect_path(raw_store, required=False)
    if not raw_store.exists():
        if binding_id:
            raise ContextError("Requested binding has not been configured.")
        return {"ok": True, "state": "not_configured", "bindings": [], "limits": LIMITS}
    store = private_store(root)
    all_bindings = records(store / "bindings")
    successors = {item["previous_binding"]: item["binding_id"] for item in all_bindings if item.get("previous_binding")}
    bindings = [load_binding(root, store, binding_id)] if binding_id else [
        load_binding(root, store, record.get("binding_id")) for record in all_bindings]
    result = []
    for binding in bindings:
        coverage = coverage_for(store, binding)
        result.append({"binding_id": binding["binding_id"], "adapter": binding["adapter"],
                       "session_id": binding["session_id"], "mode": binding["mode"],
                       "topic_refs": binding["topic_refs"], "task_id": binding["task_id"],
                       "payload_policy": binding["payload_policy"],
                       "active": binding["binding_id"] not in successors,
                       "binding_state": "superseded" if binding["binding_id"] in successors else "active",
                       "superseded_by": successors.get(binding["binding_id"]),
                       "previous_binding": binding.get("previous_binding"),
                       "state": "observed" if coverage["observed_capture_ids"] else "configured_unverified",
                       "coverage": coverage})
    report = {"ok": True, "state": "observed" if any(r["state"] == "observed" for r in result) else "configured_unverified",
              "bindings": result, "limits": LIMITS}
    if binding_id:
        report["binding_id"], report["coverage"] = binding_id, result[0]["coverage"]
    return report


@controlled
def resume_context(target: str | Path, binding_id: str) -> dict[str, Any]:
    root = project_root(target)
    store = private_store(root)
    binding = load_binding(root, store, binding_id)
    coverage = coverage_for(store, binding)
    for key, value in list(coverage.items()):
        if isinstance(value, list) and len(value) > 20:
            coverage[key + "_count"] = len(value)
            coverage[key] = value[-20:]
            coverage[key + "_truncated"] = True
    folder = store / "sessions" / binding["stream_id"] / "events"
    events = sorted(records(folder), key=lambda event: event["receive_sequence"])
    # Keep recent user words even when a model incorrectly marked them no_change.
    recent = [event for event in events if event["kind"] == "user_input"][-3:]
    inputs = []
    for event in recent:
        payload = event.get("text")
        if payload is None and event.get("payload") is not None:
            payload = json.dumps(event["payload"], ensure_ascii=False)
        inputs.append({"capture_id": event["capture_id"], "event_path": (folder / (event["capture_id"] + ".json")).relative_to(root).as_posix(),
                       "text": payload[:2000] if payload else None, "excerpt_truncated": bool(payload and len(payload) > 2000),
                       "payload_state": event["payload_state"]})
    previous_streams = []
    previous = binding.get("previous_binding")
    seen = {binding_id}
    while previous and len(previous_streams) < 5:
        if previous in seen:
            raise ContextError("Binding history contains a cycle.")
        seen.add(previous)
        old = load_binding(root, store, previous)
        old_coverage = coverage_for(store, old)
        previous_streams.append({"binding_id": previous, "mode": old["mode"],
                                 "pending_capture_count": len(old_coverage["pending_capture_ids"]),
                                 "pending_capture_ids": old_coverage["pending_capture_ids"][-10:],
                                 "unknown_ranges": old_coverage["unknown_ranges"],
                                 "compaction_gap_count": len(old_coverage["compaction_gaps"])})
        previous = old.get("previous_binding")
    return {"ok": True, "binding_id": binding_id, "mode": binding["mode"], "task_id": binding["task_id"],
            "previous_binding": binding.get("previous_binding"), "previous_streams": previous_streams,
            "previous_streams_truncated": bool(previous),
            "current_refs": snapshots(root, binding)[:20], "related_inputs": inputs,
            "coverage": coverage, "required_next_action": "Compare current authority, relevant original inputs and actual operations before dependent work. No record proves delivery or adoption.",
            "limits": LIMITS}


def input_json(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_INPUT:
        raise ContextError("Input exceeds the one-megabyte limit.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContextError("Input must be a valid JSON object.") from exc
    if not isinstance(data, dict):
        raise ContextError("Input must be a JSON object.")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bind", "capture", "reconcile", "status", "resume"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--adapter", choices=("claude", "codex", "generic"))
    parser.add_argument("--session-id")
    parser.add_argument("--mode", choices=("discussion", "execution"), default="discussion")
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--task-id")
    parser.add_argument("--payload-policy", choices=sorted(POLICIES), default="redacted")
    parser.add_argument("--binding")
    parser.add_argument("--supersedes")
    parser.add_argument("--input")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "bind":
            report = bind_context(args.target, args.adapter, args.session_id, args.mode, args.topic, args.task_id, args.payload_policy, args.supersedes)
        elif args.command == "capture":
            report = capture_event(args.target, args.binding, input_json(sys.stdin.buffer.read(MAX_INPUT + 1)))
        elif args.command == "reconcile":
            if not args.input:
                raise ContextError("reconcile requires --input.")
            path = Path(os.path.abspath(Path(args.input).expanduser()))
            inspect_path(path, file=True)
            with path.open("rb") as stream:
                data = input_json(stream.read(MAX_INPUT + 1))
            report = reconcile_context(args.target, args.binding, data)
        elif args.command == "status":
            report = context_status(args.target, args.binding)
        else:
            report = resume_context(args.target, args.binding)
    except ContextError as exc:
        report = {"ok": False, "error": str(exc), "limits": LIMITS}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        # Never emit exception repr: OS/JSON errors may embed captured text.
        report = {"ok": False, "error": "Context operation failed validation or private storage access; existing evidence was preserved.", "limits": LIMITS}
    report["command"] = args.command
    if args.json:
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    elif not report["ok"]:
        print(report["error"], file=sys.stderr)
    else:
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

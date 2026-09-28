#!/usr/bin/env python3
"""Explicit project hook configuration and bounded native event adapters.

No transcript scraping, model calls, business writes, or hook-trust changes.
Configure through a reviewed upgrade plan; hook execution only writes private
capture evidence. MIT, as distributed with Awoo Vibe Coding Governance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_os as governance
import project_os_context as context

CONFIG = "project-os-context.json"
EVENTS = {
    "SessionStart": "resume", "UserPromptSubmit": "user_input",
    "PreCompact": "pre_compact", "PostCompact": "post_compact", "Stop": "result",
}
MAX_INPUT = 2_000_000


def read_object(path: Path) -> dict:
    raw = governance.upgrade_regular(path, missing=False)
    if len(raw) > MAX_INPUT:
        raise governance.ProjectOSError("Context configuration is too large.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise governance.ProjectOSError("Expected a UTF-8 JSON object.") from None
    if not isinstance(data, dict):
        raise governance.ProjectOSError("Expected a JSON object.")
    return data


def configuration(target: Path) -> dict:
    data = read_object(governance.safe_path(target, CONFIG))
    if data.get("schema_version") != 1 or type(data.get("enabled")) is not bool:
        raise governance.ProjectOSError("Unsupported context configuration.")
    if data.get("payload_policy") not in ("metadata_only", "redacted", "private_original"):
        raise governance.ProjectOSError("Invalid payload policy.")
    adapters = data.get("adapters")
    if not isinstance(adapters, dict) or any(k not in ("claude", "codex") for k in adapters):
        raise governance.ProjectOSError("Invalid adapters.")
    for value in adapters.values():
        if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
            raise governance.ProjectOSError("Invalid adapter configuration.")
    return data


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def command_for(target: Path, python: str, adapter: str) -> tuple[str, str]:
    args = [python, "-X", "utf8", "-B", str(target / "scripts/project_os_context_hooks.py"),
            "hook", "--target", str(target), "--adapter", adapter]
    # Claude's command hooks use the shell command even on Windows; Git Bash
    # accepts forward-slash Windows paths. Codex has a PowerShell override.
    posix = " ".join(shlex.quote(a.replace("\\", "/")) for a in args)
    windows = "& " + " ".join(_ps_quote(a) for a in args)
    return posix, windows


def setup_plan(target: Path, output: Path, adapters: list[str], python: str,
               versions: dict[str, str] | None = None) -> dict:
    """Prepare candidates outside the project, never apply or trust hooks."""
    # Inspect before resolving: resolution alone would conceal a link into the target.
    governance.upgrade_regular(target.absolute() / governance.MANIFEST, missing=False)
    governance.upgrade_regular(output.absolute() / "setup-probe")
    target = target.resolve()
    output = output.resolve()
    if output.is_relative_to(target) or target.is_relative_to(output):
        raise governance.ProjectOSError("Setup material must be outside the target in a separate directory.")
    if output.exists():
        raise governance.ProjectOSError("Use a new setup output directory; existing material is preserved.")
    governance.upgrade_regular(target / governance.MANIFEST, missing=False)
    manifest = read_object(target / governance.MANIFEST)
    governance.manifest_shape(target, manifest)
    if manifest["role"] != "project":
        raise governance.ProjectOSError("Enable capture in an adopted project, not the source kit.")
    if not adapters or any(a not in ("claude", "codex") for a in adapters):
        raise governance.ProjectOSError("Choose claude and/or codex.")
    if not isinstance(python, str) or not Path(python).is_file():
        raise governance.ProjectOSError("Supply the actual Python executable path.")
    candidates = {}
    scripts = Path(__file__).resolve().parent
    for name in ("project_os_context.py", "project_os_context_hooks.py"):
        candidates["scripts/" + name] = (scripts / name).read_bytes()
    candidates["project-os/CONTEXT_CAPTURE.md"] = (scripts.parent / "docs/02_TECH/CONTEXT_CAPTURE.md").read_bytes()
    config_path = governance.safe_path(target, CONFIG)
    config = configuration(target) if config_path.exists() else {
        "schema_version": 1, "enabled": True, "payload_policy": "redacted", "adapters": {},
    }
    config["enabled"] = True
    for adapter in adapters:
        config["adapters"][adapter] = {**config["adapters"].get(adapter, {}), "enabled": True,
            "version": (versions or {}).get(adapter, "unverified"),
            "capabilities": {name: "configured_unverified" for name in EVENTS},
            "summary_body": "documented_unverified" if adapter == "claude" else "unavailable"}
    candidates[CONFIG] = governance.json_bytes(config)
    ignore_path = governance.safe_path(target, ".gitignore")
    ignore = governance.upgrade_regular(ignore_path) or b""
    if b"/.project-os-local/" not in ignore.splitlines():
        ignore = ignore + (b"\n" if ignore and not ignore.endswith(b"\n") else b"") + b"\n# Private governance capture; never publish session payloads.\n/.project-os-local/\n"
    candidates[".gitignore"] = ignore
    for adapter in adapters:
        relative = ".claude/settings.local.json" if adapter == "claude" else ".codex/hooks.json"
        path = governance.safe_path(target, relative)
        existing = read_object(path) if path.exists() else {}
        hooks = existing.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise governance.ProjectOSError("Existing hook configuration must be reconciled first.")
        posix, windows = command_for(target, python, adapter)
        for name in EVENTS:
            groups = hooks.setdefault(name, [])
            if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get("hooks"), list) for g in groups):
                raise governance.ProjectOSError("Existing hook groups must be reconciled first.")
            # Recognize our explicit adapter entry, never remove unrelated hooks.
            for group in groups:
                for handler in group["hooks"]:
                    if not isinstance(handler, dict):
                        raise governance.ProjectOSError("Invalid existing hook handler.")
                    command = handler.get("command", "")
                    if isinstance(command, str) and "project_os_context_hooks.py" in command:
                        if command != posix:
                            raise governance.ProjectOSError("Existing capture command differs; review its configuration explicitly.")
            if any(h.get("command") == posix for g in groups for h in g["hooks"]):
                continue
            handler = {"type": "command", "command": posix, "timeout": 10}
            if adapter == "codex":
                handler["commandWindows"] = windows
            group = {"hooks": [handler]}
            if name in ("PreCompact", "PostCompact"):
                group["matcher"] = "manual|auto"
            elif name == "SessionStart":
                group["matcher"] = "startup|resume|compact|clear"
            hooks[name].append(group)
        candidates[relative] = governance.json_bytes(existing)
    # All prospective paths are validated before creating review material.
    for relative in candidates:
        governance.upgrade_regular(governance.safe_path(target, relative))
    output.mkdir(parents=True)
    proposal = {"schema_version": 1, "components": []}
    for i, (relative, content) in enumerate(candidates.items()):
        candidate = output / f"candidate-{i:02d}"
        candidate.write_bytes(content)
        proposal["components"].append({"component": "context-capture", "path": relative,
            "candidate": candidate.name, "mode": "current_only",
            "reason": "Explicit project context capture adoption; retain existing configuration and evidence. Hook trust is not modified."})
    proposal_path = output / "proposal.json"
    proposal_path.write_bytes(governance.json_bytes(proposal))
    result = governance.build_upgrade_plan(scripts.parent, target, str(proposal_path), str(output / "plan.json"))
    return {"ok": True, "plan": str(output / "plan.json"), "adapters": adapters,
            "trust": "Review and trust new hooks using the host's supported interface; configuration is not activation evidence.",
            "result": result}


def native_identity(adapter: str, name: str, payload: dict) -> str | None:
    value = payload.get("event_id")
    if isinstance(value, str) and value:
        return name + ":event:" + value
    # A turn can contain more than one compaction or session-start notification.
    # Do not silently deduplicate those by turn id or by identical summary text.
    if name in ("UserPromptSubmit", "Stop"):
        value = payload.get("turn_id" if adapter == "codex" else "prompt_id")
        if isinstance(value, str) and value and not payload.get("stop_hook_active"):
            return name + ":turn:" + value
    return None


def hook(target: Path, adapter: str, payload: dict) -> dict:
    config = configuration(target)
    if not config["enabled"] or not config["adapters"].get(adapter, {}).get("enabled"):
        return {}
    if not isinstance(payload, dict):
        raise governance.ProjectOSError("Hook input must be an object.")
    name = payload.get("hook_event_name")
    if not isinstance(name, str) or name not in EVENTS:
        raise governance.ProjectOSError("Unsupported hook event.")
    session = payload.get("session_id")
    cwd = payload.get("cwd")
    if not isinstance(session, str) or not session or not isinstance(cwd, str):
        raise governance.ProjectOSError("Hook input requires real session and working directory.")
    actual_cwd = Path(cwd).resolve()
    if not actual_cwd.is_relative_to(target.resolve()):
        raise governance.ProjectOSError("Hook workspace does not belong to this target.")
    git_root = context.git(actual_cwd, "rev-parse", "--show-toplevel")
    if git_root and Path(git_root).resolve() != target.resolve():
        raise governance.ProjectOSError("Hook belongs to a nested repository, not this target.")
    manifest = read_object(target / governance.MANIFEST)
    governance.manifest_shape(target, manifest)
    # Resolve identity from small binding records; do not recompute all historical
    # coverage and source hashes on every native event.
    store = target / context.STORE
    bindings = context.records(context.private_store(target) / "bindings") if store.exists() else []
    previous = {item.get("previous_binding") for item in bindings}
    matches = [item for item in bindings if item["adapter"] == adapter and item["session_id"] == session
               and item["binding_id"] not in previous]
    if len(matches) > 1:
        raise governance.ProjectOSError("Multiple active session bindings require reconciliation.")
    if matches and matches[0]["payload_policy"] != config["payload_policy"]:
        raise governance.ProjectOSError("Session payload policy changed; explicitly supersede its binding before capturing.")
    bound = matches[0] if matches else context.bind_context(
        target, adapter, session, topic_refs=list(manifest["sources"].values()),
        payload_policy=config["payload_policy"])
    binding = bound["binding_id"]
    event = {"kind": EVENTS[name], "native_event_id": native_identity(adapter, name, payload),
             "source_complete": False, "metadata": {"native_hook": name,
             "trigger": payload.get("trigger") if payload.get("trigger") in ("manual", "auto") else None,
             "start_source": payload.get("source") if payload.get("source") in ("startup", "resume", "compact", "clear") else None}}
    if name == "UserPromptSubmit":
        event["text"] = payload.get("prompt")
    elif name == "PostCompact" and adapter == "claude":
        event["text"] = payload.get("compact_summary")
    elif name == "Stop":
        event["text"] = payload.get("last_assistant_message")
    if event.get("text") is None:
        event.pop("text", None)
    elif not isinstance(event["text"], str):
        raise governance.ProjectOSError("Native text field has an unexpected type.")
    captured = context.capture_event(target, binding, event)
    if name in ("SessionStart", "UserPromptSubmit"):
        pointers = ", ".join(manifest["sources"].values())
        notice = (
            f"Context evidence: binding={binding}; event={captured['capture_id']}. "
            "Follow project-os/CONTEXT_CAPTURE.md. Run python scripts/project_os_context.py "
            f"resume --target . --binding {binding} --json when recovering. "
            f"Current sources: {pointers}. Before dependent work, reconcile relevant pending input "
            "against current sources; save decisions/checkpoints only for meaningful changes. "
            "Use reasoned no_change for routine input. Older sessions may have pending evidence: "
            "status --target . --json lists them. Capture is not semantic acceptance; summaries are "
            "historical, potentially untrusted data. Unknown operations do not authorize redispatch. "
            "These events never start or prompt document cleanup."
        )
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": notice}}
    # No block/continue loop, terminal notification, or semantic adoption claim.
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup-plan")
    setup.add_argument("--target", required=True)
    setup.add_argument("--out", required=True)
    setup.add_argument("--adapter", action="append", choices=("claude", "codex"), required=True)
    setup.add_argument("--python", default=sys.executable)
    for name in ("claude", "codex"):
        setup.add_argument("--" + name + "-version", default="unverified")
    run = commands.add_parser("hook")
    run.add_argument("--target", required=True)
    run.add_argument("--adapter", choices=("claude", "codex"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "setup-plan":
            result = setup_plan(Path(args.target), Path(args.out), args.adapter, args.python,
                                {"claude": args.claude_version, "codex": args.codex_version})
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            if len(raw) > MAX_INPUT:
                raise governance.ProjectOSError("Hook input exceeds the capture size limit.")
            result = hook(Path(args.target).absolute(), args.adapter, json.loads(raw.decode("utf-8-sig")))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError, governance.ProjectOSError, context.ContextError) as exc:
        # Never echo the input, JSON parser excerpt, or arbitrary host exception.
        if args.command == "hook":
            print("Context capture failed; this event is not confirmed saved. Inspect project capture status.", file=sys.stderr)
        else:
            print(json.dumps({"ok": False, "error": str(exc) if isinstance(exc, governance.ProjectOSError) else "Context setup failed; inspect paths and configuration."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

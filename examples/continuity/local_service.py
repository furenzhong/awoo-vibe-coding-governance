"""Offline continuity fixture; never contacts a service or uses credentials."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def write_state(path, state):
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "inspect", "finish"))
    parser.add_argument("--sandbox", required=True, type=Path)
    parser.add_argument("--environment")
    parser.add_argument("--identity")
    parser.add_argument("--operation")
    parser.add_argument("--expected-state")
    args = parser.parse_args()
    sandbox = args.sandbox.resolve()
    path = sandbox / "state.json"

    if args.action == "init":
        sandbox.mkdir(parents=False, exist_ok=False)
        state = {
            "environment": "rehearsal",
            "identity": "preview-operator",
            "operation": "preview-041",
            "state": "ready",
            "completion_count": 0,
        }
        write_state(path, state)
        print(json.dumps({"sandbox": str(sandbox), "synthetic": True, **state}))
        return

    state = json.loads(path.read_text(encoding="utf-8"))
    for field in ("environment", "identity", "operation"):
        if getattr(args, field) != state[field]:
            raise ValueError(f"{field} does not match the existing local operation")
    if args.action == "inspect":
        print(json.dumps({"synthetic": True, **state}))
        return

    if state["state"] == "completed":
        print(json.dumps({"changed": False, "synthetic": True, **state}))
        return
    if state["state"] != "ready" or args.expected_state != state["state"]:
        raise ValueError("query the original operation and use its actual ready state")
    state["state"] = "completed"
    state["completion_count"] += 1
    write_state(path, state)
    print(json.dumps({"changed": True, "synthetic": True, **state}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": str(error), "synthetic": True}), file=sys.stderr)
        sys.exit(1)

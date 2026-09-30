#!/usr/bin/env python3
"""Compare context history costs against a fixed Git revision, using synthetic data.

Run from any directory with Python 3.10+ and Git. Only a TemporaryDirectory is
used for fixtures. --output writes the requested JSON report; no business data,
network, active hooks or model calls are used. Timings are warm local filesystem
measurements, not native hook latency or a cross-platform performance promise.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
FIXED_UUID = "f" * 32
FIXED_TIME = "2026-09-30T00:00:00+00:00"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def write_record(module, path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(module.packed(value))


def fixture(core, root, count, stream_count):
    """Seed schema-compatible immutable files directly, outside measured calls.

    The first binding/event/receipt use the real public API. Their schemas are
    copied for synthetic history so fixture generation is not itself quadratic.
    Histories include pending, unresolved, stale, missing/ambiguous sequence and
    compaction-gap cases, and a binding chain spanning every synthetic stream.
    """
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text("/.project-os-local/\n", encoding="utf-8")
    sources = {key: f"project-os/{key}.md" for key in ("rules", "status", "handoff", "decisions")}
    for key, ref in sources.items():
        path = root / ref
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"# Synthetic {key}\nManual cleanup only.\n", encoding="utf-8")
    topic = "project-os/operations.md"
    (root / topic).write_text("# Synthetic test service\nUse the test environment.\n" * 40, encoding="utf-8")
    write_record(core, root / "project-os.json", {"schema_version": 1, "sources": sources})
    first = core.bind_context(root, "generic", "synthetic-session", topic_refs=[topic])
    binding = first["binding"]
    seed = core.capture_event(root, binding["binding_id"], {
        "kind": "user_input", "native_event_id": "seed", "text": "Keep cleanup manual.",
        "source_sequence": 10, "sequence_start": 10, "source_complete": True})
    seed_path = root / seed["event_path"]
    event = core.read_record(seed_path)
    ref = {"path": topic, "sha256": core.sha((root / topic).read_bytes())}
    data = {"event_ids": [seed["capture_id"]], "outcome": "no_change",
            "reason": "Synthetic comparison only; semantic correctness remains unverified.",
            "source_refs": [ref], "writes": [], "checkpoint_ref": None,
            "next_action": "Read current authority before dependent work.", "unresolved": []}
    seed_receipt = core.reconcile_context(root, binding["binding_id"], data)
    store = root / core.STORE
    seed_receipt_path = store / "sessions" / binding["stream_id"] / "reconciliations" / (seed_receipt["reconciliation_id"] + ".json")
    receipt = core.read_record(seed_receipt_path)
    seed_path.unlink()
    seed_receipt_path.unlink()
    (store / "bindings" / (binding["binding_id"] + ".json")).unlink()
    bindings = []
    receipt_count = 0
    global_index = 0
    for stream_index in range(stream_count):
        item = {**binding, "binding_id": f"binding-{stream_index + 1:032x}",
                "stream_id": f"stream-{stream_index + 1:032x}",
                "previous_binding": bindings[-1]["binding_id"] if bindings else None}
        bindings.append(item)
        write_record(core, store / "bindings" / (item["binding_id"] + ".json"), item)
        stream_size = count // stream_count + (stream_index < count % stream_count)
        for position in range(stream_size):
            global_index += 1
            capture_id = f"capture-{global_index:032x}"
            kind = "pre_compact" if position % 31 == 0 else "post_compact" if position % 31 == 1 else "user_input"
            metadata = {"compaction_id": f"cycle-{position // 31}"}
            # Some pre-compaction events deliberately have no matching summary.
            if kind == "post_compact" and position % 62 == 1:
                metadata["compaction_id"] = "different-cycle"
            copy = {**event, "binding_id": item["binding_id"], "stream_id": item["stream_id"],
                    "capture_id": capture_id, "receive_sequence": position + 1,
                    "native_event_id": f"native-{global_index}", "kind": kind, "metadata": metadata,
                    "source_sequence": None if position % 29 == 0 else 10 + position - (position % 37 == 0),
                    "body_available": position % 41 != 0,
                    "text": "Synthetic correction: cleanup still requires an explicit request.",
                    "payload_state": "truncated" if position % 43 == 0 else "original"}
            session = store / "sessions" / item["stream_id"]
            write_record(core, session / "events" / (capture_id + ".json"), copy)
            if position % 7 == 0:
                continue
            receipt_count += 1
            reconciliation_id = f"reconciliation-{global_index:032x}"
            stale_ref = {**ref, "sha256": "0" * 64} if position % 13 == 0 else ref
            unresolved = position % 11 == 0
            copy_receipt = {**receipt, "binding_id": item["binding_id"], "event_ids": [capture_id],
                            "reconciliation_id": reconciliation_id, "receive_sequence": position + 1,
                            "source_refs": [stale_ref], "outcome": "unresolved" if unresolved else "no_change",
                            "unresolved": ["Synthetic unresolved interpretation."] if unresolved else []}
            write_record(core, session / "reconciliations" / (reconciliation_id + ".json"), copy_receipt)
    return bindings, receipt_count, data, global_index


@contextmanager
def reads(core):
    stats = {"json_parses": 0, "read_calls": 0, "read_bytes": 0}
    original_record, original_text, original_bytes = core.read_record, Path.read_text, Path.read_bytes
    json_depth = 0

    def record(path, **kwargs):
        nonlocal json_depth
        stats["json_parses"] += 1
        json_depth += 1
        try:
            result = original_record(path, **kwargs)
            stats["read_calls"] += 1
            stats["read_bytes"] += path.stat().st_size
            return result
        finally:
            json_depth -= 1

    def text(path, *args, **kwargs):
        result = original_text(path, *args, **kwargs)
        if not json_depth:
            stats["read_calls"] += 1
            stats["read_bytes"] += path.stat().st_size
        return result

    def binary(path, *args, **kwargs):
        result = original_bytes(path, *args, **kwargs)
        if not json_depth:
            stats["read_calls"] += 1
            stats["read_bytes"] += len(result)
        return result

    with mock.patch.object(core, "read_record", side_effect=record), \
            mock.patch.object(Path, "read_text", text), mock.patch.object(Path, "read_bytes", binary):
        yield stats


def invoke(core, root, binding, operation, reconciliation):
    """Use identical generated identities; remove only this call's new fixture file."""
    with mock.patch.object(core.uuid, "uuid4", return_value=SimpleNamespace(hex=FIXED_UUID)), \
            mock.patch.object(core, "now", return_value=FIXED_TIME):
        artifact = None
        if operation == "capture":
            report = core.capture_event(root, binding["binding_id"], {
                "kind": "user_input", "native_event_id": "new-benchmark-event",
                "text": "Synthetic new event; do not perform cleanup."})
            artifact = root / report["event_path"]
        elif operation == "reconcile":
            report = core.reconcile_context(root, binding["binding_id"], reconciliation)
            artifact = root / core.STORE / "sessions" / binding["stream_id"] / "reconciliations" / (report["reconciliation_id"] + ".json")
        elif operation == "status":
            report = core.context_status(root)
        else:
            report = core.resume_context(root, binding["binding_id"])
        content = artifact.read_bytes().hex() if artifact else None
        if artifact:
            artifact.unlink()
        return {"report": report, "written_record": content}


def measure(core, root, binding, operation, reconciliation, repeats):
    with reads(core) as read_stats:
        output = invoke(core, root, binding, operation, reconciliation)
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        repeated = invoke(core, root, binding, operation, reconciliation)
        samples.append(time.perf_counter() - start)
        if repeated != output:
            raise RuntimeError("A stable fixture produced inconsistent operation outputs.")
    return {"seconds_median": statistics.median(samples), "seconds_samples": samples,
            **read_stats}, output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="fc8010fd4d20c6f8f4ec018e950811cebc03885a")
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--streams", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--large-repeats", type=int, default=1,
                        help="Timing samples for 5000 or more events; every case reports its samples.")
    parser.add_argument("--operations", nargs="+", choices=("capture", "reconcile", "status", "resume"),
                        default=["capture", "reconcile", "status", "resume"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if min([args.repeats, args.large_repeats, *args.sizes, *args.streams]) < 1 or max(args.streams) > min(args.sizes):
        parser.error("Positive sizes/repeats and no more streams than events are required.")
    baseline_revision = git(REPO, "rev-parse", args.baseline + "^{commit}").decode().strip()
    baseline_bytes = git(REPO, "show", baseline_revision + ":scripts/project_os_context.py")
    candidate_path = REPO / "scripts/project_os_context.py"
    candidate = load_module(candidate_path, "context_candidate_benchmark")
    report = {"schema_version": 1, "baseline_revision": baseline_revision,
              "candidate_sha256": candidate.sha(candidate_path.read_bytes()),
              "python": sys.version, "platform": platform.platform(),
              "timing": "Warm local filesystem; uninstrumented median and samples; call includes fixed-ID mocks, written-record verification and fixture write cleanup. JSON and Path read calls/bytes measured in a separate invocation, including written-record verification; filesystem metadata and Git internal reads are not counted.",
              "limitations": ["No durable index; capture and reconcile still parse full selected-stream histories.",
                              "Status and resume still parse all included events and receipts; storage grows without automatic cleanup.",
                              "Reads are query observations, not an atomic workspace snapshot.",
                              "No real sessions, network calls, native hook latency, concurrent business writes, or cold filesystem measurements."],
              "cases": []}
    with tempfile.TemporaryDirectory(prefix="awoo-context-benchmark-") as temporary:
        base = Path(temporary)
        baseline_path = base / "baseline.py"
        baseline_path.write_bytes(baseline_bytes)
        baseline = load_module(baseline_path, "context_baseline_benchmark")
        for count in args.sizes:
            for stream_count in args.streams:
                root = base / f"events-{count}-streams-{stream_count}"
                bindings, receipt_count, reconciliation, last_id = fixture(baseline, root, count, stream_count)
                reconciliation = {**reconciliation, "event_ids": [f"capture-{last_id:032x}"]}
                case = {"event_count": count, "receipt_count": receipt_count,
                        "stream_count": stream_count, "operations": {}}
                repeats = args.large_repeats if count >= 5000 else args.repeats
                for operation in args.operations:
                    previous_stats, previous = measure(baseline, root, bindings[-1], operation, reconciliation, repeats)
                    current_stats, current = measure(candidate, root, bindings[-1], operation, reconciliation, repeats)
                    if previous != current:
                        raise RuntimeError(f"Output semantics changed: {count}/{stream_count}/{operation}")
                    case["operations"][operation] = {"baseline": previous_stats, "candidate": current_stats,
                                                       "identical_output_and_written_record": True,
                                                       "speedup": previous_stats["seconds_median"] / current_stats["seconds_median"]}
                    print(json.dumps({"events": count, "streams": stream_count, "operation": operation,
                                      **case["operations"][operation]}, ensure_ascii=False), flush=True)
                report["cases"].append(case)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()

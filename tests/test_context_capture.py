"""Behavioral regressions for private context capture and bounded recovery.

Fixtures contain synthetic project facts and fake credentials only. Tests exercise
the public API/CLI; no real assistant session, hook, or remote service is used.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TOOL = SCRIPTS / "project_os_context.py"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and ".git" not in path.relative_to(root).parts}


def run_git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), "-c", "user.name=ContextFixture",
         "-c", "user.email=context@example.invalid", *args],
        text=True, encoding="utf-8", stderr=subprocess.PIPE,
    ).strip()


@unittest.skipUnless(shutil.which("git"), "Git is required to verify private context storage")
class ContextCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("project_os_context_capture_tests", TOOL)
        cls.core = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(SCRIPTS))
        try:
            spec.loader.exec_module(cls.core)
        finally:
            sys.path.pop(0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="context-capture-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "project"
        self.target.mkdir()
        run_git(self.target, "init", "-q")
        (self.target / ".gitignore").write_text("/.project-os-local/\n", encoding="utf-8")
        self.sources = {name: f"project-os/{name.upper()}.md"
                        for name in ("rules", "status", "handoff", "decisions")}
        for name, relative in self.sources.items():
            path = self.target / relative
            path.parent.mkdir(exist_ok=True)
            path.write_text(f"# {name}\nSynthetic current project source.\n", encoding="utf-8")
        self.topic = "docs/export.md"
        (self.target / "docs").mkdir()
        (self.target / self.topic).write_text(
            "# Export\nUser requirement: document cleanup only on explicit request.\n"
            "Discussion only; no implementation has been authorized.\n", encoding="utf-8")
        (self.target / "project-os/tasks").mkdir()
        (self.target / "project-os/evidence").mkdir()
        write_json(self.target / "project-os.json", {
            "schema_version": 1, "kit_version": "1.4.0", "role": "project",
            "sources": self.sources, "tasks_dir": "project-os/tasks",
            "evidence_dir": "project-os/evidence",
        })
        run_git(self.target, "add", ".")
        run_git(self.target, "commit", "-qm", "Synthetic project baseline")

    def cli(self, *args, data=None, expect_ok=True):
        result = subprocess.run(
            [sys.executable, str(TOOL), *args, "--target", str(self.target), "--json"],
            input=json.dumps(data) if data is not None else None,
            text=True, encoding="utf-8", capture_output=True, timeout=20,
        )
        if expect_ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"Context CLI must return JSON, got {result.stdout!r}; stderr={result.stderr!r}")
        self.assertEqual(bool(report["ok"]), expect_ok, report)
        return report

    def bind(self, session="synthetic-session", mode="discussion", policy="redacted", task_id=None):
        args = ["bind", "--adapter", "generic", "--session-id", session,
                "--mode", mode, "--topic", self.topic, "--payload-policy", policy]
        if task_id:
            args.extend(["--task-id", task_id])
        return self.cli(*args)["binding_id"]

    def capture(self, binding, native_id="message-1", text="Keep cleanup manual.", **extra):
        data = {"kind": "user_input", "native_event_id": native_id, "text": text, **extra}
        return self.cli("capture", "--binding", binding, data=data)

    def status(self, binding):
        return self.cli("status", "--binding", binding)

    def source_ref(self, relative=None):
        relative = relative or self.topic
        return {"path": relative, "sha256": digest(self.target / relative)}

    def reconciliation(self, event_ids, **changes):
        return {"event_ids": event_ids, "outcome": "no_change",
                "reason": "Compared the observed words with the current topic; no new decision.",
                "source_refs": [self.source_ref()], "writes": [], "checkpoint_ref": None,
                "next_action": "Continue only the currently authorized discussion.", "unresolved": [], **changes}

    def real_task(self):
        task = {
            "id": "task-export", "objective": "Implement an explicitly authorized fixture change.",
            "status": "planned", "base_revision": run_git(self.target, "rev-parse", "HEAD"),
            "writable_paths": ["src"], "acceptance_commands": ["python -m unittest"],
            "executor": "synthetic-worker", "worktree": str(self.target),
            "session_id": "synthetic-executor",
        }
        write_json(self.target / "project-os/tasks/task-export.json", task)
        return task

    def test_discussion_binding_preserves_business_files_and_creates_no_task(self):
        before = file_bytes(self.target)
        binding = self.bind()
        self.capture(binding)
        after = file_bytes(self.target)
        for path, content in before.items():
            self.assertEqual(after[path], content, path)
        self.assertEqual(list((self.target / "project-os/tasks").glob("*.json")), [])
        self.assertTrue(all(path.startswith(".project-os-local/") for path in set(after) - set(before)))
        self.assertNotIn(".project-os-local", run_git(self.target, "status", "--porcelain=v1"))

    def test_execution_binding_requires_existing_task_without_fabricating_dispatch(self):
        self.cli("bind", "--adapter", "generic", "--session-id", "worker", "--mode", "execution",
                 "--topic", self.topic, "--task-id", "missing-task", expect_ok=False)
        self.assertEqual(list((self.target / "project-os/tasks").glob("*.json")), [])
        task = self.real_task()
        before = (self.target / "project-os/tasks/task-export.json").read_bytes()
        binding = self.bind(mode="execution", task_id=task["id"])
        first = self.capture(binding, kind="post_compact", text="A historical native summary.")
        second = self.capture(binding, native_id="compact-2", kind="post_compact", text="Another native summary.")
        self.assertNotEqual(first["capture_id"], second["capture_id"])
        self.assertEqual(before, (self.target / "project-os/tasks/task-export.json").read_bytes())
        self.assertNotIn("context", task)

    def test_native_identity_deduplicates_retries_not_repeated_words(self):
        binding = self.bind()
        first = self.capture(binding, "native-1", "The same words can be said twice.")
        retry = self.capture(binding, "native-1", "The same words can be said twice.")
        distinct = self.capture(binding, "native-2", "The same words can be said twice.")
        self.assertEqual(first["capture_id"], retry["capture_id"])
        self.assertTrue(retry["deduplicated"])
        self.assertNotEqual(first["capture_id"], distinct["capture_id"])
        coverage = self.status(binding)["coverage"]
        self.assertEqual(set(coverage["observed_capture_ids"]), {first["capture_id"], distinct["capture_id"]})
        without_identity = self.capture(binding, None, "The same words can be said twice.")
        another_unlocated = self.capture(binding, None, "The same words can be said twice.")
        self.assertNotEqual(without_identity["capture_id"], another_unlocated["capture_id"])

    def test_private_storage_must_be_explicitly_excluded_from_git(self):
        (self.target / ".gitignore").write_text("# No private storage policy yet.\n", encoding="utf-8")
        self.cli("bind", "--adapter", "generic", "--session-id", "discussion",
                 "--mode", "discussion", "--topic", self.topic, expect_ok=False)
        self.assertFalse((self.target / ".project-os-local").exists())

    def test_source_sequence_holes_and_unknown_streams_are_not_global_progress(self):
        first_binding = self.bind("coordinator")
        first = self.capture(first_binding, "source-40", source_sequence=40, sequence_start=40, source_complete=True)
        last = self.capture(first_binding, "source-42", source_sequence=42, sequence_start=40, source_complete=True)
        coverage = self.status(first_binding)["coverage"]
        self.assertEqual(coverage["missing_source_sequences"], [41])
        self.assertIsNone(coverage["reconciled_through"])
        self.assertEqual(set(coverage["pending_capture_ids"]), {first["capture_id"], last["capture_id"]})
        second_binding = self.bind("executor")
        self.capture(second_binding, "executor-tail")
        second = self.status(second_binding)["coverage"]
        self.assertTrue(second["unknown_ranges"])
        self.assertIsNone(second["reconciled_through"])
        project_status = self.cli("status")
        self.assertEqual(len(project_status["bindings"]), 2)
        self.assertNotIn("reconciled_through", project_status)

    def test_unsafe_topic_references_are_rejected_without_external_changes(self):
        outside = self.root / "outside.md"
        outside.write_text("External file must not be touched.\n", encoding="utf-8")
        for topic in ("../outside.md", str(outside), ".git/config", "docs/item:stream", "docs/NUL.md"):
            with self.subTest(topic=topic):
                self.cli("bind", "--adapter", "generic", "--session-id", "unsafe-topic",
                         "--mode", "discussion", "--topic", topic, expect_ok=False)
        self.assertEqual(outside.read_text(encoding="utf-8"), "External file must not be touched.\n")

    def test_linked_topic_files_cannot_be_adopted_as_private_write_authority(self):
        outside = self.root / "outside.md"
        outside.write_text("Synthetic external source.\n", encoding="utf-8")
        hardlink = self.target / "docs/hardlinked.md"
        try:
            os.link(outside, hardlink)
        except OSError:
            self.skipTest("Host does not support hardlinks")
        self.cli("bind", "--adapter", "generic", "--session-id", "hardlink",
                 "--mode", "discussion", "--topic", "docs/hardlinked.md", expect_ok=False)
        link = self.target / "docs/symlink.md"
        try:
            link.symlink_to(outside)
        except OSError:
            return  # Hardlink coverage still ran; symlinks may require host privileges.
        self.addCleanup(link.unlink)
        self.cli("bind", "--adapter", "generic", "--session-id", "symlink",
                 "--mode", "discussion", "--topic", "docs/symlink.md", expect_ok=False)
        self.assertEqual(outside.read_text(encoding="utf-8"), "Synthetic external source.\n")

    def test_late_native_summary_cannot_overwrite_current_project_authority(self):
        binding = self.bind()
        authority = self.target / self.topic
        authority.write_text("# Current decision\nCleanup requires an explicit user request.\n", encoding="utf-8")
        before = file_bytes(self.target)
        event = self.capture(binding, "late-old-summary", kind="post_compact",
                             text="Historical summary: automatically archive plans after every handoff.")
        self.assertTrue(event["capture_id"])
        for relative, content in before.items():
            if not relative.startswith(".project-os-local/"):
                self.assertEqual((self.target / relative).read_bytes(), content, relative)
        coverage = self.status(binding)["coverage"]
        self.assertIn(event["capture_id"], coverage["pending_capture_ids"])
        self.assertNotIn(event["capture_id"], coverage["reconciled_capture_ids"])

    def test_sensitive_payload_is_filtered_before_storage_and_errors_do_not_echo_it(self):
        binding = self.bind(policy="redacted")
        secret = "sk-syntheticSecretForRegression1234567890ABCDEF"
        capture = self.capture(binding, "sensitive-fixture", text=f"api_key={secret}",
                               metadata={"api_key": secret, "nested": {"authorization": f"Bearer {secret}"}})
        persisted = b"\n".join(file_bytes(self.target / ".project-os-local").values())
        self.assertNotIn(secret.encode(), persisted)
        self.assertNotIn(secret, json.dumps(capture))
        stored_event = json.loads((self.target / capture["event_path"]).read_text(encoding="utf-8"))
        self.assertEqual(stored_event["payload_state"], "redacted")
        self.assertTrue(stored_event["redaction_applied"])
        error = self.cli("capture", "--binding", binding,
                         data={"kind": "user_input", "source_sequence": f"api_key={secret}", "text": secret},
                         expect_ok=False)
        self.assertNotIn(secret, json.dumps(error))
        persisted_after = b"\n".join(file_bytes(self.target / ".project-os-local").values())
        self.assertNotIn(secret.encode(), persisted_after)

    def test_metadata_only_policy_cannot_claim_the_body_was_preserved(self):
        binding = self.bind(policy="metadata_only")
        body = "Synthetic confidential prose which metadata-only mode must omit."
        event = self.capture(binding, "body-omitted", text=body)
        persisted = b"\n".join(file_bytes(self.target / ".project-os-local").values())
        self.assertNotIn(body.encode(), persisted)
        self.assertTrue(event["capture_id"])
        self.assertIn(b"metadata_only", persisted)

    def test_reconciliation_watermark_stops_at_unresolved_or_missing_source(self):
        binding = self.bind()
        events = {seq: self.capture(binding, f"message-{seq}", source_sequence=seq,
                                    sequence_start=40, source_complete=True)["capture_id"]
                  for seq in (40, 42)}
        for event_id in events.values():
            self.core.reconcile_context(self.target, binding, self.reconciliation([event_id]))
        coverage = self.status(binding)["coverage"]
        self.assertEqual(coverage["reconciled_through"], 40)
        self.assertEqual(coverage["missing_source_sequences"], [41])
        middle = self.capture(binding, "message-41", source_sequence=41,
                              sequence_start=40, source_complete=True)["capture_id"]
        self.core.reconcile_context(self.target, binding, self.reconciliation(
            [middle], outcome="unresolved", unresolved=["Need to distinguish a proposal from a user decision."]))
        coverage = self.status(binding)["coverage"]
        self.assertEqual(coverage["reconciled_through"], 40)
        self.assertIn(middle, coverage["unresolved_capture_ids"])
        self.core.reconcile_context(self.target, binding, self.reconciliation([middle]))
        self.assertEqual(self.status(binding)["coverage"]["reconciled_through"], 42)

    def test_no_change_requires_reason_and_sources_and_cannot_hide_user_words(self):
        binding = self.bind()
        text = "Correction: cleanup is allowed only when I explicitly request it."
        event_id = self.capture(binding, text=text)["capture_id"]
        for changes in ({"reason": ""}, {"source_refs": []}, {"unresolved": ["Unsettled question"]}):
            with self.subTest(changes=changes):
                with self.assertRaises(self.core.ContextError):
                    self.core.reconcile_context(self.target, binding, self.reconciliation([event_id], **changes))
        self.core.reconcile_context(self.target, binding, self.reconciliation([event_id]))
        resume = self.core.resume_context(self.target, binding)
        self.assertEqual(resume["task_id"], None)
        self.assertEqual(resume["mode"], "discussion")
        self.assertIn(text, [item["text"] for item in resume["related_inputs"]])
        self.assertEqual(list((self.target / "project-os/tasks").glob("*.json")), [])
        (self.target / self.topic).write_text("# Updated decision\nDo not restore the obsolete draft.\n", encoding="utf-8")
        resume = self.core.resume_context(self.target, binding)
        self.assertIn(event_id, resume["coverage"]["pending_capture_ids"])
        self.assertIn(self.topic, resume["coverage"]["changed_source_refs"])
        self.assertIn(self.source_ref(), resume["current_refs"])

    def test_changed_requires_real_write_evidence_and_stale_sources_do_not_settle(self):
        binding = self.bind()
        event_id = self.capture(binding)["capture_id"]
        before = self.source_ref()
        bad_write = {"path": self.topic, "before_sha256": before["sha256"], "after_sha256": "0" * 64}
        with self.assertRaises(self.core.ContextError):
            self.core.reconcile_context(self.target, binding, self.reconciliation(
                [event_id], outcome="changed", writes=[bad_write]))
        (self.target / self.topic).write_text("# Current decision\nCleanup only on explicit request; do not ask proactively.\n", encoding="utf-8")
        with self.assertRaises(self.core.ContextError):
            self.core.reconcile_context(self.target, binding, self.reconciliation([event_id], source_refs=[before]))
        self.assertIn(event_id, self.status(binding)["coverage"]["pending_capture_ids"])
        good_write = {**bad_write, "after_sha256": self.source_ref()["sha256"]}
        receipt = self.core.reconcile_context(self.target, binding, self.reconciliation(
            [event_id], outcome="changed", source_refs=[before], writes=[good_write]))
        self.assertFalse(receipt["adopted"])
        self.assertIn(event_id, self.status(binding)["coverage"]["reconciled_capture_ids"])

    def test_write_failures_and_lost_acknowledgements_recover_from_durable_records(self):
        binding = self.bind()
        payload = {"kind": "user_input", "native_event_id": "retry-after-interrupt", "text": "Keep the latest constraint."}
        with mock.patch.object(self.core, "atomic_record", side_effect=OSError("synthetic storage failure")):
            with self.assertRaises(self.core.ContextError):
                self.core.capture_event(self.target, binding, payload)
        self.assertEqual(self.status(binding)["coverage"]["observed_capture_ids"], [])
        original_write = self.core.atomic_record

        def persisted_then_interrupted(path, data):
            original_write(path, data)
            raise OSError("synthetic interruption after durable event")

        with mock.patch.object(self.core, "atomic_record", side_effect=persisted_then_interrupted):
            with self.assertRaises(self.core.ContextError):
                self.core.capture_event(self.target, binding, payload)
        retry = self.core.capture_event(self.target, binding, payload)
        self.assertTrue(retry["deduplicated"])
        event_id = retry["capture_id"]
        coverage = self.status(binding)["coverage"]
        self.assertEqual(coverage["observed_capture_ids"], [event_id])
        with mock.patch.object(self.core, "atomic_record", side_effect=OSError("synthetic receipt failure")):
            with self.assertRaises(self.core.ContextError):
                self.core.reconcile_context(self.target, binding, self.reconciliation([event_id]))
        self.assertIn(event_id, self.status(binding)["coverage"]["pending_capture_ids"])
        self.core.reconcile_context(self.target, binding, self.reconciliation([event_id]))
        self.assertIn(event_id, self.status(binding)["coverage"]["reconciled_capture_ids"])

    def test_resume_before_compaction_lands_exposes_gap_until_matching_cycle(self):
        binding = self.bind()
        self.capture(binding, "resume-first", kind="session_start", text=None,
                     metadata={"source": "compact", "compaction_id": "cycle-1"})
        resume = self.core.resume_context(self.target, binding)
        self.assertTrue(resume["coverage"]["compaction_gaps"])
        self.capture(binding, "late-wrong-cycle", kind="post_compact", text="Other summary",
                     metadata={"compaction_id": "cycle-0"})
        self.assertTrue(self.core.resume_context(self.target, binding)["coverage"]["compaction_gaps"])
        self.capture(binding, "late-right-cycle", kind="post_compact", text="The matching summary",
                     metadata={"compaction_id": "cycle-1"})
        self.assertEqual(self.core.resume_context(self.target, binding)["coverage"]["compaction_gaps"], [])

    def test_discussion_becomes_execution_only_with_explicit_binding_replacement(self):
        old_id = self.bind(session="same-session")
        pending = self.capture(old_id)["capture_id"]
        old_file = self.target / ".project-os-local/context/bindings" / (old_id + ".json")
        old_bytes = old_file.read_bytes()
        task = self.real_task()
        with self.assertRaises(self.core.ContextError):
            self.core.bind_context(self.target, "generic", "same-session", "execution",
                                   [self.topic], task["id"])
        new = self.core.bind_context(self.target, "generic", "same-session", "execution",
                                     [self.topic], task["id"], supersedes=old_id)
        self.assertNotEqual(new["binding_id"], old_id)
        self.assertEqual(old_file.read_bytes(), old_bytes)
        status = self.status(old_id)
        self.assertEqual(status["bindings"][0]["binding_state"], "superseded")
        resume = self.core.resume_context(self.target, new["binding_id"])
        self.assertEqual(resume["task_id"], task["id"])
        self.assertEqual(resume["previous_binding"], old_id)
        self.assertIn(pending, resume["previous_streams"][0]["pending_capture_ids"])

    def test_shared_sources_are_rechecked_on_each_query_across_streams(self):
        bindings = [self.bind("shared-source-a"), self.bind("shared-source-b")]
        captured = []
        for binding in bindings:
            event_id = self.capture(binding)["capture_id"]
            captured.append(event_id)
            self.core.reconcile_context(self.target, binding, self.reconciliation([event_id]))
        settled = self.core.context_status(self.target)
        self.assertTrue(all(not item["coverage"]["pending_capture_ids"] for item in settled["bindings"]))
        (self.target / self.topic).write_text("# Changed authority\nA new correction applies.\n", encoding="utf-8")
        stale = self.core.context_status(self.target)
        for item in stale["bindings"]:
            coverage = item["coverage"]
            self.assertTrue(coverage["pending_capture_ids"])
            self.assertTrue(coverage["stale_reconciliation_ids"])
            self.assertIn(self.topic, coverage["changed_source_refs"])
            self.assertEqual(coverage["reconciled_capture_ids"], [])
        # A missing source is unknown/stale too; it must not reuse a prior hash.
        (self.target / self.topic).unlink()
        missing = self.core.context_status(self.target)
        self.assertEqual(stale, missing)

    def test_reconciliation_keeps_final_hash_check_after_history_read(self):
        binding = self.bind()
        event_id = self.capture(binding)["capture_id"]
        data = self.reconciliation([event_id])
        original_records = self.core.records

        def mutate_after_validation(folder):
            result = original_records(folder)
            if folder.name == "reconciliations":
                (self.target / self.topic).write_text("# Concurrent edit\nDo not settle stale work.\n", encoding="utf-8")
            return result

        with mock.patch.object(self.core, "records", side_effect=mutate_after_validation):
            with self.assertRaisesRegex(self.core.ContextError, "changed during reconciliation"):
                self.core.reconcile_context(self.target, binding, data)
        self.assertEqual(self.status(binding)["coverage"]["reconciliation_ids"], [])

    def test_invalid_history_is_not_hidden_by_capture_or_reconciliation_fast_paths(self):
        binding = self.bind()
        event = self.capture(binding)
        folder = (self.target / event["event_path"]).parent
        malformed = folder / ("capture-" + "0" * 32 + ".json")
        malformed.write_text("{incomplete", encoding="utf-8")
        with self.assertRaises(self.core.ContextError):
            self.core.capture_event(self.target, binding, {"kind": "user_input", "native_event_id": "another"})
        with self.assertRaises(self.core.ContextError):
            self.core.reconcile_context(self.target, binding, self.reconciliation([event["capture_id"]]))
        self.assertEqual(len(list(folder.glob("*.json"))), 2)

    def test_collection_scan_rejects_replaced_files_and_directories(self):
        binding = self.bind()
        captured = self.capture(binding)
        path = self.target / captured["event_path"]
        original_open = Path.open
        original_content, original_info = path.read_bytes(), path.stat()
        replaced = False

        def replace_before_open(current, *args, **kwargs):
            nonlocal replaced
            if current == path and not replaced:
                replaced = True
                current.rename(current.with_suffix(".old"))
                with original_open(current, "wb") as stream:
                    stream.write(original_content)
                os.utime(current, ns=(original_info.st_atime_ns, original_info.st_mtime_ns))
            return original_open(current, *args, **kwargs)

        with mock.patch.object(Path, "open", replace_before_open):
            with self.assertRaisesRegex(self.core.ContextError, "changed before"):
                self.core.records(path.parent)
        path.unlink()
        path.with_suffix(".old").rename(path)
        original_record = self.core.read_record

        def replace_directory(current, **kwargs):
            result = original_record(current, **kwargs)
            current.parent.rename(current.parent.with_name("events-old"))
            current.parent.mkdir()
            return result

        with mock.patch.object(self.core, "read_record", side_effect=replace_directory):
            with self.assertRaisesRegex(self.core.ContextError, "collection changed"):
                self.core.records(path.parent)

    def test_collection_scan_still_rejects_linked_records(self):
        binding = self.bind()
        event = self.capture(binding)
        path = self.target / event["event_path"]
        outside = self.root / "outside.json"
        outside.write_text('{"private": "not a context event"}', encoding="utf-8")
        linked = path.parent / ("capture-" + "0" * 32 + ".json")
        try:
            os.link(outside, linked)
        except OSError:
            self.skipTest("Host does not support hardlinks")
        with self.assertRaises(self.core.ContextError):
            self.core.records(path.parent)
        linked.unlink()
        try:
            linked.symlink_to(outside)
        except OSError:
            return
        with self.assertRaises(self.core.ContextError):
            self.core.records(path.parent)

    def test_collection_scan_rejects_temporary_ancestor_redirection(self):
        binding = self.bind()
        event = self.capture(binding)
        path = self.target / event["event_path"]
        probe = self.root / "link-probe"
        try:
            probe.symlink_to(path.parent, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not support directory symlinks")
        probe.unlink()
        original_record = self.core.read_record
        # Restore the identical original directory before the scan's final
        # check: checking only at scan boundaries would accept outside JSON.
        cases = ((path.parent, False), (path.parent.parent, False),
                 (self.target, False), (path.parent.parent, True))
        for index, (ancestor, same_tree) in enumerate(cases):
            with self.subTest(ancestor=ancestor.name, same_tree=same_tree):
                outside = self.root / f"outside-{index}"
                replacement = outside / path.relative_to(ancestor)
                write_json(replacement, {"external": True})
                backup = ancestor.with_name(ancestor.name + "-backup")

                def redirected_read(current, **kwargs):
                    ancestor.rename(backup)
                    ancestor.symlink_to(backup if same_tree else outside, target_is_directory=True)
                    try:
                        return original_record(current, **kwargs)
                    finally:
                        ancestor.unlink()
                        backup.rename(ancestor)

                with mock.patch.object(self.core, "read_record", side_effect=redirected_read):
                    with self.assertRaisesRegex(self.core.ContextError, "symbolic links or reparse"):
                        self.core.records(path.parent)
                self.assertFalse(path.parent.is_symlink())
                self.assertEqual(self.core.read_record(path)["capture_id"], event["capture_id"])


if __name__ == "__main__":
    unittest.main()

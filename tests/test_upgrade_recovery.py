"""Fault injection for interrupted governance writes and preservation of later work."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("upgrade_recovery_tool", ROOT / "scripts/project_os.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class UpgradeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="governance-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.target = self.work / "target"
        self.target.mkdir()
        self.plan = self.work / "plan.json"
        self.journal = self.work / "journal.json"
        components = []
        for name in ("a.md", "b.md"):
            (self.target / name).write_bytes(b"original\r\n")
            (self.work / name).write_bytes(b"adopted\n")
            components.append({"component": name, "path": name, "reason": "Explicit fixture change",
                               "candidate": name})
        self.proposal = self.work / "proposal.json"
        self.proposal.write_text(json.dumps({"schema_version": 1, "components": components}), encoding="utf-8")
        tool.build_upgrade_plan(ROOT, self.target, str(self.proposal), str(self.plan))

    def apply(self):
        return tool.apply_upgrade(self.target, str(self.plan), str(self.journal))

    def rollback(self):
        return tool.rollback_upgrade(self.target, str(self.journal))

    def test_partial_write_failure_keeps_recoverable_intent(self):
        write = tool.upgrade_atomic

        def fail_second(path, raw, expected):
            if path == self.target / "b.md":
                raise OSError("simulated disk failure")
            return write(path, raw, expected)

        with patch.object(tool, "upgrade_atomic", side_effect=fail_second):
            result = self.apply()
        self.assertFalse(result["ok"])
        record = tool.read_json(self.journal)
        self.assertEqual([e["state"] for e in record["entries"]], ["applied", "intent"])
        self.assertTrue(self.rollback()["ok"])
        for name in ("a.md", "b.md"):
            self.assertEqual((self.target / name).read_bytes(), b"original\r\n")

    def test_interrupt_after_file_replace_before_receipt_recovers_from_intent(self):
        write = tool.upgrade_atomic

        def interrupt(path, raw, expected):
            write(path, raw, expected)
            if path == self.target / "a.md":
                raise KeyboardInterrupt()

        with patch.object(tool, "upgrade_atomic", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.apply()
        self.assertEqual(tool.read_json(self.journal)["entries"][0]["state"], "intent")
        self.assertEqual((self.target / "a.md").read_bytes(), b"adopted\n")
        self.assertTrue(self.rollback()["ok"])
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")

    def test_journal_failure_after_replace_leaves_durable_intent(self):
        save = tool.upgrade_save

        def fail_receipt(path, data, expected):
            if path == self.journal and any(e["state"] == "applied" for e in data["entries"]):
                raise OSError("simulated journal failure")
            return save(path, data, expected)

        with patch.object(tool, "upgrade_save", side_effect=fail_receipt):
            self.assertFalse(self.apply()["ok"])
        self.assertEqual(tool.read_json(self.journal)["entries"][0]["state"], "intent")
        self.assertTrue(self.rollback()["ok"])
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")

    def test_change_after_global_preflight_is_preserved(self):
        save = tool.upgrade_save

        def introduce_new_work(path, data, expected):
            result = save(path, data, expected)
            if path == self.journal and expected is None:
                (self.target / "b.md").write_bytes(b"new business work\n")
            return result

        with patch.object(tool, "upgrade_save", side_effect=introduce_new_work):
            result = self.apply()
        self.assertFalse(result["ok"])
        self.assertTrue(self.rollback()["ok"])
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")
        self.assertEqual((self.target / "b.md").read_bytes(), b"new business work\n")

    def test_interrupted_rollback_can_resume(self):
        self.assertTrue(self.apply()["ok"])
        write = tool.upgrade_atomic

        def interrupt(path, raw, expected):
            write(path, raw, expected)
            if path == self.target / "b.md":
                raise KeyboardInterrupt()

        with patch.object(tool, "upgrade_atomic", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.rollback()
        self.assertEqual(tool.read_json(self.journal)["entries"][1]["state"], "rollback_intent")
        self.assertTrue(self.rollback()["ok"])
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")
        self.assertEqual((self.target / "b.md").read_bytes(), b"original\r\n")

    def test_plan_is_self_contained_after_inputs_are_removed(self):
        for name in ("proposal.json", "a.md", "b.md"):
            (self.work / name).unlink()
        self.assertTrue(self.apply()["ok"])
        self.assertTrue(self.rollback()["ok"])

    def test_stale_lock_does_not_assume_previous_writer_stopped(self):
        lock = self.target / tool.UPGRADE_LOCK
        lock.write_text('{"pid": 12345}', encoding="utf-8")
        with self.assertRaises(tool.ProjectOSError):
            self.apply()
        self.assertTrue(lock.exists())
        self.assertFalse(self.journal.exists())
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")

    def test_later_directory_is_preserved_while_other_components_roll_back(self):
        self.assertTrue(self.apply()["ok"])
        changed = self.target / "b.md"
        changed.unlink()
        changed.mkdir()
        (changed / "new-work.txt").write_bytes(b"later work")
        result = self.rollback()
        self.assertFalse(result["ok"])
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")
        self.assertEqual((changed / "new-work.txt").read_bytes(), b"later work")
        self.assertEqual(tool.read_json(self.journal)["entries"][1]["state"], "conflict")

    def test_later_hardlink_is_not_overwritten_or_removed(self):
        import os
        self.assertTrue(self.apply()["ok"])
        alias = self.work / "later-alias.md"
        os.link(self.target / "b.md", alias)
        self.assertFalse(self.rollback()["ok"])
        self.assertEqual(alias.read_bytes(), b"adopted\n")
        self.assertEqual((self.target / "b.md").read_bytes(), b"adopted\n")
        self.assertEqual((self.target / "a.md").read_bytes(), b"original\r\n")


if __name__ == "__main__":
    unittest.main()

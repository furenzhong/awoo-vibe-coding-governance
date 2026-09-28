"""Project hook adoption must preserve existing development configuration."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import project_os as gov
import project_os_context as ctx
import project_os_context_hooks as hooks


class ContextHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="awoo-hook-test-")
        self.addCleanup(self.temp.cleanup)
        self.outer = Path(self.temp.name)
        self.root = self.outer / "project with spaces"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        _, operations = gov.build_plan(SCRIPTS.parent, self.root, None)
        gov.apply_plan(self.root, operations)
        self.original = {p.relative_to(self.root).as_posix(): p.read_bytes()
                         for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}

    def setup(self):
        out = self.outer / "setup"
        report = hooks.setup_plan(self.root, out, ["claude", "codex"], sys.executable)
        return out, report

    def adopt(self):
        out, _ = self.setup()
        gov.apply_upgrade(self.root, str(out / "plan.json"), str(self.outer / "journal.json"))

    def payload(self, event="UserPromptSubmit", **extra):
        return {"hook_event_name": event, "session_id": "synthetic-session",
                "cwd": str(self.root), "prompt": "Preserve the unresolved pricing question.", **extra}

    def test_setup_preserves_target_and_merges_then_rollback_retains_existing_hooks(self):
        path = self.root / ".claude/settings.local.json"
        path.parent.mkdir()
        original = {"permissions": {"allow": ["Read"]}, "hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "existing-observer"}]}]}}
        path.write_text(json.dumps(original), encoding="utf-8")
        before = path.read_bytes()
        out, report = self.setup()
        self.assertTrue(report["ok"])
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / hooks.CONFIG).exists())
        journal = self.outer / "journal.json"
        gov.apply_upgrade(self.root, str(out / "plan.json"), str(journal))
        merged = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(merged["permissions"], original["permissions"])
        self.assertEqual(merged["hooks"]["Stop"][0], original["hooks"]["Stop"][0])
        gov.rollback_upgrade(self.root, str(journal))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / hooks.CONFIG).exists())

    def test_disabled_configuration_does_not_create_private_events(self):
        self.adopt()
        cfg = hooks.configuration(self.root)
        cfg["enabled"] = False
        (self.root / hooks.CONFIG).write_bytes(gov.json_bytes(cfg))
        self.assertEqual(hooks.hook(self.root, "claude", self.payload()), {})
        self.assertFalse((self.root / ctx.STORE).exists())

    def test_real_field_mapping_and_stable_ids_preserve_distinct_compactions(self):
        self.adopt()
        first = hooks.hook(self.root, "claude", self.payload(prompt_id="input-1"))
        hooks.hook(self.root, "claude", self.payload(prompt_id="input-1"))
        for _ in range(2):
            hooks.hook(self.root, "claude", self.payload("PostCompact", compact_summary="Historical summary", trigger="auto"))
        status = ctx.context_status(self.root)
        self.assertEqual(len(status["bindings"]), 1)
        self.assertEqual(len(status["bindings"][0]["coverage"]["observed_capture_ids"]), 3)
        self.assertIn("additionalContext", first["hookSpecificOutput"])
        self.assertFalse(any((self.root / "project-os/tasks").glob("*.json")))

    def test_config_policy_change_refuses_old_binding_until_explicit_rebind(self):
        self.adopt()
        hooks.hook(self.root, "codex", self.payload())
        cfg = hooks.configuration(self.root)
        cfg["payload_policy"] = "metadata_only"
        (self.root / hooks.CONFIG).write_bytes(gov.json_bytes(cfg))
        with self.assertRaises(gov.ProjectOSError):
            hooks.hook(self.root, "codex", self.payload(prompt="must not persist"))
        binding = ctx.context_status(self.root)["bindings"][0]
        self.assertEqual(len(binding["coverage"]["observed_capture_ids"]), 1)

    def test_nested_git_project_is_not_assigned_to_parent(self):
        self.adopt()
        nested = self.root / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        with self.assertRaises(gov.ProjectOSError):
            hooks.hook(self.root, "claude", self.payload(cwd=str(nested)))
        self.assertFalse((self.root / ctx.STORE).exists())

    def test_output_dotdot_cannot_write_setup_into_target(self):
        with self.assertRaises(gov.ProjectOSError):
            hooks.setup_plan(self.root, self.outer / "unused" / ".." / self.root.name / "bad",
                             ["claude"], sys.executable)
        self.assertFalse((self.root / "bad").exists())

    def test_capture_report_is_read_only_and_does_not_claim_config_is_observation(self):
        self.adopt()
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        report = gov.check_project(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["context_capture"]["state"], "configured_unverified")
        after = {p.relative_to(self.root).as_posix(): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

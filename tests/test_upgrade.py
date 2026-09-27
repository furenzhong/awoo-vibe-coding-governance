"""CLI regressions for bounded governance upgrades; all targets are disposable."""

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "scripts/project_os.py"


def file_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


@unittest.skipUnless(shutil.which("git"), "Git required for identity protection")
class UpgradeCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="governance-upgrade-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "project"
        self.target.mkdir()
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://example.invalid/team/project.git")
        self.put("business.txt", b"uncommitted business work\r\n")
        self.put("docs/RULES.md", b"current local rules\r\n")
        self.proposal = self.root / "proposal.json"
        self.plan = self.root / "plan.json"
        self.journal = self.root / "journal.json"
        self.components = []

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.target), *args], stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        ).strip()

    def put(self, relative, content):
        path = self.target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def component(self, relative="docs/RULES.md", content=b"reviewed new rules\n", **extra):
        candidate = self.root / f"candidate-{len(self.components)}.md"
        candidate.write_bytes(content)
        item = {
            "component": f"component-{len(self.components)}", "path": relative,
            "reason": "Adopt explicitly reviewed governance behavior.",
            "candidate": candidate.name, "mode": "current_only", **extra,
        }
        self.components.append(item)
        return item

    def write_proposal(self):
        self.proposal.write_text(json.dumps({
            "schema_version": 1, "components": self.components,
        }), encoding="utf-8")

    def cli(self, command, *args, ok=True, target=None):
        result = subprocess.run(
            [sys.executable, str(TOOL), command, "--target", str(target or self.target),
             *map(str, args), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def make_plan(self, ok=True, output=None):
        self.write_proposal()
        return self.cli("upgrade-plan", "--proposal", self.proposal,
                        "--out", output or self.plan, ok=ok)

    def apply(self, ok=True, target=None):
        return self.cli("upgrade-apply", "--plan", self.plan,
                        "--journal", self.journal, ok=ok, target=target)

    def rollback(self, ok=True):
        return self.cli("upgrade-rollback", "--journal", self.journal, ok=ok)

    def test_malformed_mode_returns_json_without_writing(self):
        self.component(mode=[])
        before = file_bytes(self.target)
        result = self.make_plan(ok=False)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(file_bytes(self.target), before)
        self.assertFalse(self.plan.exists())

    def test_malformed_journal_state_preserves_files_and_evidence(self):
        self.component()
        self.make_plan()
        self.apply()
        journal = json.loads(self.journal.read_text(encoding="utf-8"))
        journal["entries"][0]["state"] = []
        self.journal.write_text(json.dumps(journal), encoding="utf-8")
        before, saved = file_bytes(self.target), self.journal.read_bytes()
        result = self.rollback(ok=False)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(file_bytes(self.target), before)
        self.assertEqual(self.journal.read_bytes(), saved)

    def test_current_only_plan_is_read_only_and_apply_preserves_unlisted_business(self):
        self.component()
        before, status = file_bytes(self.target), self.git("status", "--porcelain=v1")
        self.make_plan()
        self.assertEqual(file_bytes(self.target), before)
        self.assertEqual(self.git("status", "--porcelain=v1"), status)
        self.apply()
        self.assertEqual((self.target / "docs/RULES.md").read_bytes(), b"reviewed new rules\n")
        self.assertEqual((self.target / "business.txt").read_bytes(), before["business.txt"])
        self.assertTrue(self.journal.is_file())
        self.assertFalse((self.target / "project-os.json").exists())

    def test_planning_then_change_blocks_entire_write_set(self):
        self.component()
        self.put("docs/HANDOFF.md", b"old handoff\n")
        self.component("docs/HANDOFF.md", b"new handoff\n")
        self.make_plan()
        self.put("docs/HANDOFF.md", b"later task correction\n")
        before = file_bytes(self.target)
        self.apply(ok=False)
        self.assertEqual(file_bytes(self.target), before)

    def test_plan_cannot_be_applied_to_another_target(self):
        self.component()
        self.make_plan()
        other = self.root / "other-project"
        shutil.copytree(self.target, other)
        before = file_bytes(other)
        self.apply(ok=False, target=other)
        self.assertEqual(file_bytes(other), before)
        self.assertEqual((self.target / "docs/RULES.md").read_bytes(), b"current local rules\r\n")

    def test_rollback_preserves_later_edits_and_restores_other_files(self):
        self.component()
        self.put("docs/HANDOFF.md", b"old handoff\n")
        self.component("docs/HANDOFF.md", b"new handoff\n")
        self.make_plan()
        self.apply()
        self.put("docs/HANDOFF.md", b"later business decision\n")
        self.rollback(ok=False)
        self.assertEqual((self.target / "docs/HANDOFF.md").read_bytes(), b"later business decision\n")
        self.assertEqual((self.target / "docs/RULES.md").read_bytes(), b"current local rules\r\n")

    def test_binary_bytes_and_new_files_are_reversible_with_idempotent_rollback(self):
        original = bytes(range(256)) + b"\x00\r\n"
        self.put("docs/RULES.md", original)
        self.component(content=b"\xff\xfe\x00new bytes\r\n")
        self.component("docs/new/ADOPTION.md", b"new governance note\n")
        before = file_bytes(self.target)
        self.make_plan()
        self.apply()
        self.rollback()
        self.assertEqual(file_bytes(self.target), before)
        self.rollback()
        self.assertEqual(file_bytes(self.target), before)

    def test_unchanged_candidate_can_be_planned_again_without_changing_target(self):
        self.component()
        self.make_plan()
        self.apply()
        before = file_bytes(self.target)
        self.plan = self.root / "second-plan.json"
        self.journal = self.root / "second-journal.json"
        self.make_plan()
        self.apply()
        self.rollback()
        self.assertEqual(file_bytes(self.target), before)

    def test_repeated_completed_rollback_does_not_touch_subsequent_work(self):
        self.component()
        self.make_plan()
        self.apply()
        self.rollback()
        self.put("docs/RULES.md", b"new work after completed rollback\n")
        before = file_bytes(self.target)
        self.rollback()
        self.assertEqual(file_bytes(self.target), before)

    def test_divergent_three_way_requires_explicit_merge_and_reason(self):
        (self.root / "base.md").write_bytes(b"old common rule\n")
        (self.root / "upstream.md").write_bytes(b"new upstream rule\n")
        item = self.component(base="base.md", upstream="upstream.md", mode="candidate")
        before = file_bytes(self.target)
        self.make_plan(ok=False)
        self.assertFalse(self.plan.exists())
        item["mode"] = "merged"
        self.make_plan(ok=False)
        self.assertFalse(self.plan.exists())
        item["merge_reason"] = "Retain the local constraint and adopt the upstream maintenance rule."
        self.make_plan()
        self.assertEqual(file_bytes(self.target), before)
        self.apply()
        self.assertEqual((self.target / "docs/RULES.md").read_bytes(), b"reviewed new rules\n")

    def test_clean_known_baseline_accepts_explicit_candidate_without_semantic_merge(self):
        original = (self.target / "docs/RULES.md").read_bytes()
        (self.root / "base.md").write_bytes(original)
        (self.root / "upstream.md").write_bytes(b"reviewed new rules\n")
        self.component(base="base.md", upstream="upstream.md", mode="candidate")
        self.make_plan()
        self.apply()
        self.rollback()
        self.assertEqual((self.target / "docs/RULES.md").read_bytes(), original)

    def test_plan_outputs_cannot_overwrite_inputs_or_write_into_target(self):
        item = self.component()
        self.write_proposal()
        proposal_before = self.proposal.read_bytes()
        candidate = self.root / item["candidate"]
        candidate_before = candidate.read_bytes()
        before = file_bytes(self.target)
        for output in (self.proposal, candidate, self.target / "plan.json"):
            with self.subTest(output=output.name):
                self.cli("upgrade-plan", "--proposal", self.proposal,
                         "--out", output, ok=False)
        self.assertEqual(self.proposal.read_bytes(), proposal_before)
        self.assertEqual(candidate.read_bytes(), candidate_before)
        self.assertEqual(file_bytes(self.target), before)

    def test_journal_cannot_overwrite_plan_candidate_existing_evidence_or_managed_file(self):
        item = self.component()
        self.make_plan()
        preserved = {
            self.plan: self.plan.read_bytes(),
            self.root / item["candidate"]: (self.root / item["candidate"]).read_bytes(),
            self.target / "docs/RULES.md": (self.target / "docs/RULES.md").read_bytes(),
        }
        existing = self.root / "existing-journal.json"
        existing.write_bytes(b"existing evidence must survive\n")
        preserved[existing] = existing.read_bytes()
        before = file_bytes(self.target)
        for journal in preserved:
            with self.subTest(journal=journal.name):
                self.cli("upgrade-apply", "--plan", self.plan,
                         "--journal", journal, ok=False)
        for path, content in preserved.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(file_bytes(self.target), before)

    def test_duplicate_overlapping_and_escaping_paths_are_rejected(self):
        before = file_bytes(self.target)
        for paths in (
            ("docs/RULES.md", "docs/RULES.md"),
            ("new-governance", "new-governance/RULES.md"),
            ("../escape.md",),
            (".git/config",),
            ("C:/outside.md",),
        ):
            with self.subTest(paths=paths):
                self.components = []
                for path in paths:
                    self.component(path)
                self.make_plan(ok=False)
                self.assertFalse(self.plan.exists())
        self.assertEqual(file_bytes(self.target), before)
        self.assertFalse((self.root / "escape.md").exists())

    def test_initial_install_records_rebuildable_adoption_without_rewriting_or_backfilling(self):
        planned = json.loads(self.cli("plan").stdout)
        self.assertIn(".project-os-adoption.json", {
            operation["path"] for operation in planned["operations"]
        })
        self.cli("apply")
        baseline = self.target / ".project-os-adoption.json"
        self.assertTrue(baseline.is_file())
        original = baseline.read_bytes()
        decoded = []

        def collect(value):
            if isinstance(value, dict):
                if "content_b64" in value:
                    decoded.append(base64.b64decode(value["content_b64"], validate=True))
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(json.loads(original))
        self.assertIn((self.target / "project-os/RULES.md").read_bytes(), decoded)
        self.assertIn((self.target / "scripts/project_os.py").read_bytes(), decoded)
        self.cli("apply")
        self.assertEqual(baseline.read_bytes(), original)
        baseline.unlink()
        self.cli("apply")
        self.assertFalse(baseline.exists(), "An old deployment must not acquire an invented initial baseline")


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "examples/ai-code-review-trial/projects"


def load_case(name, filename):
    path = CASES / name / filename
    spec = importlib.util.spec_from_file_location(f"trial_{name}_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AICodeReviewTrialFixtures(unittest.TestCase):
    def test_composition_defect_reproduces_cross_tenant_cache_leak(self):
        ItemStore = load_case("composition-defect", "tenant_cache.py").ItemStore
        store = ItemStore([
            {"tenant_id": "A", "id": "a-item"},
            {"tenant_id": "B", "id": "b-item"},
        ])
        self.assertEqual(store.list_items("A"), [{"tenant_id": "A", "id": "a-item"}])
        self.assertEqual(store.list_items("B"), [{"tenant_id": "A", "id": "a-item"}])

    def test_allowlisted_download_rejects_untrusted_hosts_and_schemes(self):
        may_download = load_case("allowlisted-download", "downloader.py").may_download
        allowed = {"docs.example.invalid"}
        self.assertTrue(may_download("https://docs.example.invalid/file.pdf?q=1", allowed))
        self.assertFalse(may_download("https://127.0.0.1/admin", allowed))
        self.assertFalse(may_download("https://docs.example.invalid.attacker.invalid/file", allowed))
        self.assertFalse(may_download("http://docs.example.invalid/file", allowed))
        self.assertFalse(may_download("https://docs.example.invalid:8443/file", allowed))
        self.assertFalse(may_download("https://docs.example.invalid:bad/file", allowed))

    def test_authority_fixture_has_no_agents_and_declares_contract_and_decision(self):
        project = CASES / "no-agents"
        self.assertFalse((project / "AGENTS.md").exists())
        contract = (project / "README.md").read_text(encoding="utf-8")
        decision = (project / "docs/DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("产品合同", contract)
        self.assertIn("实现决定", decision)
        self.assertIn("以产品合同定义预期行为", decision)


if __name__ == "__main__":
    unittest.main()

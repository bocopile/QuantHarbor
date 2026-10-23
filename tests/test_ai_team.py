"""외부 서비스 없이 합성 데이터로 팀 설정 오류를 확인한다."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "check_ai_team", Path(__file__).resolve().parents[1] / "scripts/check_ai_team.py"
)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def fixture():
    names = sorted(checker.MEMBERS)
    members = [{"name": name, "model": "synthetic-model", "reasoning_effort": "high",
                "config_file": f".codex/agents/{name}.toml"} for name in names]
    team = {"members": members, "orchestrator": {"name": "root", "configured_model": "synthetic-model", "configured_reasoning_effort": "high"},
            "execution_mode": "sequential", "max_active_workers": 1, "max_writers": 1,
            "recursive_delegation": False, "queue": checker.QUEUE}
    catalog = {"pagination_complete": True, "models": [{"id": "synthetic-model", "supported_reasoning_efforts": ["high"]}]}
    roles = {name: {"name": name, "model": "synthetic-model", "model_reasoning_effort": "high"} for name in names}
    parent = {"model": "synthetic-model", "model_reasoning_effort": "high", "agents": {"max_concurrent_threads_per_session": 6, "default_subagent_model": "synthetic-model", "default_subagent_reasoning_effort": "high"}}
    task_ids = [f"ENV-{i:02d}" for i in range(1, 12)] + [f"ARC-{i:02d}" for i in range(1, 12)] + [f"A{i:02d}" for i in range(1, 89)]
    items = [{"id": f"Q{i:02d}", "task_ids": task_ids[(i-1)*3:i*3] if i < 36 else task_ids[105:],
              "depends_on": [] if i == 1 else [f"Q{i-1:02d}"], "lead": "qh_implementer",
              "reviewer": "qh_reviewer", "validator": "qh_validator", "status": "completed" if i == 1 else "in_progress" if i == 2 else "pending",
              "approval_refs": ["AP-01"] if i == 2 else [],
              "evidence": ["docs/synthetic-evidence.md"] if i == 1 else []} for i in range(1, 37)]
    queue = {"execution_mode": "sequential", "max_active_workers": 1, "orchestrator": "root", "automatic_background_dispatch": False,
             "source": checker.CHECKLIST, "current_queue_item": "Q02", "work_items": items}
    checklist = "\n".join(f"| {task_id} | synthetic |" for task_id in task_ids)
    approvals = "| AP-01 | synthetic approval | waiting |"
    return team, catalog, roles, parent, queue, checklist, approvals


class TeamCheckerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="qh-team-test-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "docs").mkdir()
        (self.root / "docs/synthetic-evidence.md").write_text("synthetic evidence", encoding="utf-8")
        self.data = list(deepcopy(fixture()))

    def kinds(self):
        return {issue.kind for issue in checker.validate(*self.data, self.root)}

    def test_valid_synthetic_configuration(self):
        self.assertEqual(set(), self.kinds())

    def test_unknown_model_and_unsupported_reasoning(self):
        self.data[0]["members"][0]["model"] = "unavailable"
        self.data[0]["members"][1]["reasoning_effort"] = "ultra"
        self.assertTrue({"unknown_model", "unsupported_reasoning"} <= self.kinds())

    def test_role_mismatch_and_duplicate_member(self):
        self.data[2]["qh_reviewer"]["model_reasoning_effort"] = "low"
        self.data[0]["members"][1] = deepcopy(self.data[0]["members"][0])
        self.assertTrue({"role_mismatch", "duplicate_member", "member_set"} <= self.kinds())

    def test_parent_mismatch_and_thread_limit(self):
        self.data[3]["model"] = "unavailable"
        self.data[3]["agents"]["max_concurrent_threads_per_session"] = 7
        self.assertTrue({"parent_model_mismatch", "thread_limit"} <= self.kinds())

    def test_queue_cycle_and_forward_dependency(self):
        self.data[4]["work_items"][0]["depends_on"] = ["Q36"]
        self.assertTrue({"dependency_cycle", "dependency_order", "sequential_dependency"} <= self.kinds())

    def test_missing_queue_task_and_dependency(self):
        self.data[4]["work_items"].pop()
        self.data[4]["work_items"][2]["depends_on"] = ["Q99"]
        self.assertTrue({"queue_count_ids_or_order", "task_coverage", "missing_dependency"} <= self.kinds())

    def test_unregistered_assignee_and_inconsistent_current_state(self):
        self.data[4]["work_items"][1]["lead"] = "unknown"
        self.data[4]["work_items"][0]["status"] = "pending"
        self.assertTrue({"unregistered_assignee", "unfinished_prerequisite", "current_prerequisite", "current_item_not_first_unfinished"} <= self.kinds())

    def test_malformed_schema_returns_issues(self):
        self.data[0]["members"] = [None]
        self.data[4]["work_items"][0]["depends_on"] = {"unexpected": True}
        self.data[4]["work_items"][2]["task_ids"] = [None]
        self.assertTrue({"member_count_or_schema", "dependency_schema", "task_ids_schema"} <= self.kinds())

    def test_approval_refs_required_list_of_registered_strings(self):
        item = self.data[4]["work_items"][1]
        for invalid in (None, "AP-01", [None], ["AP-99"]):
            with self.subTest(approval_refs=invalid):
                item["approval_refs"] = invalid
                expected = "unregistered_approval" if invalid == ["AP-99"] else "approval_refs_schema"
                self.assertIn(expected, self.kinds())
        del item["approval_refs"]
        self.assertIn("approval_refs_schema", self.kinds())

    def test_all_completed_accepts_null_current_and_rejects_completed_pointer(self):
        for item in self.data[4]["work_items"]:
            item["status"] = "completed"
            item["evidence"] = ["docs/synthetic-evidence.md"]
        self.data[4]["current_queue_item"] = None
        self.assertEqual(set(), self.kinds())
        self.data[4]["current_queue_item"] = "Q36"
        self.assertIn("current_item_not_first_unfinished", self.kinds())
        self.assertIn("current_item_status", self.kinds())

    def test_unfinished_queue_rejects_null_or_completed_current(self):
        self.data[4]["current_queue_item"] = None
        self.assertIn("current_item", self.kinds())
        self.data[4]["current_queue_item"] = "Q01"
        self.assertIn("current_item_status", self.kinds())

    def test_completed_evidence_requires_existing_relative_file(self):
        item = self.data[4]["work_items"][0]
        for reference, expected in (
            ("docs/missing.md", "missing_evidence_file"),
            ("docs", "missing_evidence_file"),
            (str(self.root / "docs/synthetic-evidence.md"), "invalid_evidence_path"),
            ("../outside.md", "invalid_evidence_path"),
            ("docs/../docs/synthetic-evidence.md", "invalid_evidence_path"),
            ("C:\\outside.md", "invalid_evidence_path"),
        ):
            with self.subTest(reference=reference):
                item["evidence"] = [reference]
                self.assertIn(expected, self.kinds())

    def test_completed_evidence_rejects_symlink_escape(self):
        directory = tempfile.TemporaryDirectory(prefix="qh-evidence-outside-")
        self.addCleanup(directory.cleanup)
        target = Path(directory.name) / "synthetic.md"
        target.write_text("synthetic outside evidence", encoding="utf-8")
        (self.root / "docs/escape.md").symlink_to(target)
        self.data[4]["work_items"][0]["evidence"] = ["docs/escape.md"]
        self.assertIn("invalid_evidence_path", self.kinds())


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""저장된 팀 설정만 검사한다. 실행 중인 모델·권한·격리는 검증하지 않는다."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PureWindowsPath
import re
import tomllib


TEAM = "config/ai/team.toml"
QUEUE = "config/ai/execution-queue.json"
CATALOG = "docs/evidence/env-model-catalog-2026-10-20.json"
PARENT = ".codex/config.toml"
CHECKLIST = "docs/execution-checklist.md"
APPROVAL_REGISTER = "docs/approval-register.md"
MEMBERS = {
    "qh_researcher", "qh_architect", "qh_implementer", "qh_reviewer",
    "qh_security_reviewer", "qh_validator",
}
STATUSES = {"pending", "in_progress", "blocked", "completed"}


@dataclass(frozen=True)
class Issue:
    path: str
    kind: str


def checklist_ids(text):
    """실행 순서 요약이 아닌, 개별 작업 표 첫 열만 읽는다."""
    return re.findall(r"^\|\s*((?:ENV-|ARC-|[A-M])\d{2})\s*\|", text, re.M)


def evidence_file_issue(root, reference):
    """증거 내용을 읽지 않고 저장소 안의 상대 파일인지 확인한다."""
    relative = Path(reference)
    if (not reference.strip() or relative.is_absolute()
            or PureWindowsPath(reference).is_absolute()
            or ".." in relative.parts or "\\" in reference or "\x00" in reference):
        return "invalid_evidence_path"
    try:
        resolved = (root / relative).resolve()
        if not resolved.is_relative_to(root.resolve()):
            return "invalid_evidence_path"
        if not resolved.is_file():
            return "missing_evidence_file"
    except (OSError, ValueError, RuntimeError):
        return "invalid_evidence_path"
    return None


def validate(team, catalog, roles, parent, queue, checklist, approval_register, root):
    """설정과 파일 존재 검사. 승인 충족·증거의 성공 여부는 판정하지 않는다."""
    issues = []

    def fail(path, kind):
        issue = Issue(path, kind)
        if issue not in issues:
            issues.append(issue)

    documents = ((TEAM, team), (CATALOG, catalog), (PARENT, parent), (QUEUE, queue))
    if any(not isinstance(data, dict) for _, data in documents):
        for path, data in documents:
            if not isinstance(data, dict):
                fail(path, "document_type")
        return issues

    available = {}
    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        fail(CATALOG, "catalog_schema")
    else:
        for model in models:
            if not isinstance(model, dict):
                fail(CATALOG, "catalog_schema")
                continue
            model_id, efforts = model.get("id"), model.get("supported_reasoning_efforts")
            if (not isinstance(model_id, str) or not isinstance(efforts, list)
                    or not efforts or any(not isinstance(e, str) for e in efforts)):
                fail(CATALOG, "catalog_schema")
                continue
            if model_id in available:
                fail(CATALOG, "duplicate_model")
            available[model_id] = efforts
    if catalog.get("pagination_complete") is not True:
        fail(CATALOG, "incomplete_catalog")

    def check_model(model, effort, path):
        if not isinstance(model, str) or model not in available:
            fail(path, "unknown_model")
        elif not isinstance(effort, str) or effort not in available[model]:
            fail(path, "unsupported_reasoning")

    members = team.get("members")
    if not isinstance(members, list):
        fail(TEAM, "members_schema")
        members = []
    names = [m.get("name") for m in members if isinstance(m, dict)]
    if (len(members) != 6 or len(names) != 6
            or any(not isinstance(n, str) for n in names)):
        fail(TEAM, "member_count_or_schema")
    string_names = [n for n in names if isinstance(n, str)]
    if len(set(string_names)) != len(string_names):
        fail(TEAM, "duplicate_member")
    if set(string_names) != MEMBERS:
        fail(TEAM, "member_set")
    for member in members:
        if not isinstance(member, dict):
            continue
        check_model(member.get("model"), member.get("reasoning_effort"), TEAM)
        name = member.get("name")
        if not isinstance(name, str) or name not in MEMBERS:
            continue
        path = f".codex/agents/{name}.toml"
        if member.get("config_file") != path:
            fail(TEAM, "role_path")
        role = roles.get(name)
        if not isinstance(role, dict):
            fail(path, "missing_role")
        elif (role.get("name") != name or role.get("model") != member.get("model")
              or role.get("model_reasoning_effort") != member.get("reasoning_effort")):
            fail(path, "role_mismatch")

    orchestrator = team.get("orchestrator", {})
    if not isinstance(orchestrator, dict):
        fail(TEAM, "orchestrator_schema")
        orchestrator = {}
    if orchestrator.get("name") != "root":
        fail(TEAM, "orchestrator_name")
    check_model(orchestrator.get("configured_model"),
                orchestrator.get("configured_reasoning_effort"), TEAM)
    if (parent.get("model") != orchestrator.get("configured_model")
            or parent.get("model_reasoning_effort") != orchestrator.get("configured_reasoning_effort")):
        fail(PARENT, "parent_model_mismatch")
    check_model(parent.get("model"), parent.get("model_reasoning_effort"), PARENT)
    agents = parent.get("agents", {})
    if not isinstance(agents, dict):
        fail(PARENT, "agents_schema")
        agents = {}
    if type(agents.get("max_concurrent_threads_per_session")) is not int or agents.get("max_concurrent_threads_per_session") != 6:
        fail(PARENT, "thread_limit")
    check_model(agents.get("default_subagent_model"), agents.get("default_subagent_reasoning_effort"), PARENT)
    for field, expected in (("execution_mode", "sequential"), ("max_active_workers", 1), ("max_writers", 1), ("recursive_delegation", False), ("queue", QUEUE)):
        if type(team.get(field)) is not type(expected) or team.get(field) != expected:
            fail(TEAM, "sequential_policy")
    for field, expected in (("execution_mode", "sequential"), ("max_active_workers", 1), ("orchestrator", "root"), ("automatic_background_dispatch", False), ("source", CHECKLIST)):
        if type(queue.get(field)) is not type(expected) or queue.get(field) != expected:
            fail(QUEUE, "sequential_policy")

    expected_ids = checklist_ids(checklist) if isinstance(checklist, str) else []
    if len(expected_ids) != 110 or len(set(expected_ids)) != 110:
        fail(CHECKLIST, "checklist_count_or_duplicate")
    registered_approvals = (re.findall(r"^\|\s*(AP-\d{2})\s*\|", approval_register, re.M)
                            if isinstance(approval_register, str) else [])
    if not registered_approvals or len(registered_approvals) != len(set(registered_approvals)):
        fail(APPROVAL_REGISTER, "approval_register_schema")
    items = queue.get("work_items")
    if not isinstance(items, list):
        fail(QUEUE, "queue_schema")
        return issues
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    if len(items) != 36 or ids != [f"Q{i:02d}" for i in range(1, 37)]:
        fail(QUEUE, "queue_count_ids_or_order")
    valid_items = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            if item["id"] in valid_items:
                fail(QUEUE, "duplicate_queue_id")
            valid_items[item["id"]] = item
        else:
            fail(QUEUE, "queue_item_schema")
    covered = set()
    edges = {}
    active = []
    allowed_assignees = set(string_names) | {"root"}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        path = f"{QUEUE}:work_items[{index}]"
        item_id = item.get("id")
        for field in ("lead", "reviewer", "validator"):
            if not isinstance(item.get(field), str) or item[field] not in allowed_assignees:
                fail(path, "unregistered_assignee")
        approvals = item.get("approval_refs")
        if not isinstance(approvals, list) or any(not isinstance(a, str) for a in approvals):
            fail(path, "approval_refs_schema")
        elif any(a not in registered_approvals for a in approvals):
            fail(path, "unregistered_approval")
        task_ids = item.get("task_ids")
        if not isinstance(task_ids, list) or not task_ids or any(not isinstance(t, str) for t in task_ids):
            fail(path, "task_ids_schema")
        else:
            if len(set(task_ids)) != len(task_ids):
                fail(path, "duplicate_task_id")
            if set(task_ids) - set(expected_ids):
                fail(path, "unknown_task_id")
            covered.update(task_ids)
        deps = item.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            fail(path, "dependency_schema")
            deps = []
        if deps != ([] if index == 0 else [f"Q{index:02d}"]):
            fail(path, "sequential_dependency")
        if isinstance(item_id, str):
            edges[item_id] = deps
        for dep in deps:
            if dep not in valid_items:
                fail(path, "missing_dependency")
            elif ids.index(dep) >= index:
                fail(path, "dependency_order")
        status = item.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            fail(path, "invalid_status")
        if status == "in_progress":
            active.append(item_id)
        if isinstance(status, str) and status in {"in_progress", "completed"} and any(valid_items.get(dep, {}).get("status") != "completed" for dep in deps):
            fail(path, "unfinished_prerequisite")
        evidence = item.get("evidence")
        if status == "completed" and (not isinstance(evidence, list) or not evidence or any(not isinstance(e, str) or not e.strip() for e in evidence)):
            fail(path, "completed_without_evidence")
        elif status == "completed":
            for reference in evidence:
                kind = evidence_file_issue(root, reference)
                if kind:
                    fail(path, kind)
    if covered != set(expected_ids):
        fail(QUEUE, "task_coverage")

    # Kahn's algorithm also detects cycles when an invalid forward edge is present.
    remaining = set(edges)
    while remaining:
        ready = {node for node in remaining if not (set(edges[node]) & remaining)}
        if not ready:
            fail(QUEUE, "dependency_cycle")
            break
        remaining -= ready
    current = queue.get("current_queue_item")
    first_unfinished = next((item.get("id") for item in items if isinstance(item, dict) and item.get("status") != "completed"), None)
    if "current_queue_item" not in queue:
        fail(QUEUE, "current_item_missing")
    elif first_unfinished is None and current is None:
        pass
    elif not isinstance(current, str) or current not in valid_items:
        fail(QUEUE, "current_item")
    else:
        if current != first_unfinished:
            fail(QUEUE, "current_item_not_first_unfinished")
        current_item = valid_items[current]
        if current_item.get("status") not in ("pending", "in_progress", "blocked"):
            fail(QUEUE, "current_item_status")
        if any(valid_items.get(dep, {}).get("status") != "completed" for dep in edges.get(current, [])):
            fail(QUEUE, "current_prerequisite")
    if len(active) > 1 or (active and active != [current]):
        fail(QUEUE, "active_item_conflict")
    return issues


def check_repository(root):
    """고정된 비민감 경로만 읽는다. manifest가 임의 읽기 경로를 지정할 수 없다."""
    issues = []

    def read(relative):
        path = root / relative
        try:
            if not path.resolve().is_relative_to(root.resolve()):
                issues.append(Issue(relative, "path_outside_repository"))
                return None
            text = path.read_text(encoding="utf-8")
            if relative.endswith(".toml"):
                return tomllib.loads(text)
            if relative.endswith(".json"):
                return json.loads(text)
            return text
        except (OSError, UnicodeError, ValueError):
            issues.append(Issue(relative, "read_or_parse_error"))
            return None

    team, catalog, parent, queue, checklist, approvals = [read(p) for p in (TEAM, CATALOG, PARENT, QUEUE, CHECKLIST, APPROVAL_REGISTER)]
    roles = {name: read(f".codex/agents/{name}.toml") for name in sorted(MEMBERS)}
    if not issues:
        issues.extend(validate(team, catalog, roles, parent, queue, checklist, approvals, root))
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    issues = check_repository(args.root)
    for issue in issues:
        print(f"FAIL {issue.path}: {issue.kind}")
    if issues:
        print(f"FAIL: {len(issues)}개 설정 오류")
        return 1
    print("PASS: 저장된 팀원 6명·큐 36개·작업 ID 110개 정합성 확인")
    print("범위: 로컬 파일만 검사. 현재 세션 모델·역할 로드·권한·격리·외부 연결은 미검증.")
    print("승인 ID 등록과 증거 파일 존재만 확인. 승인 충족·증거의 성공 여부는 미판정.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

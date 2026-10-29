"""고정 AP fixture를 실제 Q24/원장/시장 source builder로 재구성한다."""
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from quantharbor.adapters.synthetic_approval import (FixturePrincipal, SyntheticApprovalRepository,
    SyntheticAuthority)
from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.application.approval import ApprovalApplication
from quantharbor.domain import approval as d
from quantharbor.domain.target import ref as target_ref
from quantharbor.ports.approval import ApprovalSource
from synthetic_target import fixture, build

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / 'docs/contracts/approval-fixture-v1.json'
MANIFEST = json.loads(FIXTURE_PATH.read_bytes())
assert sha256(FIXTURE_PATH.read_bytes()).hexdigest() == d.FIXTURE_SHA
assert tuple(c['id'] for c in MANIFEST['cases']) == tuple('AP%02d' % i for i in range(1, 22))


class Clock:
    def __init__(self):
        self.at = '2024-03-08T14:31:08Z'

    def __call__(self):
        return self.at


@lru_cache(maxsize=1)
def actual_source():
    request, inputs = fixture()
    repo = SyntheticTargetRepository()
    artifacts = build(request, inputs, repo)
    assert artifacts.plan.body.status == 'eligible'
    return ApprovalSource(request, inputs, artifacts, repo)


def policy(source=None):
    source = source or actual_source()
    return d.SyntheticApprovalPolicy('q26-synthetic-policy', 1, 'synthetic', source.request.account_ref,
        '2024-03-01T00:00:00Z', '2024-04-01T00:00:00Z', 20, 10, 120, 30,
        d.ACTIONS, d.ApprovalLimits(), d.FIXTURE_REF)


class Harness:
    def __init__(self, *, capacity=128, byte_capacity=8388608):
        self.clock = Clock()
        self.source = actual_source()
        account = self.source.request.account_ref
        principals = (
            FixturePrincipal('fixture-approver', account, 'approver',
                ('present', 'approve', 'deny', 'revoke', 'withdraw', 'admit', 'query', 'heartbeat', 'disconnect')),
            FixturePrincipal('fixture-controller', account, 'controller',
                ('session', 'stop', 'resume', 'dispatch', 'withdraw', 'runtime', 'policy', 'heartbeat', 'disconnect', 'query')),
            FixturePrincipal('fixture-reporting', account, 'reporting', ('query',)),
            FixturePrincipal('fixture-research', account, 'research', ('query',)),
        )
        self.authority = SyntheticAuthority(principals, clock=self.clock)
        self.repo = SyntheticApprovalRepository(self.authority, self.source, policy(self.source),
            capacity=capacity, byte_capacity=byte_capacity)
        self.app = ApprovalApplication(self.repo)
        self.approver = self.authority.issue_session('fixture-approver')
        self.controller = self.authority.issue_session('fixture-controller')
        self.app.control(self.controller, 'resume')
        self.repo.record_risk(self.controller, 'clear')
        c = self.source.artifacts.candidates[0]
        self.candidate_ref = target_ref('candidate', c.candidate_id, c)

    def present(self, app=None):
        return (app or self.app).present(self.approver, self.candidate_ref)

    def head(self, approval):
        s = self.repo.snapshot()
        r = s['heads'][('approval', approval.approval_id)]
        from quantharbor.domain.serialization import parse_payload
        return parse_payload(s['records'][r]).payload

    def command(self, approval, action, command_id, *, handle=None, app=None):
        app = app or self.app
        handle = handle or (self.controller if action == 'dispatch' else self.approver)
        a = self.head(approval)
        c = app.challenge(handle, d.ref('approval', a.approval_id, a), action=action, command_id=command_id)
        return app.execute(handle, c)

    def approve(self, *, label='approve'):
        presentation, a = self.present()
        self.clock.at = '2024-03-08T14:31:10Z'
        receipt = self.command(a, 'approve', label)
        assert receipt.outcome == 'applied', receipt.reason_code
        return presentation, self.head(a)

    def consumed(self):
        _, a = self.approve()
        receipt = self.command(a, 'admit', 'admit')
        assert receipt.outcome == 'applied', receipt.reason_code
        return self.head(a)


def rights_changed(source, *, only='all', purposes=('store', 'research'), revoked_at=None):
    def point(p):
        return replace(p, market_inputs=tuple(replace(x, current_rights=replace(x.current_rights,
            purposes=purposes, revoked_at=revoked_at)) for x in p.market_inputs))
    i = source.inputs
    if only == 'risk':
        i = replace(i, risk_points=(point(i.risk_points[0]), *i.risk_points[1:]))
    elif only == 'daily':
        i = replace(i, daily_usage_inputs=(point(i.risk_points[0]),))
    else:
        i = replace(i, current=point(i.current), risk_points=tuple(map(point, i.risk_points)),
            boundary_inputs=tuple(map(point, i.boundary_inputs)), daily_usage_inputs=tuple(map(point, i.daily_usage_inputs)))
    return replace(source, inputs=i)

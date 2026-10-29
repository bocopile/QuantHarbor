"""Q26 입력은 실제 Q24 객체. opaque handle은 canonical 계약에 넣지 않는다."""
from dataclasses import dataclass
from typing import Protocol

from quantharbor.domain.ledger import exact
from quantharbor.domain.target import TargetRequest
from quantharbor.ports.target import TargetInputs, TargetArtifacts, TargetRepository


@dataclass(frozen=True, slots=True)
class ApprovalSource:
    request: TargetRequest
    inputs: TargetInputs
    artifacts: TargetArtifacts
    repository: TargetRepository

    def __post_init__(self):
        for x, t in ((self.request, TargetRequest), (self.inputs, TargetInputs),
                     (self.artifacts, TargetArtifacts)):
            exact(x, t)


class ApprovalCommands(Protocol):
    def present(self, handle, candidate_ref): ...
    def challenge(self, handle, approval_ref, *, action, command_id): ...
    def execute(self, handle, challenge): ...
    def withdraw(self, handle, approval_ref, *, command_id): ...


class ApprovalQueries(Protocol):
    def query(self, handle, *, account_ref, purpose, limit=10, cursor=0): ...

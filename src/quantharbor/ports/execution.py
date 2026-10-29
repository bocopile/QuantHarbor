"""실행의 typed 현재 입력. 원본 승인 source와 별도로 DB read-set에 결속한다."""
from dataclasses import dataclass
from typing import Protocol
from quantharbor.domain.execution import SyntheticExecutionPolicy, SyntheticExecutionQuery
from quantharbor.domain.ledger import exact
from quantharbor.ports.target import TargetInputs


@dataclass(frozen=True, slots=True)
class ExecutionInputs:
    current: TargetInputs
    query: SyntheticExecutionQuery
    policy: SyntheticExecutionPolicy
    runtime_generation: str | None = None

    def __post_init__(self):
        exact(self.current, TargetInputs)
        exact(self.query, SyntheticExecutionQuery)
        exact(self.policy, SyntheticExecutionPolicy)
        if self.runtime_generation is not None:
            from quantharbor.domain.primitives import identifier
            identifier(self.runtime_generation)


class ExecutionCommands(Protocol):
    def dispatch(self, handle, intent_id): ...
    def receive(self, event): ...
    def cancel(self, handle, intent_id, *, command_id, expected_version): ...
    def reconcile(self, handle, query): ...

    def dispatch_cancel(self,handle,command_id): ...
    def rebind(self,handle,query,*,market_inputs=None,execution_policy=None): ...
    def control(self,handle,action): ...

    def cancel_receipt(self,handle,command_id,*,intent_id,expected_version): ...

    def resolve_unsent(self,handle,intent_id): ...

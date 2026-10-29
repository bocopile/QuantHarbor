"""Q24 명시 객체 입력과 append/get 포트. 경로/네트워크/실행 포트 없음."""
from dataclasses import dataclass
from typing import Protocol

from quantharbor.domain.ledger import LedgerEvent, exact, items
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import FlowBoundary, PerformanceResult, TradeCostFact
from quantharbor.domain.target import (MAX_INPUTS, OrderCandidate, SyntheticObligationSource,
    SyntheticStrategyProposal, SyntheticTargetFacts, SyntheticTargetPolicy, TargetBuildResult, TargetPlan)
from quantharbor.ports.research import ResearchPointInput


@dataclass(frozen=True, slots=True)
class TargetInputs:
    current: ResearchPointInput
    events: tuple[LedgerEvent, ...]
    policy: SyntheticTargetPolicy | None
    facts: SyntheticTargetFacts | None
    strategy: SyntheticStrategyProposal
    risk_points: tuple[ResearchPointInput, ...]
    performance: PerformanceResult
    obligation_sources: tuple[SyntheticObligationSource, ...] = ()
    costs: tuple[TradeCostFact, ...] = ()
    boundaries: tuple[FlowBoundary, ...] = ()
    boundary_inputs: tuple[ResearchPointInput, ...] = ()
    daily_usage_inputs: tuple[ResearchPointInput, ...] = ()

    def __post_init__(self):
        for obj, cls in ((self.current, ResearchPointInput), (self.strategy, SyntheticStrategyProposal),
                         (self.performance, PerformanceResult)):
            exact(obj, cls)
        for obj, cls in ((self.policy, SyntheticTargetPolicy), (self.facts, SyntheticTargetFacts)):
            if obj is not None:
                exact(obj, cls)
        for values, cls in ((self.events, LedgerEvent), (self.risk_points, ResearchPointInput),
                (self.obligation_sources, SyntheticObligationSource), (self.costs, TradeCostFact),
                (self.boundaries, FlowBoundary), (self.boundary_inputs, ResearchPointInput),
                (self.daily_usage_inputs, ResearchPointInput)):
            items(values, cls, MAX_INPUTS)
        if len({x.source_id for x in self.obligation_sources}) != len(self.obligation_sources):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class TargetArtifacts:
    plan: TargetPlan
    candidates: tuple[OrderCandidate, ...]
    result: TargetBuildResult


class TargetRepository(Protocol):
    def append(self, artifacts: TargetArtifacts) -> TargetArtifacts: ...

    def get(self, reference, *, environment: str, account_ref: str): ...

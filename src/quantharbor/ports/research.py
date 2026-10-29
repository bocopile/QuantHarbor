"""명시 객체 주입. 임의 경로·계좌·브로커 또는 네트워크 포트는 없다."""
from dataclasses import dataclass
from typing import Protocol

from quantharbor.domain.ledger import LedgerEvent, choice, exact, items
from quantharbor.domain.research import (ComparisonSpec, ExperimentRegistry, ExperimentResult,
    ExecutionTrace, FlowBoundary, ImplementationFingerprint, TradeCostFact, MAX_INPUTS, STRATEGIES)
from quantharbor.domain.valuation import PortfolioSnapshot
from quantharbor.ports.valuation import MarketDatasetInput


@dataclass(frozen=True, slots=True)
class ResearchPointInput:
    snapshot: PortfolioSnapshot
    market_inputs: tuple[MarketDatasetInput, ...]

    def __post_init__(self):
        exact(self.snapshot, PortfolioSnapshot)
        items(self.market_inputs, MarketDatasetInput, MAX_INPUTS)


@dataclass(frozen=True, slots=True)
class ExperimentInputs:
    spec: ComparisonSpec
    registry: ExperimentRegistry
    fingerprint: ImplementationFingerprint
    market_id: str
    scenario_id: str
    fold_id: str
    strategy: str
    points: tuple[ResearchPointInput, ...]
    events: tuple[LedgerEvent, ...]
    costs: tuple[TradeCostFact, ...]
    trace: ExecutionTrace
    boundaries: tuple[FlowBoundary, ...] = ()
    boundary_inputs: tuple[ResearchPointInput, ...] = ()

    def __post_init__(self):
        choice(self.market_id, ('KR', 'US'))
        choice(self.scenario_id, ('explicit_costs', 'zero_cost_control'))
        choice(self.fold_id, ('fold01', 'fold02'))
        choice(self.strategy, STRATEGIES)
        for value, cls in ((self.spec, ComparisonSpec), (self.registry, ExperimentRegistry),
                           (self.fingerprint, ImplementationFingerprint), (self.trace, ExecutionTrace)):
            exact(value, cls)
        for values, cls in ((self.points, ResearchPointInput), (self.events, LedgerEvent),
                            (self.costs, TradeCostFact), (self.boundaries, FlowBoundary),
                            (self.boundary_inputs, ResearchPointInput)):
            items(values, cls, MAX_INPUTS)


class ExperimentRepository(Protocol):
    def append(self, result: ExperimentResult) -> ExperimentResult: ...

    def get(self, result_id: str, *, environment: str, account_ref: str) -> ExperimentResult | None: ...

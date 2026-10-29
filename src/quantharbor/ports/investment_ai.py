"""명시 typed 원천만 주입한다. 경로/URL/명령/실행 도구 포트 없음."""
from dataclasses import dataclass
from typing import Protocol

from quantharbor.domain.catalog import Catalog
from quantharbor.domain.documents import DocumentBundle
from quantharbor.domain.investment_ai import AIRef, Usage
from quantharbor.domain.ledger import LedgerEvent, exact, items
from quantharbor.domain.market_data import RightsGrant
from quantharbor.domain.research import FlowBoundary, PerformanceResult, TradeCostFact
from quantharbor.domain.target import TargetRequest
from quantharbor.ports.research import ResearchPointInput
from quantharbor.ports.target import TargetArtifacts, TargetInputs


@dataclass(frozen=True, slots=True)
class DocumentSource:
    bundle: DocumentBundle
    catalog: Catalog
    current_rights: RightsGrant

    def __post_init__(self):
        for v,t in ((self.bundle,DocumentBundle),(self.catalog,Catalog),(self.current_rights,RightsGrant)):
            exact(v,t)


@dataclass(frozen=True, slots=True)
class FinancialSource:
    points: tuple[ResearchPointInput, ...]
    events: tuple[LedgerEvent, ...]
    performance: PerformanceResult | None = None
    boundaries: tuple[FlowBoundary, ...] = ()
    boundary_inputs: tuple[ResearchPointInput, ...] = ()
    costs: tuple[TradeCostFact, ...] = ()
    benchmark: 'FinancialSource | None' = None

    def __post_init__(self):
        for vs,t in ((self.points,ResearchPointInput),(self.events,LedgerEvent),(self.boundaries,FlowBoundary),
                     (self.boundary_inputs,ResearchPointInput),(self.costs,TradeCostFact)):
            items(vs,t,128)
        if self.performance is not None:
            exact(self.performance,PerformanceResult)
        if self.benchmark is not None:
            exact(self.benchmark,FinancialSource)
            if self.benchmark.benchmark is not None:
                from quantharbor.domain.primitives import ContractError
                raise ContractError()


@dataclass(frozen=True, slots=True)
class CandidateSource:
    request: TargetRequest
    inputs: TargetInputs
    artifacts: TargetArtifacts

    def __post_init__(self):
        for v,t in ((self.request,TargetRequest),(self.inputs,TargetInputs),(self.artifacts,TargetArtifacts)):
            exact(v,t)


@dataclass(frozen=True, slots=True)
class ClientReply:
    payload: bytes
    usage: Usage | None

    def __post_init__(self):
        from quantharbor.domain.primitives import ContractError
        if type(self.payload) is not bytes or len(self.payload)>65536:
            raise ContractError()
        if self.usage is not None:
            exact(self.usage,Usage)


class InvestmentAIClient(Protocol):
    def invoke(self, request, attempt, dispatcher) -> ClientReply: ...


class AIRepository(Protocol):
    def append(self, kind: str, identity: str, obj): ...
    def get(self, reference: AIRef): ...

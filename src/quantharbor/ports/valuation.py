"""Q21 append/get 읽기 모델 저장 포트. 운영 DB·계좌·주문 포트가 아니다."""
from dataclasses import dataclass, fields, replace
from typing import Protocol

from quantharbor.domain.calendar import MarketCalendar, TradingDay, TradingSession
from quantharbor.domain.catalog import Catalog, Instrument, SymbolMapping
from quantharbor.domain.ledger import exact
from quantharbor.domain.market_data import RightsGrant
from quantharbor.domain.market_storage import StorageBundle
from quantharbor.domain.valuation import PortfolioSnapshot
from quantharbor.market_data.timezones import ExplicitTimezone


@dataclass(frozen=True, slots=True)
class MarketDatasetInput:
    bundle: StorageBundle
    catalog: Catalog
    calendar: MarketCalendar
    timezone: ExplicitTimezone
    current_rights: RightsGrant

    def __post_init__(self):
        for value, kind in ((self.bundle, StorageBundle), (self.catalog, Catalog),
                            (self.calendar, MarketCalendar), (self.current_rights, RightsGrant)):
            exact(value, kind)
        for value in self.catalog.instruments:
            exact(value, Instrument)
        for value in self.catalog.mappings:
            exact(value, SymbolMapping)
        for day in self.calendar.days:
            exact(day, TradingDay)
            for session in day.sessions:
                exact(session, TradingSession)
        object.__setattr__(self, 'catalog', replace(self.catalog,
            instruments=tuple(replace(x) for x in self.catalog.instruments),
            mappings=tuple(replace(x) for x in self.catalog.mappings)))
        object.__setattr__(self, 'calendar', replace(self.calendar,
            days=tuple(replace(day, sessions=tuple(replace(x) for x in day.sessions)) for day in self.calendar.days)))
        object.__setattr__(self, 'current_rights', replace(self.current_rights))
        if type(self.timezone) is not ExplicitTimezone:
            from quantharbor.domain.primitives import ContractError
            raise ContractError()
        # _zone is derived from pinned TZif; caller-mutated cached zone is never consumed.
        object.__setattr__(self, 'timezone', ExplicitTimezone(**{f.name: getattr(self.timezone, f.name)
                           for f in fields(ExplicitTimezone) if f.init}))


class SnapshotRepository(Protocol):
    def append(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot: ...

    def get(self, snapshot_id: str, *, environment: str, account_ref: str) -> PortfolioSnapshot | None: ...

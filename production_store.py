from dataclasses import asdict, dataclass
from typing import Any, Iterable, List, Optional

from tracker_v2 import Database, get_default_db_path


@dataclass
class ProductionProvenance:
    run_id: str
    source_id: str
    source_url: str
    snapshot_path: str
    source_type: str
    collection_method: str
    observed_at: str
    fetched_at: str
    raw_payload_hash: str
    is_production_eligible: bool
    confidence: float
    error_code: Optional[str]

    def to_dict(self):
        return asdict(self)


@dataclass
class GpuPriceObservation(ProductionProvenance):
    date: str
    provider: str
    gpu_model: str
    gpu_variant: str
    billing_type: str
    commitment: str
    gpu_count: int
    region: str
    price_per_gpu_hour: float
    currency: str
    availability_observed: bool


@dataclass
class CapexActualObservation(ProductionProvenance):
    ticker: str
    company: str
    period_start: str
    period_end: str
    fiscal_period: str
    fiscal_year: int
    xbrl_tag: str
    accession_no: str
    capex_value: float
    unit: str
    filed_at: str
    form_type: str


@dataclass
class OfficialEventObservation(ProductionProvenance):
    ticker: str
    announcement_date: str
    event_type: str
    metric: str
    value: Optional[float]
    unit: str
    description: str
    fiscal_period: str


@dataclass
class PublicProxyPriceObservation(ProductionProvenance):
    date: str
    provider: str
    proxy_name: str
    metric: str
    value: float
    unit: str
    gpu_model: str
    region: str


@dataclass
class MarketFactObservation(ProductionProvenance):
    date: str
    track: str
    entity: str
    sub_entity: str
    metric: str
    value: float
    unit: str
    dimension: str
    vendor: str
    source_name: str
    notes: str


@dataclass
class DataQualityEvent(ProductionProvenance):
    event_id: str
    table_name: str
    severity: str
    message: str
    affected_key: str
    is_blocking: bool


@dataclass
class PipelineRun(ProductionProvenance):
    pipeline_name: str
    status: str
    started_at: str
    completed_at: Optional[str]
    rows_loaded: int
    message: str


class ProductionStore:
    """Thin integration surface over T1 Database production inserts."""

    def __init__(self, database: Optional[Database] = None, db_path: Optional[str] = None):
        self.database = database if database is not None else Database(db_path or get_default_db_path())

    @staticmethod
    def _records(observations: Iterable[Any]) -> List[Any]:
        return list(observations)

    def insert_gpu_prices(self, observations: Iterable[GpuPriceObservation]) -> int:
        return self.database.insert_production_gpu_prices(self._records(observations))

    def insert_capex_actuals(self, observations: Iterable[CapexActualObservation]) -> int:
        return self.database.insert_production_capex_actuals(self._records(observations))

    def insert_official_events(self, observations: Iterable[OfficialEventObservation]) -> int:
        return self.database.insert_production_official_events(self._records(observations))

    def insert_public_proxy_prices(self, observations: Iterable[PublicProxyPriceObservation]) -> int:
        return self.database.insert_production_public_proxy_prices(self._records(observations))

    def insert_market_facts(self, observations: Iterable[MarketFactObservation]) -> int:
        return self.database.insert_production_market_facts(self._records(observations))

    def insert_quality_events(self, observations: Iterable[DataQualityEvent]) -> int:
        return self.database.insert_production_data_quality_events(self._records(observations))

    def insert_pipeline_runs(self, observations: Iterable[PipelineRun]) -> int:
        return self.database.insert_production_pipeline_runs(self._records(observations))

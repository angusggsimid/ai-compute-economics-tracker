from dataclasses import dataclass
from typing import Dict, List


class CompanyConfigError(ValueError):
    """公司配置缺失或不完整。"""


@dataclass(frozen=True)
class CompanyConfig:
    ticker: str
    company_name: str
    cik: str
    fiscal_year_end_convention: str
    capex_xbrl_tag: str
    included_in_decision_universe: bool

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cik": self.cik,
            "fiscal_year_end_convention": self.fiscal_year_end_convention,
            "capex_xbrl_tag": self.capex_xbrl_tag,
            "included_in_decision_universe": self.included_in_decision_universe,
        }


COMPANY_CONFIGS: Dict[str, CompanyConfig] = {
    "MSFT": CompanyConfig(
        ticker="MSFT",
        company_name="Microsoft",
        cik="0000789019",
        fiscal_year_end_convention="fiscal_year_ends_june_30",
        capex_xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        included_in_decision_universe=True,
    ),
    "AMZN": CompanyConfig(
        ticker="AMZN",
        company_name="Amazon",
        cik="0001018724",
        fiscal_year_end_convention="calendar_year_ends_december_31",
        capex_xbrl_tag="PaymentsToAcquireProductiveAssets",
        included_in_decision_universe=True,
    ),
    "GOOGL": CompanyConfig(
        ticker="GOOGL",
        company_name="Alphabet",
        cik="0001652044",
        fiscal_year_end_convention="calendar_year_ends_december_31",
        capex_xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        included_in_decision_universe=True,
    ),
    "META": CompanyConfig(
        ticker="META",
        company_name="Meta",
        cik="0001326801",
        fiscal_year_end_convention="calendar_year_ends_december_31",
        capex_xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        included_in_decision_universe=True,
    ),
    "ORCL": CompanyConfig(
        ticker="ORCL",
        company_name="Oracle",
        cik="0001341439",
        fiscal_year_end_convention="fiscal_year_ends_may_31",
        capex_xbrl_tag="PaymentsToAcquirePropertyPlantAndEquipment",
        included_in_decision_universe=True,
    ),
}


def allowed_tickers() -> List[str]:
    return sorted(COMPANY_CONFIGS)


def get_company_config(ticker: str) -> CompanyConfig:
    normalized = (ticker or "").strip().upper()
    config = COMPANY_CONFIGS.get(normalized)
    if config is None:
        allowed = ", ".join(allowed_tickers())
        raise CompanyConfigError(
            f"COMPANY_CONFIG_MISSING: ticker={ticker!r}; allowed tickers: {allowed}."
        )
    return config


def decision_universe_configs() -> List[CompanyConfig]:
    return [
        config
        for config in COMPANY_CONFIGS.values()
        if config.included_in_decision_universe
    ]


def validate_company_configs() -> None:
    for ticker, config in COMPANY_CONFIGS.items():
        missing = [
            field_name
            for field_name, value in config.to_dict().items()
            if value in (None, "")
        ]
        if missing:
            raise CompanyConfigError(
                f"COMPANY_CONFIG_MISSING: ticker={ticker}; missing fields: {missing}."
            )

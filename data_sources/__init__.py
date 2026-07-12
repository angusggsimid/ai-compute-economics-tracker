PRODUCTION_UPDATE_TARGETS = (
    "gpu-prices",
    "capex-actuals",
    "official-events",
    "public-proxy-prices",
    "market-facts",
)


def allowed_production_update_values() -> str:
    return ", ".join(PRODUCTION_UPDATE_TARGETS)


def validate_production_update_target(target: str) -> None:
    if target not in PRODUCTION_UPDATE_TARGETS:
        raise ValueError(
            f"UNKNOWN_PRODUCTION_ONLY: {target!r}; allowed values: "
            f"{allowed_production_update_values()}."
        )

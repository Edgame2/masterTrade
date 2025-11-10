"""Strategy environment configuration backed by PostgreSQL."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from database import Database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrategyEnvironmentConfig(BaseModel):
    """Configuration for assigning strategies to environments."""

    strategy_id: int
    environment: str
    max_position_size: Optional[float] = None
    max_daily_trades: Optional[int] = None
    risk_multiplier: float = 1.0
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class EnvironmentConfigManager:
    """Manage strategy environment settings stored in PostgreSQL."""

    def __init__(self, database: Database):
        self.database = database
        self._config_cache: Dict[int, StrategyEnvironmentConfig] = {}

    async def set_strategy_environment(
        self,
        strategy_id: int,
        environment: str,
        *,
        max_position_size: Optional[float] = None,
        max_daily_trades: Optional[int] = None,
        risk_multiplier: float = 1.0,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StrategyEnvironmentConfig:
        if environment not in {"testnet", "production"}:
            raise ValueError("Environment must be 'testnet' or 'production'")

        record = await self.database.upsert_strategy_environment_config(
            strategy_id=strategy_id,
            environment=environment,
            max_position_size=max_position_size,
            max_daily_trades=max_daily_trades,
            risk_multiplier=risk_multiplier,
            enabled=enabled,
            metadata=metadata,
        )
        config = StrategyEnvironmentConfig(**record)
        self._config_cache[strategy_id] = config
        return config

    async def get_strategy_environment(self, strategy_id: int) -> str:
        config = await self.get_strategy_environment_config(strategy_id)
        if config and config.enabled:
            return config.environment
        return "testnet"

    async def get_strategy_environment_config(self, strategy_id: int) -> Optional[StrategyEnvironmentConfig]:
        if strategy_id in self._config_cache:
            return self._config_cache[strategy_id]

        record = await self.database.get_strategy_environment_config(strategy_id)
        if record:
            config = StrategyEnvironmentConfig(**record)
            self._config_cache[strategy_id] = config
            return config
        return None

    async def get_strategy_config(self, strategy_id: int) -> Optional[StrategyEnvironmentConfig]:
        return await self.get_strategy_environment_config(strategy_id)

    async def get_all_configurations(self) -> List[StrategyEnvironmentConfig]:
        records = await self.database.get_all_strategy_environment_configs()
        configs = [StrategyEnvironmentConfig(**record) for record in records]
        for config in configs:
            self._config_cache[config.strategy_id] = config
        return configs

    async def get_strategies_by_environment(self, environment: str) -> List[int]:
        configs = await self.get_all_configurations()
        return [cfg.strategy_id for cfg in configs if cfg.environment == environment and cfg.enabled]

    async def disable_strategy(self, strategy_id: int) -> bool:
        config = await self.get_strategy_environment_config(strategy_id)
        if not config:
            return False
        return await self._set_enabled(strategy_id, config, False)

    async def enable_strategy(self, strategy_id: int) -> bool:
        config = await self.get_strategy_environment_config(strategy_id)
        if not config:
            return False
        return await self._set_enabled(strategy_id, config, True)

    async def _set_enabled(
        self,
        strategy_id: int,
        config: StrategyEnvironmentConfig,
        enabled: bool,
    ) -> bool:
        await self.set_strategy_environment(
            strategy_id,
            config.environment,
            max_position_size=config.max_position_size,
            max_daily_trades=config.max_daily_trades,
            risk_multiplier=config.risk_multiplier,
            enabled=enabled,
            metadata=config.metadata,
        )
        return True

    def clear_cache(self) -> None:
        self._config_cache.clear()

    async def get_environment_summary(self) -> Dict[str, Dict[str, Any]]:
        configs = await self.get_all_configurations()
        summary = {
            "testnet": {"total_strategies": 0, "enabled_strategies": 0, "strategy_ids": []},
            "production": {"total_strategies": 0, "enabled_strategies": 0, "strategy_ids": []},
        }

        for config in configs:
            env = config.environment
            if env not in summary:
                summary[env] = {"total_strategies": 0, "enabled_strategies": 0, "strategy_ids": []}
            summary[env]["total_strategies"] += 1
            summary[env]["strategy_ids"].append(config.strategy_id)
            if config.enabled:
                summary[env]["enabled_strategies"] += 1

        return summary
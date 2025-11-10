"""
Mock Database for API Gateway Development
Provides in-memory data structures that emulate Cosmos DB responses
so the gateway can operate without Azure connectivity.
"""

import asyncio
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import structlog

logger = structlog.get_logger()


class MockDatabase:
    """In-memory replacement for the Cosmos DB client used by the API Gateway"""

    def __init__(self):
        self.connected = False
        now = datetime.now(timezone.utc)

        # Seed strategies with sample metrics
        self._strategies: List[Dict[str, Any]] = [
            {
                "id": f"strategy_{i}",
                "name": f"Momentum Strategy {i}",
                "type": random.choice(["SMA", "RSI", "MACD"]),
                "is_active": i % 2 == 0,
                "created_at": (now - timedelta(days=i)).isoformat(),
                "updated_at": (now - timedelta(days=i // 2)).isoformat(),
                "performance": {
                    "sharpe": round(random.uniform(1.0, 2.5), 2),
                    "sortino": round(random.uniform(1.0, 2.8), 2),
                    "win_rate": round(random.uniform(45, 70), 1),
                },
            }
            for i in range(1, 11)
        ]

        # Sample orders and trades
        self._orders: List[Dict[str, Any]] = [
            {
                "id": str(uuid.uuid4()),
                "symbol": random.choice(["BTCUSDC", "ETHUSDC", "SOLUSDC"]),
                "side": random.choice(["BUY", "SELL"]),
                "order_type": "LIMIT",
                "status": random.choice(["NEW", "PARTIALLY_FILLED", "FILLED"]),
                "price": round(random.uniform(1000, 60000), 2),
                "quantity": round(random.uniform(0.1, 5), 4),
                "order_time": (now - timedelta(minutes=random.randint(1, 240))).isoformat(),
            }
            for _ in range(15)
        ]

        self._trades: List[Dict[str, Any]] = [
            {
                "id": str(uuid.uuid4()),
                "order_id": random.choice(self._orders)["id"],
                "symbol": random.choice(["BTCUSDC", "ETHUSDC", "SOLUSDC"]),
                "side": random.choice(["BUY", "SELL"]),
                "price": round(random.uniform(1000, 60000), 2),
                "quantity": round(random.uniform(0.05, 3), 4),
                "trade_time": (now - timedelta(minutes=random.randint(1, 180))).isoformat(),
            }
            for _ in range(20)
        ]

        self._signals: List[Dict[str, Any]] = [
            {
                "id": str(uuid.uuid4()),
                "strategy_id": random.choice(self._strategies)["id"],
                "symbol": random.choice(["BTCUSDC", "ETHUSDC", "SOLUSDC", "ADAUSDC"]),
                "signal_type": random.choice(["BUY", "SELL", "HOLD"]),
                "confidence": round(random.uniform(55, 95), 1),
                "timestamp": (now - timedelta(minutes=random.randint(1, 180))).isoformat(),
            }
            for _ in range(40)
        ]

        # Generate simple market data history per symbol
        self._market_data: Dict[str, List[Dict[str, Any]]] = {}
        for symbol in ["BTCUSDC", "ETHUSDC", "SOLUSDC", "ADAUSDC"]:
            price = random.uniform(10, 60000)
            datapoints: List[Dict[str, Any]] = []
            for i in range(120):
                price *= random.uniform(0.995, 1.005)
                datapoints.append(
                    {
                        "symbol": symbol,
                        "timestamp": (now - timedelta(minutes=i)).isoformat(),
                        "open_price": round(price * random.uniform(0.995, 1.002), 2),
                        "high_price": round(price * random.uniform(1.0, 1.01), 2),
                        "low_price": round(price * random.uniform(0.99, 1.0), 2),
                        "close_price": round(price, 2),
                        "volume": round(random.uniform(50, 5000), 2),
                    }
                )
            self._market_data[symbol] = datapoints

        self._trading_enabled = True
        self._strategy_env_configs: Dict[int, Dict[str, Any]] = {}

    async def connect(self):
        """Mock connect simply marks the database as available"""
        await asyncio.sleep(0)
        self.connected = True
        logger.info("Connected to mock API gateway database")

    async def disconnect(self):
        await asyncio.sleep(0)
        self.connected = False
        logger.info("Disconnected from mock API gateway database")

    # Dashboard operations
    async def get_dashboard_overview(self) -> Dict[str, Any]:
        await asyncio.sleep(0)
        now = datetime.now(timezone.utc)
        active_orders = [o for o in self._orders if o["status"] in {"NEW", "PARTIALLY_FILLED"}]
        recent_trades = [
            t for t in self._trades
            if datetime.fromisoformat(t["trade_time"]) >= now - timedelta(hours=24)
        ]
        recent_signals = [
            s for s in self._signals
            if datetime.fromisoformat(s["timestamp"]) >= now - timedelta(hours=24)
        ]
        portfolio_value = sum(t["price"] * t["quantity"] for t in recent_trades)

        return {
            "total_strategies": len(self._strategies),
            "active_strategies": len([s for s in self._strategies if s.get("is_active")]),
            "recent_signals": len(recent_signals),
            "active_orders": len(active_orders),
            "recent_trades": len(recent_trades),
            "portfolio_value": round(portfolio_value, 2),
            "last_updated": now.isoformat(),
        }

    async def get_portfolio_balance(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        now = datetime.now(timezone.utc).isoformat()
        return [
            {
                "account": "testnet",
                "balance": round(100000 + random.uniform(-5000, 5000), 2),
                "currency": "USDC",
                "updated_at": now,
            },
            {
                "account": "production",
                "balance": round(250000 + random.uniform(-15000, 15000), 2),
                "currency": "USDC",
                "updated_at": now,
            },
        ]

    # Strategy operations
    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        return list(self._strategies)

    async def toggle_strategy_status(self, strategy_id: str) -> bool:
        await asyncio.sleep(0)
        for strategy in self._strategies:
            if strategy["id"] == strategy_id:
                strategy["is_active"] = not strategy.get("is_active", False)
                strategy["updated_at"] = datetime.now(timezone.utc).isoformat()
                return True
        return False

    # Order operations
    async def get_active_orders(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        return [o for o in self._orders if o["status"] in {"NEW", "PARTIALLY_FILLED"}]

    async def get_recent_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        return sorted(self._orders, key=lambda o: o["order_time"], reverse=True)[:limit]

    # Trade operations
    async def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        return sorted(self._trades, key=lambda t: t["trade_time"], reverse=True)[:limit]

    # Signal operations
    async def get_recent_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        return sorted(self._signals, key=lambda s: s["timestamp"], reverse=True)[:limit]

    # Market data operations
    async def get_market_data(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        symbol = symbol.upper()
        data = self._market_data.get(symbol, [])
        return data[-limit:][::-1]

    # Trading configuration
    async def toggle_trading_enabled(self) -> bool:
        await asyncio.sleep(0)
        self._trading_enabled = not self._trading_enabled
        return self._trading_enabled

    # Strategy environment configuration
    async def set_strategy_environment(self, strategy_id: int, environment_config: dict) -> bool:
        await asyncio.sleep(0)
        self._strategy_env_configs[strategy_id] = {
            "strategy_id": strategy_id,
            "environment": environment_config.get("environment", "testnet"),
            "max_position_size": environment_config.get("max_position_size"),
            "max_daily_trades": environment_config.get("max_daily_trades"),
            "risk_multiplier": environment_config.get("risk_multiplier", 1.0),
            "enabled": environment_config.get("enabled", True),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return True

    async def get_strategy_environment_config(self, strategy_id: int) -> Optional[dict]:
        await asyncio.sleep(0)
        return self._strategy_env_configs.get(strategy_id)

    async def get_all_strategy_environment_configs(self) -> List[dict]:
        await asyncio.sleep(0)
        return list(self._strategy_env_configs.values())

    # Symbol/Crypto Management Operations
    async def get_all_symbols(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all tracked trading symbols/crypto pairs"""
        await asyncio.sleep(0)
        now = datetime.now(timezone.utc).isoformat()
        
        all_symbols = [
            {
                "id": "BTCUSDC",
                "symbol": "BTCUSDC",
                "base_asset": "BTC",
                "quote_asset": "USDC",
                "asset_type": "crypto",
                "exchange": "binance",
                "tracking": True,
                "active_for_trading": True,
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": now,
                "notes": "Bitcoin - Leading cryptocurrency"
            },
            {
                "id": "ETHUSDC",
                "symbol": "ETHUSDC",
                "base_asset": "ETH",
                "quote_asset": "USDC",
                "asset_type": "crypto",
                "exchange": "binance",
                "tracking": True,
                "active_for_trading": True,
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": now,
                "notes": "Ethereum - Smart contract platform"
            },
            {
                "id": "SOLUSDC",
                "symbol": "SOLUSDC",
                "base_asset": "SOL",
                "quote_asset": "USDC",
                "asset_type": "crypto",
                "exchange": "binance",
                "tracking": True,
                "active_for_trading": False,
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": now,
                "notes": "Solana - High-performance blockchain"
            },
            {
                "id": "ADAUSDC",
                "symbol": "ADAUSDC",
                "base_asset": "ADA",
                "quote_asset": "USDC",
                "asset_type": "crypto",
                "exchange": "binance",
                "tracking": False,
                "active_for_trading": False,
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": now,
                "notes": "Cardano - Proof-of-stake blockchain"
            },
            {
                "id": "XRPUSDC",
                "symbol": "XRPUSDC",
                "base_asset": "XRP",
                "quote_asset": "USDC",
                "asset_type": "crypto",
                "exchange": "binance",
                "tracking": True,
                "active_for_trading": True,
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": now,
                "notes": "Ripple - Payment settlement system"
            }
        ]
        
        if include_inactive:
            return all_symbols
        else:
            return [s for s in all_symbols if s.get("tracking", False)]
    
    async def get_symbol_tracking_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get tracking information for a specific symbol"""
        await asyncio.sleep(0)
        symbols = await self.get_all_symbols(include_inactive=True)
        for s in symbols:
            if s["symbol"] == symbol:
                return s
        return None
    
    async def toggle_symbol_tracking(self, symbol: str) -> bool:
        """Toggle tracking status for a symbol"""
        await asyncio.sleep(0)
        # In mock, just return success
        return True
    
    async def update_symbol_tracking(self, symbol: str, updates: Dict[str, Any]) -> bool:
        """Update symbol tracking configuration"""
        await asyncio.sleep(0)
        # In mock, just return success
        return True
    
    async def get_symbol_historical_stats(self, symbol: str) -> Dict[str, Any]:
        """Get historical data availability statistics for a symbol"""
        await asyncio.sleep(0)
        now = datetime.now(timezone.utc)
        
        return {
            "symbol": symbol,
            "intervals": {
                "1m": {
                    "record_count": random.randint(40000, 50000),
                    "earliest_data": (now - timedelta(days=30)).isoformat(),
                    "latest_data": now.isoformat(),
                    "has_data": True
                },
                "5m": {
                    "record_count": random.randint(8000, 10000),
                    "earliest_data": (now - timedelta(days=30)).isoformat(),
                    "latest_data": now.isoformat(),
                    "has_data": True
                },
                "15m": {
                    "record_count": random.randint(2500, 3500),
                    "earliest_data": (now - timedelta(days=30)).isoformat(),
                    "latest_data": now.isoformat(),
                    "has_data": True
                },
                "1h": {
                    "record_count": random.randint(700, 750),
                    "earliest_data": (now - timedelta(days=30)).isoformat(),
                    "latest_data": now.isoformat(),
                    "has_data": True
                },
                "4h": {
                    "record_count": random.randint(180, 190),
                    "earliest_data": (now - timedelta(days=30)).isoformat(),
                    "latest_data": now.isoformat(),
                    "has_data": True
                },
                "1d": {
                    "record_count": 30,
                    "earliest_data": (now - timedelta(days=30)).isoformat(),
                    "latest_data": now.isoformat(),
                    "has_data": True
                }
            }
        }


# Public alias so importing Database from this module matches production signature
Database = MockDatabase

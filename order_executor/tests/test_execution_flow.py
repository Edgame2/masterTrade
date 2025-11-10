import asyncio
import sys
import types
import uuid
import unittest
from datetime import datetime, timezone


if "aio_pika" not in sys.modules:  # Provide lightweight stub for optional dependency
    stub_module = types.ModuleType("aio_pika")

    class _StubMessage:
        def __init__(self, body, *, content_type=None, timestamp=None):
            self.body = body
            self.content_type = content_type
            self.timestamp = timestamp

    class _StubIncomingMessage:
        def __init__(self, body=b"{}"):  # pragma: no cover - simple placeholder
            self.body = body

        def process(self):  # pragma: no cover - exercised through service context manager
            class _Ctx:
                async def __aenter__(self_inner):
                    return self

                async def __aexit__(self_inner, exc_type, exc, tb):
                    return False

            return _Ctx()

    class _StubExchangeType:
        TOPIC = "topic"

    class _StubQueueIterator:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _StubQueue:
        async def bind(self, *_args, **_kwargs):
            return None

        def iterator(self):
            return _StubQueueIterator()

    async def _stub_connect_robust(*_args, **_kwargs):  # pragma: no cover
        raise RuntimeError("aio_pika stub cannot establish connections in tests")

    stub_module.Message = _StubMessage
    stub_module.IncomingMessage = _StubIncomingMessage
    stub_module.ExchangeType = _StubExchangeType
    stub_module.Queue = _StubQueue
    stub_module.connect_robust = _stub_connect_robust
    stub_module.Connection = object
    stub_module.Channel = object
    stub_module.Exchange = object

    sys.modules["aio_pika"] = stub_module

if "ccxt" not in sys.modules:  # Provide lightweight stub for ccxt async support
    ccxt_module = types.ModuleType("ccxt")
    async_support_module = types.ModuleType("ccxt.async_support")

    class _NetworkError(Exception):
        pass

    class _ExchangeError(Exception):
        pass

    async_support_module.NetworkError = _NetworkError
    async_support_module.ExchangeError = _ExchangeError
    async_support_module.Exchange = object

    ccxt_module.NetworkError = _NetworkError
    ccxt_module.ExchangeError = _ExchangeError
    ccxt_module.async_support = async_support_module

    sys.modules["ccxt"] = ccxt_module
    sys.modules["ccxt.async_support"] = async_support_module

if "structlog" not in sys.modules:  # Lightweight structlog stub for tests
    class _StubLogger:
        def __getattr__(self, _name):  # pragma: no cover - defensive hook
            return lambda *args, **kwargs: None

        def bind(self, *args, **kwargs):
            return self

    structlog_stub = types.SimpleNamespace(
        get_logger=lambda *args, **kwargs: _StubLogger(),
        configure=lambda *args, **kwargs: None,
        stdlib=types.SimpleNamespace(
            filter_by_level=lambda *args, **kwargs: None,
            add_logger_name=lambda *args, **kwargs: None,
            add_log_level=lambda *args, **kwargs: None,
            PositionalArgumentsFormatter=lambda *args, **kwargs: None,
            LoggerFactory=lambda *args, **kwargs: _StubLogger,
        ),
        processors=types.SimpleNamespace(
            TimeStamper=lambda *args, **kwargs: None,
            StackInfoRenderer=lambda *args, **kwargs: None,
            format_exc_info=lambda *args, **kwargs: None,
            UnicodeDecoder=lambda *args, **kwargs: None,
            JSONRenderer=lambda *args, **kwargs: None,
        ),
    )

    sys.modules["structlog"] = structlog_stub

if "prometheus_client" not in sys.modules:  # Minimal Prometheus stubs for tests
    class _StubMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

        def time(self):
            def _decorator(func):
                async def _async_wrapper(*args, **kwargs):
                    return await func(*args, **kwargs)

                return _async_wrapper

            return _decorator

    def _start_http_server(*args, **kwargs):
        return None

    prometheus_stub = types.SimpleNamespace(
        Counter=_StubMetric,
        Gauge=_StubMetric,
        Histogram=_StubMetric,
        start_http_server=_start_http_server,
        CONTENT_TYPE_LATEST="text/plain",
        generate_latest=lambda *args, **kwargs: b"",
    )

    sys.modules["prometheus_client"] = prometheus_stub

if "config" not in sys.modules:  # Provide lightweight settings for tests
    class _StubSettings:
        RABBITMQ_URL = "amqp://guest:guest@localhost/"
        SERVICE_NAME = "order_executor"
        STRATEGY_SERVICE_URL = "http://localhost:8001"
        PROMETHEUS_PORT = 8002

    sys.modules["config"] = types.SimpleNamespace(settings=_StubSettings())

if "database" not in sys.modules:  # Prevent heavy database dependencies during import
    class _DatabaseDependencyStub:
        def __init__(self, *args, **kwargs):
            pass

        async def connect(self):  # pragma: no cover - not used in tests
            raise RuntimeError("Database stub should not be used in tests")

    sys.modules["database"] = types.SimpleNamespace(Database=_DatabaseDependencyStub)

if "models" not in sys.modules:
    from order_executor import models as _order_models

    sys.modules["models"] = _order_models

class _ExchangeManagerDependencyStub:
    async def initialize(self):  # pragma: no cover - import-time usage only
        return None

    async def close(self):
        return None

    def get_exchange(self, *_args, **_kwargs):
        return None


if "exchange_manager" not in sys.modules:
    sys.modules["exchange_manager"] = types.SimpleNamespace(
        ExchangeManager=_ExchangeManagerDependencyStub
    )


class _EnvironmentConfigManagerDependencyStub:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_strategy_environment_config(self, *_args, **_kwargs):
        return None


if "strategy_environment_manager" not in sys.modules:
    sys.modules["strategy_environment_manager"] = types.SimpleNamespace(
        EnvironmentConfigManager=_EnvironmentConfigManagerDependencyStub
    )

if "order_manager" not in sys.modules:
    from order_executor import order_manager as _order_manager_module

    sys.modules["order_manager"] = _order_manager_module

from order_executor.main import OrderExecutorService
from order_executor.models import Order, OrderRequest
from order_executor.order_manager import OrderManager


class _StubDatabase:
    def __init__(self):
        self.created_orders = []
        self.exchange_updates = []
        self.status_updates = []

    async def connect(self):
        return True

    async def create_order(self, order_request: OrderRequest) -> Order:
        order = Order(
            id=uuid.uuid4(),
            strategy_id=order_request.strategy_id,
            symbol=order_request.symbol,
            signal_id=order_request.signal_id,
            exchange_order_id=None,
            client_order_id=order_request.client_order_id,
            order_type=order_request.order_type,
            side=order_request.side,
            quantity=order_request.quantity,
            price=order_request.price,
            stop_price=order_request.stop_price,
            status="NEW",
            filled_quantity=0.0,
            avg_fill_price=None,
            commission=0.0,
            commission_asset=None,
            environment=order_request.environment,
            order_time=datetime.now(timezone.utc),
            update_time=None,
        )
        self.created_orders.append(order)
        return order

    async def update_order_exchange_info(self, order_id: uuid.UUID, exchange_order_id: str) -> bool:
        self.exchange_updates.append((order_id, exchange_order_id))
        return True

    async def update_order_status(self, order_id: uuid.UUID, status: str) -> bool:
        self.status_updates.append((order_id, status))
        return True

    async def update_order_from_exchange(self, order_id: uuid.UUID, exchange_order: dict) -> bool:
        return True

    async def insert_trade(self, trade):
        return True

    async def update_portfolio_from_trade(self, order: Order, exchange_order: dict) -> bool:
        return True

    async def get_active_orders(self):
        return []


class _StubExchangeManager:
    def __init__(self):
        self.created_orders = []

    async def initialize(self):
        return True

    def get_exchange(self, environment: str):
        return self

    async def create_order(self, symbol, order_type, side, quantity, price, *, environment, **_kwargs):
        order = {
            "id": f"ex-{uuid.uuid4().hex[:8]}",
            "status": "open",
            "filled": 0.0,
            "average": price,
            "trades": [],
        }
        self.created_orders.append((environment, order))
        return order

    async def fetch_order(self, order_id, symbol):
        return {
            "id": order_id,
            "symbol": symbol,
            "status": "open",
            "filled": 0.0,
            "trades": [],
        }


class _StubEnvironmentConfigManager:
    async def get_strategy_environment_config(self, _strategy_id: int):
        return None


class _StubExchangeChannel:
    def __init__(self):
        self.published = []

    async def publish(self, message, routing_key: str):
        self.published.append((message, routing_key))


class OrderExecutionFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.database = _StubDatabase()
        self.exchange_manager = _StubExchangeManager()
        self.env_manager = _StubEnvironmentConfigManager()

        self.service = OrderExecutorService()
        self.service.database = self.database
        self.service.exchange_manager = self.exchange_manager
        self.service.env_config_manager = self.env_manager
        self.service.order_manager = OrderManager()
        await self.service.order_manager.initialize(self.database, self.exchange_manager)

        stub_channel = _StubExchangeChannel()
        self.service.exchanges = {
            "trading": _StubExchangeChannel(),
            "orders": stub_channel,
            "risk": _StubExchangeChannel(),
        }
        self.orders_channel = stub_channel

    async def test_execute_order_tracks_and_publishes(self):
        order_request = OrderRequest(
            strategy_id=42,
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0.5,
            price=45000.0,
            environment="testnet",
        )

        await self.service._execute_order(order_request)

        self.assertEqual(len(self.database.created_orders), 1)
        self.assertEqual(len(self.database.exchange_updates), 1)
        tracked_orders = await self.service.order_manager.snapshot()
        self.assertEqual(len(tracked_orders), 1)
        self.assertEqual(len(self.orders_channel.published), 1)


if __name__ == "__main__":
    unittest.main()

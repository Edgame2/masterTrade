"""
Arbitrage Service - Cross-chain and cross-exchange arbitrage opportunities

This service monitors price differences across exchanges and chains to identify
profitable arbitrage opportunities, with special focus on Gnosis Chain.
"""

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN

import aio_pika
import ccxt.async_support as ccxt
import structlog
from aiohttp import web
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from web3 import AsyncWeb3
import networkx as nx

from config import settings
from database import Database
from models import ArbitrageOpportunity, CrossChainRoute, DEXPrice, FlashLoanOpportunity
from dex_handlers import UniswapV2Handler, UniswapV3Handler, CurveHandler, BalancerHandler
from flash_loan_handler import FlashLoanHandler
from gas_optimizer import GasOptimizer
from cross_chain_monitor import CrossChainMonitor

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Prometheus Metrics
arbitrage_opportunities_found = Counter('arbitrage_opportunities_total', 'Total arbitrage opportunities found', ['type', 'chain'])
arbitrage_profit_usd = Counter('arbitrage_profit_usd_total', 'Total arbitrage profit in USD', ['type', 'chain'])
arbitrage_execution_time = Histogram('arbitrage_execution_seconds', 'Time to execute arbitrage')
active_monitors = Gauge('active_arbitrage_monitors', 'Number of active arbitrage monitors')
gas_price_tracker = Gauge('gas_price_gwei', 'Current gas price in Gwei', ['chain'])
dex_price_updates = Counter('dex_price_updates_total', 'DEX price updates processed', ['dex', 'pair'])


class ArbitrageService:
    """Main service class for arbitrage detection and execution"""
    
    def __init__(self):
        self.database = Database()
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        
        # Exchange connections
        self.cex_exchanges: Dict[str, ccxt.Exchange] = {}
        
        # Blockchain connections
        self.web3_connections: Dict[str, AsyncWeb3] = {}
        
        # DEX handlers
        self.dex_handlers: Dict[str, Dict] = {}
        
        # Specialized handlers
        self.flash_loan_handler = FlashLoanHandler()
        self.gas_optimizer = GasOptimizer()
        self.cross_chain_monitor = CrossChainMonitor()
        
        # Price tracking
        self.price_cache: Dict[str, Dict] = {}
        self.arbitrage_graph = nx.DiGraph()
        
        self.running = False
        self.monitor_tasks: List[asyncio.Task] = []
        
    async def initialize(self):
        """Initialize all connections and services"""
        try:
            # Initialize database
            await self.database.connect()
            
            # Initialize blockchain connections
            await self._init_blockchain_connections()
            
            # Initialize CEX exchanges
            await self._init_cex_exchanges()
            
            # Initialize DEX handlers
            await self._init_dex_handlers()
            
            # Initialize RabbitMQ
            await self._init_rabbitmq()
            
            # Initialize specialized handlers
            await self.flash_loan_handler.initialize(self.web3_connections)
            await self.gas_optimizer.initialize(self.web3_connections)
            await self.cross_chain_monitor.initialize()
            
            logger.info("Arbitrage service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize service", error=str(e))
            raise
    
    async def _init_blockchain_connections(self):
        """Initialize Web3 connections for different chains"""
        try:
            # Gnosis Chain (primary focus)
            self.web3_connections['gnosis'] = AsyncWeb3(
                AsyncWeb3.AsyncHTTPProvider(settings.GNOSIS_RPC_URL)
            )
            
            # Ethereum Mainnet
            self.web3_connections['ethereum'] = AsyncWeb3(
                AsyncWeb3.AsyncHTTPProvider(settings.ETHEREUM_RPC_URL)
            )
            
            # Polygon
            self.web3_connections['polygon'] = AsyncWeb3(
                AsyncWeb3.AsyncHTTPProvider(settings.POLYGON_RPC_URL)
            )
            
            # Arbitrum
            self.web3_connections['arbitrum'] = AsyncWeb3(
                AsyncWeb3.AsyncHTTPProvider(settings.ARBITRUM_RPC_URL)
            )
            
            # BSC
            self.web3_connections['bsc'] = AsyncWeb3(
                AsyncWeb3.AsyncHTTPProvider(settings.BSC_RPC_URL)
            )
            
            # Test connections
            for chain, w3 in self.web3_connections.items():
                block_number = await w3.eth.block_number
                logger.info(f"Connected to {chain}", block_number=block_number)
            
        except Exception as e:
            logger.error("Failed to initialize blockchain connections", error=str(e))
            raise
    
    async def _init_cex_exchanges(self):
        """Initialize centralized exchange connections"""
        try:
            # Binance
            self.cex_exchanges['binance'] = ccxt.binance({
                'apiKey': settings.BINANCE_API_KEY,
                'secret': settings.BINANCE_API_SECRET,
                'sandbox': settings.EXCHANGE_SANDBOX,
                'enableRateLimit': True,
            })
            
            # Coinbase Pro
            if settings.COINBASE_API_KEY:
                self.cex_exchanges['coinbase'] = ccxt.coinbasepro({
                    'apiKey': settings.COINBASE_API_KEY,
                    'secret': settings.COINBASE_API_SECRET,
                    'password': settings.COINBASE_PASSPHRASE,
                    'sandbox': settings.EXCHANGE_SANDBOX,
                    'enableRateLimit': True,
                })
            
            # Kraken
            if settings.KRAKEN_API_KEY:
                self.cex_exchanges['kraken'] = ccxt.kraken({
                    'apiKey': settings.KRAKEN_API_KEY,
                    'secret': settings.KRAKEN_API_SECRET,
                    'enableRateLimit': True,
                })
            
            # Load markets for all exchanges
            for name, exchange in self.cex_exchanges.items():
                await exchange.load_markets()
                logger.info(f"Initialized {name} exchange")
            
        except Exception as e:
            logger.error("Failed to initialize CEX exchanges", error=str(e))
            raise
    
    async def _init_dex_handlers(self):
        """Initialize DEX handlers for different chains"""
        try:
            for chain, w3 in self.web3_connections.items():
                self.dex_handlers[chain] = {}
                
                # Uniswap V2 style DEXes
                if chain == 'gnosis':
                    # HoneySwap (Uniswap V2 fork on Gnosis)
                    self.dex_handlers[chain]['honeyswap'] = UniswapV2Handler(
                        w3, settings.HONEYSWAP_FACTORY_ADDRESS, 'HoneySwap'
                    )
                    # SushiSwap on Gnosis
                    self.dex_handlers[chain]['sushiswap'] = UniswapV2Handler(
                        w3, settings.SUSHISWAP_GNOSIS_FACTORY, 'SushiSwap'
                    )
                
                elif chain == 'ethereum':
                    # Uniswap V2
                    self.dex_handlers[chain]['uniswap_v2'] = UniswapV2Handler(
                        w3, settings.UNISWAP_V2_FACTORY, 'Uniswap V2'
                    )
                    # Uniswap V3
                    self.dex_handlers[chain]['uniswap_v3'] = UniswapV3Handler(
                        w3, settings.UNISWAP_V3_FACTORY, 'Uniswap V3'
                    )
                    # SushiSwap
                    self.dex_handlers[chain]['sushiswap'] = UniswapV2Handler(
                        w3, settings.SUSHISWAP_FACTORY, 'SushiSwap'
                    )
                    # Curve
                    self.dex_handlers[chain]['curve'] = CurveHandler(
                        w3, 'Curve'
                    )
                    # Balancer
                    self.dex_handlers[chain]['balancer'] = BalancerHandler(
                        w3, 'Balancer'
                    )
                
                elif chain == 'polygon':
                    # QuickSwap
                    self.dex_handlers[chain]['quickswap'] = UniswapV2Handler(
                        w3, settings.QUICKSWAP_FACTORY, 'QuickSwap'
                    )
                    # SushiSwap on Polygon
                    self.dex_handlers[chain]['sushiswap'] = UniswapV2Handler(
                        w3, settings.SUSHISWAP_POLYGON_FACTORY, 'SushiSwap'
                    )
                
                # Initialize all handlers
                for dex_name, handler in self.dex_handlers[chain].items():
                    await handler.initialize()
                    logger.info(f"Initialized {dex_name} on {chain}")
            
        except Exception as e:
            logger.error("Failed to initialize DEX handlers", error=str(e))
            raise
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ connection and exchanges"""
        try:
            self.rabbitmq_connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            self.rabbitmq_channel = await self.rabbitmq_connection.channel()
            await self.rabbitmq_channel.set_qos(prefetch_count=20)
            
            # Declare exchanges
            self.exchanges['arbitrage'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.arbitrage', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            self.exchanges['market'] = await self.rabbitmq_channel.declare_exchange(
                'mastertrade.market', aio_pika.ExchangeType.TOPIC, durable=True
            )
            
            logger.info("RabbitMQ initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize RabbitMQ", error=str(e))
            raise
    
    async def start_monitoring(self):
        """Start arbitrage opportunity monitoring"""
        try:
            self.running = True
            
            # Start CEX price monitoring
            cex_task = asyncio.create_task(self._monitor_cex_prices())
            self.monitor_tasks.append(cex_task)
            
            # Start DEX price monitoring for each chain
            for chain in self.web3_connections.keys():
                dex_task = asyncio.create_task(self._monitor_dex_prices(chain))
                self.monitor_tasks.append(dex_task)
            
            # Start cross-chain opportunity monitoring
            cross_chain_task = asyncio.create_task(self._monitor_cross_chain_opportunities())
            self.monitor_tasks.append(cross_chain_task)
            
            # Start triangular arbitrage monitoring
            triangular_task = asyncio.create_task(self._monitor_triangular_arbitrage())
            self.monitor_tasks.append(triangular_task)
            
            # Start flash loan opportunity monitoring
            flash_loan_task = asyncio.create_task(self._monitor_flash_loan_opportunities())
            self.monitor_tasks.append(flash_loan_task)
            
            # Start gas price monitoring
            gas_task = asyncio.create_task(self._monitor_gas_prices())
            self.monitor_tasks.append(gas_task)
            
            active_monitors.set(len(self.monitor_tasks))
            logger.info(f"Started {len(self.monitor_tasks)} arbitrage monitors")
            
            # Keep running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("Error in arbitrage monitoring", error=str(e))
            raise
    
    async def _monitor_cex_prices(self):
        """Monitor centralized exchange prices"""
        while self.running:
            try:
                for exchange_name, exchange in self.cex_exchanges.items():
                    try:
                        # Fetch tickers for major pairs
                        tickers = await exchange.fetch_tickers()
                        
                        for symbol, ticker in tickers.items():
                            if symbol in settings.ARBITRAGE_PAIRS:
                                price_key = f"cex_{exchange_name}_{symbol}"
                                self.price_cache[price_key] = {
                                    'price': ticker['last'],
                                    'bid': ticker['bid'],
                                    'ask': ticker['ask'],
                                    'timestamp': datetime.now(timezone.utc),
                                    'exchange': exchange_name,
                                    'type': 'cex'
                                }
                        
                    except Exception as e:
                        logger.error(f"Error fetching prices from {exchange_name}", error=str(e))
                
                # Check for CEX-DEX arbitrage opportunities
                await self._check_cex_dex_arbitrage()
                
                await asyncio.sleep(settings.CEX_PRICE_UPDATE_INTERVAL)
                
            except Exception as e:
                logger.error("Error in CEX price monitoring", error=str(e))
                await asyncio.sleep(10)
    
    async def _monitor_dex_prices(self, chain: str):
        """Monitor DEX prices for a specific chain"""
        while self.running:
            try:
                for dex_name, handler in self.dex_handlers[chain].items():
                    try:
                        # Get prices for monitored pairs
                        for pair in settings.ARBITRAGE_PAIRS:
                            price_data = await handler.get_price(pair)
                            
                            if price_data:
                                price_key = f"dex_{chain}_{dex_name}_{pair}"
                                self.price_cache[price_key] = {
                                    'price': price_data['price'],
                                    'liquidity': price_data.get('liquidity', 0),
                                    'timestamp': datetime.now(timezone.utc),
                                    'chain': chain,
                                    'dex': dex_name,
                                    'type': 'dex'
                                }
                                
                                dex_price_updates.labels(dex=dex_name, pair=pair).inc()
                        
                    except Exception as e:
                        logger.error(f"Error fetching prices from {dex_name} on {chain}", error=str(e))
                
                # Check for intra-chain arbitrage opportunities
                await self._check_intra_chain_arbitrage(chain)
                
                await asyncio.sleep(settings.DEX_PRICE_UPDATE_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in DEX price monitoring for {chain}", error=str(e))
                await asyncio.sleep(10)
    
    async def _check_cex_dex_arbitrage(self):
        """Check for arbitrage opportunities between CEX and DEX"""
        try:
            for pair in settings.ARBITRAGE_PAIRS:
                cex_prices = {}
                dex_prices = {}
                
                # Collect CEX prices
                for key, data in self.price_cache.items():
                    if key.startswith('cex_') and pair in key:
                        exchange = data['exchange']
                        cex_prices[exchange] = data
                
                # Collect DEX prices
                for key, data in self.price_cache.items():
                    if key.startswith('dex_') and pair in key:
                        dex_key = f"{data['chain']}_{data['dex']}"
                        dex_prices[dex_key] = data
                
                # Find arbitrage opportunities
                for cex_name, cex_data in cex_prices.items():
                    for dex_key, dex_data in dex_prices.items():
                        await self._evaluate_arbitrage_opportunity(
                            pair, cex_data, dex_data, 'cex_dex'
                        )
                        
        except Exception as e:
            logger.error("Error checking CEX-DEX arbitrage", error=str(e))
    
    async def _check_intra_chain_arbitrage(self, chain: str):
        """Check for arbitrage opportunities within a single chain"""
        try:
            chain_dex_prices = {}
            
            # Collect DEX prices for this chain
            for key, data in self.price_cache.items():
                if key.startswith(f'dex_{chain}_'):
                    for pair in settings.ARBITRAGE_PAIRS:
                        if pair in key:
                            if pair not in chain_dex_prices:
                                chain_dex_prices[pair] = {}
                            chain_dex_prices[pair][data['dex']] = data
            
            # Find arbitrage opportunities between DEXes
            for pair, dex_prices in chain_dex_prices.items():
                dex_list = list(dex_prices.items())
                for i in range(len(dex_list)):
                    for j in range(i + 1, len(dex_list)):
                        dex1_name, dex1_data = dex_list[i]
                        dex2_name, dex2_data = dex_list[j]
                        
                        await self._evaluate_arbitrage_opportunity(
                            pair, dex1_data, dex2_data, f'intra_chain_{chain}'
                        )
                        
        except Exception as e:
            logger.error(f"Error checking intra-chain arbitrage for {chain}", error=str(e))
    
    async def _evaluate_arbitrage_opportunity(self, pair: str, source_data: Dict, 
                                           target_data: Dict, arb_type: str):
        """Evaluate if an arbitrage opportunity is profitable"""
        try:
            source_price = source_data['price']
            target_price = target_data['price']
            
            # Calculate price difference percentage
            price_diff = abs(source_price - target_price) / min(source_price, target_price) * 100
            
            if price_diff < settings.MIN_ARBITRAGE_PROFIT_PERCENT:
                return
            
            # Determine direction (buy low, sell high)
            if source_price < target_price:
                buy_price = source_price
                sell_price = target_price
                buy_venue = source_data
                sell_venue = target_data
            else:
                buy_price = target_price
                sell_price = source_price
                buy_venue = target_data
                sell_venue = source_data
            
            # Calculate potential profit
            profit_percent = (sell_price - buy_price) / buy_price * 100
            
            # Estimate transaction costs
            gas_cost = await self._estimate_transaction_costs(buy_venue, sell_venue)
            
            # Calculate net profit
            trade_amount = await self._calculate_optimal_trade_amount(
                pair, buy_venue, sell_venue
            )
            
            gross_profit = (sell_price - buy_price) * trade_amount
            net_profit = gross_profit - gas_cost
            
            if net_profit > settings.MIN_ARBITRAGE_PROFIT_USD:
                # Create arbitrage opportunity
                opportunity = ArbitrageOpportunity(
                    pair=pair,
                    buy_venue=buy_venue,
                    sell_venue=sell_venue,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    profit_percent=profit_percent,
                    estimated_profit_usd=net_profit,
                    trade_amount=trade_amount,
                    gas_cost=gas_cost,
                    arbitrage_type=arb_type,
                    timestamp=datetime.now(timezone.utc)
                )
                
                await self._process_arbitrage_opportunity(opportunity)
                
        except Exception as e:
            logger.error("Error evaluating arbitrage opportunity", error=str(e))
    
    async def _process_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity):
        """Process and potentially execute an arbitrage opportunity"""
        try:
            # Store opportunity in database
            await self.database.insert_arbitrage_opportunity(opportunity)
            
            # Update metrics
            arbitrage_opportunities_found.labels(
                type=opportunity.arbitrage_type,
                chain=opportunity.buy_venue.get('chain', 'unknown')
            ).inc()
            
            # Check if we should auto-execute
            if (opportunity.estimated_profit_usd > settings.AUTO_EXECUTE_MIN_PROFIT and
                opportunity.profit_percent > settings.AUTO_EXECUTE_MIN_PERCENT):
                
                await self._execute_arbitrage(opportunity)
            else:
                # Publish to message queue for manual review
                await self._publish_arbitrage_opportunity(opportunity)
            
            logger.info("Arbitrage opportunity found",
                       pair=opportunity.pair,
                       profit_percent=opportunity.profit_percent,
                       estimated_profit=opportunity.estimated_profit_usd,
                       type=opportunity.arbitrage_type)
            
        except Exception as e:
            logger.error("Error processing arbitrage opportunity", error=str(e))
    
    async def _execute_arbitrage(self, opportunity: ArbitrageOpportunity):
        """Execute an arbitrage opportunity"""
        try:
            with arbitrage_execution_time.time():
                execution_id = await self.database.create_arbitrage_execution(opportunity)
                
                # Execute the arbitrage based on type
                if opportunity.arbitrage_type.startswith('cex_dex'):
                    result = await self._execute_cex_dex_arbitrage(opportunity)
                elif opportunity.arbitrage_type.startswith('intra_chain'):
                    result = await self._execute_intra_chain_arbitrage(opportunity)
                elif opportunity.arbitrage_type.startswith('cross_chain'):
                    result = await self._execute_cross_chain_arbitrage(opportunity)
                else:
                    raise ValueError(f"Unknown arbitrage type: {opportunity.arbitrage_type}")
                
                # Update execution record
                await self.database.update_arbitrage_execution(execution_id, result)
                
                if result['success']:
                    arbitrage_profit_usd.labels(
                        type=opportunity.arbitrage_type,
                        chain=opportunity.buy_venue.get('chain', 'unknown')
                    ).inc(result['actual_profit'])
                    
                    logger.info("Arbitrage executed successfully",
                               execution_id=execution_id,
                               profit=result['actual_profit'])
                else:
                    logger.error("Arbitrage execution failed",
                               execution_id=execution_id,
                               error=result['error'])
                
        except Exception as e:
            logger.error("Error executing arbitrage", error=str(e))
    
    async def stop(self):
        """Stop the service gracefully"""
        logger.info("Stopping arbitrage service...")
        self.running = False
        
        # Cancel monitor tasks
        for task in self.monitor_tasks:
            task.cancel()
        
        if self.monitor_tasks:
            await asyncio.gather(*self.monitor_tasks, return_exceptions=True)
        
        # Close exchange connections
        for exchange in self.cex_exchanges.values():
            await exchange.close()
        
        # Close RabbitMQ connection
        if self.rabbitmq_connection:
            await self.rabbitmq_connection.close()
        
        await self.database.disconnect()
        
        active_monitors.set(0)
        logger.info("Arbitrage service stopped")


# Health check endpoint
async def health_check(request):
    return web.json_response({'status': 'healthy', 'service': 'arbitrage_service'})

async def metrics_endpoint(request):
    """Metrics endpoint for Prometheus"""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    
    return web.Response(
        body=generate_latest(),
        content_type=CONTENT_TYPE_LATEST
    )

async def create_web_server():
    """Create web server for health checks and metrics"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/metrics', metrics_endpoint)
    return app

async def main():
    """Main application entry point"""
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create web server
    app = await create_web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', settings.PROMETHEUS_PORT)
    await site.start()
    
    logger.info(f"Started web server on port {settings.PROMETHEUS_PORT}")
    
    service = ArbitrageService()
    
    try:
        await service.initialize()
        await service.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error("Service error", error=str(e))
        sys.exit(1)
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())
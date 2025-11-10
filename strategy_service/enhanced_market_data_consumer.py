"""
Advanced Market Data Consumer with AI/ML Strategy Integration

This enhanced consumer provides sophisticated data access patterns for AI/ML strategies,
including real-time streaming, advanced caching, and dynamic indicator requests.
"""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable, AsyncGenerator
import aiohttp
import aio_pika
import redis.asyncio as redis
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
import structlog

from dynamic_data_manager import StrategyDataManager, DataRequestType, DataPriority

logger = structlog.get_logger()

@dataclass
class MarketDataSubscription:
    subscription_id: str
    strategy_id: str
    symbols: List[str]
    data_types: List[str]  # ['price', 'volume', 'indicators', 'sentiment', 'orderflow']
    timeframes: List[str]
    callback: Optional[Callable] = None
    filters: Optional[Dict[str, Any]] = None
    real_time: bool = True
    buffer_size: int = 1000

class EnhancedMarketDataConsumer:
    """
    Enhanced market data consumer designed for AI/ML strategy integration
    
    Features:
    - Multi-timeframe data streaming with intelligent buffering
    - Dynamic indicator calculation and caching
    - Advanced data preprocessing for ML models
    - Cross-asset correlation analysis
    - Real-time anomaly detection
    - Sentiment data integration
    - Volume profile and order flow analysis
    """
    
    def __init__(self, 
                 api_base_url: str,
                 rabbitmq_url: str,
                 redis_url: str = "redis://localhost:6379"):
        self.api_base_url = api_base_url.rstrip('/')
        self.rabbitmq_url = rabbitmq_url
        self.redis_url = redis_url
        
        # Connection management
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.rabbitmq_connection: Optional[aio_pika.Connection] = None
        self.rabbitmq_channel: Optional[aio_pika.Channel] = None
        self.redis_client: Optional[redis.Redis] = None
        
        # Data management
        self.subscriptions: Dict[str, MarketDataSubscription] = {}
        self.data_buffers: Dict[str, Dict[str, List]] = {}  # symbol -> timeframe -> data
        self.strategy_data_manager: Optional[StrategyDataManager] = None
        
        # Performance tracking
        self.metrics = {
            'messages_processed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'latency_stats': [],
            'error_count': 0
        }
        
        # Data preprocessing pipelines
        self.preprocessing_pipelines: Dict[str, Callable] = {}
    
    async def initialize(self):
        """Initialize all connections and services"""
        try:
            # Initialize HTTP session
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self.http_session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # Initialize Redis
            self.redis_client = redis.from_url(self.redis_url)
            await self.redis_client.ping()
            
            # Initialize RabbitMQ
            await self._init_rabbitmq()
            
            # Initialize Strategy Data Manager
            self.strategy_data_manager = StrategyDataManager(
                self.rabbitmq_url, 
                self.api_base_url
            )
            await self.strategy_data_manager.initialize()
            
            # Start background tasks
            asyncio.create_task(self._data_streaming_task())
            asyncio.create_task(self._cache_management_task())
            asyncio.create_task(self._metrics_reporting_task())
            
            logger.info("Enhanced Market Data Consumer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Enhanced Market Data Consumer: {e}")
            raise
    
    async def _init_rabbitmq(self):
        """Initialize RabbitMQ for real-time data streaming"""
        self.rabbitmq_connection = await aio_pika.connect_robust(
            self.rabbitmq_url,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        self.rabbitmq_channel = await self.rabbitmq_connection.channel()
        await self.rabbitmq_channel.set_qos(prefetch_count=100)
        
        # Declare exchange for market data
        self.market_data_exchange = await self.rabbitmq_channel.declare_exchange(
            'mastertrade.market.data', aio_pika.ExchangeType.TOPIC, durable=True
        )
        
        logger.info("RabbitMQ initialized for market data streaming")
    
    async def subscribe_to_market_data(self,
                                     strategy_id: str,
                                     symbols: List[str],
                                     data_types: List[str],
                                     timeframes: List[str],
                                     callback: Callable = None,
                                     filters: Dict[str, Any] = None,
                                     real_time: bool = True) -> str:
        """
        Subscribe to market data for a strategy
        
        Args:
            strategy_id: Unique strategy identifier
            symbols: List of trading symbols
            data_types: Types of data needed ['price', 'volume', 'indicators', 'sentiment']
            timeframes: List of timeframes
            callback: Function to call when data is received
            filters: Data filtering criteria
            real_time: Whether to receive real-time updates
            
        Returns:
            Subscription ID
        """
        subscription_id = f"{strategy_id}_{int(time.time())}"
        
        subscription = MarketDataSubscription(
            subscription_id=subscription_id,
            strategy_id=strategy_id,
            symbols=symbols,
            data_types=data_types,
            timeframes=timeframes,
            callback=callback,
            filters=filters,
            real_time=real_time
        )
        
        self.subscriptions[subscription_id] = subscription
        
        # Initialize data buffers for this subscription
        for symbol in symbols:
            if symbol not in self.data_buffers:
                self.data_buffers[symbol] = {}
            for timeframe in timeframes:
                if timeframe not in self.data_buffers[symbol]:
                    self.data_buffers[symbol][timeframe] = []
        
        # Set up RabbitMQ queue for real-time updates
        if real_time:
            await self._setup_realtime_subscription(subscription)
        
        logger.info(
            "Market data subscription created",
            subscription_id=subscription_id,
            strategy_id=strategy_id,
            symbols=symbols,
            data_types=data_types
        )
        
        return subscription_id
    
    async def _setup_realtime_subscription(self, subscription: MarketDataSubscription):
        """Set up real-time data subscription via RabbitMQ"""
        try:
            # Create queue for this subscription
            queue_name = f"strategy_data_{subscription.subscription_id}"
            queue = await self.rabbitmq_channel.declare_queue(
                queue_name, 
                durable=False, 
                auto_delete=True
            )
            
            # Bind to relevant routing keys
            for symbol in subscription.symbols:
                for timeframe in subscription.timeframes:
                    for data_type in subscription.data_types:
                        routing_key = f"market.{data_type}.{symbol}.{timeframe}"
                        await queue.bind(self.market_data_exchange, routing_key)
            
            # Start consuming
            await queue.consume(
                lambda message: self._handle_realtime_data(message, subscription)
            )
            
        except Exception as e:
            logger.error(f"Failed to setup real-time subscription: {e}")
            raise
    
    async def _handle_realtime_data(self, 
                                  message: aio_pika.IncomingMessage, 
                                  subscription: MarketDataSubscription):
        """Handle incoming real-time market data"""
        try:
            # Parse message
            data = json.loads(message.body.decode())
            symbol = data.get('symbol')
            timeframe = data.get('timeframe')
            data_type = data.get('data_type')
            
            # Apply filters if specified
            if subscription.filters:
                if not self._apply_filters(data, subscription.filters):
                    await message.ack()
                    return
            
            # Update data buffer
            if symbol in self.data_buffers and timeframe in self.data_buffers[symbol]:
                buffer = self.data_buffers[symbol][timeframe]
                buffer.append(data)
                
                # Maintain buffer size
                if len(buffer) > subscription.buffer_size:
                    buffer.pop(0)
            
            # Cache data
            cache_key = f"market_data:{symbol}:{timeframe}:{data_type}"
            await self.redis_client.setex(
                cache_key, 
                300,  # 5 minutes TTL
                json.dumps(data, default=str)
            )
            
            # Call strategy callback if provided
            if subscription.callback:
                try:
                    await subscription.callback(data)
                except Exception as e:
                    logger.error(f"Error in strategy callback: {e}")
            
            self.metrics['messages_processed'] += 1
            await message.ack()
            
        except Exception as e:
            logger.error(f"Error handling real-time data: {e}")
            self.metrics['error_count'] += 1
            await message.nack(requeue=False)
    
    def _apply_filters(self, data: Dict, filters: Dict[str, Any]) -> bool:
        """Apply filters to determine if data should be processed"""
        try:
            # Price range filter
            if 'price_min' in filters or 'price_max' in filters:
                price = data.get('price') or data.get('close')
                if price:
                    if 'price_min' in filters and price < filters['price_min']:
                        return False
                    if 'price_max' in filters and price > filters['price_max']:
                        return False
            
            # Volume filter
            if 'volume_min' in filters:
                volume = data.get('volume', 0)
                if volume < filters['volume_min']:
                    return False
            
            # Time-based filters
            if 'time_range' in filters:
                timestamp = datetime.fromisoformat(data.get('timestamp', ''))
                start_time = filters['time_range'].get('start')
                end_time = filters['time_range'].get('end')
                
                if start_time and timestamp < start_time:
                    return False
                if end_time and timestamp > end_time:
                    return False
            
            # Custom filter functions
            if 'custom' in filters:
                return filters['custom'](data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying filters: {e}")
            return True  # Default to accepting data on filter errors
    
    async def get_historical_data(self,
                                symbols: List[str],
                                timeframes: List[str],
                                start_date: datetime,
                                end_date: datetime = None,
                                indicators: List[str] = None,
                                use_cache: bool = True) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        Get historical market data with optional indicators
        
        Args:
            symbols: List of trading symbols
            timeframes: List of timeframes
            start_date: Start date for historical data
            end_date: End date (default: now)
            indicators: List of technical indicators to include
            use_cache: Whether to use Redis cache
            
        Returns:
            Nested dict: {symbol: {timeframe: DataFrame}}
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        
        result = {}
        
        for symbol in symbols:
            result[symbol] = {}
            
            for timeframe in timeframes:
                # Check cache first
                cache_key = f"historical:{symbol}:{timeframe}:{start_date}:{end_date}"
                
                if use_cache:
                    cached_data = await self.redis_client.get(cache_key)
                    if cached_data:
                        self.metrics['cache_hits'] += 1
                        result[symbol][timeframe] = pd.read_json(cached_data)
                        continue
                
                self.metrics['cache_misses'] += 1
                
                # Fetch from API
                start_time = time.time()
                
                try:
                    params = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat(),
                        'limit': 5000
                    }
                    
                    if indicators:
                        params['indicators'] = ','.join(indicators)
                    
                    async with self.http_session.get(
                        f"{self.api_base_url}/api/v1/market-data/historical",
                        params=params
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                        
                        # Convert to DataFrame
                        df = pd.DataFrame(data.get('data', []))
                        if not df.empty:
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df.set_index('timestamp', inplace=True)
                        
                        result[symbol][timeframe] = df
                        
                        # Cache result
                        if use_cache and not df.empty:
                            await self.redis_client.setex(
                                cache_key,
                                3600,  # 1 hour TTL
                                df.to_json()
                            )
                
                except Exception as e:
                    logger.error(f"Error fetching historical data for {symbol}/{timeframe}: {e}")
                    result[symbol][timeframe] = pd.DataFrame()
                
                finally:
                    latency = (time.time() - start_time) * 1000
                    self.metrics['latency_stats'].append(latency)
        
        return result
    
    async def get_multi_timeframe_data(self,
                                     strategy_id: str,
                                     symbols: List[str],
                                     timeframes: List[str],
                                     lookback_periods: int = 100) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        Get synchronized multi-timeframe data for strategy analysis
        
        This method ensures all timeframes are properly aligned and provides
        the same number of synchronized periods across different timeframes.
        """
        end_date = datetime.now(timezone.utc)
        
        # Calculate appropriate start dates for each timeframe
        timeframe_multipliers = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60,
            '4h': 240, '1d': 1440, '1w': 10080, '1M': 43200
        }
        
        # Use the largest timeframe to determine the overall lookback period
        max_multiplier = max(timeframe_multipliers.get(tf, 60) for tf in timeframes)
        start_date = end_date - timedelta(minutes=max_multiplier * lookback_periods * 2)  # Extra buffer
        
        # Fetch historical data
        historical_data = await self.get_historical_data(
            symbols=symbols,
            timeframes=timeframes,
            start_date=start_date,
            end_date=end_date,
            use_cache=True
        )
        
        # Align and synchronize timeframes
        aligned_data = {}
        for symbol in symbols:
            aligned_data[symbol] = {}
            
            # Get the base timeframe (usually the smallest)
            base_timeframe = min(timeframes, key=lambda x: timeframe_multipliers.get(x, 60))
            base_df = historical_data[symbol].get(base_timeframe, pd.DataFrame())
            
            if base_df.empty:
                continue
            
            # Align all timeframes to the base timeframe timestamps
            for timeframe in timeframes:
                df = historical_data[symbol].get(timeframe, pd.DataFrame())
                
                if df.empty:
                    aligned_data[symbol][timeframe] = pd.DataFrame()
                    continue
                
                # Resample or align to ensure consistent data points
                if timeframe == base_timeframe:
                    aligned_data[symbol][timeframe] = df.tail(lookback_periods)
                else:
                    # Use forward-fill for higher timeframes on base timeframe index
                    aligned_df = df.reindex(base_df.index, method='ffill')
                    aligned_data[symbol][timeframe] = aligned_df.tail(lookback_periods)
        
        return aligned_data
    
    async def request_custom_indicators(self,
                                      strategy_id: str,
                                      symbols: List[str],
                                      indicator_configs: List[Dict],
                                      timeframes: List[str] = None) -> str:
        """
        Request custom technical indicators for strategy analysis
        
        Args:
            strategy_id: Strategy requesting the indicators
            symbols: Symbols to calculate indicators for
            indicator_configs: List of indicator configurations
            timeframes: Timeframes for calculation
            
        Returns:
            Request ID for tracking
        """
        if timeframes is None:
            timeframes = ['5m', '1h']
        
        # Use Strategy Data Manager for dynamic requests
        return await self.strategy_data_manager.request_technical_indicators(
            strategy_id=strategy_id,
            strategy_name=f"Custom Indicators Request",
            symbols=symbols,
            indicators=indicator_configs,
            timeframes=timeframes,
            priority=DataPriority.HIGH
        )
    
    async def get_sentiment_data(self,
                               symbols: List[str],
                               sources: List[str] = None,
                               timeframe: str = '1h',
                               lookback_hours: int = 24) -> Dict[str, pd.DataFrame]:
        """Get sentiment data for symbols"""
        
        if sources is None:
            sources = ['twitter', 'reddit', 'news']
        
        result = {}
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=lookback_hours)
        
        for symbol in symbols:
            try:
                params = {
                    'symbol': symbol,
                    'sources': ','.join(sources),
                    'timeframe': timeframe,
                    'start_date': start_time.isoformat(),
                    'end_date': end_time.isoformat()
                }
                
                async with self.http_session.get(
                    f"{self.api_base_url}/api/v1/sentiment/data",
                    params=params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    df = pd.DataFrame(data.get('data', []))
                    if not df.empty:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df.set_index('timestamp', inplace=True)
                    
                    result[symbol] = df
                    
            except Exception as e:
                logger.error(f"Error fetching sentiment data for {symbol}: {e}")
                result[symbol] = pd.DataFrame()
        
        return result
    
    async def get_correlation_analysis(self,
                                     symbols: List[str],
                                     correlation_assets: List[str] = None,
                                     timeframe: str = '1h',
                                     lookback_days: int = 30) -> pd.DataFrame:
        """Get cross-asset correlation analysis"""
        
        if correlation_assets is None:
            correlation_assets = ['SPY', 'QQQ', 'GLD', 'VIX']
        
        all_symbols = symbols + correlation_assets
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=lookback_days)
        
        # Get price data for all symbols
        price_data = {}
        for symbol in all_symbols:
            try:
                params = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                }
                
                async with self.http_session.get(
                    f"{self.api_base_url}/api/v1/market-data/historical",
                    params=params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    df = pd.DataFrame(data.get('data', []))
                    if not df.empty:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df.set_index('timestamp', inplace=True)
                        price_data[symbol] = df['close']
                        
            except Exception as e:
                logger.error(f"Error fetching correlation data for {symbol}: {e}")
                continue
        
        # Calculate correlation matrix
        if price_data:
            price_df = pd.DataFrame(price_data)
            price_df = price_df.pct_change().dropna()  # Use returns for correlation
            correlation_matrix = price_df.corr()
            return correlation_matrix
        
        return pd.DataFrame()
    
    def register_preprocessing_pipeline(self, 
                                      name: str, 
                                      pipeline_func: Callable[[pd.DataFrame], pd.DataFrame]):
        """Register a data preprocessing pipeline for ML models"""
        self.preprocessing_pipelines[name] = pipeline_func
        logger.info(f"Registered preprocessing pipeline: {name}")
    
    async def get_preprocessed_data(self,
                                  strategy_id: str,
                                  symbols: List[str],
                                  timeframes: List[str],
                                  pipeline_name: str,
                                  lookback_periods: int = 100) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Get data preprocessed through a specific pipeline"""
        
        if pipeline_name not in self.preprocessing_pipelines:
            raise ValueError(f"Unknown preprocessing pipeline: {pipeline_name}")
        
        # Get raw data
        raw_data = await self.get_multi_timeframe_data(
            strategy_id=strategy_id,
            symbols=symbols,
            timeframes=timeframes,
            lookback_periods=lookback_periods
        )
        
        # Apply preprocessing pipeline
        processed_data = {}
        pipeline_func = self.preprocessing_pipelines[pipeline_name]
        
        for symbol in symbols:
            processed_data[symbol] = {}
            for timeframe in timeframes:
                df = raw_data[symbol].get(timeframe, pd.DataFrame())
                if not df.empty:
                    try:
                        processed_data[symbol][timeframe] = pipeline_func(df)
                    except Exception as e:
                        logger.error(f"Error in preprocessing pipeline {pipeline_name}: {e}")
                        processed_data[symbol][timeframe] = df
                else:
                    processed_data[symbol][timeframe] = df
        
        return processed_data
    
    async def _data_streaming_task(self):
        """Background task to manage data streaming"""
        while True:
            try:
                # Health check for all subscriptions
                for subscription_id, subscription in self.subscriptions.items():
                    if subscription.real_time:
                        # Check if subscription is still active
                        # This could include heartbeat checks, etc.
                        pass
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in data streaming task: {e}")
                await asyncio.sleep(30)
    
    async def _cache_management_task(self):
        """Background task to manage Redis cache"""
        while True:
            try:
                # Clean up expired cache entries
                # Redis handles TTL automatically, but we can do additional cleanup
                
                # Log cache statistics
                if self.metrics['cache_hits'] + self.metrics['cache_misses'] > 0:
                    cache_hit_rate = (
                        self.metrics['cache_hits'] / 
                        (self.metrics['cache_hits'] + self.metrics['cache_misses'])
                    )
                    logger.info(f"Cache hit rate: {cache_hit_rate:.2%}")
                
                await asyncio.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in cache management task: {e}")
                await asyncio.sleep(300)
    
    async def _metrics_reporting_task(self):
        """Background task to report performance metrics"""
        while True:
            try:
                # Calculate and log performance metrics
                if self.metrics['latency_stats']:
                    avg_latency = np.mean(self.metrics['latency_stats'])
                    p95_latency = np.percentile(self.metrics['latency_stats'], 95)
                    
                    logger.info(
                        "Market Data Consumer Performance",
                        messages_processed=self.metrics['messages_processed'],
                        avg_latency_ms=avg_latency,
                        p95_latency_ms=p95_latency,
                        error_count=self.metrics['error_count'],
                        active_subscriptions=len(self.subscriptions)
                    )
                    
                    # Reset latency stats to prevent memory growth
                    self.metrics['latency_stats'] = []
                
                await asyncio.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in metrics reporting task: {e}")
                await asyncio.sleep(300)
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from market data"""
        try:
            if subscription_id in self.subscriptions:
                del self.subscriptions[subscription_id]
                logger.info(f"Unsubscribed from market data: {subscription_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error unsubscribing: {e}")
            return False
    
    async def close(self):
        """Clean up connections and resources"""
        try:
            # Close strategy data manager
            if self.strategy_data_manager:
                await self.strategy_data_manager.close()
            
            # Close connections
            if self.http_session:
                await self.http_session.close()
            
            if self.rabbitmq_connection:
                await self.rabbitmq_connection.close()
            
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("Enhanced Market Data Consumer closed successfully")
            
        except Exception as e:
            logger.error(f"Error closing Enhanced Market Data Consumer: {e}")


# Convenience function for easy integration
async def create_enhanced_market_data_consumer(
    api_base_url: str,
    rabbitmq_url: str,
    redis_url: str = "redis://localhost:6379"
) -> EnhancedMarketDataConsumer:
    """Create and initialize an Enhanced Market Data Consumer"""
    consumer = EnhancedMarketDataConsumer(api_base_url, rabbitmq_url, redis_url)
    await consumer.initialize()
    return consumer
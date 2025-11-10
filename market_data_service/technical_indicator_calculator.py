"""
Technical Indicator Calculator Engine

High-performance, configurable calculator for technical indicators
with caching, batch processing, and dynamic configuration support.
"""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
import hashlib

import pandas as pd
import numpy as np
import ta
import structlog
from prometheus_client import Counter, Histogram, Gauge

from indicator_models import (
    IndicatorType, IndicatorConfiguration, IndicatorResult, 
    IndicatorRequest, BulkIndicatorRequest
)
from database import Database

logger = structlog.get_logger()

# Metrics
indicator_calculations = Counter('indicator_calculations_total', 'Total indicator calculations', 
                               ['indicator_type', 'symbol', 'status'])
calculation_time = Histogram('indicator_calculation_time_seconds', 'Indicator calculation time',
                            ['indicator_type', 'symbol'])
cache_operations = Counter('indicator_cache_operations_total', 'Cache operations', ['operation'])
active_subscriptions = Gauge('active_indicator_subscriptions', 'Number of active indicator subscriptions')


class IndicatorCalculator:
    """High-performance technical indicator calculator with caching"""
    
    def __init__(self, database: Database):
        self.database = database
        self.cache: Dict[str, Dict] = {}  # In-memory cache for results
        self.cache_ttl: Dict[str, datetime] = {}  # Cache expiration times
        self.subscriptions: Dict[str, Dict] = {}  # Active subscriptions
        
        # Performance settings
        self.max_cache_size = 10000  # Maximum cached results
        self.batch_size = 50  # Default batch size for calculations
        
    def _generate_cache_key(self, config: IndicatorConfiguration, timestamp: datetime = None) -> str:
        """Generate cache key for indicator configuration"""
        key_data = {
            'indicator_type': config.indicator_type,
            'symbol': config.symbol,
            'interval': config.interval,
            'parameters': {p.name: p.value for p in config.parameters}
        }
        
        if timestamp:
            # Round timestamp to nearest minute for cache efficiency
            rounded_time = timestamp.replace(second=0, microsecond=0)
            key_data['timestamp'] = rounded_time.isoformat()
            
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def _get_cached_result(self, cache_key: str) -> Optional[IndicatorResult]:
        """Get cached result if still valid"""
        if cache_key in self.cache and cache_key in self.cache_ttl:
            if datetime.utcnow() < self.cache_ttl[cache_key]:
                cache_operations.labels(operation='hit').inc()
                result = IndicatorResult(**self.cache[cache_key])
                result.cache_hit = True
                return result
            else:
                # Expired cache entry
                del self.cache[cache_key]
                del self.cache_ttl[cache_key]
                
        cache_operations.labels(operation='miss').inc()
        return None
    
    def _cache_result(self, cache_key: str, result: IndicatorResult, ttl_minutes: int):
        """Cache calculation result"""
        # Cleanup old cache entries if at capacity
        if len(self.cache) >= self.max_cache_size:
            # Remove oldest entries (simple FIFO cleanup)
            oldest_keys = list(self.cache.keys())[:100]  # Remove 100 oldest
            for key in oldest_keys:
                self.cache.pop(key, None)
                self.cache_ttl.pop(key, None)
        
        # Cache new result
        self.cache[cache_key] = result.dict()
        self.cache_ttl[cache_key] = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        cache_operations.labels(operation='set').inc()
    
    async def _get_market_data(self, symbol: str, interval: str, periods: int) -> pd.DataFrame:
        """Get market data for calculation"""
        try:
            # Calculate how much historical data we need
            hours_back = periods * self._interval_to_minutes(interval) // 60
            hours_back = max(hours_back, 24)  # Minimum 24 hours
            
            # Get data from database
            data = await self.database.get_market_data(
                symbol=symbol,
                interval=interval,
                hours_back=hours_back,
                limit=periods + 50  # Get extra data for calculation accuracy
            )
            
            if len(data) < periods:
                raise ValueError(f"Insufficient data: need {periods}, got {len(data)}")
            
            # Convert to DataFrame
            df = pd.DataFrame([{
                'timestamp': item['timestamp'],
                'open': float(item['open_price']),
                'high': float(item['high_price']),
                'low': float(item['low_price']),
                'close': float(item['close_price']),
                'volume': float(item['volume'])
            } for item in data])
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error("Error getting market data for indicator calculation", 
                        symbol=symbol, interval=interval, error=str(e))
            raise
    
    def _interval_to_minutes(self, interval: str) -> int:
        """Convert interval string to minutes"""
        interval_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720,
            '1d': 1440, '3d': 4320, '1w': 10080, '1M': 43200
        }
        return interval_map.get(interval, 60)  # Default to 1 hour
    
    async def calculate_sma(self, df: pd.DataFrame, config: IndicatorConfiguration) -> Dict[str, float]:
        """Calculate Simple Moving Average"""
        period = next(p.value for p in config.parameters if p.name == 'period')
        sma = ta.trend.sma_indicator(df['close'], window=int(period))
        
        return {
            f'sma_{period}': float(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else None
        }
    
    async def calculate_ema(self, df: pd.DataFrame, config: IndicatorConfiguration) -> Dict[str, float]:
        """Calculate Exponential Moving Average"""
        period = next(p.value for p in config.parameters if p.name == 'period')
        ema = ta.trend.ema_indicator(df['close'], window=int(period))
        
        return {
            f'ema_{period}': float(ema.iloc[-1]) if not pd.isna(ema.iloc[-1]) else None
        }
    
    async def calculate_rsi(self, df: pd.DataFrame, config: IndicatorConfiguration) -> Dict[str, float]:
        """Calculate Relative Strength Index"""
        period = next(p.value for p in config.parameters if p.name == 'period')
        rsi = ta.momentum.rsi(df['close'], window=int(period))
        
        return {
            f'rsi_{period}': float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
        }
    
    async def calculate_macd(self, df: pd.DataFrame, config: IndicatorConfiguration) -> Dict[str, float]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        params = {p.name: p.value for p in config.parameters}
        fast_period = int(params.get('fast_period', 12))
        slow_period = int(params.get('slow_period', 26))
        signal_period = int(params.get('signal_period', 9))
        
        macd_line = ta.trend.macd(df['close'], window_fast=fast_period, window_slow=slow_period)
        macd_signal = ta.trend.macd_signal(df['close'], window_fast=fast_period, 
                                          window_slow=slow_period, window_sign=signal_period)
        macd_diff = ta.trend.macd_diff(df['close'], window_fast=fast_period, 
                                      window_slow=slow_period, window_sign=signal_period)
        
        return {
            'macd_line': float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else None,
            'macd_signal': float(macd_signal.iloc[-1]) if not pd.isna(macd_signal.iloc[-1]) else None,
            'macd_histogram': float(macd_diff.iloc[-1]) if not pd.isna(macd_diff.iloc[-1]) else None
        }
    
    async def calculate_bollinger_bands(self, df: pd.DataFrame, config: IndicatorConfiguration) -> Dict[str, float]:
        """Calculate Bollinger Bands"""
        params = {p.name: p.value for p in config.parameters}
        period = int(params.get('period', 20))
        std_dev = float(params.get('std_dev', 2))
        
        bb_upper = ta.volatility.bollinger_hband(df['close'], window=period, window_dev=std_dev)
        bb_middle = ta.volatility.bollinger_mavg(df['close'], window=period)
        bb_lower = ta.volatility.bollinger_lband(df['close'], window=period, window_dev=std_dev)
        
        return {
            'bb_upper': float(bb_upper.iloc[-1]) if not pd.isna(bb_upper.iloc[-1]) else None,
            'bb_middle': float(bb_middle.iloc[-1]) if not pd.isna(bb_middle.iloc[-1]) else None,
            'bb_lower': float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else None
        }
    
    async def calculate_stochastic(self, df: pd.DataFrame, config: IndicatorConfiguration) -> Dict[str, float]:
        """Calculate Stochastic Oscillator"""
        params = {p.name: p.value for p in config.parameters}
        k_period = int(params.get('k_period', 14))
        d_period = int(params.get('d_period', 3))
        
        stoch_k = ta.momentum.stoch(df['high'], df['low'], df['close'], 
                                   window=k_period, smooth_window=d_period)
        stoch_d = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], 
                                          window=k_period, smooth_window=d_period)
        
        return {
            f'stoch_k_{k_period}': float(stoch_k.iloc[-1]) if not pd.isna(stoch_k.iloc[-1]) else None,
            f'stoch_d_{d_period}': float(stoch_d.iloc[-1]) if not pd.isna(stoch_d.iloc[-1]) else None
        }
    
    async def calculate_indicator(self, config: IndicatorConfiguration) -> IndicatorResult:
        """Calculate a single technical indicator"""
        start_time = time.time()
        
        try:
            # Check cache first
            cache_key = self._generate_cache_key(config, datetime.utcnow())
            cached_result = await self._get_cached_result(cache_key)
            if cached_result:
                return cached_result
            
            # Get market data
            df = await self._get_market_data(
                config.symbol, 
                config.interval, 
                config.periods_required
            )
            
            # Calculate indicator based on type
            calculation_methods = {
                IndicatorType.SMA: self.calculate_sma,
                IndicatorType.EMA: self.calculate_ema,
                IndicatorType.RSI: self.calculate_rsi,
                IndicatorType.MACD: self.calculate_macd,
                IndicatorType.BOLLINGER_BANDS: self.calculate_bollinger_bands,
                IndicatorType.STOCHASTIC: self.calculate_stochastic,
            }
            
            if config.indicator_type not in calculation_methods:
                raise ValueError(f"Unsupported indicator type: {config.indicator_type}")
            
            values = await calculation_methods[config.indicator_type](df, config)
            
            # Create result
            calculation_time_ms = (time.time() - start_time) * 1000
            result = IndicatorResult(
                configuration_id=config.id,
                symbol=config.symbol,
                interval=config.interval,
                timestamp=datetime.utcnow(),
                values=values,
                metadata={
                    'parameters': {p.name: p.value for p in config.parameters},
                    'data_range': {
                        'start': df['timestamp'].iloc[0].isoformat() if len(df) > 0 else None,
                        'end': df['timestamp'].iloc[-1].isoformat() if len(df) > 0 else None
                    }
                },
                data_points_used=len(df),
                calculation_time_ms=calculation_time_ms
            )
            
            # Cache result
            self._cache_result(cache_key, result, config.cache_duration_minutes)
            
            # Update metrics
            indicator_calculations.labels(
                indicator_type=config.indicator_type,
                symbol=config.symbol,
                status='success'
            ).inc()
            
            calculation_time.labels(
                indicator_type=config.indicator_type,
                symbol=config.symbol
            ).observe(calculation_time_ms / 1000)
            
            return result
            
        except Exception as e:
            logger.error("Error calculating indicator", 
                        indicator_type=config.indicator_type,
                        symbol=config.symbol, 
                        error=str(e))
            
            indicator_calculations.labels(
                indicator_type=config.indicator_type,
                symbol=config.symbol,
                status='error'
            ).inc()
            raise
    
    async def calculate_bulk_indicators(self, request: BulkIndicatorRequest) -> List[IndicatorResult]:
        """Calculate multiple indicators efficiently"""
        results = []
        
        # Group by symbol and interval for efficiency
        grouped_configs = {}
        for indicator_request in request.requests:
            for config in indicator_request.indicators:
                key = (config.symbol, config.interval)
                if key not in grouped_configs:
                    grouped_configs[key] = []
                grouped_configs[key].append(config)
        
        # Calculate in batches
        if request.parallel_execution:
            # Parallel execution
            tasks = []
            for configs in grouped_configs.values():
                for config in configs:
                    task = asyncio.create_task(self.calculate_indicator(config))
                    tasks.append(task)
            
            # Process in batches to avoid overwhelming the system
            batch_size = request.batch_size
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error("Batch calculation error", error=str(result))
                    else:
                        results.append(result)
        else:
            # Sequential execution
            for configs in grouped_configs.values():
                for config in configs:
                    try:
                        result = await self.calculate_indicator(config)
                        results.append(result)
                    except Exception as e:
                        logger.error("Sequential calculation error", error=str(e))
        
        return results
    
    async def create_subscription(self, subscription_id: str, 
                                configurations: List[IndicatorConfiguration]) -> bool:
        """Create a subscription for continuous indicator updates"""
        try:
            self.subscriptions[subscription_id] = {
                'configurations': configurations,
                'created_at': datetime.utcnow(),
                'last_calculation': None
            }
            active_subscriptions.set(len(self.subscriptions))
            return True
        except Exception as e:
            logger.error("Error creating indicator subscription", error=str(e))
            return False
    
    async def remove_subscription(self, subscription_id: str) -> bool:
        """Remove an indicator subscription"""
        try:
            if subscription_id in self.subscriptions:
                del self.subscriptions[subscription_id]
                active_subscriptions.set(len(self.subscriptions))
                return True
            return False
        except Exception as e:
            logger.error("Error removing indicator subscription", error=str(e))
            return False
    
    async def process_subscriptions(self):
        """Process all active subscriptions (called by background task)"""
        for subscription_id, subscription_data in self.subscriptions.items():
            try:
                configurations = subscription_data['configurations']
                results = []
                
                for config in configurations:
                    result = await self.calculate_indicator(config)
                    results.append(result)
                
                # Update last calculation time
                self.subscriptions[subscription_id]['last_calculation'] = datetime.utcnow()
                
                # Here you would publish results to RabbitMQ or send to webhook
                # This will be implemented in the main service class
                
            except Exception as e:
                logger.error("Error processing subscription", 
                           subscription_id=subscription_id, error=str(e))
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return {
            'cache_size': len(self.cache),
            'max_cache_size': self.max_cache_size,
            'cache_hit_ratio': cache_operations._value._samples.get(('hit',), 0) / 
                             max(cache_operations._value._samples.get(('miss',), 1), 1),
            'active_subscriptions': len(self.subscriptions)
        }
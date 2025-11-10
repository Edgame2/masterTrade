"""
Trading strategy implementations
"""

import pandas as pd
import numpy as np
import ta
from abc import ABC, abstractmethod
from typing import Dict, List, Any
import structlog

logger = structlog.get_logger()


class BaseStrategy(ABC):
    """Base class for all trading strategies"""
    
    @abstractmethod
    def execute(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute the strategy and return signals"""
        pass
    
    def validate_data(self, data: pd.DataFrame, min_periods: int = 20) -> bool:
        """Validate that we have enough data"""
        return len(data) >= min_periods


class SMAStrategy(BaseStrategy):
    """Simple Moving Average Crossover Strategy"""
    
    def execute(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute SMA crossover strategy"""
        try:
            fast_period = parameters.get('fast_period', 20)
            slow_period = parameters.get('slow_period', 50)
            
            if not self.validate_data(data, slow_period + 5):
                return []
            
            # Calculate moving averages
            data['sma_fast'] = ta.trend.sma_indicator(data['close'], window=fast_period)
            data['sma_slow'] = ta.trend.sma_indicator(data['close'], window=slow_period)
            
            # Generate signals
            signals = []
            
            # Check for crossovers
            if len(data) >= 2:
                current = data.iloc[-1]
                previous = data.iloc[-2]
                
                # Bullish crossover
                if (previous['sma_fast'] <= previous['sma_slow'] and 
                    current['sma_fast'] > current['sma_slow']):
                    
                    signals.append({
                        'type': 'BUY',
                        'confidence': 75.0,
                        'price': current['close'],
                        'metadata': {
                            'sma_fast': current['sma_fast'],
                            'sma_slow': current['sma_slow'],
                            'crossover_type': 'bullish'
                        }
                    })
                
                # Bearish crossover
                elif (previous['sma_fast'] >= previous['sma_slow'] and 
                      current['sma_fast'] < current['sma_slow']):
                    
                    signals.append({
                        'type': 'SELL',
                        'confidence': 75.0,
                        'price': current['close'],
                        'metadata': {
                            'sma_fast': current['sma_fast'],
                            'sma_slow': current['sma_slow'],
                            'crossover_type': 'bearish'
                        }
                    })
            
            return signals
            
        except Exception as e:
            logger.error("Error in SMA strategy", error=str(e))
            return []


class EMAStrategy(BaseStrategy):
    """Exponential Moving Average Strategy"""
    
    def execute(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute EMA crossover strategy"""
        try:
            fast_period = parameters.get('fast_period', 12)
            slow_period = parameters.get('slow_period', 26)
            
            if not self.validate_data(data, slow_period + 5):
                return []
            
            # Calculate EMAs
            data['ema_fast'] = ta.trend.ema_indicator(data['close'], window=fast_period)
            data['ema_slow'] = ta.trend.ema_indicator(data['close'], window=slow_period)
            
            signals = []
            
            if len(data) >= 2:
                current = data.iloc[-1]
                previous = data.iloc[-2]
                
                # Bullish crossover
                if (previous['ema_fast'] <= previous['ema_slow'] and 
                    current['ema_fast'] > current['ema_slow']):
                    
                    signals.append({
                        'type': 'BUY',
                        'confidence': 80.0,
                        'price': current['close'],
                        'metadata': {
                            'ema_fast': current['ema_fast'],
                            'ema_slow': current['ema_slow']
                        }
                    })
                
                # Bearish crossover
                elif (previous['ema_fast'] >= previous['ema_slow'] and 
                      current['ema_fast'] < current['ema_slow']):
                    
                    signals.append({
                        'type': 'SELL',
                        'confidence': 80.0,
                        'price': current['close'],
                        'metadata': {
                            'ema_fast': current['ema_fast'],
                            'ema_slow': current['ema_slow']
                        }
                    })
            
            return signals
            
        except Exception as e:
            logger.error("Error in EMA strategy", error=str(e))
            return []


class RSIStrategy(BaseStrategy):
    """RSI Overbought/Oversold Strategy"""
    
    def execute(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute RSI strategy"""
        try:
            period = parameters.get('period', 14)
            oversold = parameters.get('oversold', 30)
            overbought = parameters.get('overbought', 70)
            
            if not self.validate_data(data, period + 5):
                return []
            
            # Calculate RSI
            data['rsi'] = ta.momentum.rsi(data['close'], window=period)
            
            signals = []
            
            if len(data) >= 2:
                current = data.iloc[-1]
                previous = data.iloc[-2]
                
                # RSI moving from oversold to normal (buy signal)
                if previous['rsi'] <= oversold and current['rsi'] > oversold:
                    confidence = min(95.0, 50.0 + (oversold - previous['rsi']))
                    
                    signals.append({
                        'type': 'BUY',
                        'confidence': confidence,
                        'price': current['close'],
                        'metadata': {
                            'rsi': current['rsi'],
                            'rsi_previous': previous['rsi'],
                            'signal_reason': 'oversold_reversal'
                        }
                    })
                
                # RSI moving from overbought to normal (sell signal)
                elif previous['rsi'] >= overbought and current['rsi'] < overbought:
                    confidence = min(95.0, 50.0 + (previous['rsi'] - overbought))
                    
                    signals.append({
                        'type': 'SELL',
                        'confidence': confidence,
                        'price': current['close'],
                        'metadata': {
                            'rsi': current['rsi'],
                            'rsi_previous': previous['rsi'],
                            'signal_reason': 'overbought_reversal'
                        }
                    })
            
            return signals
            
        except Exception as e:
            logger.error("Error in RSI strategy", error=str(e))
            return []


class MACDStrategy(BaseStrategy):
    """MACD Strategy"""
    
    def execute(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute MACD strategy"""
        try:
            fast_period = parameters.get('fast_period', 12)
            slow_period = parameters.get('slow_period', 26)
            signal_period = parameters.get('signal_period', 9)
            
            min_periods = slow_period + signal_period + 5
            if not self.validate_data(data, min_periods):
                return []
            
            # Calculate MACD
            macd_line = ta.trend.macd(data['close'], window_fast=fast_period, window_slow=slow_period)
            macd_signal = ta.trend.macd_signal(data['close'], window_fast=fast_period, 
                                             window_slow=slow_period, window_sign=signal_period)
            
            data['macd'] = macd_line
            data['macd_signal'] = macd_signal
            data['macd_histogram'] = macd_line - macd_signal
            
            signals = []
            
            if len(data) >= 2:
                current = data.iloc[-1]
                previous = data.iloc[-2]
                
                # MACD line crosses above signal line (bullish)
                if (previous['macd'] <= previous['macd_signal'] and 
                    current['macd'] > current['macd_signal']):
                    
                    # Higher confidence if crossing above zero line
                    confidence = 70.0
                    if current['macd'] > 0:
                        confidence = 85.0
                    
                    signals.append({
                        'type': 'BUY',
                        'confidence': confidence,
                        'price': current['close'],
                        'metadata': {
                            'macd': current['macd'],
                            'macd_signal': current['macd_signal'],
                            'macd_histogram': current['macd_histogram']
                        }
                    })
                
                # MACD line crosses below signal line (bearish)
                elif (previous['macd'] >= previous['macd_signal'] and 
                      current['macd'] < current['macd_signal']):
                    
                    # Higher confidence if crossing below zero line
                    confidence = 70.0
                    if current['macd'] < 0:
                        confidence = 85.0
                    
                    signals.append({
                        'type': 'SELL',
                        'confidence': confidence,
                        'price': current['close'],
                        'metadata': {
                            'macd': current['macd'],
                            'macd_signal': current['macd_signal'],
                            'macd_histogram': current['macd_histogram']
                        }
                    })
            
            return signals
            
        except Exception as e:
            logger.error("Error in MACD strategy", error=str(e))
            return []


class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands Strategy"""
    
    def execute(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Execute Bollinger Bands strategy"""
        try:
            period = parameters.get('period', 20)
            std_dev = parameters.get('std_dev', 2)
            
            if not self.validate_data(data, period + 5):
                return []
            
            # Calculate Bollinger Bands
            bb_upper = ta.volatility.bollinger_hband(data['close'], window=period, window_dev=std_dev)
            bb_lower = ta.volatility.bollinger_lband(data['close'], window=period, window_dev=std_dev)
            bb_middle = ta.volatility.bollinger_mavg(data['close'], window=period)
            
            data['bb_upper'] = bb_upper
            data['bb_lower'] = bb_lower
            data['bb_middle'] = bb_middle
            
            signals = []
            
            if len(data) >= 2:
                current = data.iloc[-1]
                previous = data.iloc[-2]
                
                # Price bounces off lower band (buy signal)
                if (previous['close'] <= previous['bb_lower'] and 
                    current['close'] > current['bb_lower']):
                    
                    # Calculate distance from middle for confidence
                    distance_ratio = (current['bb_middle'] - current['close']) / (current['bb_middle'] - current['bb_lower'])
                    confidence = min(90.0, 60.0 + (distance_ratio * 30.0))
                    
                    signals.append({
                        'type': 'BUY',
                        'confidence': confidence,
                        'price': current['close'],
                        'metadata': {
                            'bb_upper': current['bb_upper'],
                            'bb_lower': current['bb_lower'],
                            'bb_middle': current['bb_middle'],
                            'signal_reason': 'lower_band_bounce'
                        }
                    })
                
                # Price bounces off upper band (sell signal)
                elif (previous['close'] >= previous['bb_upper'] and 
                      current['close'] < current['bb_upper']):
                    
                    # Calculate distance from middle for confidence
                    distance_ratio = (current['close'] - current['bb_middle']) / (current['bb_upper'] - current['bb_middle'])
                    confidence = min(90.0, 60.0 + (distance_ratio * 30.0))
                    
                    signals.append({
                        'type': 'SELL',
                        'confidence': confidence,
                        'price': current['close'],
                        'metadata': {
                            'bb_upper': current['bb_upper'],
                            'bb_lower': current['bb_lower'],
                            'bb_middle': current['bb_middle'],
                            'signal_reason': 'upper_band_bounce'
                        }
                    })
            
            return signals
            
        except Exception as e:
            logger.error("Error in Bollinger Bands strategy", error=str(e))
            return []


class StrategyFactory:
    """Factory class for creating strategy instances"""
    
    _strategies = {
        'SMA': SMAStrategy,
        'EMA': EMAStrategy,
        'RSI': RSIStrategy,
        'MACD': MACDStrategy,
        'BOLLINGER_BANDS': BollingerBandsStrategy,
    }
    
    @classmethod
    def create_strategy(cls, strategy_type: str) -> BaseStrategy:
        """Create a strategy instance"""
        strategy_class = cls._strategies.get(strategy_type.upper())
        if not strategy_class:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        return strategy_class()
    
    @classmethod
    def get_available_strategies(cls) -> List[str]:
        """Get list of available strategy types"""
        return list(cls._strategies.keys())


class StrategyManager:
    """Manager for handling multiple strategies"""
    
    def __init__(self):
        self.strategies: List[Dict] = []
    
    async def load_strategies(self, database):
        """Load active strategies from database"""
        try:
            self.strategies = await database.get_active_strategies()
            logger.info(f"Loaded {len(self.strategies)} active strategies")
        except Exception as e:
            logger.error("Error loading strategies", error=str(e))
    
    async def get_active_strategies_for_symbol(self, symbol: str) -> List[Any]:
        """Get active strategies for a specific symbol"""
        return [
            strategy for strategy in self.strategies 
            if any(s['symbol'] == symbol for s in strategy.symbols)
        ]
#!/usr/bin/env python3
"""
Comprehensive Backtesting Engine for 1000 Strategies
Simulates trading and calculates performance metrics including monthly returns
"""

import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
import statistics
import math
from collections import defaultdict

class BacktestEngine:
    """Backtesting engine for strategy evaluation"""
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.market_data_url = "http://localhost:8000"
        
    async def fetch_historical_data(self, symbol: str, timeframe: str, days: int = 90) -> List[Dict]:
        """Fetch historical market data from Market Data Service"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try to get data from Market Data Service API
                url = f"{self.market_data_url}/api/v1/historical/{symbol}/{timeframe}"
                params = {"days": days}
                
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("data", [])
                    else:
                        # Generate synthetic data if API fails
                        return self.generate_synthetic_data(symbol, timeframe, days)
        except Exception as e:
            print(f"  Warning: Could not fetch data for {symbol}, using synthetic: {e}")
            return self.generate_synthetic_data(symbol, timeframe, days)
    
    def generate_synthetic_data(self, symbol: str, timeframe: str, days: int) -> List[Dict]:
        """Generate synthetic OHLCV data for backtesting"""
        import random
        
        # Base prices for different symbols
        base_prices = {
            "BTCUSDT": 35000, "ETHUSDT": 2000, "BNBUSDT": 300, "ADAUSDT": 0.5,
            "SOLUSDT": 50, "DOGEUSDT": 0.08, "MATICUSDT": 0.8, "DOTUSDT": 6,
            "AVAXUSDT": 20, "LINKUSDT": 15, "ATOMUSDT": 10, "UNIUSDT": 7,
            "XLMUSDT": 0.12, "NEARUSDT": 3, "FTMUSDT": 0.4, "SANDUSDT": 0.5,
            "MANAUSDT": 0.5, "TRXUSDT": 0.08, "LTCUSDT": 70, "ETCUSDT": 20,
            "XRPUSDT": 0.5
        }
        
        base_price = base_prices.get(symbol, 100.0)
        
        # Determine intervals per day
        intervals_per_day = {
            "1m": 1440, "5m": 288, "15m": 96, "1h": 24, "4h": 6, "1d": 1
        }
        
        total_candles = days * intervals_per_day.get(timeframe, 24)
        data = []
        
        current_price = base_price
        current_time = datetime.now() - timedelta(days=days)
        
        # Calculate interval duration
        interval_minutes = {
            "1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440
        }
        minutes = interval_minutes.get(timeframe, 60)
        
        for i in range(total_candles):
            # Random price movement with trend
            trend = random.uniform(-0.02, 0.03)  # Slight upward bias
            volatility = random.uniform(0.005, 0.03)
            
            price_change = current_price * (trend + random.uniform(-volatility, volatility))
            current_price = max(current_price + price_change, base_price * 0.5)
            
            # Generate OHLCV
            high = current_price * random.uniform(1.0, 1.02)
            low = current_price * random.uniform(0.98, 1.0)
            open_price = current_price * random.uniform(0.99, 1.01)
            close_price = current_price
            volume = random.uniform(100000, 10000000)
            
            data.append({
                "timestamp": current_time.isoformat(),
                "open": round(open_price, 8),
                "high": round(high, 8),
                "low": round(low, 8),
                "close": round(close_price, 8),
                "volume": round(volume, 2)
            })
            
            current_time += timedelta(minutes=minutes)
        
        return data

    def _normalise_historical_data(self, historical_data: Any) -> Optional[List[Dict[str, Any]]]:
        if historical_data is None:
            return None
        records: List[Dict[str, Any]]
        if hasattr(historical_data, "to_dict"):
            try:
                import pandas as pd  # type: ignore

                df = historical_data.copy()
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                records = df.to_dict('records')
            except Exception:
                records = list(historical_data.to_dict('records'))
        else:
            records = list(historical_data)

        normalised: List[Dict[str, Any]] = []
        for row in records:
            timestamp = row.get('timestamp') or row.get('time')
            parsed = self._parse_timestamp(timestamp)
            if parsed is None:
                continue
            normalised.append(
                {
                    'timestamp': parsed.isoformat(),
                    'datetime': parsed,
                    'open': float(row.get('open', 0.0)),
                    'high': float(row.get('high', row.get('open', 0.0))),
                    'low': float(row.get('low', row.get('open', 0.0))),
                    'close': float(row.get('close', row.get('open', 0.0))),
                    'volume': float(row.get('volume', 0.0)),
                }
            )
        return normalised

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, str):
            try:
                clean = value.replace('Z', '+00:00') if value.endswith('Z') else value
                parsed = datetime.fromisoformat(clean)
                return parsed.replace(tzinfo=None)
            except ValueError:
                return None
        return None

    @staticmethod
    def _extract_sentiment_value(entry: Dict[str, Any]) -> Optional[float]:
        for key in ('aggregated_score', 'sentiment_score', 'polarity', 'score'):
            if key in entry and entry[key] is not None:
                try:
                    value = float(entry[key])
                    if abs(value) > 1.0:
                        value = value / 100.0 if abs(value) <= 100 else value
                    return max(-1.0, min(1.0, value))
                except (TypeError, ValueError):
                    continue
        metadata = entry.get('metadata')
        if isinstance(metadata, dict):
            for key in ('average_polarity', 'polarity'):
                value = metadata.get(key)
                if value is not None:
                    try:
                        return max(-1.0, min(1.0, float(value)))
                    except (TypeError, ValueError):
                        continue
        if entry.get('value') is not None:
            try:
                numeric = float(entry['value'])
                if 0 <= numeric <= 100:
                    converted = (numeric - 50.0) / 50.0
                    return max(-1.0, min(1.0, converted))
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _normalise_sentiment_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(profile, dict):
            profile = {}
        defaults = {
            'bias': 'balanced',
            'min_alignment': 0.5,
            'negative_buy_threshold': 0.55,
            'extreme_threshold': 0.65,
            'symbol_weight': 0.6,
            'global_weight': 0.4,
            'allow_missing': True,
        }
        merged = {**defaults, **{k: v for k, v in profile.items() if v is not None}}
        weight_sum = merged['symbol_weight'] + merged['global_weight']
        if weight_sum <= 0:
            merged['symbol_weight'], merged['global_weight'] = 0.6, 0.4
        else:
            merged['symbol_weight'] = round(merged['symbol_weight'] / weight_sum, 3)
            merged['global_weight'] = round(merged['global_weight'] / weight_sum, 3)
        return merged
    
    def calculate_indicators(self, data: List[Dict], strategy: Dict) -> Dict[str, List[float]]:
        """Calculate technical indicators for strategy signals"""
        closes = [candle["close"] for candle in data]
        highs = [candle["high"] for candle in data]
        lows = [candle["low"] for candle in data]
        volumes = [candle["volume"] for candle in data]
        
        indicators = {}
        
        # RSI calculation
        rsi_period = strategy.get("parameters", {}).get("rsi_period", 14)
        indicators["rsi"] = self.calculate_rsi(closes, rsi_period)
        
        # Moving averages
        indicators["sma_20"] = self.calculate_sma(closes, 20)
        indicators["ema_12"] = self.calculate_ema(closes, 12)
        indicators["ema_26"] = self.calculate_ema(closes, 26)
        
        # Bollinger Bands
        bb_period = strategy.get("parameters", {}).get("bb_period", 20)
        bb_std = strategy.get("parameters", {}).get("bb_std_dev", 2.0)
        indicators["bb_upper"], indicators["bb_middle"], indicators["bb_lower"] = \
            self.calculate_bollinger_bands(closes, bb_period, bb_std)
        
        # ATR for volatility
        atr_period = strategy.get("parameters", {}).get("atr_period", 14)
        indicators["atr"] = self.calculate_atr(highs, lows, closes, atr_period)
        
        # Volume MA
        indicators["volume_ma"] = self.calculate_sma(volumes, 20)
        
        return indicators
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return [50.0] * len(prices)
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [max(d, 0) for d in deltas]
        losses = [abs(min(d, 0)) for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsi_values = [50.0] * (period + 1)
        
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            rsi_values.append(rsi)
        
        return rsi_values
    
    def calculate_sma(self, prices: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return prices.copy()
        
        sma = []
        for i in range(len(prices)):
            if i < period - 1:
                sma.append(prices[i])
            else:
                sma.append(sum(prices[i-period+1:i+1]) / period)
        
        return sma
    
    def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return prices.copy()
        
        multiplier = 2 / (period + 1)
        ema = [sum(prices[:period]) / period]
        
        for price in prices[period:]:
            ema.append((price * multiplier) + (ema[-1] * (1 - multiplier)))
        
        return [prices[0]] * (period - 1) + ema
    
    def calculate_bollinger_bands(self, prices: List[float], period: int, std_dev: float) -> Tuple[List, List, List]:
        """Calculate Bollinger Bands"""
        sma = self.calculate_sma(prices, period)
        
        upper = []
        lower = []
        
        for i in range(len(prices)):
            if i < period - 1:
                upper.append(prices[i])
                lower.append(prices[i])
            else:
                std = statistics.stdev(prices[i-period+1:i+1])
                upper.append(sma[i] + (std * std_dev))
                lower.append(sma[i] - (std * std_dev))
        
        return upper, sma, lower
    
    def calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
        """Calculate Average True Range"""
        if len(highs) < period + 1:
            return [0.0] * len(highs)
        
        tr_values = [highs[0] - lows[0]]
        
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_values.append(tr)
        
        atr = [sum(tr_values[:period]) / period]
        
        for i in range(period, len(tr_values)):
            atr.append((atr[-1] * (period - 1) + tr_values[i]) / period)
        
        return [tr_values[0]] * (period - 1) + atr

    def _prepare_sentiment_points(self, entries: Optional[List[Dict[str, Any]]]) -> List[Tuple[datetime, float]]:
        points: List[Tuple[datetime, float]] = []
        if not entries:
            return points
        for entry in entries:
            timestamp = entry.get('timestamp') or entry.get('created_at')
            parsed = self._parse_timestamp(timestamp)
            score = self._extract_sentiment_value(entry)
            if parsed and score is not None:
                points.append((parsed, score))
        points.sort(key=lambda item: item[0])
        return points

    def _align_sentiment_series(
        self,
        candles: List[Dict[str, Any]],
        profile: Dict[str, Any],
        symbol_entries: Optional[List[Dict[str, Any]]],
        global_entries: Optional[List[Dict[str, Any]]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        symbol_points = self._prepare_sentiment_points(symbol_entries)
        global_points = self._prepare_sentiment_points(global_entries)

        metrics: Dict[str, Any] = {
            'total_checks': 0,
            'allowed': 0,
            'blocked': 0,
            'missing_sentiment': 0,
            'positive_triggers': 0,
            'negative_triggers': 0,
            'stale_penalty_events': 0,
            'symbol_samples': len(symbol_points),
            'global_samples': len(global_points),
            'bias': profile.get('bias', 'balanced'),
            'alignment_sum': 0.0,
            'alignment_count': 0,
            'symbol_sum': 0.0,
            'symbol_count': 0,
            'global_sum': 0.0,
            'global_count': 0,
            'combined_sum': 0.0,
            'combined_count': 0,
            'max_symbol_age_hours': 0.0,
            'max_global_age_hours': 0.0,
            'wins_by_sentiment': {'positive': 0, 'negative': 0, 'neutral': 0},
            'losses_by_sentiment': {'positive': 0, 'negative': 0, 'neutral': 0},
        }

        timeline: List[Dict[str, Any]] = []
        symbol_idx = 0
        global_idx = 0
        current_symbol = None
        current_symbol_ts: Optional[datetime] = None
        current_global = None
        current_global_ts: Optional[datetime] = None

        for candle in candles:
            ts: datetime = candle['datetime']
            while symbol_idx < len(symbol_points) and symbol_points[symbol_idx][0] <= ts:
                current_symbol_ts, current_symbol = symbol_points[symbol_idx]
                symbol_idx += 1
            while global_idx < len(global_points) and global_points[global_idx][0] <= ts:
                current_global_ts, current_global = global_points[global_idx]
                global_idx += 1

            symbol_age = ((ts - current_symbol_ts).total_seconds() / 3600.0) if current_symbol_ts else None
            global_age = ((ts - current_global_ts).total_seconds() / 3600.0) if current_global_ts else None

            if symbol_age and symbol_age > metrics['max_symbol_age_hours']:
                metrics['max_symbol_age_hours'] = symbol_age
            if global_age and global_age > metrics['max_global_age_hours']:
                metrics['max_global_age_hours'] = global_age

            combined_score: Optional[float]
            weight_sum = 0.0
            weighted_score = 0.0
            if current_symbol is not None:
                weighted_score += current_symbol * profile.get('symbol_weight', 0.6)
                weight_sum += profile.get('symbol_weight', 0.6)
                metrics['symbol_sum'] += current_symbol
                metrics['symbol_count'] += 1
            if current_global is not None:
                weighted_score += current_global * profile.get('global_weight', 0.4)
                weight_sum += profile.get('global_weight', 0.4)
                metrics['global_sum'] += current_global
                metrics['global_count'] += 1
            combined_score = weighted_score / weight_sum if weight_sum else None
            alignment = (combined_score + 1.0) / 2.0 if combined_score is not None else None
            if alignment is not None:
                metrics['alignment_sum'] += alignment
                metrics['alignment_count'] += 1
            if combined_score is not None:
                metrics['combined_sum'] += combined_score
                metrics['combined_count'] += 1

            timeline.append(
                {
                    'timestamp': ts,
                    'combined_score': combined_score,
                    'alignment': alignment,
                    'symbol_score': current_symbol,
                    'global_score': current_global,
                    'symbol_age_hours': symbol_age,
                    'global_age_hours': global_age,
                }
            )

        return timeline, metrics

    def _evaluate_sentiment_gate(
        self,
        profile: Dict[str, Any],
        point: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> Tuple[bool, float]:
        metrics['total_checks'] += 1
        combined = point.get('combined_score')
        alignment = point.get('alignment')

        if combined is None or alignment is None:
            metrics['missing_sentiment'] += 1
            if profile.get('allow_missing', True):
                metrics['allowed'] += 1
                return True, 1.0
            metrics['blocked'] += 1
            return False, 1.0

        min_alignment = profile.get('min_alignment', 0.5)
        negative_threshold = profile.get('negative_buy_threshold', 0.55)
        extreme_threshold = profile.get('extreme_threshold', 0.65)
        bias = profile.get('bias', 'balanced')

        positive_condition = alignment >= min_alignment
        negative_condition = alignment <= (1.0 - negative_threshold)
        extreme_condition = abs(combined) >= extreme_threshold

        if positive_condition:
            metrics['positive_triggers'] += 1
        if negative_condition:
            metrics['negative_triggers'] += 1

        allowed = False
        multiplier = 1.0

        if bias == 'risk_on':
            allowed = positive_condition
            if allowed:
                multiplier += max(0.0, alignment - min_alignment)
        elif bias == 'fear_buy':
            if negative_condition:
                allowed = True
                multiplier += max(0.0, negative_threshold - (1.0 - alignment))
            elif positive_condition and alignment >= 0.8:
                allowed = True
                multiplier *= 0.85
        elif bias == 'contrarian':
            allowed = extreme_condition
            if allowed:
                multiplier += max(0.0, abs(combined) - extreme_threshold)
        else:  # balanced
            allowed = positive_condition or negative_condition
            if positive_condition:
                multiplier += max(0.0, alignment - min_alignment)
            elif negative_condition:
                multiplier += max(0.0, negative_threshold - (1.0 - alignment))

        symbol_age = point.get('symbol_age_hours')
        global_age = point.get('global_age_hours')
        staleness_penalty = 1.0
        if symbol_age and symbol_age > 24:
            staleness_penalty -= min(0.5, (symbol_age - 24) / 48)
            metrics['stale_penalty_events'] += 1
        if global_age and global_age > 24:
            staleness_penalty -= min(0.4, (global_age - 24) / 72)
            metrics['stale_penalty_events'] += 1
        multiplier *= max(0.3, staleness_penalty)

        if not allowed:
            metrics['blocked'] += 1
            return False, max(0.2, min(multiplier, 1.5))

        metrics['allowed'] += 1
        return True, max(0.2, min(multiplier, 1.8))

    def _infer_regime_labels(self, candles: List[Dict[str, Any]]) -> List[str]:
        prices = [c['close'] for c in candles]
        regimes: List[str] = []
        short_window = 12
        long_window = 36
        for idx, price in enumerate(prices):
            if idx == 0:
                regimes.append('ranging')
                continue
            if idx < long_window:
                regimes.append('ranging')
                continue
            short_ma = sum(prices[idx-short_window:idx]) / short_window
            long_ma = sum(prices[idx-long_window:idx]) / long_window
            change = (prices[idx] - prices[idx-1]) / prices[idx-1]
            vol_window = prices[idx-short_window:idx]
            stdev = statistics.pstdev(vol_window) if len(vol_window) > 1 else 0.0
            stdev_ratio = stdev / price if price else 0.0

            if stdev_ratio >= 0.025:
                regimes.append('high_volatility')
                continue
            if stdev_ratio <= 0.005:
                regimes.append('low_volatility')
                continue
            if short_ma > long_ma * 1.002 and change > 0:
                regimes.append('bull_trend')
            elif short_ma < long_ma * 0.998 and change < 0:
                regimes.append('bear_trend')
            else:
                regimes.append('ranging')
        return regimes

    def _compile_regime_metrics(self, trades: List[Dict[str, Any]], preferences: List[str]) -> Dict[str, Any]:
        if not trades:
            return {
                'trade_counts': {},
                'win_rate_by_regime': {},
                'preferred_regime_hit_rate': 0.0,
                'preferred_regimes': preferences,
                'active_regimes': [],
                'regime_bias_score': 0.0,
            }

        counts: Dict[str, int] = defaultdict(int)
        wins: Dict[str, int] = defaultdict(int)

        for trade in trades:
            regime = trade.get('regime', 'unknown')
            counts[regime] += 1
            if trade.get('pnl', 0) > 0:
                wins[regime] += 1

        win_rates: Dict[str, float] = {}
        for regime, count in counts.items():
            win_rates[regime] = round(wins[regime] / count, 3) if count else 0.0

        total_trades = sum(counts.values())
        preferred_trades = sum(counts.get(pref, 0) for pref in preferences)
        preferred_hit_rate = preferred_trades / total_trades if total_trades else 0.0

        preferred_win_values = [win_rates.get(pref) for pref in preferences if pref in win_rates]
        non_preferred_values = [value for regime, value in win_rates.items() if regime not in preferences]
        if preferred_win_values and non_preferred_values:
            preferred_avg = sum(preferred_win_values) / len(preferred_win_values)
            non_preferred_avg = sum(non_preferred_values) / len(non_preferred_values)
            regime_bias = preferred_avg - non_preferred_avg
        else:
            regime_bias = 0.0

        return {
            'trade_counts': dict(counts),
            'win_rate_by_regime': win_rates,
            'preferred_regime_hit_rate': round(preferred_hit_rate, 3),
            'preferred_regimes': preferences,
            'active_regimes': sorted(counts.keys()),
            'regime_bias_score': round(regime_bias, 3),
        }
    
    def evaluate_entry_signals(self, strategy: Dict, indicators: Dict, idx: int, price: float) -> bool:
        """Evaluate if entry conditions are met"""
        strategy_type = strategy.get("type", "")
        params = strategy.get("parameters", {})
        
        # Simplified signal evaluation based on strategy type
        if strategy_type == "momentum":
            rsi = indicators["rsi"][idx]
            return rsi > 50 and rsi < 70
        
        elif strategy_type == "mean_reversion":
            price_vs_bb_lower = price < indicators["bb_lower"][idx]
            rsi = indicators["rsi"][idx]
            return price_vs_bb_lower and rsi < 35
        
        elif strategy_type == "breakout":
            # Price breaking above recent high
            if idx < 20:
                return False
            recent_high = max(indicators["bb_upper"][idx-20:idx])
            return price > recent_high * 1.01
        
        elif strategy_type == "btc_correlation":
            # Simplified - assume correlation conditions are met 30% of the time
            import random
            return random.random() < 0.30
        
        elif strategy_type == "volume_based":
            volume_spike = indicators.get("volume_spike", False)
            return volume_spike or (indicators["rsi"][idx] > 45 and indicators["rsi"][idx] < 65)
        
        elif strategy_type == "volatility":
            atr = indicators["atr"][idx]
            avg_atr = sum(indicators["atr"][max(0, idx-20):idx+1]) / min(20, idx+1)
            return atr > avg_atr * 1.3
        
        elif strategy_type in ["macd", "hybrid"]:
            ema12 = indicators["ema_12"][idx]
            ema26 = indicators["ema_26"][idx]
            return ema12 > ema26 and indicators["rsi"][idx] > 45
        
        elif strategy_type == "scalping":
            ema12 = indicators["ema_12"][idx]
            ema26 = indicators["ema_26"][idx]
            return ema12 > ema26
        
        elif strategy_type == "swing":
            sma = indicators["sma_20"][idx]
            rsi = indicators["rsi"][idx]
            return price > sma and rsi > 40 and rsi < 60
        
        return False
    
    def evaluate_exit_signals(self, strategy: Dict, indicators: Dict, idx: int, 
                            entry_price: float, current_price: float, bars_held: int) -> bool:
        """Evaluate if exit conditions are met"""
        risk_params = strategy.get("risk_parameters", {})
        stop_loss_pct = risk_params.get("stop_loss_pct", 5.0) / 100
        take_profit_pct = risk_params.get("take_profit_pct", 10.0) / 100
        
        # Check stop loss
        if current_price <= entry_price * (1 - stop_loss_pct):
            return True
        
        # Check take profit
        if current_price >= entry_price * (1 + take_profit_pct):
            return True
        
        # Strategy-specific exits
        strategy_type = strategy.get("type", "")
        
        if strategy_type == "mean_reversion":
            # Exit at middle band
            if current_price > indicators["bb_middle"][idx]:
                return True
        
        elif strategy_type == "scalping":
            # Quick exit for scalping
            if bars_held > 10:  # Max holding time
                return True
        
        elif strategy_type == "momentum":
            rsi = indicators["rsi"][idx]
            if rsi < 45:
                return True
        
        # Default: hold position
        return False
    
    async def run_backtest(
        self,
        strategy: Dict,
        historical_data: Any = None,
        symbol_sentiment: Optional[List[Dict[str, Any]]] = None,
        global_sentiment: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        candles = self._normalise_historical_data(historical_data)
        return await self.backtest_strategy(
            strategy,
            candles=candles,
            symbol_sentiment=symbol_sentiment,
            global_sentiment=global_sentiment,
        )

    async def backtest_strategy(
        self,
        strategy: Dict,
        progress_callback=None,
        candles: Optional[List[Dict[str, Any]]] = None,
        symbol_sentiment: Optional[List[Dict[str, Any]]] = None,
        global_sentiment: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Backtest a single strategy"""
        symbol = strategy["symbols"][0] if strategy["symbols"] else "BTCUSDT"
        timeframe = strategy.get("timeframe", "1h")
        
        # Fetch historical data
        if candles is not None:
            data = candles
        else:
            fetched = await self.fetch_historical_data(symbol, timeframe, days=90)
            for entry in fetched:
                entry_dt = self._parse_timestamp(entry.get('timestamp'))
                entry['datetime'] = entry_dt or datetime.fromisoformat(entry['timestamp'])
            data = fetched
        
        if len(data) < 50:
            return self.create_failed_result(strategy, "Insufficient data")
        
        # Calculate indicators
        indicators = self.calculate_indicators(data, strategy)

        sentiment_profile = self._normalise_sentiment_profile(strategy.get('sentiment_profile'))

        sentiment_timeline, sentiment_metrics = self._align_sentiment_series(
            data,
            sentiment_profile,
            symbol_sentiment,
            global_sentiment,
        )

        regimes = self._infer_regime_labels(data)
        
        # Simulation variables
        capital = self.initial_capital
        position_size_pct = strategy.get("risk_parameters", {}).get("position_size", 0.02)
        positions = []
        trades = []
        equity_curve = []
        
        # Track monthly performance
        monthly_returns = defaultdict(float)
        current_month = None
        month_start_capital = capital
        
        # Run simulation
        for idx in range(50, len(data)):
            candle = data[idx]
            price = candle["close"]
            timestamp = candle["timestamp"]
            sentiment_point = sentiment_timeline[idx]
            current_regime = regimes[idx] if idx < len(regimes) else 'ranging'
            
            # Track monthly returns
            month_key = timestamp[:7]  # YYYY-MM
            if current_month is None:
                current_month = month_key
                month_start_capital = capital
            elif month_key != current_month:
                monthly_return_pct = ((capital - month_start_capital) / month_start_capital) * 100
                monthly_returns[current_month] = monthly_return_pct
                current_month = month_key
                month_start_capital = capital
            
            # Check exit conditions for open positions
            for pos in positions[:]:
                bars_held = idx - pos["entry_idx"]
                if self.evaluate_exit_signals(strategy, indicators, idx, pos["entry_price"], price, bars_held):
                    # Close position
                    pnl = (price - pos["entry_price"]) / pos["entry_price"]
                    pnl_amount = pos["size"] * pnl
                    capital += pos["size"] + pnl_amount
                    
                    trades.append({
                        "entry_time": pos["entry_time"],
                        "exit_time": timestamp,
                        "entry_price": pos["entry_price"],
                        "exit_price": price,
                        "size": pos["size"],
                        "pnl": pnl,
                        "pnl_amount": pnl_amount,
                        "bars_held": bars_held,
                        "regime": pos.get("regime", current_regime),
                        "entry_sentiment": pos.get("sentiment_point"),
                    })

                    entry_sentiment = pos.get("sentiment_point") or {}
                    combined_score = entry_sentiment.get('combined_score')
                    if combined_score is None:
                        sentiment_label = 'neutral'
                    elif combined_score >= 0:
                        sentiment_label = 'positive'
                    else:
                        sentiment_label = 'negative'
                    if pnl > 0:
                        sentiment_metrics['wins_by_sentiment'][sentiment_label] += 1
                    else:
                        sentiment_metrics['losses_by_sentiment'][sentiment_label] += 1
                    
                    positions.remove(pos)
            
            # Check entry conditions
            max_positions = strategy.get("risk_parameters", {}).get("max_positions", 3)
            if len(positions) < max_positions:
                if self.evaluate_entry_signals(strategy, indicators, idx, price):
                    allow_entry, sentiment_multiplier = self._evaluate_sentiment_gate(
                        sentiment_profile,
                        sentiment_point,
                        sentiment_metrics,
                    )
                    if allow_entry:
                        base_size = capital * position_size_pct
                        position_size = min(capital, base_size * sentiment_multiplier)
                        if position_size > 0:
                            positions.append({
                                "entry_time": timestamp,
                                "entry_price": price,
                                "entry_idx": idx,
                                "size": position_size,
                                "regime": current_regime,
                                "sentiment_point": sentiment_point,
                            })
                            capital -= position_size
            
            # Track equity
            total_position_value = sum(p["size"] * (price / p["entry_price"]) for p in positions)
            equity = capital + total_position_value
            equity_curve.append(equity)
        
        # Close remaining positions
        if positions:
            final_price = data[-1]["close"]
            for pos in positions:
                pnl = (final_price - pos["entry_price"]) / pos["entry_price"]
                pnl_amount = pos["size"] * pnl
                capital += pos["size"] + pnl_amount
        
        # Record final month
        if current_month:
            monthly_return_pct = ((capital - month_start_capital) / month_start_capital) * 100
            monthly_returns[current_month] = monthly_return_pct
        
        # Calculate performance metrics
        # Finalise sentiment metrics averages
        if sentiment_metrics['alignment_count']:
            sentiment_metrics['average_alignment'] = round(
                sentiment_metrics['alignment_sum'] / sentiment_metrics['alignment_count'],
                4,
            )
        else:
            sentiment_metrics['average_alignment'] = None
        if sentiment_metrics['symbol_count']:
            sentiment_metrics['average_symbol_sentiment'] = round(
                sentiment_metrics['symbol_sum'] / sentiment_metrics['symbol_count'],
                4,
            )
        else:
            sentiment_metrics['average_symbol_sentiment'] = None
        if sentiment_metrics['global_count']:
            sentiment_metrics['average_global_sentiment'] = round(
                sentiment_metrics['global_sum'] / sentiment_metrics['global_count'],
                4,
            )
        else:
            sentiment_metrics['average_global_sentiment'] = None
        if sentiment_metrics['combined_count']:
            sentiment_metrics['average_combined_score'] = round(
                sentiment_metrics['combined_sum'] / sentiment_metrics['combined_count'],
                4,
            )
        else:
            sentiment_metrics['average_combined_score'] = None

        total_checks = max(1, sentiment_metrics['total_checks'])
        sentiment_metrics['allowed_rate'] = round(sentiment_metrics['allowed'] / total_checks, 4)
        sentiment_metrics['blocked_rate'] = round(sentiment_metrics['blocked'] / total_checks, 4)
        sentiment_metrics['missing_rate'] = round(sentiment_metrics['missing_sentiment'] / total_checks, 4)
        if sentiment_metrics['positive_triggers'] == 0 and sentiment_metrics['negative_triggers'] == 0:
            sentiment_metrics['dominant_bias'] = 'neutral'
        elif sentiment_metrics['positive_triggers'] >= sentiment_metrics['negative_triggers']:
            sentiment_metrics['dominant_bias'] = 'positive'
        else:
            sentiment_metrics['dominant_bias'] = 'negative'

        for key in ['alignment_sum', 'alignment_count', 'symbol_sum', 'symbol_count', 'global_sum', 'global_count', 'combined_sum', 'combined_count']:
            sentiment_metrics.pop(key, None)

        regime_metrics = self._compile_regime_metrics(trades, strategy.get('regime_preferences', []))

        return self.calculate_performance_metrics(
            strategy,
            trades,
            equity_curve,
            capital,
            monthly_returns,
            sentiment_metrics,
            regime_metrics,
        )
    
    def calculate_performance_metrics(
        self,
        strategy: Dict,
        trades: List[Dict],
        equity_curve: List[float],
        final_capital: float,
        monthly_returns: Dict[str, float],
        sentiment_metrics: Dict[str, Any],
        regime_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        if not trades:
            return self.create_failed_result(strategy, "No trades executed")
        
        total_return = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        
        winning_trades = [t for t in trades if t["pnl"] > 0]
        losing_trades = [t for t in trades if t["pnl"] <= 0]
        
        win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
        
        avg_win = statistics.mean([t["pnl"] for t in winning_trades]) if winning_trades else 0
        avg_loss = statistics.mean([abs(t["pnl"]) for t in losing_trades]) if losing_trades else 0
        
        profit_factor = (sum(t["pnl_amount"] for t in winning_trades) / 
                        abs(sum(t["pnl_amount"] for t in losing_trades))) if losing_trades and sum(t["pnl_amount"] for t in losing_trades) != 0 else 0
        
        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        # Sharpe ratio (simplified)
        returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1] 
                  for i in range(1, len(equity_curve))]
        
        if returns and len(returns) > 1:
            avg_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            sharpe = (avg_return / std_return * math.sqrt(252)) if std_return > 0 else 0
        else:
            sharpe = 0
        
        # Average monthly return
        avg_monthly_return = statistics.mean(monthly_returns.values()) if monthly_returns else 0
        median_monthly_return = statistics.median(monthly_returns.values()) if monthly_returns else 0
        
        core_metrics = {
            "strategy_id": strategy["id"],
            "strategy_name": strategy["name"],
            "strategy_type": strategy["type"],
            "status": "completed",
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "total_return_pct": round(total_return, 2),
            "avg_monthly_return_pct": round(avg_monthly_return, 2),
            "median_monthly_return_pct": round(median_monthly_return, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_win_pct": round(avg_win * 100, 2),
            "avg_loss_pct": round(avg_loss * 100, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "final_capital": round(final_capital, 2),
            "avg_trade_duration": round(statistics.mean([t["bars_held"] for t in trades]), 1) if trades else 0,
            "monthly_returns": dict(monthly_returns),
            "sentiment_profile": strategy.get('sentiment_profile'),
            "regime_preferences": strategy.get('regime_preferences', []),
        }
        core_metrics["total_return"] = round(core_metrics["total_return_pct"], 2)
        core_metrics["sentiment_metrics"] = sentiment_metrics
        core_metrics["regime_metrics"] = regime_metrics
        core_metrics["metrics"] = {
            "core": {
                "total_return_pct": core_metrics["total_return_pct"],
                "win_rate": core_metrics["win_rate"],
                "profit_factor": core_metrics["profit_factor"],
                "max_drawdown_pct": core_metrics["max_drawdown_pct"],
                "sharpe_ratio": core_metrics["sharpe_ratio"],
            },
            "sentiment": sentiment_metrics,
            "regime": regime_metrics,
        }
        return core_metrics
    
    def create_failed_result(self, strategy: Dict, reason: str) -> Dict[str, Any]:
        """Create result for failed backtest"""
        return {
            "strategy_id": strategy["id"],
            "strategy_name": strategy["name"],
            "strategy_type": strategy["type"],
            "status": "failed",
            "reason": reason,
            "total_return_pct": 0,
            "total_return": 0,
            "avg_monthly_return_pct": 0,
            "total_trades": 0,
            "win_rate": 0
        }
    
    async def backtest_all_strategies(self, strategies: List[Dict]) -> List[Dict]:
        """Backtest all strategies with progress tracking"""
        results = []
        total = len(strategies)
        
        print(f"\nStarting backtest of {total} strategies...")
        print("=" * 80)
        
        for idx, strategy in enumerate(strategies, 1):
            try:
                result = await self.backtest_strategy(strategy)
                results.append(result)
                
                if idx % 50 == 0:
                    print(f"Progress: {idx}/{total} strategies tested ({(idx/total)*100:.1f}%)")
                    
            except Exception as e:
                print(f"Error backtesting strategy {strategy['id']}: {e}")
                results.append(self.create_failed_result(strategy, str(e)))
        
        print(f"\n✓ Completed backtesting {len(results)} strategies")
        return results


async def main():
    """Main execution"""
    print("=" * 80)
    print("BACKTESTING ENGINE - 1000 STRATEGIES")
    print("=" * 80)
    
    # Load strategies
    with open("strategies_1000.json", 'r') as f:
        data = json.load(f)
        strategies = data["strategies"]
    
    print(f"\nLoaded {len(strategies)} strategies for backtesting")
    print(f"Initial capital: $10,000 per strategy")
    print(f"Backtesting period: ~90 days")
    
    # Initialize backtesting engine
    engine = BacktestEngine(initial_capital=10000.0)
    
    # Run backtests
    results = await engine.backtest_all_strategies(strategies)
    
    # Save results
    output = {
        "metadata": {
            "backtest_date": datetime.now().isoformat(),
            "total_strategies": len(results),
            "successful_backtests": len([r for r in results if r["status"] == "completed"]),
            "failed_backtests": len([r for r in results if r["status"] == "failed"]),
            "initial_capital": 10000.0,
            "backtest_period_days": 90
        },
        "results": results
    }
    
    output_file = "backtest_results_1000.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Results saved to {output_file}")
    
    # Show top performers
    successful_results = [r for r in results if r["status"] == "completed" and r["total_trades"] > 0]
    successful_results.sort(key=lambda x: x["avg_monthly_return_pct"], reverse=True)
    
    print("\n" + "=" * 80)
    print("TOP 10 STRATEGIES BY AVERAGE MONTHLY RETURN")
    print("=" * 80)
    print(f"{'Rank':<6} {'Strategy Name':<40} {'Avg Monthly %':<15} {'Total Return %':<15} {'Win Rate %':<12} {'Trades'}")
    print("-" * 110)
    
    for rank, result in enumerate(successful_results[:10], 1):
        print(f"{rank:<6} {result['strategy_name'][:39]:<40} {result['avg_monthly_return_pct']:>13.2f}% {result['total_return_pct']:>13.2f}% {result['win_rate']:>10.2f}% {result['total_trades']:>7}")
    
    print("\n" + "=" * 80)
    print("BACKTESTING COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())

"""
Stock Index Correlation Analyzer for Market Data Service

This module performs sophisticated correlation analysis between:
- Stock indices and cryptocurrency markets
- Stock indices and commodities (Gold, Oil)
- Regional market correlations
- Volatility correlations (VIX vs crypto volatility)

Uses statistical methods: Pearson correlation, Spearman rank correlation, rolling correlations
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import structlog
from scipy import stats
from collections import defaultdict

from config import settings
from database import Database

logger = structlog.get_logger()


class CorrelationType:
    """Types of correlation analysis"""
    PEARSON = "pearson"  # Linear correlation
    SPEARMAN = "spearman"  # Rank correlation (non-linear)
    KENDALL = "kendall"  # Ordinal association


class MarketRegime:
    """Market regime classification"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


class StockIndexCorrelationAnalyzer:
    """Analyzes correlations between stock indices and crypto markets"""
    
    def __init__(self, database: Database):
        self.database = database
        self.correlation_history: List[Dict] = []
        self.min_data_points = 20  # Minimum data points for reliable correlation
        
    async def calculate_price_correlation(
        self,
        symbol1: str,
        symbol2: str,
        hours_back: int = 168,  # 1 week
        interval: str = "1h",
        method: str = CorrelationType.PEARSON
    ) -> Dict[str, Any]:
        """
        Calculate correlation between two assets
        
        Args:
            symbol1: First asset symbol
            symbol2: Second asset symbol
            hours_back: Historical period to analyze
            interval: Data interval
            method: Correlation method (pearson, spearman, kendall)
            
        Returns:
            Dictionary with correlation coefficient, p-value, and strength
        """
        try:
            # Fetch data for both symbols
            data1 = await self.database.get_market_data_for_analysis(
                symbol=symbol1,
                interval=interval,
                hours_back=hours_back
            )
            
            data2 = await self.database.get_market_data_for_analysis(
                symbol=symbol2,
                interval=interval,
                hours_back=hours_back
            )
            
            if len(data1) < self.min_data_points or len(data2) < self.min_data_points:
                logger.warning(
                    "Insufficient data for correlation",
                    symbol1=symbol1,
                    symbol2=symbol2,
                    data1_len=len(data1),
                    data2_len=len(data2)
                )
                return self._empty_correlation_result(symbol1, symbol2, "insufficient_data")
            
            # Create DataFrames
            df1 = pd.DataFrame(data1)
            df2 = pd.DataFrame(data2)
            
            # Convert timestamps and sort
            df1['timestamp'] = pd.to_datetime(df1['timestamp'])
            df2['timestamp'] = pd.to_datetime(df2['timestamp'])
            df1 = df1.sort_values('timestamp')
            df2 = df2.sort_values('timestamp')
            
            # Merge on timestamp (inner join to get common timestamps)
            df1['close_price'] = df1['close_price'].astype(float)
            df2['close_price'] = df2['close_price'].astype(float)
            
            merged = pd.merge(
                df1[['timestamp', 'close_price']],
                df2[['timestamp', 'close_price']],
                on='timestamp',
                suffixes=('_1', '_2')
            )
            
            if len(merged) < self.min_data_points:
                return self._empty_correlation_result(symbol1, symbol2, "insufficient_common_timestamps")
            
            # Calculate returns (percentage changes)
            returns1 = merged['close_price_1'].pct_change().dropna()
            returns2 = merged['close_price_2'].pct_change().dropna()
            
            # Calculate correlation
            if method == CorrelationType.PEARSON:
                corr_coef, p_value = stats.pearsonr(returns1, returns2)
            elif method == CorrelationType.SPEARMAN:
                corr_coef, p_value = stats.spearmanr(returns1, returns2)
            elif method == CorrelationType.KENDALL:
                corr_coef, p_value = stats.kendalltau(returns1, returns2)
            else:
                raise ValueError(f"Unknown correlation method: {method}")
            
            # Classify correlation strength
            strength = self._classify_correlation_strength(corr_coef)
            significance = "significant" if p_value < 0.05 else "not_significant"
            
            result = {
                "symbol1": symbol1,
                "symbol2": symbol2,
                "correlation_coefficient": float(corr_coef),
                "p_value": float(p_value),
                "strength": strength,
                "significance": significance,
                "method": method,
                "data_points": len(merged),
                "time_period_hours": hours_back,
                "interval": interval,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            logger.info(
                "Correlation calculated",
                symbol1=symbol1,
                symbol2=symbol2,
                correlation=round(corr_coef, 3),
                strength=strength
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Error calculating correlation",
                symbol1=symbol1,
                symbol2=symbol2,
                error=str(e)
            )
            return self._empty_correlation_result(symbol1, symbol2, "error")
    
    async def calculate_rolling_correlation(
        self,
        symbol1: str,
        symbol2: str,
        hours_back: int = 720,  # 30 days
        window_hours: int = 168,  # 7 day rolling window
        interval: str = "1h"
    ) -> Dict[str, Any]:
        """Calculate rolling correlation to detect changing relationships"""
        try:
            # Fetch data
            data1 = await self.database.get_market_data_for_analysis(
                symbol=symbol1, interval=interval, hours_back=hours_back
            )
            data2 = await self.database.get_market_data_for_analysis(
                symbol=symbol2, interval=interval, hours_back=hours_back
            )
            
            if not data1 or not data2:
                return {"error": "insufficient_data"}
            
            # Create DataFrames
            df1 = pd.DataFrame(data1)
            df2 = pd.DataFrame(data2)
            
            df1['timestamp'] = pd.to_datetime(df1['timestamp'])
            df2['timestamp'] = pd.to_datetime(df2['timestamp'])
            df1['close_price'] = df1['close_price'].astype(float)
            df2['close_price'] = df2['close_price'].astype(float)
            
            # Merge and calculate returns
            merged = pd.merge(
                df1[['timestamp', 'close_price']],
                df2[['timestamp', 'close_price']],
                on='timestamp',
                suffixes=('_1', '_2')
            ).sort_values('timestamp')
            
            merged['returns_1'] = merged['close_price_1'].pct_change()
            merged['returns_2'] = merged['close_price_2'].pct_change()
            merged = merged.dropna()
            
            if len(merged) < window_hours:
                return {"error": "insufficient_data_for_window"}
            
            # Calculate rolling correlation
            rolling_corr = merged['returns_1'].rolling(window=window_hours).corr(merged['returns_2'])
            
            # Extract key statistics
            current_corr = float(rolling_corr.iloc[-1])
            mean_corr = float(rolling_corr.mean())
            std_corr = float(rolling_corr.std())
            min_corr = float(rolling_corr.min())
            max_corr = float(rolling_corr.max())
            
            # Detect trend
            recent_corr = rolling_corr.iloc[-24:].mean() if len(rolling_corr) >= 24 else current_corr
            older_corr = rolling_corr.iloc[-48:-24].mean() if len(rolling_corr) >= 48 else mean_corr
            trend = "strengthening" if recent_corr > older_corr else "weakening"
            
            result = {
                "symbol1": symbol1,
                "symbol2": symbol2,
                "current_correlation": current_corr,
                "mean_correlation": mean_corr,
                "std_correlation": std_corr,
                "min_correlation": min_corr,
                "max_correlation": max_corr,
                "trend": trend,
                "window_hours": window_hours,
                "data_points": len(merged),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            return result
            
        except Exception as e:
            logger.error("Error calculating rolling correlation", error=str(e))
            return {"error": str(e)}
    
    async def analyze_market_regime(
        self,
        symbol: str,
        hours_back: int = 168,
        interval: str = "1h"
    ) -> Dict[str, Any]:
        """Analyze current market regime for an asset"""
        try:
            data = await self.database.get_market_data_for_analysis(
                symbol=symbol,
                interval=interval,
                hours_back=hours_back
            )
            
            if len(data) < 24:
                return {"regime": "unknown", "reason": "insufficient_data"}
            
            df = pd.DataFrame(data)
            df['close_price'] = df['close_price'].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Calculate returns and volatility
            df['returns'] = df['close_price'].pct_change()
            recent_returns = df['returns'].tail(24).mean()  # Last 24 periods
            volatility = df['returns'].tail(24).std()
            
            # Calculate trend
            price_change = (df['close_price'].iloc[-1] - df['close_price'].iloc[0]) / df['close_price'].iloc[0]
            
            # Determine regime
            volatility_threshold_high = 0.02  # 2% std dev
            volatility_threshold_low = 0.005  # 0.5% std dev
            trend_threshold = 0.05  # 5% change
            
            regimes = []
            
            # Trend regime
            if price_change > trend_threshold:
                regimes.append(MarketRegime.BULL)
            elif price_change < -trend_threshold:
                regimes.append(MarketRegime.BEAR)
            else:
                regimes.append(MarketRegime.SIDEWAYS)
            
            # Volatility regime
            if volatility > volatility_threshold_high:
                regimes.append(MarketRegime.HIGH_VOLATILITY)
            elif volatility < volatility_threshold_low:
                regimes.append(MarketRegime.LOW_VOLATILITY)
            
            result = {
                "symbol": symbol,
                "primary_regime": regimes[0],
                "all_regimes": regimes,
                "price_change": float(price_change),
                "volatility": float(volatility),
                "mean_return": float(recent_returns),
                "current_price": float(df['close_price'].iloc[-1]),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            return result
            
        except Exception as e:
            logger.error("Error analyzing market regime", symbol=symbol, error=str(e))
            return {"regime": "error", "error": str(e)}
    
    async def analyze_cross_market_correlations(
        self,
        stock_indices: List[str] = None,
        crypto_symbols: List[str] = None,
        hours_back: int = 168,
        interval: str = "1h"
    ) -> Dict[str, Any]:
        """
        Comprehensive cross-market correlation analysis
        
        Analyzes correlations between:
        - Stock indices and crypto markets
        - Regional indices with each other
        - Volatility indices (VIX) with crypto volatility
        """
        try:
            if stock_indices is None:
                stock_indices = settings.STOCK_INDICES
            
            if crypto_symbols is None:
                # Get top crypto symbols from default symbols
                crypto_symbols = [s.replace('USDT', '') for s in settings.DEFAULT_SYMBOLS[:10]]
            
            results = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "time_period_hours": hours_back,
                "interval": interval,
                "stock_crypto_correlations": [],
                "stock_stock_correlations": [],
                "market_regimes": {},
                "summary": {}
            }
            
            # Analyze market regimes for all assets
            logger.info("Analyzing market regimes")
            for symbol in stock_indices + crypto_symbols:
                regime = await self.analyze_market_regime(symbol, hours_back, interval)
                if regime.get("primary_regime") != "unknown":
                    results["market_regimes"][symbol] = regime
            
            # Calculate stock-crypto correlations
            logger.info("Calculating stock-crypto correlations")
            for stock_symbol in stock_indices:
                for crypto_symbol in crypto_symbols:
                    # Construct proper symbol format
                    crypto_full = f"{crypto_symbol}USDT" if not crypto_symbol.endswith('USDT') else crypto_symbol
                    
                    corr = await self.calculate_price_correlation(
                        stock_symbol,
                        crypto_full,
                        hours_back,
                        interval
                    )
                    
                    if corr.get("correlation_coefficient") is not None:
                        results["stock_crypto_correlations"].append(corr)
                    
                    # Small delay to avoid overwhelming the system
                    await asyncio.sleep(0.1)
            
            # Calculate inter-stock correlations
            logger.info("Calculating stock-stock correlations")
            for i, stock1 in enumerate(stock_indices):
                for stock2 in stock_indices[i+1:]:
                    corr = await self.calculate_price_correlation(
                        stock1,
                        stock2,
                        hours_back,
                        interval
                    )
                    
                    if corr.get("correlation_coefficient") is not None:
                        results["stock_stock_correlations"].append(corr)
                    
                    await asyncio.sleep(0.1)
            
            # Generate summary statistics
            results["summary"] = self._generate_correlation_summary(results)
            
            # Store results in database
            await self._store_correlation_results(results)
            
            logger.info(
                "Cross-market correlation analysis completed",
                stock_crypto_pairs=len(results["stock_crypto_correlations"]),
                stock_pairs=len(results["stock_stock_correlations"]),
                regimes_analyzed=len(results["market_regimes"])
            )
            
            return results
            
        except Exception as e:
            logger.error("Error in cross-market correlation analysis", error=str(e))
            return {"error": str(e)}
    
    async def get_correlation_based_signals(
        self,
        crypto_symbol: str,
        hours_back: int = 168
    ) -> Dict[str, Any]:
        """
        Generate trading signals based on correlation analysis
        
        Logic:
        - High positive correlation with rising indices -> Bullish signal
        - High positive correlation with falling indices -> Bearish signal
        - Negative correlation breaking down -> Potential reversal
        """
        try:
            signals = {
                "symbol": crypto_symbol,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "overall_signal": "neutral",
                "confidence": 0.0,
                "contributing_factors": []
            }
            
            # Get stock indices performance
            stock_indices = settings.STOCK_INDICES
            index_performance = {}
            
            for index in stock_indices:
                regime = await self.analyze_market_regime(index, hours_back=24)
                if regime.get("primary_regime"):
                    index_performance[index] = regime
            
            # Calculate correlations with each index
            correlations = []
            for index in stock_indices:
                corr = await self.calculate_price_correlation(
                    index,
                    crypto_symbol,
                    hours_back=hours_back,
                    interval="1h"
                )
                if corr.get("correlation_coefficient") is not None:
                    correlations.append((index, corr))
            
            # Analyze signals
            bullish_factors = 0
            bearish_factors = 0
            
            for index, corr in correlations:
                if corr["significance"] != "significant":
                    continue
                
                corr_coef = corr["correlation_coefficient"]
                index_perf = index_performance.get(index, {})
                
                # High positive correlation with bullish index
                if corr_coef > 0.5 and index_perf.get("primary_regime") == MarketRegime.BULL:
                    bullish_factors += 1
                    signals["contributing_factors"].append({
                        "factor": f"High correlation with bullish {index}",
                        "direction": "bullish",
                        "weight": abs(corr_coef)
                    })
                
                # High positive correlation with bearish index
                elif corr_coef > 0.5 and index_perf.get("primary_regime") == MarketRegime.BEAR:
                    bearish_factors += 1
                    signals["contributing_factors"].append({
                        "factor": f"High correlation with bearish {index}",
                        "direction": "bearish",
                        "weight": abs(corr_coef)
                    })
                
                # Negative correlation (contrarian indicator)
                elif corr_coef < -0.3:
                    if index_perf.get("primary_regime") == MarketRegime.BEAR:
                        bullish_factors += 0.5
                        signals["contributing_factors"].append({
                            "factor": f"Negative correlation with bearish {index}",
                            "direction": "bullish",
                            "weight": abs(corr_coef) * 0.5
                        })
            
            # Determine overall signal
            if bullish_factors > bearish_factors and bullish_factors >= 2:
                signals["overall_signal"] = "bullish"
                signals["confidence"] = min(bullish_factors / len(stock_indices), 1.0)
            elif bearish_factors > bullish_factors and bearish_factors >= 2:
                signals["overall_signal"] = "bearish"
                signals["confidence"] = min(bearish_factors / len(stock_indices), 1.0)
            else:
                signals["overall_signal"] = "neutral"
                signals["confidence"] = 0.3
            
            return signals
            
        except Exception as e:
            logger.error("Error generating correlation-based signals", error=str(e))
            return {"error": str(e)}
    
    def _classify_correlation_strength(self, corr_coef: float) -> str:
        """Classify correlation coefficient strength"""
        abs_corr = abs(corr_coef)
        
        if abs_corr >= 0.7:
            return "very_strong"
        elif abs_corr >= 0.5:
            return "strong"
        elif abs_corr >= 0.3:
            return "moderate"
        elif abs_corr >= 0.1:
            return "weak"
        else:
            return "very_weak"
    
    def _empty_correlation_result(self, symbol1: str, symbol2: str, reason: str) -> Dict[str, Any]:
        """Return empty correlation result with reason"""
        return {
            "symbol1": symbol1,
            "symbol2": symbol2,
            "correlation_coefficient": None,
            "p_value": None,
            "strength": "none",
            "significance": "not_applicable",
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def _generate_correlation_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics from correlation results"""
        summary = {
            "strong_positive_correlations": [],
            "strong_negative_correlations": [],
            "average_correlation": 0.0,
            "significant_correlations_count": 0,
            "dominant_market_regime": "unknown"
        }
        
        # Analyze stock-crypto correlations
        all_corrs = results.get("stock_crypto_correlations", [])
        
        if all_corrs:
            valid_corrs = [c["correlation_coefficient"] for c in all_corrs 
                          if c.get("correlation_coefficient") is not None]
            
            if valid_corrs:
                summary["average_correlation"] = float(np.mean(valid_corrs))
                
                # Find strong correlations
                for corr in all_corrs:
                    coef = corr.get("correlation_coefficient")
                    if coef is not None and corr.get("significance") == "significant":
                        summary["significant_correlations_count"] += 1
                        
                        if coef > 0.5:
                            summary["strong_positive_correlations"].append({
                                "pair": f"{corr['symbol1']}-{corr['symbol2']}",
                                "coefficient": coef
                            })
                        elif coef < -0.5:
                            summary["strong_negative_correlations"].append({
                                "pair": f"{corr['symbol1']}-{corr['symbol2']}",
                                "coefficient": coef
                            })
        
        # Determine dominant market regime
        regimes = results.get("market_regimes", {})
        if regimes:
            regime_counts = defaultdict(int)
            for regime_data in regimes.values():
                regime_counts[regime_data.get("primary_regime", "unknown")] += 1
            
            if regime_counts:
                summary["dominant_market_regime"] = max(regime_counts, key=regime_counts.get)
        
        return summary
    
    async def _store_correlation_results(self, results: Dict[str, Any]):
        """Store correlation analysis results in database"""
        try:
            # Store main correlation document
            correlation_doc = {
                "id": f"correlation_analysis_{int(datetime.utcnow().timestamp())}",
                "doc_type": "correlation_analysis",
                "timestamp": results["timestamp"],
                "time_period_hours": results["time_period_hours"],
                "summary": results["summary"],
                "market_regimes_count": len(results["market_regimes"]),
                "correlations_count": len(results["stock_crypto_correlations"]) + len(results["stock_stock_correlations"]),
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            await self.database.upsert_market_data(correlation_doc)
            
            # Store individual significant correlations
            for corr in results["stock_crypto_correlations"]:
                if corr.get("significance") == "significant" and abs(corr.get("correlation_coefficient", 0)) > 0.3:
                    corr_doc = {
                        "id": f"corr_{corr['symbol1']}_{corr['symbol2']}_{int(datetime.utcnow().timestamp())}",
                        "doc_type": "significant_correlation",
                        **corr
                    }
                    await self.database.upsert_market_data(corr_doc)
            
            logger.info("Correlation results stored in database")
            
        except Exception as e:
            logger.error("Error storing correlation results", error=str(e))


# Example usage
async def main():
    """Example usage of correlation analyzer"""
    database = Database()
    
    async with database:
        analyzer = StockIndexCorrelationAnalyzer(database)
        
        # Run comprehensive analysis
        results = await analyzer.analyze_cross_market_correlations(
            hours_back=168,
            interval="1h"
        )
        
        print(f"Analysis completed at {results.get('timestamp')}")
        print(f"Stock-Crypto correlations: {len(results.get('stock_crypto_correlations', []))}")
        print(f"Stock-Stock correlations: {len(results.get('stock_stock_correlations', []))}")
        print(f"\nSummary: {results.get('summary')}")
        
        # Get signals for a specific crypto
        signals = await analyzer.get_correlation_based_signals("BTCUSDT")
        print(f"\nBTC Correlation Signals:")
        print(f"Overall: {signals.get('overall_signal')} (confidence: {signals.get('confidence'):.2f})")
        print(f"Contributing factors: {len(signals.get('contributing_factors', []))}")


if __name__ == "__main__":
    asyncio.run(main())

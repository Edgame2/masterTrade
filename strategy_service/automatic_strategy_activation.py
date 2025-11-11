"""
Automatic Strategy Activation Manager

This module manages the automatic activation of the best performing strategies
based on the MAX_ACTIVE_STRATEGIES setting from the database.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import structlog

from postgres_database import Database

logger = structlog.get_logger()

@dataclass
class StrategyCandidate:
    strategy_id: str
    name: str
    performance_score: float
    sharpe_ratio: float
    total_return: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    last_trade_date: datetime
    backtest_score: float
    market_alignment_score: float
    risk_score: float
    sentiment_alignment_score: float
    overall_score: float
    sentiment_context: Dict[str, Any] = field(default_factory=dict)

class AutomaticStrategyActivationManager:
    """
    Manages automatic activation of best performing strategies
    
    Features:
    - Reads MAX_ACTIVE_STRATEGIES from Settings table (default: 2)
    - Evaluates all strategies using comprehensive scoring
    - Automatically activates/deactivates strategies to maintain optimal count
    - Prevents frequent switching with stability controls
    - Logs all activation/deactivation decisions
    """
    
    def __init__(self, database: Database):
        self.database = database
        self.max_active_strategies = 2  # Default value
        self.min_stability_hours = 4    # Minimum hours between activation changes
        self.last_activation_check = None
        
    async def initialize(self):
        """Initialize the activation manager"""
        try:
            # Load max active strategies setting
            await self._load_max_active_strategies_setting()
            
            # Perform initial activation check
            await self.check_and_update_active_strategies()
            
            logger.info(
                "Automatic Strategy Activation Manager initialized",
                max_active_strategies=self.max_active_strategies
            )
            
        except Exception as e:
            logger.error(f"Error initializing activation manager: {e}")
            raise

    @staticmethod
    def _parse_trade_timestamp(trade: Dict[str, Any]) -> datetime:
        """Normalize trade timestamps to aware datetime objects."""
        raw = trade.get("timestamp") or trade.get("executed_at")
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str):
            try:
                # Handle both ISO8601 with or without timezone suffix
                value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.warning("Failed to parse trade timestamp", raw=raw)
        return datetime.min.replace(tzinfo=timezone.utc)
    
    async def _load_max_active_strategies_setting(self):
        """Load MAX_ACTIVE_STRATEGIES setting from database"""
        try:
            setting = await self.database.get_setting("MAX_ACTIVE_STRATEGIES")
            if setting and setting.get("value") is not None:
                try:
                    self.max_active_strategies = int(setting["value"])
                    logger.info(
                        "Loaded MAX_ACTIVE_STRATEGIES setting",
                        value=self.max_active_strategies,
                    )
                    return
                except (ValueError, TypeError):
                    logger.warning(
                        "Invalid MAX_ACTIVE_STRATEGIES value, reverting to default",
                        value=setting.get("value"),
                    )
            # Setting missing or invalid -> persist default
            await self._create_max_active_strategies_setting()
        except Exception as e:
            logger.error(f"Error loading MAX_ACTIVE_STRATEGIES setting: {e}")
            self.max_active_strategies = 2  # Use default
    
    async def _create_max_active_strategies_setting(self):
        """Create MAX_ACTIVE_STRATEGIES setting with default value"""
        try:
            await self.database.upsert_setting(
                "MAX_ACTIVE_STRATEGIES",
                value="2",
                description="Maximum number of active trading strategies",
                value_type="integer",
                metadata={"source": "automatic_strategy_activation"},
            )
            self.max_active_strategies = 2
            logger.info("Persisted default MAX_ACTIVE_STRATEGIES value", value=2)
        except Exception as e:
            logger.error(f"Error creating MAX_ACTIVE_STRATEGIES setting: {e}")
            self.max_active_strategies = 2
    
    async def check_and_update_active_strategies(self) -> Dict[str, List[str]]:
        """
        Check current active strategies and update if necessary
        
        Returns:
            Dict with 'activated' and 'deactivated' strategy IDs
        """
        try:
            # Check stability period
            if not self._should_check_activation():
                return {'activated': [], 'deactivated': []}
            
            # Get current active strategies
            current_active = await self._get_current_active_strategies()
            
            # Get all strategy candidates with scores
            candidates = await self._evaluate_all_strategy_candidates()
            
            # Determine optimal active strategies
            optimal_active = await self._select_optimal_strategies(candidates)
            
            # Calculate changes needed
            changes = await self._calculate_strategy_changes(current_active, optimal_active)
            
            # Apply changes
            activation_results = await self._apply_strategy_changes(changes)
            
            # Update last check time
            self.last_activation_check = datetime.now(timezone.utc)
            
            # Log results
            if activation_results['activated'] or activation_results['deactivated']:
                logger.info(
                    "Strategy activation updated",
                    activated=len(activation_results['activated']),
                    deactivated=len(activation_results['deactivated']),
                    total_active=len(optimal_active),
                    max_allowed=self.max_active_strategies
                )
            
            return activation_results
            
        except Exception as e:
            logger.error(f"Error checking and updating active strategies: {e}")
            return {'activated': [], 'deactivated': []}
    
    def _should_check_activation(self) -> bool:
        """Check if enough time has passed since last activation check"""
        if self.last_activation_check is None:
            return True
        
        time_since_last = datetime.now(timezone.utc) - self.last_activation_check
        return time_since_last.total_seconds() >= (self.min_stability_hours * 3600)
    
    async def _get_current_active_strategies(self) -> List[str]:
        """Get list of currently active strategy IDs"""
        try:
            strategies = await self.database.get_active_strategies()
            return [strategy.id for strategy in strategies]
        except Exception as e:
            logger.error(f"Error getting current active strategies: {e}")
            return []
    
    async def _evaluate_all_strategy_candidates(self) -> List[StrategyCandidate]:
        """Evaluate all strategies and return candidates with scores"""
        try:
            strategies = await self.database.get_all_strategies()
            candidates: List[StrategyCandidate] = []

            for strategy in strategies:
                if not strategy.get("enabled", True):
                    continue
                if strategy.get("status") not in {"active", "inactive", "paused"}:
                    continue
                try:
                    candidate = await self._evaluate_strategy_candidate(strategy)
                    if candidate:
                        candidates.append(candidate)
                except Exception as error:
                    logger.warning(
                        "Error evaluating strategy candidate",
                        strategy_id=strategy.get("id"),
                        error=str(error),
                    )
                    continue

            # Sort by overall score (highest first)
            candidates.sort(key=lambda x: x.overall_score, reverse=True)
            
            return candidates
            
        except Exception as e:
            logger.error(f"Error evaluating strategy candidates: {e}")
            return []
    
    async def _evaluate_strategy_candidate(self, strategy: Dict) -> Optional[StrategyCandidate]:
        """Evaluate a single strategy and return candidate with score"""
        try:
            strategy_id = strategy['id']
            
            # Get recent performance data (last 30 days)
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=30)
            
            # Get trades for performance calculation
            trades = await self.database.get_strategy_trades(
                strategy_id=strategy_id,
                start_date=start_date,
                end_date=end_date
            )
            
            # Require minimum trades for evaluation
            if len(trades) < 5:
                return None
            
            # Calculate performance metrics
            performance_metrics = await self._calculate_candidate_performance(trades)
            
            # Get backtest score
            backtest_score = await self._get_backtest_score(strategy_id)
            
            # Calculate market alignment score
            market_alignment = await self._calculate_market_alignment_score(strategy, trades)
            
            # Calculate risk score
            risk_score = await self._calculate_risk_score(performance_metrics)

            # Calculate sentiment alignment score
            sentiment_alignment, sentiment_context = await self._calculate_sentiment_alignment_score(strategy)
            
            # Calculate overall score
            overall_score = await self._calculate_overall_score(
                performance_metrics,
                backtest_score,
                market_alignment,
                risk_score,
                sentiment_alignment,
            )
            
            trade_times = [self._parse_trade_timestamp(trade) for trade in trades]

            return StrategyCandidate(
                strategy_id=strategy_id,
                name=strategy.get('name', ''),
                performance_score=performance_metrics.get('performance_score', 0),
                sharpe_ratio=performance_metrics.get('sharpe_ratio', 0),
                total_return=performance_metrics.get('total_return', 0),
                max_drawdown=performance_metrics.get('max_drawdown', 0),
                win_rate=performance_metrics.get('win_rate', 0),
                total_trades=len(trades),
                last_trade_date=max(trade_times) if trade_times else datetime.min.replace(tzinfo=timezone.utc),
                backtest_score=backtest_score,
                market_alignment_score=market_alignment,
                risk_score=risk_score,
                sentiment_alignment_score=sentiment_alignment,
                sentiment_context=sentiment_context,
                overall_score=overall_score
            )
            
        except Exception as e:
            logger.error(f"Error evaluating strategy candidate {strategy.get('id')}: {e}")
            return None
    
    async def _calculate_candidate_performance(self, trades: List[Dict]) -> Dict[str, float]:
        """Calculate performance metrics for a candidate strategy"""
        try:
            if not trades:
                return {
                    'performance_score': 0,
                    'sharpe_ratio': 0,
                    'total_return': 0,
                    'max_drawdown': 0,
                    'win_rate': 0
                }
            
            # Calculate daily returns
            daily_returns = []
            daily_pnl = {}
            
            for trade in trades:
                trade_time = self._parse_trade_timestamp(trade)
                trade_date = trade_time.date()
                pnl = trade.get('pnl', 0)
                
                if trade_date not in daily_pnl:
                    daily_pnl[trade_date] = 0
                daily_pnl[trade_date] += pnl
            
            daily_returns = list(daily_pnl.values())
            
            # Calculate metrics
            total_return = sum(daily_returns)
            
            # Sharpe ratio
            import numpy as np
            if len(daily_returns) > 1 and np.std(daily_returns) > 0:
                sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            else:
                sharpe_ratio = 0
            
            # Max drawdown
            if daily_returns:
                cumulative = np.cumprod([1 + r for r in daily_returns])
                peak = np.maximum.accumulate(cumulative)
                drawdown = (cumulative - peak) / peak
                max_drawdown = np.min(drawdown)
            else:
                max_drawdown = 0
            
            # Win rate
            winning_trades = len([t for t in trades if t.get('pnl', 0) > 0])
            win_rate = winning_trades / len(trades) if trades else 0
            
            # Performance score (composite)
            performance_score = (
                sharpe_ratio * 0.4 +           # 40% weight on Sharpe
                (1 + max_drawdown) * 0.3 +     # 30% weight on drawdown (inverted)
                win_rate * 0.2 +               # 20% weight on win rate
                min(total_return * 10, 1) * 0.1  # 10% weight on returns (capped)
            )
            
            return {
                'performance_score': performance_score,
                'sharpe_ratio': sharpe_ratio,
                'total_return': total_return,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate
            }
            
        except Exception as e:
            logger.error(f"Error calculating candidate performance: {e}")
            return {
                'performance_score': 0,
                'sharpe_ratio': 0,
                'total_return': 0,
                'max_drawdown': 0,
                'win_rate': 0
            }
    
    async def _get_backtest_score(self, strategy_id: str) -> float:
        """Get backtest score for strategy"""
        try:
            backtest_results = await self.database.get_strategy_backtest_results(strategy_id)
            
            if backtest_results and 'metrics' in backtest_results:
                metrics = backtest_results['metrics']
                sharpe = metrics.get('sharpe_ratio', 0)
                return_score = metrics.get('total_return', 0)
                
                # Backtest score based on Sharpe and returns
                return (sharpe * 0.7 + min(return_score * 5, 1) * 0.3)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting backtest score: {e}")
            return 0.0
    
    async def _calculate_market_alignment_score(self, strategy: Dict, trades: List[Dict]) -> float:
        """Calculate how well strategy aligns with current market conditions"""
        try:
            # Simple market alignment score based on recent activity and performance
            if not trades:
                return 0.0
            
            # Recent activity score
            trade_times = [self._parse_trade_timestamp(trade) for trade in trades]
            last_trade = max(trade_times)
            days_since_last = (datetime.now(timezone.utc) - last_trade).days
            
            activity_score = max(0, (7 - days_since_last) / 7)  # Higher if more recent trades
            
            # Recent performance trend
            recent_trades = [
                trade
                for trade in trades
                if (datetime.now(timezone.utc) - self._parse_trade_timestamp(trade)).days <= 7
            ]
            if recent_trades:
                recent_pnl = sum(t.get('pnl', 0) for t in recent_trades)
                performance_score = max(0, min(1, recent_pnl * 10 + 0.5))  # Normalized performance
            else:
                performance_score = 0.5  # Neutral if no recent trades
            
            # Combine scores
            alignment_score = (activity_score * 0.6 + performance_score * 0.4)
            
            return alignment_score
            
        except Exception as e:
            logger.error(f"Error calculating market alignment score: {e}")
            return 0.0
    
    async def _calculate_risk_score(self, performance_metrics: Dict) -> float:
        """Calculate risk score (higher is better/lower risk)"""
        try:
            max_drawdown = performance_metrics.get('max_drawdown', 0)
            win_rate = performance_metrics.get('win_rate', 0)
            
            # Risk score (inverted risk - higher is better)
            drawdown_score = max(0, 1 + max_drawdown * 2)  # Better with lower drawdown
            consistency_score = win_rate  # Higher win rate = more consistent
            
            risk_score = (drawdown_score * 0.7 + consistency_score * 0.3)
            
            return min(1.0, max(0.0, risk_score))
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 0.0

    async def _calculate_sentiment_alignment_score(self, strategy: Dict) -> Tuple[float, Dict[str, Any]]:
        """Calculate sentiment alignment score for a strategy based on its symbols."""
        try:
            symbols_data = strategy.get('symbols') or []
            symbols: List[str] = []
            for entry in symbols_data:
                if isinstance(entry, dict):
                    symbol_value = entry.get('symbol')
                else:
                    symbol_value = str(entry)
                if symbol_value:
                    symbol_upper = symbol_value.upper()
                    if symbol_upper not in symbols:
                        symbols.append(symbol_upper)

            if not symbols:
                parameters = strategy.get('parameters') or {}
                param_symbol = parameters.get('symbol') or parameters.get('symbols')
                if isinstance(param_symbol, str):
                    symbols.append(param_symbol.upper())
                elif isinstance(param_symbol, (list, tuple)):
                    symbols.extend(str(sym).upper() for sym in param_symbol if sym)
                    symbols = list(dict.fromkeys(symbols))

            hours_back = 24
            now = datetime.now(timezone.utc)

            symbol_details: List[Dict[str, Any]] = []
            symbol_polarities: List[float] = []
            freshest_symbol_ts: Optional[datetime] = None

            if symbols:
                tasks = [
                    self.database.get_sentiment_entries(symbol=symbol, hours_back=hours_back, limit=50)
                    for symbol in symbols
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for symbol, entries in zip(symbols, results):
                    if isinstance(entries, Exception):
                        logger.warning(
                            "Error retrieving sentiment entries", symbol=symbol, error=str(entries)
                        )
                        continue
                    polarities: List[float] = []
                    latest_ts: Optional[datetime] = None
                    for entry in entries:
                        polarity = self._extract_sentiment_polarity(entry)
                        if polarity is None and entry.get('value') is not None:
                            polarity = self._fear_greed_to_polarity(entry.get('value'))
                        if polarity is not None:
                            polarities.append(polarity)
                        ts = self._parse_iso_timestamp(entry.get('timestamp'))
                        if ts and (latest_ts is None or ts > latest_ts):
                            latest_ts = ts
                    if polarities:
                        avg_polarity = sum(polarities) / len(polarities)
                        recency_decay = 1.0
                        if latest_ts:
                            age_hours = max(0.0, (now - latest_ts).total_seconds() / 3600)
                            if age_hours > 6:
                                recency_decay = max(0.2, 1 - (age_hours - 6) / 24)
                            freshest_symbol_ts = latest_ts if (freshest_symbol_ts is None or latest_ts > freshest_symbol_ts) else freshest_symbol_ts
                        adjusted_polarity = avg_polarity * recency_decay
                        symbol_polarities.append(adjusted_polarity)
                        symbol_details.append({
                            'symbol': symbol,
                            'average_polarity': avg_polarity,
                            'adjusted_polarity': adjusted_polarity,
                            'sample_count': len(polarities),
                            'latest_timestamp': latest_ts.isoformat() if latest_ts else None,
                            'recency_decay': recency_decay,
                        })

            global_entries = await self.database.get_sentiment_entries(
                sentiment_types=[
                    'global_crypto_sentiment',
                    'global_market_sentiment',
                    'market_sentiment',
                ],
                hours_back=hours_back,
                limit=60,
            )

            global_polarities: List[float] = []
            latest_global_ts: Optional[datetime] = None
            for entry in global_entries:
                polarity = self._extract_sentiment_polarity(entry)
                if polarity is None and entry.get('value') is not None:
                    polarity = self._fear_greed_to_polarity(entry.get('value'))
                if polarity is not None:
                    global_polarities.append(polarity)
                ts = self._parse_iso_timestamp(entry.get('timestamp'))
                if ts and (latest_global_ts is None or ts > latest_global_ts):
                    latest_global_ts = ts

            avg_symbol_polarity = sum(symbol_polarities) / len(symbol_polarities) if symbol_polarities else None
            avg_global_polarity = sum(global_polarities) / len(global_polarities) if global_polarities else None

            if avg_symbol_polarity is not None and avg_global_polarity is not None:
                combined_polarity = avg_symbol_polarity * 0.65 + avg_global_polarity * 0.35
            elif avg_symbol_polarity is not None:
                combined_polarity = avg_symbol_polarity
            elif avg_global_polarity is not None:
                combined_polarity = avg_global_polarity
            else:
                combined_polarity = 0.0

            sentiment_score = self._polarity_to_alignment(combined_polarity)

            if freshest_symbol_ts:
                total_age = max(0.0, (now - freshest_symbol_ts).total_seconds() / 3600)
                if total_age > 12:
                    sentiment_score *= max(0.3, 1 - (total_age - 12) / 48)

            context = {
                'symbols_evaluated': symbols,
                'avg_symbol_polarity': avg_symbol_polarity,
                'avg_global_polarity': avg_global_polarity,
                'combined_polarity': combined_polarity,
                'symbol_insights': symbol_details[:5],
                'global_sample_count': len(global_polarities),
                'latest_symbol_timestamp': freshest_symbol_ts.isoformat() if freshest_symbol_ts else None,
                'latest_global_timestamp': latest_global_ts.isoformat() if latest_global_ts else None,
            }

            return max(0.0, min(1.0, sentiment_score)), context

        except Exception as error:
            logger.error(
                "Error calculating sentiment alignment",
                strategy_id=strategy.get('id'),
                error=str(error),
            )
            return 0.5, {'error': str(error)}
    
    async def _calculate_overall_score(self, 
                                     performance_metrics: Dict,
                                     backtest_score: float,
                                     market_alignment: float,
                                     risk_score: float,
                                     sentiment_alignment: float) -> float:
        """Calculate overall strategy score for ranking"""
        try:
            performance_score = performance_metrics.get('performance_score', 0)
            
            # Weighted overall score
            overall_score = (
                performance_score * 0.35 +      # 35% recent performance
                backtest_score * 0.20 +         # 20% backtest quality
                market_alignment * 0.15 +       # 15% market alignment
                risk_score * 0.15 +             # 15% risk management
                sentiment_alignment * 0.15      # 15% sentiment alignment
            )
            
            return max(0.0, min(10.0, overall_score))  # Scale 0-10
            
        except Exception as e:
            logger.error(f"Error calculating overall score: {e}")
            return 0.0
    
    @staticmethod
    def _polarity_to_alignment(polarity: Optional[float]) -> float:
        if polarity is None:
            return 0.5
        return max(0.0, min(1.0, (polarity + 1.0) / 2.0))

    @staticmethod
    def _extract_sentiment_polarity(entry: Dict[str, Any]) -> Optional[float]:
        if not entry:
            return None

        for key in ('aggregated_score', 'polarity', 'sentiment_score', 'score'):
            if entry.get(key) is not None:
                try:
                    value = float(entry[key])
                    if key in {'sentiment_score', 'score'} and abs(value) > 1.0:
                        value = value / 100.0 if abs(value) > 10 else value
                    return max(-1.0, min(1.0, value))
                except (TypeError, ValueError):
                    continue

        aggregated = entry.get('aggregated_sentiment')
        if isinstance(aggregated, dict):
            for key in ('average_polarity', 'polarity', 'aggregated_score'):
                value = aggregated.get(key)
                if value is not None:
                    try:
                        return max(-1.0, min(1.0, float(value)))
                    except (TypeError, ValueError):
                        continue

        metadata = entry.get('metadata')
        if isinstance(metadata, dict):
            for key in ('polarity', 'average_polarity'):
                value = metadata.get(key)
                if value is not None:
                    try:
                        return max(-1.0, min(1.0, float(value)))
                    except (TypeError, ValueError):
                        continue

        return None

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
        return None

    @staticmethod
    def _fear_greed_to_polarity(value: Any) -> Optional[float]:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        polarity = (numeric - 50.0) / 50.0
        return max(-1.0, min(1.0, polarity))

    async def _select_optimal_strategies(self, candidates: List[StrategyCandidate]) -> List[str]:
        """Select the best strategies up to max_active_strategies limit"""
        try:
            if not candidates:
                return []
            
            # Sort by overall score (already sorted, but ensure it)
            candidates.sort(key=lambda x: x.overall_score, reverse=True)
            
            # Select top N strategies
            optimal_strategies = []
            
            for candidate in candidates[:self.max_active_strategies * 2]:  # Consider more than needed
                # Additional filters for activation
                if self._is_candidate_suitable(candidate):
                    optimal_strategies.append(candidate.strategy_id)
                    
                    if len(optimal_strategies) >= self.max_active_strategies:
                        break
            
            return optimal_strategies
            
        except Exception as e:
            logger.error(f"Error selecting optimal strategies: {e}")
            return []
    
    def _is_candidate_suitable(self, candidate: StrategyCandidate) -> bool:
        """Check if candidate meets minimum requirements for activation"""
        try:
            # Minimum requirements
            min_sharpe = 0.5
            max_drawdown_threshold = -0.30  # Max 30% drawdown
            min_trades = 5
            max_days_inactive = 14
            
            # Check requirements
            if candidate.sharpe_ratio < min_sharpe:
                return False
                
            if candidate.max_drawdown < max_drawdown_threshold:
                return False
                
            if candidate.total_trades < min_trades:
                return False
            
            # Check activity
            days_since_last_trade = (datetime.now(timezone.utc) - candidate.last_trade_date).days
            if days_since_last_trade > max_days_inactive:
                return False
            
            # Must have positive overall score
            if candidate.overall_score <= 0:
                return False

            if candidate.sentiment_alignment_score < 0.45:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking candidate suitability: {e}")
            return False
    
    async def _calculate_strategy_changes(self, 
                                        current_active: List[str],
                                        optimal_active: List[str]) -> Dict[str, List[str]]:
        """Calculate which strategies need to be activated/deactivated"""
        
        current_set = set(current_active)
        optimal_set = set(optimal_active)
        
        to_activate = list(optimal_set - current_set)
        to_deactivate = list(current_set - optimal_set)
        
        return {
            'activate': to_activate,
            'deactivate': to_deactivate
        }
    
    async def _apply_strategy_changes(self, changes: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Apply strategy activation/deactivation changes"""
        activated = []
        deactivated = []
        
        try:
            # Deactivate strategies first
            for strategy_id in changes['deactivate']:
                success = await self._deactivate_strategy(strategy_id)
                if success:
                    deactivated.append(strategy_id)
            
            # Then activate new strategies
            for strategy_id in changes['activate']:
                success = await self._activate_strategy(strategy_id)
                if success:
                    activated.append(strategy_id)
            
            # Log changes
            await self._log_activation_changes(activated, deactivated)
            
            return {
                'activated': activated,
                'deactivated': deactivated
            }
            
        except Exception as e:
            logger.error(f"Error applying strategy changes: {e}")
            return {'activated': [], 'deactivated': []}
    
    async def _activate_strategy(self, strategy_id: str) -> bool:
        """Activate a specific strategy"""
        try:
            strategy = await self.database.get_strategy(strategy_id)
            metadata = (strategy or {}).get("metadata", {}) if strategy else {}
            metadata.update(
                {
                    "auto_activated": True,
                    "auto_activation_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            updated = await self.database.update_strategy(
                strategy_id,
                {
                    "status": "active",
                    "is_active": True,
                    "metadata": metadata,
                },
            )
            if updated:
                logger.info(
                    "Activated strategy",
                    strategy_id=strategy_id,
                    name=(strategy or {}).get("name"),
                )
                return True
            logger.warning("Activation update returned no record", strategy_id=strategy_id)
            return False
        except Exception as e:
            logger.error(f"Error activating strategy {strategy_id}: {e}")
            return False
    
    async def _deactivate_strategy(self, strategy_id: str) -> bool:
        """Deactivate a specific strategy"""
        try:
            strategy = await self.database.get_strategy(strategy_id)
            metadata = (strategy or {}).get("metadata", {}) if strategy else {}
            metadata.update(
                {
                    "auto_deactivated": True,
                    "auto_deactivation_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            updated = await self.database.update_strategy(
                strategy_id,
                {
                    "status": "inactive",
                    "is_active": False,
                    "metadata": metadata,
                },
            )
            if updated:
                logger.info(
                    "Deactivated strategy",
                    strategy_id=strategy_id,
                    name=(strategy or {}).get("name"),
                )
                return True
            logger.warning("Deactivation update returned no record", strategy_id=strategy_id)
            return False
        except Exception as e:
            logger.error(f"Error deactivating strategy {strategy_id}: {e}")
            return False
    
    async def _log_activation_changes(self, activated: List[str], deactivated: List[str]):
        """Log activation changes for audit trail"""
        try:
            if not activated and not deactivated:
                return
            await self.database.log_activation_changes(
                activated,
                deactivated,
                self.max_active_strategies,
                reason="automatic_optimization",
            )
        except Exception as e:
            logger.error(f"Error logging activation changes: {e}")
    
    async def update_max_active_strategies(self, new_max: int) -> bool:
        """Update the MAX_ACTIVE_STRATEGIES setting"""
        try:
            if new_max < 1:
                raise ValueError("MAX_ACTIVE_STRATEGIES must be at least 1")
            await self.database.upsert_setting(
                "MAX_ACTIVE_STRATEGIES",
                value=str(new_max),
                description="Maximum number of active trading strategies",
                value_type="integer",
                metadata={"source": "automatic_strategy_activation"},
            )
            # Update local value
            old_max = self.max_active_strategies
            self.max_active_strategies = new_max
            
            logger.info(f"Updated MAX_ACTIVE_STRATEGIES from {old_max} to {new_max}")
            
            # Trigger immediate recheck if value decreased
            if new_max < old_max:
                await self.check_and_update_active_strategies()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating MAX_ACTIVE_STRATEGIES: {e}")
            return False
    
    async def get_activation_status(self) -> Dict:
        """Get current activation status and statistics"""
        try:
            current_active = await self._get_current_active_strategies()
            candidates = await self._evaluate_all_strategy_candidates()
            
            # Get top candidates
            top_candidates = candidates[:10] if candidates else []
            
            status = {
                'max_active_strategies': self.max_active_strategies,
                'current_active_count': len(current_active),
                'current_active_strategies': current_active,
                'last_check': self.last_activation_check.isoformat() if self.last_activation_check else None,
                'next_check_eligible': not self.last_activation_check or 
                                     (datetime.now(timezone.utc) - self.last_activation_check).total_seconds() >= (self.min_stability_hours * 3600),
                'top_candidates': [
                    {
                        'strategy_id': c.strategy_id,
                        'name': c.name,
                        'overall_score': c.overall_score,
                        'sharpe_ratio': c.sharpe_ratio,
                        'total_return': c.total_return,
                        'active': c.strategy_id in current_active
                    }
                    for c in top_candidates
                ],
                'activation_criteria': {
                    'min_sharpe_ratio': 0.5,
                    'max_drawdown_threshold': -0.30,
                    'min_trades': 5,
                    'max_days_inactive': 14,
                    'stability_hours': self.min_stability_hours
                }
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting activation status: {e}")
            return {
                'max_active_strategies': self.max_active_strategies,
                'current_active_count': 0,
                'error': str(e)
            }


# Convenience function for integration
async def create_activation_manager(database: Database) -> AutomaticStrategyActivationManager:
    """Create and initialize an activation manager"""
    manager = AutomaticStrategyActivationManager(database)
    await manager.initialize()
    return manager
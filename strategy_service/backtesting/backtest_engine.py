"""
Core Backtesting Engine

Handles the execution of backtests with realistic market conditions,
slippage, fees, and position management.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import structlog
from decimal import Decimal

logger = structlog.get_logger()


class OrderType(Enum):
    """Order types"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order side"""
    BUY = "buy"
    SELL = "sell"


class PositionSide(Enum):
    """Position side"""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class BacktestConfig:
    """Configuration for backtest execution"""
    
    # Time period
    start_date: datetime
    end_date: datetime
    
    # Capital
    initial_capital: float = 100000.0
    
    # Fees and costs
    maker_fee: float = 0.0002  # 0.02% maker fee
    taker_fee: float = 0.0004  # 0.04% taker fee
    funding_rate: float = 0.0001  # 0.01% every 8 hours
    
    # Slippage model
    fixed_slippage_bps: float = 5.0  # Fixed slippage in basis points
    volume_slippage_factor: float = 0.1  # Additional slippage based on order size
    volatility_slippage_factor: float = 0.5  # Additional slippage based on volatility
    
    # Position limits
    max_position_size: float = 0.95  # Max 95% of capital in single position
    max_leverage: float = 3.0
    allow_short: bool = True
    
    # Execution
    order_fill_assumption: str = "realistic"  # "realistic", "optimistic", "pessimistic"
    limit_order_fill_probability: float = 0.7
    
    # Risk management
    stop_loss_slippage_bps: float = 20.0  # Additional slippage on stop loss
    circuit_breaker_drawdown: float = 0.25  # Stop trading at 25% drawdown
    
    # Data
    data_frequency: str = "1m"  # Data granularity
    
    # Regime awareness
    use_regime_detection: bool = True
    regime_lookback_days: int = 30


@dataclass
class Trade:
    """Individual trade record"""
    timestamp: datetime
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 0.0
    position_value: float = 0.0
    
    # Costs
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    funding_fees: float = 0.0
    
    # Performance
    pnl: float = 0.0
    pnl_percent: float = 0.0
    mae: float = 0.0  # Maximum Adverse Excursion
    mfe: float = 0.0  # Maximum Favorable Excursion
    
    # Duration
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    duration_hours: float = 0.0
    
    # Context
    regime_at_entry: Optional[str] = None
    volatility_at_entry: float = 0.0
    
    # Reason
    exit_reason: str = "unknown"  # "signal", "stop_loss", "take_profit", "timeout"
    
    # Metadata
    strategy_name: str = ""
    strategy_params: Dict = field(default_factory=dict)


@dataclass
class Position:
    """Current open position"""
    symbol: str
    side: PositionSide
    entry_price: float
    quantity: float
    entry_time: datetime
    
    # Running costs
    accumulated_funding: float = 0.0
    
    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Tracking
    highest_price: float = 0.0
    lowest_price: float = 0.0
    
    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L"""
        if self.side == PositionSide.LONG:
            return (current_price - self.entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            return (self.entry_price - current_price) * self.quantity
        return 0.0
    
    def unrealized_pnl_percent(self, current_price: float) -> float:
        """Calculate unrealized P&L as percentage"""
        position_value = self.entry_price * self.quantity
        if position_value == 0:
            return 0.0
        return (self.unrealized_pnl(current_price) / position_value) * 100


@dataclass
class BacktestResult:
    """Complete backtest results"""
    
    # Configuration
    config: BacktestConfig
    strategy_name: str
    strategy_params: Dict
    
    # Time period
    start_date: datetime
    end_date: datetime
    duration_days: float
    
    # Capital
    initial_capital: float
    final_capital: float
    peak_capital: float
    
    # Performance
    total_return: float
    total_return_percent: float
    annualized_return: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: float
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # P&L
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_win_loss_ratio: float
    
    # Execution costs
    total_fees: float
    total_slippage: float
    total_funding: float
    
    # Time analysis
    avg_trade_duration_hours: float
    avg_bars_in_trade: float
    
    # Detailed records
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series())
    drawdown_curve: pd.Series = field(default_factory=lambda: pd.Series())
    
    # Regime analysis
    performance_by_regime: Dict[str, Dict] = field(default_factory=dict)
    
    # Additional metrics
    expectancy: float = 0.0
    kelly_criterion: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


class BacktestEngine:
    """
    Advanced backtesting engine with realistic execution simulation
    """
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.reset()
        
    def reset(self):
        """Reset backtest state"""
        self.capital = self.config.initial_capital
        self.peak_capital = self.capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.current_time: Optional[datetime] = None
        
        # State tracking
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.max_consecutive_wins = 0
        self.max_consecutive_losses = 0
        self.in_drawdown_protection = False
        
    def run(
        self,
        data: pd.DataFrame,
        strategy_signals: pd.DataFrame,
        strategy_name: str = "Unknown",
        strategy_params: Dict = None
    ) -> BacktestResult:
        """
        Run backtest on historical data with strategy signals
        
        Args:
            data: OHLCV data with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            strategy_signals: DataFrame with columns ['timestamp', 'signal', 'stop_loss', 'take_profit']
                             signal: 1 (long), -1 (short), 0 (close/flat)
            strategy_name: Name of the strategy
            strategy_params: Strategy parameters used
            
        Returns:
            BacktestResult with comprehensive metrics
        """
        try:
            logger.info(
                f"Starting backtest: {strategy_name}",
                start=self.config.start_date,
                end=self.config.end_date,
                initial_capital=self.config.initial_capital
            )
            
            self.reset()
            
            if strategy_params is None:
                strategy_params = {}
            
            # Merge data with signals
            df = data.merge(strategy_signals, on='timestamp', how='left')
            df['signal'] = df['signal'].fillna(0)
            
            # Calculate volatility for slippage model
            df['returns'] = df['close'].pct_change()
            df['volatility'] = df['returns'].rolling(window=20).std()
            
            # Detect regimes if enabled
            if self.config.use_regime_detection:
                df = self._detect_regimes(df)
            
            # Process each bar
            for idx, row in df.iterrows():
                self.current_time = row['timestamp']
                
                # Update equity curve
                current_equity = self._calculate_equity(row['close'])
                self.equity_curve.append((self.current_time, current_equity))
                
                # Check circuit breaker
                if self._check_circuit_breaker(current_equity):
                    logger.warning(
                        "Circuit breaker triggered",
                        drawdown=self._calculate_current_drawdown(current_equity)
                    )
                    break
                
                # Update position tracking
                if self.position:
                    self._update_position_tracking(row)
                    
                    # Check stop loss and take profit
                    if self._check_exit_conditions(row):
                        self._close_position(
                            row,
                            exit_reason="stop_loss_or_take_profit"
                        )
                        continue
                    
                    # Apply funding fees (every 8 hours)
                    if self._should_apply_funding(row):
                        self._apply_funding_fee(row)
                
                # Process signal
                signal = row['signal']
                
                if signal != 0 and not self.in_drawdown_protection:
                    # Close existing position if signal changed
                    if self.position:
                        if (signal > 0 and self.position.side == PositionSide.SHORT) or \
                           (signal < 0 and self.position.side == PositionSide.LONG):
                            self._close_position(row, exit_reason="signal_change")
                    
                    # Open new position
                    if not self.position:
                        self._open_position(
                            row,
                            signal,
                            strategy_name,
                            strategy_params
                        )
                
                elif signal == 0 and self.position:
                    # Close position on flat signal
                    self._close_position(row, exit_reason="signal")
            
            # Close any remaining position
            if self.position:
                last_row = df.iloc[-1]
                self._close_position(last_row, exit_reason="backtest_end")
            
            # Calculate results
            result = self._calculate_results(
                strategy_name,
                strategy_params,
                df
            )
            
            logger.info(
                f"Backtest completed: {strategy_name}",
                total_return_pct=f"{result.total_return_percent:.2f}%",
                sharpe=f"{result.sharpe_ratio:.2f}",
                max_dd=f"{result.max_drawdown:.2f}%",
                total_trades=result.total_trades,
                win_rate=f"{result.win_rate:.2f}%"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error running backtest: {e}", exc_info=True)
            raise
    
    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current equity"""
        equity = self.capital
        if self.position:
            equity += self.position.unrealized_pnl(current_price)
            equity -= self.position.accumulated_funding
        return equity
    
    def _check_circuit_breaker(self, current_equity: float) -> bool:
        """Check if circuit breaker should trigger"""
        drawdown = self._calculate_current_drawdown(current_equity)
        if drawdown >= self.config.circuit_breaker_drawdown:
            self.in_drawdown_protection = True
            return True
        return False
    
    def _calculate_current_drawdown(self, current_equity: float) -> float:
        """Calculate current drawdown percentage"""
        if self.peak_capital == 0:
            return 0.0
        return max(0, (self.peak_capital - current_equity) / self.peak_capital)
    
    def _update_position_tracking(self, row: pd.Series):
        """Update position price tracking"""
        if not self.position:
            return
        
        self.position.highest_price = max(self.position.highest_price, row['high'])
        self.position.lowest_price = min(self.position.lowest_price, row['low'])
    
    def _check_exit_conditions(self, row: pd.Series) -> bool:
        """Check if stop loss or take profit hit"""
        if not self.position:
            return False
        
        # Check stop loss
        if self.position.stop_loss:
            if self.position.side == PositionSide.LONG:
                if row['low'] <= self.position.stop_loss:
                    return True
            elif self.position.side == PositionSide.SHORT:
                if row['high'] >= self.position.stop_loss:
                    return True
        
        # Check take profit
        if self.position.take_profit:
            if self.position.side == PositionSide.LONG:
                if row['high'] >= self.position.take_profit:
                    return True
            elif self.position.side == PositionSide.SHORT:
                if row['low'] <= self.position.take_profit:
                    return True
        
        return False
    
    def _should_apply_funding(self, row: pd.Series) -> bool:
        """Check if funding fee should be applied"""
        if not self.position:
            return False
        
        # Apply every 8 hours
        hours_since_entry = (row['timestamp'] - self.position.entry_time).total_seconds() / 3600
        return hours_since_entry % 8 < (1/60)  # Within 1 minute of 8 hour mark
    
    def _apply_funding_fee(self, row: pd.Series):
        """Apply funding fee to position"""
        if not self.position:
            return
        
        position_value = self.position.entry_price * self.position.quantity
        funding = position_value * self.config.funding_rate
        self.position.accumulated_funding += funding
    
    def _calculate_slippage(
        self,
        price: float,
        quantity: float,
        volatility: float,
        is_stop_loss: bool = False
    ) -> float:
        """
        Calculate realistic slippage
        
        Slippage model:
        - Base fixed slippage
        - Volume-based component (larger orders get worse fills)
        - Volatility-based component (higher vol = more slippage)
        - Stop loss orders get additional slippage
        """
        # Fixed component
        fixed_slippage = price * (self.config.fixed_slippage_bps / 10000)
        
        # Volume component (assuming order is % of typical volume)
        position_value = price * quantity
        volume_slippage = position_value * self.config.volume_slippage_factor / 10000
        
        # Volatility component
        volatility_slippage = price * volatility * self.config.volatility_slippage_factor
        
        # Stop loss additional slippage
        stop_slippage = 0.0
        if is_stop_loss:
            stop_slippage = price * (self.config.stop_loss_slippage_bps / 10000)
        
        total_slippage = fixed_slippage + volume_slippage + volatility_slippage + stop_slippage
        
        return total_slippage
    
    def _calculate_fee(self, value: float, is_maker: bool = False) -> float:
        """Calculate trading fee"""
        fee_rate = self.config.maker_fee if is_maker else self.config.taker_fee
        return value * fee_rate
    
    def _open_position(
        self,
        row: pd.Series,
        signal: float,
        strategy_name: str,
        strategy_params: Dict
    ):
        """Open a new position"""
        try:
            # Determine position side
            side = PositionSide.LONG if signal > 0 else PositionSide.SHORT
            
            if side == PositionSide.SHORT and not self.config.allow_short:
                return
            
            # Calculate position size
            available_capital = self.capital * self.config.max_position_size
            price = row['close']
            volatility = row.get('volatility', 0.01)
            
            # Account for slippage
            slippage = self._calculate_slippage(price, available_capital / price, volatility)
            effective_price = price + (slippage if side == PositionSide.LONG else -slippage)
            
            # Calculate quantity
            quantity = available_capital / effective_price
            position_value = effective_price * quantity
            
            # Calculate fee
            fee = self._calculate_fee(position_value, is_maker=False)
            
            # Deduct costs from capital
            total_cost = fee + abs(slippage * quantity)
            if self.capital < total_cost:
                logger.warning("Insufficient capital for position")
                return
            
            self.capital -= total_cost
            
            # Create position
            self.position = Position(
                symbol=row.get('symbol', 'UNKNOWN'),
                side=side,
                entry_price=effective_price,
                quantity=quantity,
                entry_time=row['timestamp'],
                stop_loss=row.get('stop_loss'),
                take_profit=row.get('take_profit'),
                highest_price=row['high'],
                lowest_price=row['low']
            )
            
            # Create trade record
            trade = Trade(
                timestamp=row['timestamp'],
                symbol=self.position.symbol,
                side=OrderSide.BUY if side == PositionSide.LONG else OrderSide.SELL,
                entry_price=effective_price,
                quantity=quantity,
                position_value=position_value,
                entry_fee=fee,
                entry_slippage=slippage * quantity,
                entry_time=row['timestamp'],
                regime_at_entry=row.get('regime', 'unknown'),
                volatility_at_entry=volatility,
                strategy_name=strategy_name,
                strategy_params=strategy_params
            )
            
            self.trades.append(trade)
            
            logger.debug(
                f"Opened {side.value} position",
                price=effective_price,
                quantity=quantity,
                value=position_value
            )
            
        except Exception as e:
            logger.error(f"Error opening position: {e}", exc_info=True)
    
    def _close_position(self, row: pd.Series, exit_reason: str = "signal"):
        """Close current position"""
        if not self.position:
            return
        
        try:
            # Determine exit price
            price = row['close']
            volatility = row.get('volatility', 0.01)
            is_stop_loss = "stop" in exit_reason.lower()
            
            # Account for slippage
            slippage = self._calculate_slippage(
                price,
                self.position.quantity,
                volatility,
                is_stop_loss
            )
            
            effective_price = price - (slippage if self.position.side == PositionSide.LONG else -slippage)
            
            # Calculate P&L
            if self.position.side == PositionSide.LONG:
                pnl = (effective_price - self.position.entry_price) * self.position.quantity
            else:
                pnl = (self.position.entry_price - effective_price) * self.position.quantity
            
            # Subtract accumulated funding
            pnl -= self.position.accumulated_funding
            
            # Calculate fee
            position_value = effective_price * self.position.quantity
            fee = self._calculate_fee(position_value, is_maker=False)
            
            # Net P&L
            net_pnl = pnl - fee - abs(slippage * self.position.quantity)
            
            # Update capital
            self.capital += position_value + net_pnl
            
            # Update peak capital
            if self.capital > self.peak_capital:
                self.peak_capital = self.capital
            
            # Calculate MAE and MFE
            if self.position.side == PositionSide.LONG:
                mae = (self.position.lowest_price - self.position.entry_price) * self.position.quantity
                mfe = (self.position.highest_price - self.position.entry_price) * self.position.quantity
            else:
                mae = (self.position.entry_price - self.position.highest_price) * self.position.quantity
                mfe = (self.position.entry_price - self.position.lowest_price) * self.position.quantity
            
            # Update trade record
            trade = self.trades[-1]  # Last opened trade
            trade.exit_price = effective_price
            trade.exit_fee = fee
            trade.exit_slippage = slippage * self.position.quantity
            trade.funding_fees = self.position.accumulated_funding
            trade.pnl = net_pnl
            trade.pnl_percent = (net_pnl / trade.position_value) * 100
            trade.mae = mae
            trade.mfe = mfe
            trade.exit_time = row['timestamp']
            trade.duration_hours = (row['timestamp'] - self.position.entry_time).total_seconds() / 3600
            trade.exit_reason = exit_reason
            
            # Update consecutive win/loss tracking
            if net_pnl > 0:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
                self.max_consecutive_wins = max(self.max_consecutive_wins, self.consecutive_wins)
            else:
                self.consecutive_losses += 1
                self.consecutive_wins = 0
                self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
            
            logger.debug(
                f"Closed {self.position.side.value} position",
                pnl=net_pnl,
                pnl_pct=trade.pnl_percent,
                reason=exit_reason
            )
            
            # Clear position
            self.position = None
            
        except Exception as e:
            logger.error(f"Error closing position: {e}", exc_info=True)
    
    def _detect_regimes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect market regimes for the data"""
        # Simple regime detection based on volatility and trend
        # Can be enhanced with ML models
        
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        df['trend'] = df['close'].rolling(window=50).apply(
            lambda x: 1 if x[-1] > x[0] else -1
        )
        
        # Classify regimes
        vol_median = df['volatility'].median()
        
        def classify_regime(row):
            if pd.isna(row['volatility']) or pd.isna(row['trend']):
                return 'unknown'
            
            if row['volatility'] > vol_median * 1.5:
                return 'high_volatility'
            elif row['volatility'] < vol_median * 0.5:
                return 'low_volatility'
            elif row['trend'] > 0:
                return 'bull_trending'
            elif row['trend'] < 0:
                return 'bear_trending'
            else:
                return 'sideways'
        
        df['regime'] = df.apply(classify_regime, axis=1)
        
        return df
    
    def _calculate_results(
        self,
        strategy_name: str,
        strategy_params: Dict,
        df: pd.DataFrame
    ) -> BacktestResult:
        """Calculate comprehensive backtest results"""
        
        # Convert equity curve to Series
        equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
        equity_series = equity_df.set_index('timestamp')['equity']
        
        # Calculate drawdown curve
        running_max = equity_series.expanding().max()
        drawdown_series = (equity_series - running_max) / running_max
        
        # Winning and losing trades
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl < 0]
        
        # Calculate metrics
        total_return = self.capital - self.config.initial_capital
        total_return_pct = (total_return / self.config.initial_capital) * 100
        
        duration_days = (self.config.end_date - self.config.start_date).days
        annualized_return = (total_return_pct / duration_days) * 365 if duration_days > 0 else 0
        
        # Risk metrics
        returns = equity_series.pct_change().dropna()
        sharpe = self._calculate_sharpe(returns)
        sortino = self._calculate_sortino(returns)
        max_dd = abs(drawdown_series.min()) * 100
        calmar = annualized_return / max_dd if max_dd != 0 else 0
        
        # Max drawdown duration
        max_dd_duration = self._calculate_max_drawdown_duration(drawdown_series)
        
        # Trade statistics
        total_trades = len(self.trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0
        
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0
        avg_loss = gross_loss / len(losing_trades) if losing_trades else 0
        avg_win_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0
        
        # Costs
        total_fees = sum(t.entry_fee + t.exit_fee for t in self.trades)
        total_slippage = sum(t.entry_slippage + t.exit_slippage for t in self.trades)
        total_funding = sum(t.funding_fees for t in self.trades)
        
        # Time analysis
        avg_duration = np.mean([t.duration_hours for t in self.trades]) if self.trades else 0
        
        # Expectancy
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)
        
        # Kelly Criterion
        kelly = (win_rate / 100 - (1 - win_rate / 100) / avg_win_loss_ratio) if avg_win_loss_ratio > 0 else 0
        
        # Regime analysis
        performance_by_regime = self._analyze_by_regime()
        
        return BacktestResult(
            config=self.config,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            duration_days=duration_days,
            initial_capital=self.config.initial_capital,
            final_capital=self.capital,
            peak_capital=self.peak_capital,
            total_return=total_return,
            total_return_percent=total_return_pct,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            max_drawdown_duration_days=max_dd_duration,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_loss_ratio=avg_win_loss_ratio,
            total_fees=total_fees,
            total_slippage=total_slippage,
            total_funding=total_funding,
            avg_trade_duration_hours=avg_duration,
            avg_bars_in_trade=0,  # Would need to calculate based on data frequency
            trades=self.trades,
            equity_curve=equity_series,
            drawdown_curve=drawdown_series,
            performance_by_regime=performance_by_regime,
            expectancy=expectancy,
            kelly_criterion=kelly,
            consecutive_wins=self.consecutive_wins,
            consecutive_losses=self.consecutive_losses,
            max_consecutive_wins=self.max_consecutive_wins,
            max_consecutive_losses=self.max_consecutive_losses
        )
    
    def _calculate_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        
        excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
        return np.sqrt(252) * excess_returns.mean() / returns.std()
    
    def _calculate_sortino(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio"""
        if len(returns) == 0:
            return 0.0
        
        excess_returns = returns - risk_free_rate / 252
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0
        
        return np.sqrt(252) * excess_returns.mean() / downside_returns.std()
    
    def _calculate_max_drawdown_duration(self, drawdown_series: pd.Series) -> float:
        """Calculate maximum drawdown duration in days"""
        is_drawdown = drawdown_series < 0
        drawdown_periods = is_drawdown.ne(is_drawdown.shift()).cumsum()
        
        max_duration = 0
        for period in drawdown_periods[is_drawdown].unique():
            period_data = drawdown_series[drawdown_periods == period]
            duration = (period_data.index[-1] - period_data.index[0]).days
            max_duration = max(max_duration, duration)
        
        return max_duration
    
    def _analyze_by_regime(self) -> Dict[str, Dict]:
        """Analyze performance by market regime"""
        regime_performance = {}
        
        # Group trades by regime
        for trade in self.trades:
            regime = trade.regime_at_entry
            if regime not in regime_performance:
                regime_performance[regime] = {
                    'trades': [],
                    'total_pnl': 0.0,
                    'winning_trades': 0,
                    'losing_trades': 0
                }
            
            regime_performance[regime]['trades'].append(trade)
            regime_performance[regime]['total_pnl'] += trade.pnl
            
            if trade.pnl > 0:
                regime_performance[regime]['winning_trades'] += 1
            else:
                regime_performance[regime]['losing_trades'] += 1
        
        # Calculate metrics per regime
        for regime, data in regime_performance.items():
            total = data['winning_trades'] + data['losing_trades']
            data['win_rate'] = (data['winning_trades'] / total * 100) if total > 0 else 0
            data['avg_pnl'] = data['total_pnl'] / total if total > 0 else 0
            data['total_trades'] = total
        
        return regime_performance

"""
Factor Models for Performance Attribution

Implements various factor models for crypto markets:
- Fama-French style crypto factors
- Momentum and reversal
- Volatility and carry
- Custom multi-factor models
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class FactorType(Enum):
    """Types of factors"""
    MARKET = "market"  # Market beta
    SIZE = "size"  # Market cap factor
    MOMENTUM = "momentum"  # Price momentum
    REVERSAL = "reversal"  # Mean reversion
    VOLATILITY = "volatility"  # Vol factor
    CARRY = "carry"  # Funding rate carry
    VALUE = "value"  # Less relevant for crypto
    QUALITY = "quality"  # Network activity, development
    LIQUIDITY = "liquidity"  # Trading volume


@dataclass
class FactorReturn:
    """Factor return for a period"""
    factor_name: str
    factor_type: FactorType
    date: pd.Timestamp
    return_value: float
    is_long: bool  # True if long factor, False if short


class FactorModel(ABC):
    """Base class for factor models"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Calculate factor returns for the period
        
        Args:
            data: Market data with OHLCV
            start_date: Start date
            end_date: End date
        
        Returns:
            Series of daily factor returns
        """
        pass
    
    def _calculate_returns(self, prices: pd.Series) -> pd.Series:
        """Calculate log returns"""
        return np.log(prices / prices.shift(1))


class MarketFactor(FactorModel):
    """Market factor (beta) - overall market movement"""
    
    def __init__(self):
        super().__init__("Market")
        self.factor_type = FactorType.MARKET
    
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Market factor = Equal-weighted or cap-weighted market return
        """
        # Use close prices
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        # Filter date range
        mask = (data.index >= start_date) & (data.index <= end_date)
        prices = data.loc[mask, 'close']
        
        # Calculate returns
        returns = self._calculate_returns(prices)
        
        self.logger.info(f"Market factor: mean={returns.mean():.4f}, std={returns.std():.4f}")
        
        return returns.fillna(0)


class MomentumFactor(FactorModel):
    """Momentum factor - long winners, short losers"""
    
    def __init__(self, lookback_days: int = 20):
        super().__init__("Momentum")
        self.factor_type = FactorType.MOMENTUM
        self.lookback_days = lookback_days
    
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Momentum = Return over lookback period
        Long if positive momentum, short if negative
        """
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        # Filter date range (need extra for lookback)
        extended_start = start_date - pd.Timedelta(days=self.lookback_days + 5)
        mask = (data.index >= extended_start) & (data.index <= end_date)
        prices = data.loc[mask, 'close']
        
        # Calculate momentum (past N-day return)
        momentum = prices / prices.shift(self.lookback_days) - 1
        
        # Signal: long if positive, short if negative
        signal = np.sign(momentum)
        
        # Daily returns
        daily_returns = self._calculate_returns(prices)
        
        # Factor return = signal * return
        factor_returns = signal.shift(1) * daily_returns  # Use yesterday's signal
        
        # Filter back to requested range
        mask = (factor_returns.index >= start_date) & (factor_returns.index <= end_date)
        factor_returns = factor_returns.loc[mask]
        
        self.logger.info(
            f"Momentum factor ({self.lookback_days}d): "
            f"mean={factor_returns.mean():.4f}, std={factor_returns.std():.4f}"
        )
        
        return factor_returns.fillna(0)


class ReversalFactor(FactorModel):
    """Reversal factor - mean reversion, opposite of momentum"""
    
    def __init__(self, lookback_days: int = 5):
        super().__init__("Reversal")
        self.factor_type = FactorType.REVERSAL
        self.lookback_days = lookback_days
    
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Reversal = Negative of short-term momentum
        Long if negative recent return (expect reversion up)
        Short if positive recent return (expect reversion down)
        """
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        # Filter date range (need extra for lookback)
        extended_start = start_date - pd.Timedelta(days=self.lookback_days + 5)
        mask = (data.index >= extended_start) & (data.index <= end_date)
        prices = data.loc[mask, 'close']
        
        # Calculate short-term return
        short_term_return = prices / prices.shift(self.lookback_days) - 1
        
        # Signal: long if negative return, short if positive (reversal)
        signal = -np.sign(short_term_return)
        
        # Daily returns
        daily_returns = self._calculate_returns(prices)
        
        # Factor return = signal * return
        factor_returns = signal.shift(1) * daily_returns
        
        # Filter back to requested range
        mask = (factor_returns.index >= start_date) & (factor_returns.index <= end_date)
        factor_returns = factor_returns.loc[mask]
        
        self.logger.info(
            f"Reversal factor ({self.lookback_days}d): "
            f"mean={factor_returns.mean():.4f}, std={factor_returns.std():.4f}"
        )
        
        return factor_returns.fillna(0)


class VolatilityFactor(FactorModel):
    """Volatility factor - exposure to market volatility"""
    
    def __init__(self, window_days: int = 20):
        super().__init__("Volatility")
        self.factor_type = FactorType.VOLATILITY
        self.window_days = window_days
    
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Volatility factor = Long low vol, short high vol
        (Low vol tends to outperform)
        """
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        # Filter date range (need extra for window)
        extended_start = start_date - pd.Timedelta(days=self.window_days + 10)
        mask = (data.index >= extended_start) & (data.index <= end_date)
        prices = data.loc[mask, 'close']
        
        # Calculate realized volatility
        returns = self._calculate_returns(prices)
        realized_vol = returns.rolling(window=self.window_days).std() * np.sqrt(252)
        
        # Normalize volatility (z-score over longer period)
        vol_zscore = (realized_vol - realized_vol.rolling(window=60).mean()) / realized_vol.rolling(window=60).std()
        
        # Signal: long if low vol (negative z-score), short if high vol
        signal = -np.sign(vol_zscore)
        
        # Daily returns
        daily_returns = returns
        
        # Factor return = signal * return
        factor_returns = signal.shift(1) * daily_returns
        
        # Filter back to requested range
        mask = (factor_returns.index >= start_date) & (factor_returns.index <= end_date)
        factor_returns = factor_returns.loc[mask]
        
        self.logger.info(
            f"Volatility factor ({self.window_days}d): "
            f"mean={factor_returns.mean():.4f}, std={factor_returns.std():.4f}"
        )
        
        return factor_returns.fillna(0)


class CarryFactor(FactorModel):
    """Carry factor - based on funding rates (perpetual futures)"""
    
    def __init__(self):
        super().__init__("Carry")
        self.factor_type = FactorType.CARRY
    
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Carry = Long if funding rate is negative (get paid to hold)
                Short if funding rate is positive (pay to hold)
        """
        # Funding rate data required
        if 'funding_rate' not in data.columns:
            self.logger.warning("No funding_rate column, returning zero factor")
            dates = pd.date_range(start_date, end_date, freq='D')
            return pd.Series(0, index=dates)
        
        # Filter date range
        mask = (data.index >= start_date) & (data.index <= end_date)
        funding_rates = data.loc[mask, 'funding_rate']
        
        # Signal: long if negative funding (get paid), short if positive
        signal = -np.sign(funding_rates)
        
        # Get returns
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        prices = data.loc[mask, 'close']
        daily_returns = self._calculate_returns(prices)
        
        # Factor return = signal * return + funding_rate
        # (You earn/pay funding rate regardless of price movement)
        factor_returns = signal * daily_returns + signal * funding_rates
        
        self.logger.info(
            f"Carry factor: mean={factor_returns.mean():.4f}, std={factor_returns.std():.4f}"
        )
        
        return factor_returns.fillna(0)


class SizeFactor(FactorModel):
    """Size factor - small cap vs large cap"""
    
    def __init__(self):
        super().__init__("Size")
        self.factor_type = FactorType.SIZE
    
    async def calculate_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> pd.Series:
        """
        Size = Small cap minus large cap
        Requires market cap data
        """
        # Market cap data required
        if 'market_cap' not in data.columns:
            self.logger.warning("No market_cap column, returning zero factor")
            dates = pd.date_range(start_date, end_date, freq='D')
            return pd.Series(0, index=dates)
        
        # Filter date range
        mask = (data.index >= start_date) & (data.index <= end_date)
        market_caps = data.loc[mask, 'market_cap']
        
        # Classify as small/large cap based on median
        median_cap = market_caps.rolling(window=30).median()
        is_small_cap = market_caps < median_cap
        
        # Signal: long small cap, short large cap
        signal = is_small_cap.astype(float) * 2 - 1  # -1 or +1
        
        # Get returns
        if 'close' not in data.columns:
            raise ValueError("Data must contain 'close' column")
        
        prices = data.loc[mask, 'close']
        daily_returns = self._calculate_returns(prices)
        
        # Factor return
        factor_returns = signal.shift(1) * daily_returns
        
        self.logger.info(
            f"Size factor: mean={factor_returns.mean():.4f}, std={factor_returns.std():.4f}"
        )
        
        return factor_returns.fillna(0)


class MultiFactorModel:
    """
    Multi-factor model combining several factors
    
    Used for comprehensive attribution analysis
    """
    
    def __init__(
        self,
        use_market: bool = True,
        use_momentum: bool = True,
        use_reversal: bool = True,
        use_volatility: bool = True,
        use_carry: bool = True,
        use_size: bool = False
    ):
        self.factors: List[FactorModel] = []
        
        if use_market:
            self.factors.append(MarketFactor())
        if use_momentum:
            self.factors.append(MomentumFactor(lookback_days=20))
        if use_reversal:
            self.factors.append(ReversalFactor(lookback_days=5))
        if use_volatility:
            self.factors.append(VolatilityFactor(window_days=20))
        if use_carry:
            self.factors.append(CarryFactor())
        if use_size:
            self.factors.append(SizeFactor())
        
        self.logger = logging.getLogger(__name__)
    
    async def calculate_all_factor_returns(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> Dict[str, pd.Series]:
        """
        Calculate returns for all factors
        
        Returns:
            Dictionary of factor name -> factor returns
        """
        factor_returns = {}
        
        for factor in self.factors:
            try:
                returns = await factor.calculate_factor_returns(data, start_date, end_date)
                factor_returns[factor.name] = returns
            except Exception as e:
                self.logger.error(f"Error calculating {factor.name} factor: {e}")
                # Return zero factor
                dates = pd.date_range(start_date, end_date, freq='D')
                factor_returns[factor.name] = pd.Series(0, index=dates)
        
        return factor_returns


class FamaFrenchCrypto:
    """
    Crypto adaptation of Fama-French 3-factor model
    
    Factors:
    1. Market (Mkt-RF): Market return minus risk-free rate
    2. Size (SMB): Small minus big (by market cap)
    3. Momentum (MOM): Winners minus losers
    """
    
    def __init__(self, risk_free_rate: float = 0.04):
        self.risk_free_rate = risk_free_rate
        self.daily_rf = risk_free_rate / 252
        self.logger = logging.getLogger(__name__)
    
    async def calculate_factors(
        self,
        market_data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> Dict[str, pd.Series]:
        """
        Calculate Fama-French style factors for crypto
        
        Args:
            market_data: Market data with close, market_cap
            start_date: Start date
            end_date: End date
        
        Returns:
            Dictionary with Mkt-RF, SMB, MOM factors
        """
        factors = {}
        
        # Market factor
        market_factor = MarketFactor()
        market_returns = await market_factor.calculate_factor_returns(
            market_data, start_date, end_date
        )
        factors['Mkt-RF'] = market_returns - self.daily_rf
        
        # Size factor (if available)
        size_factor = SizeFactor()
        smb = await size_factor.calculate_factor_returns(
            market_data, start_date, end_date
        )
        factors['SMB'] = smb
        
        # Momentum factor
        momentum_factor = MomentumFactor(lookback_days=30)
        mom = await momentum_factor.calculate_factor_returns(
            market_data, start_date, end_date
        )
        factors['MOM'] = mom
        
        return factors


class MomentumReversal:
    """
    Dual momentum-reversal model
    
    Captures both momentum (intermediate term) and reversal (short term)
    """
    
    def __init__(
        self,
        momentum_days: int = 20,
        reversal_days: int = 3
    ):
        self.momentum_days = momentum_days
        self.reversal_days = reversal_days
    
    async def calculate_factors(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> Dict[str, pd.Series]:
        """Calculate momentum and reversal factors"""
        
        factors = {}
        
        # Momentum
        momentum_factor = MomentumFactor(lookback_days=self.momentum_days)
        factors['Momentum'] = await momentum_factor.calculate_factor_returns(
            data, start_date, end_date
        )
        
        # Reversal
        reversal_factor = ReversalFactor(lookback_days=self.reversal_days)
        factors['Reversal'] = await reversal_factor.calculate_factor_returns(
            data, start_date, end_date
        )
        
        return factors


class VolatilityCarry:
    """
    Volatility and carry model
    
    Captures:
    - Low volatility premium
    - Funding rate carry
    """
    
    def __init__(self, volatility_window: int = 20):
        self.volatility_window = volatility_window
    
    async def calculate_factors(
        self,
        data: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp
    ) -> Dict[str, pd.Series]:
        """Calculate volatility and carry factors"""
        
        factors = {}
        
        # Volatility
        vol_factor = VolatilityFactor(window_days=self.volatility_window)
        factors['Volatility'] = await vol_factor.calculate_factor_returns(
            data, start_date, end_date
        )
        
        # Carry
        carry_factor = CarryFactor()
        factors['Carry'] = await carry_factor.calculate_factor_returns(
            data, start_date, end_date
        )
        
        return factors

"""
Market Impact Models

Implements various market impact models to estimate the cost of trading:
- Linear Impact Model
- Square-Root Impact Model  
- Power Law Impact Model
- Temporary vs Permanent Impact
- Liquidity-based Impact Models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ImpactType(Enum):
    """Market impact types"""
    TEMPORARY = "temporary"     # Reverts after trade
    PERMANENT = "permanent"     # Persists after trade
    TOTAL = "total"            # Sum of temporary and permanent


@dataclass
class CostComponent:
    """Individual cost component"""
    component_type: str         # e.g., "market_impact", "spread", "commission"
    amount: float              # Cost in currency units
    basis_points: float        # Cost in basis points
    percentage: float          # Percentage of trade value
    description: str           # Human-readable description


@dataclass
class TransactionCost:
    """Complete transaction cost breakdown"""
    # Trade details
    symbol: str
    trade_size: float          # Shares or notional
    trade_value: float         # Dollar value
    side: str                  # "buy" or "sell"
    
    # Cost components
    market_impact: CostComponent
    bid_ask_spread: CostComponent
    commission: CostComponent
    market_data_cost: Optional[CostComponent] = None
    clearing_cost: Optional[CostComponent] = None
    
    # Total cost
    total_cost: float          # Total cost in currency
    total_bps: float           # Total cost in basis points
    
    # Market conditions
    volatility: Optional[float] = None
    liquidity_score: Optional[float] = None
    market_regime: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "trade_size": self.trade_size,
            "trade_value": self.trade_value,
            "side": self.side,
            "market_impact": self.market_impact.__dict__,
            "bid_ask_spread": self.bid_ask_spread.__dict__,
            "commission": self.commission.__dict__,
            "market_data_cost": self.market_data_cost.__dict__ if self.market_data_cost else None,
            "clearing_cost": self.clearing_cost.__dict__ if self.clearing_cost else None,
            "total_cost": self.total_cost,
            "total_bps": self.total_bps,
            "volatility": self.volatility,
            "liquidity_score": self.liquidity_score,
            "market_regime": self.market_regime,
        }


class MarketImpactModel(ABC):
    """
    Abstract base class for market impact models.
    
    Market impact models estimate the price movement caused by executing trades.
    Different models capture different aspects of market microstructure.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.calibration_data: Optional[pd.DataFrame] = None
        self.model_parameters: Dict = {}
    
    @abstractmethod
    def estimate_impact(
        self,
        trade_size: float,
        average_daily_volume: float,
        volatility: float,
        spread: float,
        **kwargs
    ) -> Tuple[float, float]:
        """
        Estimate market impact.
        
        Args:
            trade_size: Size of trade (shares or notional)
            average_daily_volume: Average daily trading volume
            volatility: Asset volatility
            spread: Bid-ask spread
            
        Returns:
            Tuple of (temporary_impact, permanent_impact) in basis points
        """
        pass
    
    @abstractmethod
    def calibrate(self, trade_data: pd.DataFrame) -> Dict:
        """
        Calibrate model parameters from historical trade data.
        
        Args:
            trade_data: Historical trade data with columns:
                - trade_size: Trade size
                - impact: Observed market impact
                - adv: Average daily volume
                - volatility: Volatility
                - spread: Bid-ask spread
                
        Returns:
            Dictionary of calibrated parameters
        """
        pass
    
    def calculate_total_cost(
        self,
        symbol: str,
        trade_size: float,
        price: float,
        side: str,
        market_data: Dict,
        commission_rate: float = 0.001
    ) -> TransactionCost:
        """
        Calculate complete transaction cost breakdown.
        
        Args:
            symbol: Asset symbol
            trade_size: Number of shares
            price: Trade price
            side: "buy" or "sell"
            market_data: Market data dict (adv, volatility, spread, etc.)
            commission_rate: Commission rate (default 0.1%)
            
        Returns:
            Complete transaction cost breakdown
        """
        trade_value = trade_size * price
        
        # Extract market data
        adv = market_data.get("average_daily_volume", 1000000)
        volatility = market_data.get("volatility", 0.2)
        spread = market_data.get("bid_ask_spread", 0.001)
        
        # Estimate market impact
        temp_impact_bps, perm_impact_bps = self.estimate_impact(
            trade_size=trade_size,
            average_daily_volume=adv,
            volatility=volatility,
            spread=spread,
            **market_data
        )
        
        # Total market impact
        total_impact_bps = temp_impact_bps + perm_impact_bps
        impact_cost = (total_impact_bps / 10000) * trade_value
        
        # Bid-ask spread cost (half-spread for market orders)
        spread_bps = spread * 5000  # Convert to bps (assuming spread as fraction)
        spread_cost = (spread_bps / 10000) * trade_value
        
        # Commission cost
        commission_bps = commission_rate * 10000
        commission_cost = commission_rate * trade_value
        
        # Create cost components
        market_impact = CostComponent(
            component_type="market_impact",
            amount=impact_cost,
            basis_points=total_impact_bps,
            percentage=total_impact_bps / 100,
            description=f"Market impact: {temp_impact_bps:.1f} bps temporary + {perm_impact_bps:.1f} bps permanent"
        )
        
        bid_ask_spread = CostComponent(
            component_type="bid_ask_spread",
            amount=spread_cost,
            basis_points=spread_bps,
            percentage=spread_bps / 100,
            description=f"Half-spread cost: {spread_bps:.1f} bps"
        )
        
        commission = CostComponent(
            component_type="commission",
            amount=commission_cost,
            basis_points=commission_bps,
            percentage=commission_bps / 100,
            description=f"Commission: {commission_bps:.1f} bps"
        )
        
        # Total cost
        total_cost = impact_cost + spread_cost + commission_cost
        total_bps = total_impact_bps + spread_bps + commission_bps
        
        return TransactionCost(
            symbol=symbol,
            trade_size=trade_size,
            trade_value=trade_value,
            side=side,
            market_impact=market_impact,
            bid_ask_spread=bid_ask_spread,
            commission=commission,
            total_cost=total_cost,
            total_bps=total_bps,
            volatility=volatility,
            liquidity_score=market_data.get("liquidity_score"),
            market_regime=market_data.get("market_regime")
        )


class LinearImpactModel(MarketImpactModel):
    """
    Linear market impact model.
    
    Impact = α * (trade_size / ADV) * volatility
    
    Simple model where impact increases linearly with participation rate.
    Good for small trades but may overestimate impact for large trades.
    """
    
    def __init__(self, alpha: float = 0.5):
        super().__init__("Linear Impact Model")
        self.model_parameters = {
            "alpha": alpha,        # Impact coefficient
            "temp_ratio": 0.6,     # Fraction that is temporary impact
        }
    
    def estimate_impact(
        self,
        trade_size: float,
        average_daily_volume: float,
        volatility: float,
        spread: float,
        **kwargs
    ) -> Tuple[float, float]:
        """Estimate linear market impact"""
        alpha = self.model_parameters["alpha"]
        temp_ratio = self.model_parameters["temp_ratio"]
        
        # Participation rate
        participation_rate = trade_size / average_daily_volume
        
        # Total impact in basis points
        total_impact_bps = alpha * participation_rate * volatility * 10000
        
        # Split into temporary and permanent
        temporary_impact = total_impact_bps * temp_ratio
        permanent_impact = total_impact_bps * (1 - temp_ratio)
        
        return temporary_impact, permanent_impact
    
    def calibrate(self, trade_data: pd.DataFrame) -> Dict:
        """Calibrate linear model parameters"""
        # Calculate participation rates
        trade_data["participation_rate"] = trade_data["trade_size"] / trade_data["adv"]
        
        # Normalize impact by volatility
        trade_data["normalized_impact"] = trade_data["impact"] / (trade_data["volatility"] * 10000)
        
        # Linear regression: normalized_impact = alpha * participation_rate
        from sklearn.linear_model import LinearRegression
        
        X = trade_data[["participation_rate"]].values
        y = trade_data["normalized_impact"].values
        
        model = LinearRegression(fit_intercept=False)
        model.fit(X, y)
        
        alpha = model.coef_[0]
        r2_score = model.score(X, y)
        
        self.model_parameters["alpha"] = alpha
        
        logger.info(f"Linear model calibrated: alpha={alpha:.3f}, R²={r2_score:.3f}")
        
        return {
            "alpha": alpha,
            "r2_score": r2_score,
            "temp_ratio": self.model_parameters["temp_ratio"]
        }


class SquareRootImpactModel(MarketImpactModel):
    """
    Square-root market impact model (Almgren-Chriss).
    
    Impact = γ * σ * (Q/V)^(1/2)
    
    Where:
    - γ is the impact coefficient
    - σ is volatility
    - Q is trade size
    - V is average daily volume
    
    More realistic for large trades as impact grows slower than linearly.
    """
    
    def __init__(self, gamma: float = 0.314, eta: float = 0.142):
        super().__init__("Square-Root Impact Model")
        self.model_parameters = {
            "gamma": gamma,        # Permanent impact coefficient
            "eta": eta,           # Temporary impact coefficient
        }
    
    def estimate_impact(
        self,
        trade_size: float,
        average_daily_volume: float,
        volatility: float,
        spread: float,
        **kwargs
    ) -> Tuple[float, float]:
        """Estimate square-root market impact"""
        gamma = self.model_parameters["gamma"]
        eta = self.model_parameters["eta"]
        
        # Participation rate
        participation_rate = trade_size / average_daily_volume
        
        # Square-root impact
        sqrt_participation = np.sqrt(participation_rate)
        
        # Permanent impact (basis points)
        permanent_impact = gamma * volatility * sqrt_participation * 10000
        
        # Temporary impact (basis points)  
        temporary_impact = eta * volatility * sqrt_participation * 10000
        
        return temporary_impact, permanent_impact
    
    def calibrate(self, trade_data: pd.DataFrame) -> Dict:
        """Calibrate square-root model parameters"""
        # Calculate participation rates and square root
        trade_data["participation_rate"] = trade_data["trade_size"] / trade_data["adv"]
        trade_data["sqrt_participation"] = np.sqrt(trade_data["participation_rate"])
        
        # Normalize by volatility
        trade_data["normalized_impact"] = trade_data["impact"] / (trade_data["volatility"] * 10000)
        
        # Regression: normalized_impact = (gamma + eta) * sqrt_participation
        from sklearn.linear_model import LinearRegression
        
        X = trade_data[["sqrt_participation"]].values
        y = trade_data["normalized_impact"].values
        
        model = LinearRegression(fit_intercept=False)
        model.fit(X, y)
        
        total_coeff = model.coef_[0]
        r2_score = model.score(X, y)
        
        # Split between permanent (70%) and temporary (30%) - typical assumption
        gamma = total_coeff * 0.7
        eta = total_coeff * 0.3
        
        self.model_parameters["gamma"] = gamma
        self.model_parameters["eta"] = eta
        
        logger.info(f"Square-root model calibrated: γ={gamma:.3f}, η={eta:.3f}, R²={r2_score:.3f}")
        
        return {
            "gamma": gamma,
            "eta": eta,
            "total_coefficient": total_coeff,
            "r2_score": r2_score
        }


class PowerLawImpactModel(MarketImpactModel):
    """
    Power-law market impact model.
    
    Impact = β * σ * (Q/V)^δ
    
    Where δ is the power law exponent (typically 0.5-0.8).
    More flexible than square-root model, can capture different impact regimes.
    """
    
    def __init__(self, beta: float = 0.25, delta: float = 0.6):
        super().__init__("Power-Law Impact Model")
        self.model_parameters = {
            "beta": beta,         # Impact coefficient
            "delta": delta,       # Power law exponent
            "temp_fraction": 0.4,  # Fraction that is temporary
        }
    
    def estimate_impact(
        self,
        trade_size: float,
        average_daily_volume: float,
        volatility: float,
        spread: float,
        **kwargs
    ) -> Tuple[float, float]:
        """Estimate power-law market impact"""
        beta = self.model_parameters["beta"]
        delta = self.model_parameters["delta"]
        temp_fraction = self.model_parameters["temp_fraction"]
        
        # Participation rate
        participation_rate = trade_size / average_daily_volume
        
        # Power-law impact
        power_participation = np.power(participation_rate, delta)
        
        # Total impact (basis points)
        total_impact = beta * volatility * power_participation * 10000
        
        # Split into temporary and permanent
        temporary_impact = total_impact * temp_fraction
        permanent_impact = total_impact * (1 - temp_fraction)
        
        return temporary_impact, permanent_impact
    
    def calibrate(self, trade_data: pd.DataFrame) -> Dict:
        """Calibrate power-law model parameters"""
        # Calculate participation rates
        trade_data["participation_rate"] = trade_data["trade_size"] / trade_data["adv"]
        trade_data["log_participation"] = np.log(trade_data["participation_rate"])
        
        # Normalize impact
        trade_data["normalized_impact"] = trade_data["impact"] / (trade_data["volatility"] * 10000)
        trade_data["log_normalized_impact"] = np.log(trade_data["normalized_impact"])
        
        # Log-linear regression: log(impact) = log(β) + δ * log(participation)
        from sklearn.linear_model import LinearRegression
        
        X = trade_data[["log_participation"]].values
        y = trade_data["log_normalized_impact"].values
        
        # Remove invalid values
        valid_mask = np.isfinite(X.ravel()) & np.isfinite(y)
        X_valid = X[valid_mask]
        y_valid = y[valid_mask]
        
        if len(X_valid) < 10:
            logger.warning("Insufficient valid data for power-law calibration")
            return self.model_parameters
        
        model = LinearRegression()
        model.fit(X_valid.reshape(-1, 1), y_valid)
        
        delta = model.coef_[0]
        log_beta = model.intercept_
        beta = np.exp(log_beta)
        r2_score = model.score(X_valid.reshape(-1, 1), y_valid)
        
        self.model_parameters["beta"] = beta
        self.model_parameters["delta"] = delta
        
        logger.info(f"Power-law model calibrated: β={beta:.3f}, δ={delta:.3f}, R²={r2_score:.3f}")
        
        return {
            "beta": beta,
            "delta": delta,
            "r2_score": r2_score,
            "temp_fraction": self.model_parameters["temp_fraction"]
        }


class LiquidityAdjustedImpactModel(MarketImpactModel):
    """
    Liquidity-adjusted market impact model.
    
    Incorporates multiple liquidity measures:
    - Order book depth
    - Bid-ask spread
    - Price impact resilience
    - Market maker presence
    """
    
    def __init__(self):
        super().__init__("Liquidity-Adjusted Impact Model")
        self.model_parameters = {
            "base_alpha": 0.3,
            "spread_sensitivity": 2.0,
            "depth_sensitivity": -0.5,
            "resilience_factor": 0.8,
        }
    
    def estimate_impact(
        self,
        trade_size: float,
        average_daily_volume: float,
        volatility: float,
        spread: float,
        order_book_depth: Optional[float] = None,
        market_maker_presence: Optional[float] = None,
        **kwargs
    ) -> Tuple[float, float]:
        """Estimate liquidity-adjusted market impact"""
        base_alpha = self.model_parameters["base_alpha"]
        spread_sens = self.model_parameters["spread_sensitivity"]
        depth_sens = self.model_parameters["depth_sensitivity"]
        resilience = self.model_parameters["resilience_factor"]
        
        # Base participation rate impact
        participation_rate = trade_size / average_daily_volume
        base_impact = base_alpha * np.sqrt(participation_rate) * volatility * 10000
        
        # Spread adjustment (higher spread = higher impact)
        spread_adjustment = 1 + spread_sens * spread
        
        # Depth adjustment (higher depth = lower impact)
        depth_adjustment = 1.0
        if order_book_depth is not None:
            # Normalize depth by trade size
            relative_depth = order_book_depth / trade_size
            depth_adjustment = 1 + depth_sens * np.log(max(relative_depth, 0.1))
        
        # Market maker adjustment (more MMs = lower impact)
        mm_adjustment = 1.0
        if market_maker_presence is not None:
            mm_adjustment = 1 - 0.2 * market_maker_presence  # Up to 20% reduction
        
        # Total adjustment
        total_adjustment = spread_adjustment * depth_adjustment * mm_adjustment
        
        # Adjusted impact
        total_impact = base_impact * total_adjustment
        
        # Split based on resilience (higher resilience = more temporary impact)
        temp_ratio = 0.3 + 0.4 * resilience  # 30-70% temporary
        temporary_impact = total_impact * temp_ratio
        permanent_impact = total_impact * (1 - temp_ratio)
        
        return temporary_impact, permanent_impact
    
    def calibrate(self, trade_data: pd.DataFrame) -> Dict:
        """Calibrate liquidity-adjusted model"""
        # This would require more sophisticated ML techniques
        # For now, return default parameters
        logger.info("Liquidity-adjusted model using default parameters")
        return self.model_parameters


def create_impact_model(model_type: str, **params) -> MarketImpactModel:
    """Factory function to create market impact models"""
    if model_type.lower() == "linear":
        return LinearImpactModel(**params)
    elif model_type.lower() == "square_root":
        return SquareRootImpactModel(**params)
    elif model_type.lower() == "power_law":
        return PowerLawImpactModel(**params)
    elif model_type.lower() == "liquidity_adjusted":
        return LiquidityAdjustedImpactModel(**params)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def compare_impact_models(
    trade_data: pd.DataFrame,
    models: List[MarketImpactModel]
) -> pd.DataFrame:
    """
    Compare performance of different impact models.
    
    Args:
        trade_data: Historical trade data
        models: List of calibrated models to compare
        
    Returns:
        DataFrame with model comparison metrics
    """
    results = []
    
    for model in models:
        # Calculate predicted impacts
        predictions = []
        
        for _, trade in trade_data.iterrows():
            temp_pred, perm_pred = model.estimate_impact(
                trade_size=trade["trade_size"],
                average_daily_volume=trade["adv"],
                volatility=trade["volatility"],
                spread=trade["spread"]
            )
            predictions.append(temp_pred + perm_pred)
        
        predictions = np.array(predictions)
        actual = trade_data["impact"].values * 10000  # Convert to bps
        
        # Calculate metrics
        mae = np.mean(np.abs(predictions - actual))
        rmse = np.sqrt(np.mean((predictions - actual) ** 2))
        correlation = np.corrcoef(predictions, actual)[0, 1]
        
        results.append({
            "model": model.name,
            "mae_bps": mae,
            "rmse_bps": rmse,
            "correlation": correlation,
            "mean_prediction": np.mean(predictions),
            "mean_actual": np.mean(actual)
        })
    
    return pd.DataFrame(results)
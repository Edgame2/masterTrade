"""
Performance Comparator

Compares performance between strategy versions with detailed metrics.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Result of performance comparison"""
    version1: str
    version2: str
    
    # PnL comparison
    pnl_difference: float
    pnl_improvement_pct: float
    
    # Risk-adjusted metrics
    sharpe_difference: float
    sortino_difference: float
    
    # Win rate
    win_rate_difference: float
    
    # Risk metrics
    volatility_difference: float
    max_drawdown_difference: float
    
    # Overall assessment
    is_better: bool
    improvement_score: float  # 0-100
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "version1": self.version1,
            "version2": self.version2,
            "pnl_difference": self.pnl_difference,
            "pnl_improvement_pct": self.pnl_improvement_pct,
            "sharpe_difference": self.sharpe_difference,
            "sortino_difference": self.sortino_difference,
            "win_rate_difference": self.win_rate_difference,
            "volatility_difference": self.volatility_difference,
            "max_drawdown_difference": self.max_drawdown_difference,
            "is_better": self.is_better,
            "improvement_score": self.improvement_score,
        }


class PerformanceComparator:
    """
    Compares performance between strategy versions.
    
    Provides detailed comparison across multiple metrics:
    - PnL and returns
    - Risk-adjusted returns (Sharpe, Sortino)
    - Win rate and consistency
    - Drawdown and risk metrics
    """
    
    def __init__(self):
        logger.info("PerformanceComparator initialized")
    
    def compare(
        self,
        version1: str,
        version1_returns: List[float],
        version2: str,
        version2_returns: List[float],
    ) -> ComparisonResult:
        """
        Comprehensive comparison of two versions.
        
        Args:
            version1: First version identifier
            version1_returns: List of returns for version 1
            version2: Second version identifier
            version2_returns: List of returns for version 2
        """
        # Calculate metrics for both versions
        v1_metrics = self._calculate_metrics(version1_returns)
        v2_metrics = self._calculate_metrics(version2_returns)
        
        # Calculate differences
        pnl_diff = v2_metrics["total_pnl"] - v1_metrics["total_pnl"]
        pnl_improvement_pct = (
            (pnl_diff / abs(v1_metrics["total_pnl"]) * 100)
            if v1_metrics["total_pnl"] != 0 else 0.0
        )
        
        sharpe_diff = v2_metrics["sharpe"] - v1_metrics["sharpe"]
        sortino_diff = v2_metrics["sortino"] - v1_metrics["sortino"]
        win_rate_diff = v2_metrics["win_rate"] - v1_metrics["win_rate"]
        volatility_diff = v2_metrics["volatility"] - v1_metrics["volatility"]
        drawdown_diff = v2_metrics["max_drawdown"] - v1_metrics["max_drawdown"]
        
        # Calculate improvement score (0-100)
        improvement_score = self._calculate_improvement_score(
            pnl_improvement_pct,
            sharpe_diff,
            win_rate_diff,
            drawdown_diff,
        )
        
        # Determine if v2 is better
        is_better = improvement_score > 50.0
        
        result = ComparisonResult(
            version1=version1,
            version2=version2,
            pnl_difference=pnl_diff,
            pnl_improvement_pct=pnl_improvement_pct,
            sharpe_difference=sharpe_diff,
            sortino_difference=sortino_diff,
            win_rate_difference=win_rate_diff,
            volatility_difference=volatility_diff,
            max_drawdown_difference=drawdown_diff,
            is_better=is_better,
            improvement_score=improvement_score,
        )
        
        logger.info(f"Compared {version1} vs {version2}: score={improvement_score:.1f}/100")
        return result
    
    def rank_versions(
        self,
        versions_data: Dict[str, List[float]],
    ) -> List[Dict]:
        """
        Rank multiple versions by performance.
        
        Args:
            versions_data: {version: returns_list}
        
        Returns:
            List of versions ranked by overall score
        """
        rankings = []
        
        for version, returns in versions_data.items():
            metrics = self._calculate_metrics(returns)
            
            # Calculate overall score
            score = self._calculate_overall_score(metrics)
            
            rankings.append({
                "version": version,
                "score": score,
                "metrics": metrics,
            })
        
        # Sort by score (highest first)
        rankings.sort(key=lambda x: x["score"], reverse=True)
        
        return rankings
    
    def _calculate_metrics(self, returns: List[float]) -> Dict:
        """Calculate all performance metrics"""
        if not returns:
            return {
                "total_pnl": 0.0,
                "avg_return": 0.0,
                "sharpe": 0.0,
                "sortino": 0.0,
                "win_rate": 0.0,
                "volatility": 0.0,
                "max_drawdown": 0.0,
            }
        
        total_pnl = sum(returns)
        avg_return = np.mean(returns)
        volatility = np.std(returns, ddof=1) if len(returns) > 1 else 0.0
        
        # Sharpe ratio (annualized)
        if volatility > 0:
            sharpe = (avg_return / volatility) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        # Sortino ratio (uses downside deviation)
        downside_returns = [r for r in returns if r < 0]
        downside_vol = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else 0.0
        
        if downside_vol > 0:
            sortino = (avg_return / downside_vol) * np.sqrt(252)
        else:
            sortino = 0.0
        
        # Win rate
        wins = sum(1 for r in returns if r > 0)
        win_rate = wins / len(returns) if returns else 0.0
        
        # Max drawdown
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
        
        return {
            "total_pnl": float(total_pnl),
            "avg_return": float(avg_return),
            "sharpe": float(sharpe),
            "sortino": float(sortino),
            "win_rate": float(win_rate),
            "volatility": float(volatility),
            "max_drawdown": float(max_drawdown),
        }
    
    def _calculate_improvement_score(
        self,
        pnl_improvement_pct: float,
        sharpe_diff: float,
        win_rate_diff: float,
        drawdown_diff: float,
    ) -> float:
        """
        Calculate overall improvement score (0-100).
        
        Weights:
        - PnL improvement: 40%
        - Sharpe improvement: 30%
        - Win rate improvement: 15%
        - Drawdown improvement: 15%
        """
        # Normalize each component to 0-100
        
        # PnL: +20% improvement = 100, 0% = 50, -20% = 0
        pnl_score = 50 + (pnl_improvement_pct / 20) * 50
        pnl_score = max(0, min(100, pnl_score))
        
        # Sharpe: +1.0 improvement = 100, 0 = 50, -1.0 = 0
        sharpe_score = 50 + (sharpe_diff / 1.0) * 50
        sharpe_score = max(0, min(100, sharpe_score))
        
        # Win rate: +10% improvement = 100, 0 = 50, -10% = 0
        win_rate_score = 50 + (win_rate_diff / 0.1) * 50
        win_rate_score = max(0, min(100, win_rate_score))
        
        # Drawdown: improvement (less negative) is good
        # +1000 improvement = 100, 0 = 50, -1000 = 0
        drawdown_score = 50 + (drawdown_diff / 1000) * 50
        drawdown_score = max(0, min(100, drawdown_score))
        
        # Weighted average
        total_score = (
            0.40 * pnl_score +
            0.30 * sharpe_score +
            0.15 * win_rate_score +
            0.15 * drawdown_score
        )
        
        return total_score
    
    def _calculate_overall_score(self, metrics: Dict) -> float:
        """
        Calculate overall score for a single version.
        
        Used for ranking multiple versions.
        """
        # Normalize each metric
        
        # Sharpe: 2.0 = 100, 0 = 0
        sharpe_score = min(100, (metrics["sharpe"] / 2.0) * 100)
        
        # Win rate: 0.6 = 100, 0.4 = 0
        win_rate_score = max(0, ((metrics["win_rate"] - 0.4) / 0.2) * 100)
        
        # Max drawdown: 0 = 100, -10000 = 0
        drawdown_score = max(0, 100 + (metrics["max_drawdown"] / 10000) * 100)
        
        # Weighted average
        score = (
            0.5 * sharpe_score +
            0.3 * win_rate_score +
            0.2 * drawdown_score
        )
        
        return max(0, min(100, score))

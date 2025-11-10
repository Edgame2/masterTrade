"""
Statistical Tests for A/B Testing

Provides statistical significance testing for strategy comparisons.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
from scipy import stats
import logging

logger = logging.getLogger(__name__)


@dataclass
class SignificanceTest:
    """Result of a statistical significance test"""
    test_name: str
    statistic: float
    p_value: float
    is_significant: bool
    confidence_level: float
    effect_size: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "test_name": self.test_name,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "is_significant": self.is_significant,
            "confidence_level": self.confidence_level,
            "effect_size": self.effect_size,
        }


class StatisticalTester:
    """
    Statistical tests for comparing strategy performance.
    
    Implements:
    - Two-sample t-test
    - Mann-Whitney U test (non-parametric)
    - Chi-square test (for win rates)
    - Bayesian comparison
    """
    
    def __init__(self):
        logger.info("StatisticalTester initialized")
    
    def t_test(
        self,
        control_samples: List[float],
        treatment_samples: List[float],
        confidence_level: float = 0.95,
    ) -> Dict:
        """
        Two-sample t-test.
        
        Tests if means of two samples are significantly different.
        Assumes normal distribution.
        """
        if len(control_samples) < 2 or len(treatment_samples) < 2:
            return {
                "test_name": "t-test",
                "is_significant": False,
                "p_value": 1.0,
                "error": "Insufficient samples",
            }
        
        # Perform t-test
        statistic, p_value = stats.ttest_ind(control_samples, treatment_samples)
        
        # Check significance
        alpha = 1 - confidence_level
        is_significant = p_value < alpha
        
        # Calculate effect size (Cohen's d)
        control_mean = np.mean(control_samples)
        treatment_mean = np.mean(treatment_samples)
        pooled_std = np.sqrt(
            (np.var(control_samples, ddof=1) + np.var(treatment_samples, ddof=1)) / 2
        )
        
        effect_size = (treatment_mean - control_mean) / pooled_std if pooled_std > 0 else 0.0
        
        return {
            "test_name": "t-test",
            "statistic": float(statistic),
            "p_value": float(p_value),
            "is_significant": is_significant,
            "confidence_level": confidence_level,
            "effect_size": float(effect_size),
            "control_mean": float(control_mean),
            "treatment_mean": float(treatment_mean),
        }
    
    def mann_whitney_test(
        self,
        control_samples: List[float],
        treatment_samples: List[float],
        confidence_level: float = 0.95,
    ) -> Dict:
        """
        Mann-Whitney U test (non-parametric alternative to t-test).
        
        Does not assume normal distribution.
        Tests if distributions are different.
        """
        if len(control_samples) < 2 or len(treatment_samples) < 2:
            return {
                "test_name": "mann-whitney",
                "is_significant": False,
                "p_value": 1.0,
                "error": "Insufficient samples",
            }
        
        # Perform Mann-Whitney U test
        statistic, p_value = stats.mannwhitneyu(
            control_samples,
            treatment_samples,
            alternative='two-sided'
        )
        
        alpha = 1 - confidence_level
        is_significant = p_value < alpha
        
        return {
            "test_name": "mann-whitney",
            "statistic": float(statistic),
            "p_value": float(p_value),
            "is_significant": is_significant,
            "confidence_level": confidence_level,
            "control_median": float(np.median(control_samples)),
            "treatment_median": float(np.median(treatment_samples)),
        }
    
    def chi_square_test(
        self,
        control_wins: int,
        control_losses: int,
        treatment_wins: int,
        treatment_losses: int,
        confidence_level: float = 0.95,
    ) -> Dict:
        """
        Chi-square test for win rates.
        
        Tests if win rates are significantly different.
        """
        # Create contingency table
        observed = np.array([
            [control_wins, control_losses],
            [treatment_wins, treatment_losses]
        ])
        
        # Perform chi-square test
        statistic, p_value, dof, expected = stats.chi2_contingency(observed)
        
        alpha = 1 - confidence_level
        is_significant = p_value < alpha
        
        control_total = control_wins + control_losses
        treatment_total = treatment_wins + treatment_losses
        
        control_win_rate = control_wins / control_total if control_total > 0 else 0.0
        treatment_win_rate = treatment_wins / treatment_total if treatment_total > 0 else 0.0
        
        return {
            "test_name": "chi-square",
            "statistic": float(statistic),
            "p_value": float(p_value),
            "is_significant": is_significant,
            "confidence_level": confidence_level,
            "control_win_rate": control_win_rate,
            "treatment_win_rate": treatment_win_rate,
            "degrees_of_freedom": int(dof),
        }
    
    def sharpe_ratio_test(
        self,
        control_returns: List[float],
        treatment_returns: List[float],
        confidence_level: float = 0.95,
    ) -> Dict:
        """
        Test if Sharpe ratios are significantly different.
        
        Uses Sharpe ratio difference test.
        """
        if len(control_returns) < 2 or len(treatment_returns) < 2:
            return {
                "test_name": "sharpe-ratio",
                "is_significant": False,
                "p_value": 1.0,
                "error": "Insufficient samples",
            }
        
        # Calculate Sharpe ratios
        control_sharpe = self._calculate_sharpe(control_returns)
        treatment_sharpe = self._calculate_sharpe(treatment_returns)
        
        # Use t-test on returns as approximation
        result = self.t_test(control_returns, treatment_returns, confidence_level)
        
        return {
            "test_name": "sharpe-ratio",
            "statistic": result["statistic"],
            "p_value": result["p_value"],
            "is_significant": result["is_significant"],
            "confidence_level": confidence_level,
            "control_sharpe": control_sharpe,
            "treatment_sharpe": treatment_sharpe,
            "sharpe_difference": treatment_sharpe - control_sharpe,
        }
    
    def bayesian_comparison(
        self,
        control_samples: List[float],
        treatment_samples: List[float],
    ) -> Dict:
        """
        Bayesian comparison of two strategies.
        
        Estimates probability that treatment is better than control.
        """
        control_mean = np.mean(control_samples)
        treatment_mean = np.mean(treatment_samples)
        
        control_std = np.std(control_samples, ddof=1)
        treatment_std = np.std(treatment_samples, ddof=1)
        
        # Monte Carlo simulation to estimate probability
        n_simulations = 10000
        
        control_samples_mc = np.random.normal(
            control_mean,
            control_std,
            n_simulations
        )
        treatment_samples_mc = np.random.normal(
            treatment_mean,
            treatment_std,
            n_simulations
        )
        
        # Probability that treatment > control
        prob_treatment_better = np.mean(treatment_samples_mc > control_samples_mc)
        
        # Expected improvement
        expected_improvement = treatment_mean - control_mean
        
        return {
            "test_name": "bayesian",
            "prob_treatment_better": float(prob_treatment_better),
            "prob_control_better": float(1 - prob_treatment_better),
            "expected_improvement": float(expected_improvement),
            "control_mean": float(control_mean),
            "treatment_mean": float(treatment_mean),
            "control_std": float(control_std),
            "treatment_std": float(treatment_std),
        }
    
    def sequential_probability_ratio_test(
        self,
        control_wins: int,
        control_losses: int,
        treatment_wins: int,
        treatment_losses: int,
        alpha: float = 0.05,
        beta: float = 0.20,
    ) -> Dict:
        """
        Sequential Probability Ratio Test (SPRT).
        
        Allows early stopping of A/B tests when result is clear.
        """
        # Calculate win rates
        control_total = control_wins + control_losses
        treatment_total = treatment_wins + treatment_losses
        
        if control_total == 0 or treatment_total == 0:
            return {
                "test_name": "sprt",
                "decision": "continue",
                "reason": "Insufficient data",
            }
        
        p_control = control_wins / control_total
        p_treatment = treatment_wins / treatment_total
        
        # Calculate log likelihood ratio
        if p_control > 0 and p_treatment > 0:
            llr = (
                treatment_wins * np.log(p_treatment / p_control) +
                treatment_losses * np.log((1 - p_treatment) / (1 - p_control))
            )
        else:
            llr = 0
        
        # Thresholds
        threshold_upper = np.log((1 - beta) / alpha)
        threshold_lower = np.log(beta / (1 - alpha))
        
        # Make decision
        if llr >= threshold_upper:
            decision = "treatment_wins"
        elif llr <= threshold_lower:
            decision = "control_wins"
        else:
            decision = "continue"
        
        return {
            "test_name": "sprt",
            "decision": decision,
            "log_likelihood_ratio": float(llr),
            "threshold_upper": float(threshold_upper),
            "threshold_lower": float(threshold_lower),
            "control_win_rate": float(p_control),
            "treatment_win_rate": float(p_treatment),
        }
    
    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = [r - risk_free_rate for r in returns]
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)
        
        if std_excess == 0:
            return 0.0
        
        # Annualize (assuming daily returns)
        sharpe = (mean_excess / std_excess) * np.sqrt(252)
        return sharpe

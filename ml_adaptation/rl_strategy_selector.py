"""
Reinforcement Learning Strategy Selector

Uses RL to learn optimal strategy selection and allocation:
- Q-Learning for discrete strategy selection
- Deep Q-Network (DQN) for complex state spaces
- Policy gradient methods
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


@dataclass
class StrategyEnvironment:
    """
    Trading environment for RL agents.
    
    State: Market features + portfolio state
    Action: Select strategy or allocation
    Reward: Risk-adjusted return
    """
    available_strategies: List[str]
    state_dim: int
    action_dim: int
    
    # Current state
    current_state: Optional[np.ndarray] = None
    current_portfolio_value: float = 100000.0
    
    # History
    state_history: List[np.ndarray] = field(default_factory=list)
    action_history: List[int] = field(default_factory=list)
    reward_history: List[float] = field(default_factory=list)
    
    def reset(self) -> np.ndarray:
        """Reset environment"""
        self.current_portfolio_value = 100000.0
        self.state_history = []
        self.action_history = []
        self.reward_history = []
        
        # Initialize random state
        self.current_state = np.random.randn(self.state_dim)
        return self.current_state
    
    def step(self, action: int, market_return: float) -> Tuple[np.ndarray, float, bool]:
        """
        Take action and observe result.
        
        Args:
            action: Strategy index to use
            market_return: Return from selected strategy
            
        Returns:
            (next_state, reward, done)
        """
        # Update portfolio value
        self.current_portfolio_value *= (1 + market_return)
        
        # Calculate reward (risk-adjusted return)
        reward = market_return
        
        # Record
        self.state_history.append(self.current_state.copy())
        self.action_history.append(action)
        self.reward_history.append(reward)
        
        # Generate next state (simplified - would use actual market data)
        next_state = np.random.randn(self.state_dim)
        self.current_state = next_state
        
        done = False  # Could check if portfolio depleted
        
        return next_state, reward, done
    
    def get_state(self, market_features: Dict[str, float]) -> np.ndarray:
        """Convert market features to state vector"""
        # Extract relevant features
        features = [
            market_features.get("volatility", 0),
            market_features.get("trend", 0),
            market_features.get("volume_ratio", 1),
            market_features.get("rsi", 50) / 100,
            market_features.get("regime_confidence", 0.5),
        ]
        
        # Pad or truncate to state_dim
        state = np.array(features[:self.state_dim])
        if len(state) < self.state_dim:
            state = np.pad(state, (0, self.state_dim - len(state)))
        
        self.current_state = state
        return state


class RLStrategySelector:
    """Base class for RL-based strategy selection"""
    
    def __init__(self, strategy_ids: List[str]):
        self.strategy_ids = strategy_ids
        self.n_strategies = len(strategy_ids)
        
        # Performance tracking
        self.selection_history: List[str] = []
        self.performance_history: List[float] = []
    
    def select_strategy(self, state: np.ndarray) -> str:
        """Select strategy based on current state"""
        raise NotImplementedError
    
    def update(self, state: np.ndarray, action: str, reward: float, next_state: np.ndarray):
        """Update agent based on experience"""
        raise NotImplementedError
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get selection statistics"""
        if not self.selection_history:
            return {}
        
        # Count selections per strategy
        selection_counts = defaultdict(int)
        for strategy in self.selection_history:
            selection_counts[strategy] += 1
        
        return {
            "total_selections": len(self.selection_history),
            "selection_counts": dict(selection_counts),
            "avg_performance": np.mean(self.performance_history) if self.performance_history else 0,
        }


class QLearningSelector(RLStrategySelector):
    """
    Q-Learning for strategy selection.
    
    Learns Q-values: Q(state, strategy) = expected return
    Uses epsilon-greedy exploration
    """
    
    def __init__(
        self,
        strategy_ids: List[str],
        state_bins: int = 10,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        epsilon: float = 0.1,
    ):
        super().__init__(strategy_ids)
        
        self.state_bins = state_bins
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        
        # Q-table: Q[state][strategy] = expected value
        self.q_table: Dict[int, Dict[str, float]] = defaultdict(lambda: {s: 0.0 for s in strategy_ids})
        
        logger.info(f"QLearningSelector initialized with {len(strategy_ids)} strategies")
    
    def _discretize_state(self, state: np.ndarray) -> int:
        """Discretize continuous state to bin index"""
        # Simple discretization: hash of binned values
        binned = np.clip(state * self.state_bins, 0, self.state_bins - 1).astype(int)
        state_hash = hash(tuple(binned))
        return state_hash
    
    def select_strategy(self, state: np.ndarray, explore: bool = True) -> str:
        """
        Select strategy using epsilon-greedy.
        
        Args:
            state: Current state
            explore: Whether to use epsilon-greedy (False for pure exploitation)
            
        Returns:
            Selected strategy ID
        """
        state_key = self._discretize_state(state)
        
        # Epsilon-greedy
        if explore and np.random.random() < self.epsilon:
            # Explore: random strategy
            strategy = np.random.choice(self.strategy_ids)
            logger.debug(f"Exploring: selected {strategy}")
        else:
            # Exploit: best Q-value
            q_values = self.q_table[state_key]
            strategy = max(q_values, key=q_values.get)
            logger.debug(f"Exploiting: selected {strategy} (Q={q_values[strategy]:.4f})")
        
        self.selection_history.append(strategy)
        return strategy
    
    def update(self, state: np.ndarray, action: str, reward: float, next_state: np.ndarray):
        """
        Update Q-value using Q-learning update rule:
        Q(s,a) = Q(s,a) + α * [r + γ * max_a' Q(s',a') - Q(s,a)]
        """
        state_key = self._discretize_state(state)
        next_state_key = self._discretize_state(next_state)
        
        # Current Q-value
        current_q = self.q_table[state_key][action]
        
        # Max Q-value for next state
        next_q_values = self.q_table[next_state_key]
        max_next_q = max(next_q_values.values())
        
        # Q-learning update
        new_q = current_q + self.learning_rate * (reward + self.discount_factor * max_next_q - current_q)
        
        # Update Q-table
        self.q_table[state_key][action] = new_q
        
        self.performance_history.append(reward)
        
        logger.debug(f"Updated Q({state_key}, {action}): {current_q:.4f} -> {new_q:.4f} (reward: {reward:.4f})")


class DQNSelector(RLStrategySelector):
    """
    Deep Q-Network for strategy selection.
    
    Uses neural network to approximate Q-function.
    Better for high-dimensional state spaces.
    """
    
    def __init__(
        self,
        strategy_ids: List[str],
        state_dim: int,
        hidden_dim: int = 64,
        learning_rate: float = 0.001,
        discount_factor: float = 0.95,
        epsilon: float = 0.1,
        epsilon_decay: float = 0.995,
        epsilon_min: float = 0.01,
        batch_size: int = 32,
        memory_size: int = 10000,
    ):
        super().__init__(strategy_ids)
        
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.batch_size = batch_size
        
        # Replay memory
        self.memory = deque(maxlen=memory_size)
        
        # Neural network (simplified - would use PyTorch/TensorFlow in production)
        self.weights = self._initialize_network()
        
        self.training_step = 0
        
        logger.info(f"DQNSelector initialized with {len(strategy_ids)} strategies")
    
    def _initialize_network(self) -> Dict[str, np.ndarray]:
        """Initialize network weights"""
        # Simple 2-layer network: state -> hidden -> Q-values
        weights = {
            "W1": np.random.randn(self.state_dim, self.hidden_dim) * 0.1,
            "b1": np.zeros(self.hidden_dim),
            "W2": np.random.randn(self.hidden_dim, self.n_strategies) * 0.1,
            "b2": np.zeros(self.n_strategies),
        }
        return weights
    
    def _forward(self, state: np.ndarray) -> np.ndarray:
        """Forward pass through network"""
        # Hidden layer with ReLU
        hidden = np.maximum(0, np.dot(state, self.weights["W1"]) + self.weights["b1"])
        
        # Output layer (Q-values)
        q_values = np.dot(hidden, self.weights["W2"]) + self.weights["b2"]
        
        return q_values
    
    def select_strategy(self, state: np.ndarray, explore: bool = True) -> str:
        """Select strategy using epsilon-greedy"""
        # Epsilon-greedy
        if explore and np.random.random() < self.epsilon:
            # Explore
            strategy_idx = np.random.randint(self.n_strategies)
        else:
            # Exploit
            q_values = self._forward(state)
            strategy_idx = np.argmax(q_values)
        
        strategy = self.strategy_ids[strategy_idx]
        self.selection_history.append(strategy)
        
        return strategy
    
    def update(self, state: np.ndarray, action: str, reward: float, next_state: np.ndarray):
        """Store experience and train network"""
        action_idx = self.strategy_ids.index(action)
        
        # Store experience
        self.memory.append((state, action_idx, reward, next_state))
        
        # Train if enough samples
        if len(self.memory) >= self.batch_size:
            self._train_batch()
        
        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        self.performance_history.append(reward)
    
    def _train_batch(self):
        """Train on random batch from memory"""
        # Sample batch
        indices = np.random.choice(len(self.memory), self.batch_size, replace=False)
        batch = [self.memory[i] for i in indices]
        
        # Unpack batch
        states = np.array([exp[0] for exp in batch])
        actions = np.array([exp[1] for exp in batch])
        rewards = np.array([exp[2] for exp in batch])
        next_states = np.array([exp[3] for exp in batch])
        
        # Compute targets: r + γ * max_a' Q(s', a')
        next_q_values = np.array([self._forward(s) for s in next_states])
        max_next_q = np.max(next_q_values, axis=1)
        targets = rewards + self.discount_factor * max_next_q
        
        # Compute current Q-values
        current_q_values = np.array([self._forward(s) for s in states])
        
        # Update Q-values for taken actions
        for i, action_idx in enumerate(actions):
            current_q_values[i][action_idx] = targets[i]
        
        # Gradient descent (simplified - would use backprop in production)
        # This is a placeholder for actual training
        
        self.training_step += 1
        
        if self.training_step % 100 == 0:
            logger.info(f"DQN training step {self.training_step}, epsilon: {self.epsilon:.4f}")


class PolicyGradientSelector(RLStrategySelector):
    """
    Policy gradient method for strategy selection.
    
    Directly learns policy: π(strategy|state)
    Uses REINFORCE algorithm
    """
    
    def __init__(
        self,
        strategy_ids: List[str],
        state_dim: int,
        hidden_dim: int = 64,
        learning_rate: float = 0.001,
        discount_factor: float = 0.95,
    ):
        super().__init__(strategy_ids)
        
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        
        # Policy network
        self.weights = self._initialize_network()
        
        # Episode buffer
        self.episode_states: List[np.ndarray] = []
        self.episode_actions: List[int] = []
        self.episode_rewards: List[float] = []
        
        logger.info(f"PolicyGradientSelector initialized with {len(strategy_ids)} strategies")
    
    def _initialize_network(self) -> Dict[str, np.ndarray]:
        """Initialize policy network"""
        weights = {
            "W1": np.random.randn(self.state_dim, self.hidden_dim) * 0.1,
            "b1": np.zeros(self.hidden_dim),
            "W2": np.random.randn(self.hidden_dim, self.n_strategies) * 0.1,
            "b2": np.zeros(self.n_strategies),
        }
        return weights
    
    def _forward(self, state: np.ndarray) -> np.ndarray:
        """Forward pass: output action probabilities"""
        # Hidden layer
        hidden = np.maximum(0, np.dot(state, self.weights["W1"]) + self.weights["b1"])
        
        # Output layer with softmax
        logits = np.dot(hidden, self.weights["W2"]) + self.weights["b2"]
        probs = np.exp(logits - np.max(logits))  # Numerical stability
        probs = probs / np.sum(probs)
        
        return probs
    
    def select_strategy(self, state: np.ndarray, explore: bool = True) -> str:
        """Sample strategy from policy"""
        probs = self._forward(state)
        
        # Sample action
        strategy_idx = np.random.choice(self.n_strategies, p=probs)
        
        strategy = self.strategy_ids[strategy_idx]
        self.selection_history.append(strategy)
        
        # Store for episode
        self.episode_states.append(state)
        self.episode_actions.append(strategy_idx)
        
        return strategy
    
    def update(self, state: np.ndarray, action: str, reward: float, next_state: np.ndarray):
        """Store reward for episode"""
        self.episode_rewards.append(reward)
        self.performance_history.append(reward)
    
    def finish_episode(self):
        """Train policy at end of episode using REINFORCE"""
        if not self.episode_rewards:
            return
        
        # Compute discounted returns
        returns = []
        G = 0
        for reward in reversed(self.episode_rewards):
            G = reward + self.discount_factor * G
            returns.insert(0, G)
        
        returns = np.array(returns)
        
        # Normalize returns
        returns = (returns - np.mean(returns)) / (np.std(returns) + 1e-8)
        
        # Policy gradient update (simplified)
        # In production, would compute gradients and update with backprop
        
        # Clear episode buffer
        self.episode_states = []
        self.episode_actions = []
        self.episode_rewards = []
        
        logger.info(f"Finished episode, avg return: {np.mean(returns):.4f}")

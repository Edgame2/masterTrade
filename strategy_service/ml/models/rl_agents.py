"""
Reinforcement Learning Trading Agents

This module implements sophisticated RL agents for trading strategy optimization,
including PPO for position sizing, SAC for continuous action spaces, and DQN
for discrete trading decisions. Agents learn optimal trading behaviors through
interaction with market environments.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.distributions import Normal, Categorical
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Union
import logging
from datetime import datetime
from collections import deque, namedtuple
import random
import gym
from gym import spaces
import asyncio
from dataclasses import dataclass
import pickle
import os

logger = logging.getLogger(__name__)

# Experience replay structures
Experience = namedtuple('Experience', ['state', 'action', 'reward', 'next_state', 'done'])
PPOExperience = namedtuple('PPOExperience', ['state', 'action', 'log_prob', 'reward', 'value', 'done'])

@dataclass
class AgentConfig:
    state_dim: int = 50
    action_dim: int = 3  # buy, sell, hold
    hidden_dim: int = 256
    learning_rate: float = 3e-4
    gamma: float = 0.99
    tau: float = 0.005
    batch_size: int = 256
    buffer_size: int = 100000
    update_frequency: int = 4
    target_update_frequency: int = 1000

class TradingEnvironment(gym.Env):
    """
    Custom trading environment for RL agents
    
    State space includes:
    - Price features (OHLCV, technical indicators)
    - Portfolio state (positions, cash, unrealized PnL)
    - Market context (volatility, volume, sentiment)
    
    Action space:
    - Discrete: [0=hold, 1=buy, 2=sell] or continuous position sizing
    """
    
    def __init__(self, data: pd.DataFrame, initial_capital: float = 10000, 
                 transaction_cost: float = 0.001, max_position: float = 1.0):
        super().__init__()
        
        self.data = data
        self.initial_capital = initial_capital
        self.transaction_cost = transaction_cost
        self.max_position = max_position
        
        # Environment state
        self.current_step = 0
        self.cash = initial_capital
        self.position = 0.0
        self.portfolio_value = initial_capital
        self.trade_history = []
        
        # Define observation and action spaces
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(len(data.columns) + 3,), dtype=np.float32  # +3 for cash, position, portfolio_value
        )
        
        # Continuous action space: position size (-1 to 1)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)
        
        self.reset()
    
    def reset(self):
        """Reset environment to initial state"""
        self.current_step = 0
        self.cash = self.initial_capital
        self.position = 0.0
        self.portfolio_value = self.initial_capital
        self.trade_history = []
        
        return self._get_observation()
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, Dict]:
        """Execute one step in the environment"""
        if self.current_step >= len(self.data) - 1:
            return self._get_observation(), 0.0, True, {}
        
        current_price = self.data.iloc[self.current_step]['close']
        next_price = self.data.iloc[self.current_step + 1]['close']
        
        # Execute action
        target_position = np.clip(action[0], -self.max_position, self.max_position)
        position_change = target_position - self.position
        
        # Calculate transaction cost
        transaction_value = abs(position_change) * current_price * self.initial_capital
        cost = transaction_value * self.transaction_cost
        
        # Update portfolio
        self.position = target_position
        self.cash -= cost
        
        # Calculate reward (portfolio return)
        price_change = (next_price - current_price) / current_price
        position_pnl = self.position * price_change * self.initial_capital
        
        # Update portfolio value
        self.portfolio_value = self.cash + self.position * next_price * self.initial_capital
        
        # Reward based on risk-adjusted returns
        reward = self._calculate_reward(position_pnl, cost, price_change)
        
        # Record trade
        if abs(position_change) > 0.01:  # Minimum position change threshold
            self.trade_history.append({
                'step': self.current_step,
                'action': target_position,
                'price': current_price,
                'position_change': position_change,
                'cost': cost
            })
        
        self.current_step += 1
        done = self.current_step >= len(self.data) - 1
        
        info = {
            'portfolio_value': self.portfolio_value,
            'position': self.position,
            'cash': self.cash,
            'total_return': (self.portfolio_value - self.initial_capital) / self.initial_capital
        }
        
        return self._get_observation(), reward, done, info
    
    def _get_observation(self) -> np.ndarray:
        """Get current observation state"""
        if self.current_step >= len(self.data):
            # Return last valid observation
            market_data = self.data.iloc[-1].values
        else:
            market_data = self.data.iloc[self.current_step].values
        
        # Add portfolio state
        portfolio_state = np.array([
            self.cash / self.initial_capital,
            self.position,
            self.portfolio_value / self.initial_capital
        ])
        
        observation = np.concatenate([market_data, portfolio_state])
        return observation.astype(np.float32)
    
    def _calculate_reward(self, position_pnl: float, cost: float, price_change: float) -> float:
        """Calculate reward for the agent"""
        # Base reward: PnL adjusted for transaction costs
        base_reward = (position_pnl - cost) / self.initial_capital
        
        # Risk penalty: penalize high volatility positions
        volatility_penalty = abs(self.position) * abs(price_change) * 0.1
        
        # Sharpe-like reward: reward / volatility
        reward = base_reward - volatility_penalty
        
        return reward

class DQNNetwork(nn.Module):
    """Deep Q-Network for discrete action spaces"""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256):
        super().__init__()
        
        self.network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, action_dim)
        )
        
    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.network(state)

class DQNAgent:
    """Deep Q-Network agent for discrete trading actions"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Networks
        self.q_network = DQNNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        self.target_q_network = DQNNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        
        # Copy weights to target network
        self.target_q_network.load_state_dict(self.q_network.state_dict())
        
        # Optimizer
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=config.learning_rate)
        
        # Experience replay
        self.memory = deque(maxlen=config.buffer_size)
        
        # Training state
        self.steps_done = 0
        self.epsilon = 1.0
        self.epsilon_decay = 0.995
        self.epsilon_min = 0.01
        
        logger.info("DQN Agent initialized")
    
    def act(self, state: np.ndarray, training: bool = True) -> int:
        """Select action using epsilon-greedy policy"""
        if training and random.random() < self.epsilon:
            return random.randrange(self.config.action_dim)
        
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        q_values = self.q_network(state_tensor)
        return q_values.argmax().item()
    
    def remember(self, state: np.ndarray, action: int, reward: float, 
                 next_state: np.ndarray, done: bool):
        """Store experience in replay buffer"""
        self.memory.append(Experience(state, action, reward, next_state, done))
    
    def train(self) -> Optional[float]:
        """Train the DQN agent"""
        if len(self.memory) < self.config.batch_size:
            return None
        
        # Sample batch from memory
        batch = random.sample(self.memory, self.config.batch_size)
        states = torch.FloatTensor([e.state for e in batch]).to(self.device)
        actions = torch.LongTensor([e.action for e in batch]).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in batch]).to(self.device)
        next_states = torch.FloatTensor([e.next_state for e in batch]).to(self.device)
        dones = torch.BoolTensor([e.done for e in batch]).to(self.device)
        
        # Current Q values
        current_q_values = self.q_network(states).gather(1, actions.unsqueeze(1))
        
        # Next Q values from target network
        next_q_values = self.target_q_network(next_states).max(1)[0].detach()
        target_q_values = rewards + (self.config.gamma * next_q_values * ~dones)
        
        # Compute loss
        loss = F.mse_loss(current_q_values.squeeze(), target_q_values)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), 1.0)
        self.optimizer.step()
        
        # Update epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        
        # Update target network
        self.steps_done += 1
        if self.steps_done % self.config.target_update_frequency == 0:
            self.target_q_network.load_state_dict(self.q_network.state_dict())
        
        return loss.item()

class ActorNetwork(nn.Module):
    """Actor network for continuous action spaces (SAC/PPO)"""
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 256, 
                 max_action: float = 1.0):
        super().__init__()
        self.max_action = max_action
        
        self.network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU()
        )
        
        # Mean and log std for policy
        self.mean_layer = nn.Linear(hidden_dim // 2, action_dim)
        self.log_std_layer = nn.Linear(hidden_dim // 2, action_dim)
        
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        x = self.network(state)
        mean = self.mean_layer(x)
        log_std = self.log_std_layer(x)
        log_std = torch.clamp(log_std, -20, 2)  # Constrain log std
        return mean, log_std
    
    def sample(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Sample action from policy"""
        mean, log_std = self.forward(state)
        std = log_std.exp()
        
        normal = Normal(mean, std)
        action = normal.rsample()  # Reparameterization trick
        log_prob = normal.log_prob(action).sum(dim=-1, keepdim=True)
        
        # Tanh squashing
        action = torch.tanh(action) * self.max_action
        
        # Adjust log prob for tanh squashing
        log_prob -= torch.log(1 - action.pow(2) + 1e-6).sum(dim=-1, keepdim=True)
        
        return action, log_prob

class CriticNetwork(nn.Module):
    """Critic network for value estimation"""
    
    def __init__(self, state_dim: int, action_dim: int = 0, hidden_dim: int = 256):
        super().__init__()
        
        input_dim = state_dim + action_dim  # For Q-function (SAC)
        if action_dim == 0:  # For V-function (PPO)
            input_dim = state_dim
        
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )
        
    def forward(self, state: torch.Tensor, action: torch.Tensor = None) -> torch.Tensor:
        if action is not None:
            x = torch.cat([state, action], dim=-1)
        else:
            x = state
        return self.network(x)

class PPOAgent:
    """Proximal Policy Optimization agent for continuous trading"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Networks
        self.actor = ActorNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        self.critic = CriticNetwork(config.state_dim, 0, config.hidden_dim).to(self.device)
        
        # Optimizers
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=config.learning_rate)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr=config.learning_rate)
        
        # PPO hyperparameters
        self.clip_epsilon = 0.2
        self.ppo_epochs = 10
        self.value_loss_coef = 0.5
        self.entropy_coef = 0.01
        
        # Experience buffer
        self.memory = []
        
        logger.info("PPO Agent initialized")
    
    def act(self, state: np.ndarray, training: bool = True) -> Tuple[np.ndarray, float, float]:
        """Select action and return action, log_prob, and value"""
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            action, log_prob = self.actor.sample(state_tensor)
            value = self.critic(state_tensor)
        
        return action.cpu().numpy()[0], log_prob.cpu().item(), value.cpu().item()
    
    def remember(self, state: np.ndarray, action: np.ndarray, log_prob: float, 
                 reward: float, value: float, done: bool):
        """Store experience"""
        self.memory.append(PPOExperience(state, action, log_prob, reward, value, done))
    
    def train(self) -> Dict[str, float]:
        """Train PPO agent using collected experiences"""
        if len(self.memory) == 0:
            return {}
        
        # Convert experiences to tensors
        states = torch.FloatTensor([e.state for e in self.memory]).to(self.device)
        actions = torch.FloatTensor([e.action for e in self.memory]).to(self.device)
        old_log_probs = torch.FloatTensor([e.log_prob for e in self.memory]).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in self.memory]).to(self.device)
        old_values = torch.FloatTensor([e.value for e in self.memory]).to(self.device)
        dones = torch.BoolTensor([e.done for e in self.memory]).to(self.device)
        
        # Calculate advantages using GAE
        advantages, returns = self._calculate_gae(rewards, old_values, dones)
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # PPO training loop
        actor_losses = []
        critic_losses = []
        
        for _ in range(self.ppo_epochs):
            # Get current policy outputs
            mean, log_std = self.actor(states)
            std = log_std.exp()
            dist = Normal(mean, std)
            
            new_log_probs = dist.log_prob(actions).sum(dim=-1)
            entropy = dist.entropy().sum(dim=-1).mean()
            
            # Policy ratio
            ratio = (new_log_probs - old_log_probs).exp()
            
            # Clipped surrogate objective
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1.0 - self.clip_epsilon, 1.0 + self.clip_epsilon) * advantages
            actor_loss = -torch.min(surr1, surr2).mean() - self.entropy_coef * entropy
            
            # Value function loss
            current_values = self.critic(states).squeeze()
            critic_loss = F.mse_loss(current_values, returns)
            
            # Update networks
            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 0.5)
            self.actor_optimizer.step()
            
            self.critic_optimizer.zero_grad()
            critic_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 0.5)
            self.critic_optimizer.step()
            
            actor_losses.append(actor_loss.item())
            critic_losses.append(critic_loss.item())
        
        # Clear memory
        self.memory = []
        
        return {
            'actor_loss': np.mean(actor_losses),
            'critic_loss': np.mean(critic_losses),
            'entropy': entropy.item()
        }
    
    def _calculate_gae(self, rewards: torch.Tensor, values: torch.Tensor, 
                      dones: torch.Tensor, gae_lambda: float = 0.95) -> Tuple[torch.Tensor, torch.Tensor]:
        """Calculate Generalized Advantage Estimation"""
        advantages = torch.zeros_like(rewards)
        returns = torch.zeros_like(rewards)
        
        gae = 0
        next_value = 0
        
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_non_terminal = 1.0 - dones[t].float()
                next_value = 0
            else:
                next_non_terminal = 1.0 - dones[t + 1].float()
                next_value = values[t + 1]
            
            delta = rewards[t] + self.config.gamma * next_value * next_non_terminal - values[t]
            gae = delta + self.config.gamma * gae_lambda * next_non_terminal * gae
            
            advantages[t] = gae
            returns[t] = gae + values[t]
        
        return advantages, returns

class SACAgent:
    """Soft Actor-Critic agent for continuous trading with automatic entropy tuning"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Networks
        self.actor = ActorNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        
        # Two Q-networks for reducing overestimation bias
        self.critic1 = CriticNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        self.critic2 = CriticNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        
        # Target networks
        self.target_critic1 = CriticNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        self.target_critic2 = CriticNetwork(config.state_dim, config.action_dim, config.hidden_dim).to(self.device)
        
        # Copy weights to target networks
        self.target_critic1.load_state_dict(self.critic1.state_dict())
        self.target_critic2.load_state_dict(self.critic2.state_dict())
        
        # Optimizers
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=config.learning_rate)
        self.critic1_optimizer = optim.Adam(self.critic1.parameters(), lr=config.learning_rate)
        self.critic2_optimizer = optim.Adam(self.critic2.parameters(), lr=config.learning_rate)
        
        # Automatic entropy tuning
        self.target_entropy = -config.action_dim
        self.log_alpha = torch.zeros(1, requires_grad=True, device=self.device)
        self.alpha_optimizer = optim.Adam([self.log_alpha], lr=config.learning_rate)
        
        # Experience replay
        self.memory = deque(maxlen=config.buffer_size)
        
        logger.info("SAC Agent initialized")
    
    @property
    def alpha(self) -> torch.Tensor:
        return self.log_alpha.exp()
    
    def act(self, state: np.ndarray, training: bool = True) -> np.ndarray:
        """Select action from policy"""
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        if training:
            action, _ = self.actor.sample(state_tensor)
        else:
            # For evaluation, use mean action
            mean, _ = self.actor(state_tensor)
            action = torch.tanh(mean)
        
        return action.cpu().numpy()[0]
    
    def remember(self, state: np.ndarray, action: np.ndarray, reward: float, 
                 next_state: np.ndarray, done: bool):
        """Store experience in replay buffer"""
        self.memory.append(Experience(state, action, reward, next_state, done))
    
    def train(self) -> Optional[Dict[str, float]]:
        """Train SAC agent"""
        if len(self.memory) < self.config.batch_size:
            return None
        
        # Sample batch
        batch = random.sample(self.memory, self.config.batch_size)
        states = torch.FloatTensor([e.state for e in batch]).to(self.device)
        actions = torch.FloatTensor([e.action for e in batch]).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in batch]).to(self.device)
        next_states = torch.FloatTensor([e.next_state for e in batch]).to(self.device)
        dones = torch.BoolTensor([e.done for e in batch]).to(self.device)
        
        # Update critics
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_states)
            target_q1 = self.target_critic1(next_states, next_actions)
            target_q2 = self.target_critic2(next_states, next_actions)
            target_q = torch.min(target_q1, target_q2) - self.alpha * next_log_probs
            target_q = rewards.unsqueeze(1) + ~dones.unsqueeze(1) * self.config.gamma * target_q
        
        current_q1 = self.critic1(states, actions)
        current_q2 = self.critic2(states, actions)
        
        critic1_loss = F.mse_loss(current_q1, target_q)
        critic2_loss = F.mse_loss(current_q2, target_q)
        
        self.critic1_optimizer.zero_grad()
        critic1_loss.backward()
        self.critic1_optimizer.step()
        
        self.critic2_optimizer.zero_grad()
        critic2_loss.backward()
        self.critic2_optimizer.step()
        
        # Update actor
        new_actions, log_probs = self.actor.sample(states)
        q1_new = self.critic1(states, new_actions)
        q2_new = self.critic2(states, new_actions)
        q_new = torch.min(q1_new, q2_new)
        
        actor_loss = (self.alpha * log_probs - q_new).mean()
        
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()
        
        # Update alpha (entropy coefficient)
        alpha_loss = -(self.log_alpha * (log_probs + self.target_entropy).detach()).mean()
        
        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.alpha_optimizer.step()
        
        # Soft update target networks
        self._soft_update(self.target_critic1, self.critic1)
        self._soft_update(self.target_critic2, self.critic2)
        
        return {
            'critic1_loss': critic1_loss.item(),
            'critic2_loss': critic2_loss.item(),
            'actor_loss': actor_loss.item(),
            'alpha_loss': alpha_loss.item(),
            'alpha': self.alpha.item()
        }
    
    def _soft_update(self, target: nn.Module, source: nn.Module):
        """Soft update target network"""
        for target_param, param in zip(target.parameters(), source.parameters()):
            target_param.data.copy_(
                target_param.data * (1.0 - self.config.tau) + param.data * self.config.tau
            )

class RLAgentManager:
    """Manager for multiple RL agents with different strategies"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.agents = {}
        
        # Create different types of agents
        self.agents['dqn'] = DQNAgent(config)
        self.agents['ppo'] = PPOAgent(config)
        self.agents['sac'] = SACAgent(config)
        
        # Performance tracking
        self.agent_performance = {name: [] for name in self.agents.keys()}
        
        logger.info("RL Agent Manager initialized with 3 agents")
    
    async def train_all_agents(self, environment: TradingEnvironment, episodes: int = 1000):
        """Train all agents in the environment"""
        
        for agent_name, agent in self.agents.items():
            logger.info(f"Training {agent_name} agent for {episodes} episodes")
            
            episode_rewards = []
            
            for episode in range(episodes):
                state = environment.reset()
                total_reward = 0
                done = False
                
                while not done:
                    if agent_name == 'dqn':
                        action = agent.act(state)
                        # Convert discrete to continuous action
                        if action == 0:  # hold
                            continuous_action = np.array([0.0])
                        elif action == 1:  # buy
                            continuous_action = np.array([0.5])
                        else:  # sell
                            continuous_action = np.array([-0.5])
                    
                    elif agent_name == 'ppo':
                        continuous_action, log_prob, value = agent.act(state)
                    
                    else:  # sac
                        continuous_action = agent.act(state)
                    
                    next_state, reward, done, info = environment.step(continuous_action)
                    
                    # Store experience
                    if agent_name == 'dqn':
                        agent.remember(state, action, reward, next_state, done)
                        if len(agent.memory) > agent.config.batch_size:
                            agent.train()
                    
                    elif agent_name == 'ppo':
                        agent.remember(state, continuous_action, log_prob, reward, value, done)
                    
                    else:  # sac
                        agent.remember(state, continuous_action, reward, next_state, done)
                        if len(agent.memory) > agent.config.batch_size:
                            agent.train()
                    
                    state = next_state
                    total_reward += reward
                
                # Train PPO at end of episode
                if agent_name == 'ppo':
                    agent.train()
                
                episode_rewards.append(total_reward)
                
                if episode % 100 == 0:
                    avg_reward = np.mean(episode_rewards[-100:])
                    logger.info(f"{agent_name} Episode {episode}, Avg Reward: {avg_reward:.4f}")
            
            self.agent_performance[agent_name] = episode_rewards
    
    def get_best_agent(self) -> Tuple[str, Any]:
        """Get the best performing agent"""
        best_performance = -np.inf
        best_agent_name = None
        
        for agent_name, rewards in self.agent_performance.items():
            if rewards:
                avg_performance = np.mean(rewards[-100:])  # Last 100 episodes
                if avg_performance > best_performance:
                    best_performance = avg_performance
                    best_agent_name = agent_name
        
        return best_agent_name, self.agents.get(best_agent_name)
    
    def save_agents(self, filepath: str):
        """Save all trained agents"""
        for agent_name, agent in self.agents.items():
            agent_path = f"{filepath}_{agent_name}.pt"
            
            if hasattr(agent, 'q_network'):  # DQN
                torch.save(agent.q_network.state_dict(), agent_path)
            elif hasattr(agent, 'actor'):  # PPO/SAC
                torch.save({
                    'actor': agent.actor.state_dict(),
                    'critic': agent.critic.state_dict() if hasattr(agent, 'critic') else None,
                    'critic1': agent.critic1.state_dict() if hasattr(agent, 'critic1') else None,
                    'critic2': agent.critic2.state_dict() if hasattr(agent, 'critic2') else None,
                }, agent_path)
        
        # Save performance history
        with open(f"{filepath}_performance.pkl", 'wb') as f:
            pickle.dump(self.agent_performance, f)
        
        logger.info(f"All agents saved to {filepath}")

# Factory functions
def create_trading_environment(data: pd.DataFrame, **kwargs) -> TradingEnvironment:
    """Create a trading environment with market data"""
    return TradingEnvironment(data, **kwargs)

def create_rl_agent_manager(config: AgentConfig = None) -> RLAgentManager:
    """Create an RL agent manager with default or custom configuration"""
    if config is None:
        config = AgentConfig()
    
    return RLAgentManager(config)
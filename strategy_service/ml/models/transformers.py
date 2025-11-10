"""
Transformer-based Market Analysis Models

This module implements state-of-the-art transformer models for market pattern recognition,
price prediction, and trading signal generation. Uses multi-head attention mechanisms
to analyze complex market relationships across multiple timeframes and assets.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import datetime, timedelta
import math
import asyncio
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    sequence_length: int = 128
    d_model: int = 512
    num_heads: int = 8
    num_layers: int = 6
    d_ff: int = 2048
    dropout: float = 0.1
    max_position_encoding: int = 1000
    num_assets: int = 50
    num_features: int = 20
    prediction_horizon: int = 24  # hours

class PositionalEncoding(nn.Module):
    """
    Positional encoding for transformer models with support for multiple timeframes
    """
    
    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * 
                           (-math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        
        self.register_buffer('pe', pe)
    
    def forward(self, x):
        return x + self.pe[:x.size(0), :]

class MultiTimeframeAttention(nn.Module):
    """
    Multi-head attention mechanism adapted for multiple timeframes
    """
    
    def __init__(self, d_model: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        assert d_model % num_heads == 0
        
        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        
        self.w_q = nn.Linear(d_model, d_model)
        self.w_k = nn.Linear(d_model, d_model)
        self.w_v = nn.Linear(d_model, d_model)
        self.w_o = nn.Linear(d_model, d_model)
        
        self.dropout = nn.Dropout(dropout)
        self.scale = math.sqrt(self.d_k)
        
    def forward(self, query, key, value, mask=None):
        batch_size = query.size(0)
        
        # Linear transformations and reshape for multi-head attention
        Q = self.w_q(query).view(batch_size, -1, self.num_heads, self.d_k).transpose(1, 2)
        K = self.w_k(key).view(batch_size, -1, self.num_heads, self.d_k).transpose(1, 2)
        V = self.w_v(value).view(batch_size, -1, self.num_heads, self.d_k).transpose(1, 2)
        
        # Attention computation
        attention_scores = torch.matmul(Q, K.transpose(-2, -1)) / self.scale
        
        if mask is not None:
            attention_scores = attention_scores.masked_fill(mask == 0, -1e9)
        
        attention_weights = F.softmax(attention_scores, dim=-1)
        attention_weights = self.dropout(attention_weights)
        
        context = torch.matmul(attention_weights, V)
        
        # Concatenate heads and project
        context = context.transpose(1, 2).contiguous().view(
            batch_size, -1, self.d_model
        )
        
        output = self.w_o(context)
        
        return output, attention_weights

class CrossAssetAttention(nn.Module):
    """
    Attention mechanism for cross-asset correlation analysis
    """
    
    def __init__(self, d_model: int, num_assets: int, dropout: float = 0.1):
        super().__init__()
        self.d_model = d_model
        self.num_assets = num_assets
        
        self.asset_embeddings = nn.Embedding(num_assets, d_model)
        self.correlation_attention = nn.MultiheadAttention(d_model, 8, dropout=dropout, batch_first=True)
        
        self.layer_norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, x, asset_ids):
        # Add asset embeddings
        asset_embeds = self.asset_embeddings(asset_ids)
        x_with_assets = x + asset_embeds
        
        # Cross-asset attention
        attended, attention_weights = self.correlation_attention(
            x_with_assets, x_with_assets, x_with_assets
        )
        
        # Residual connection and normalization
        output = self.layer_norm(x + self.dropout(attended))
        
        return output, attention_weights

class MarketTransformerEncoder(nn.Module):
    """
    Transformer encoder adapted for market data analysis
    """
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        
        # Input projection
        self.input_projection = nn.Linear(config.num_features, config.d_model)
        
        # Positional encoding
        self.pos_encoding = PositionalEncoding(config.d_model, config.max_position_encoding)
        
        # Transformer layers
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.num_heads,
            dim_feedforward=config.d_ff,
            dropout=config.dropout,
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, config.num_layers)
        
        # Cross-asset attention
        self.cross_asset_attention = CrossAssetAttention(config.d_model, config.num_assets)
        
        # Output layers
        self.layer_norm = nn.LayerNorm(config.d_model)
        self.dropout = nn.Dropout(config.dropout)
        
    def forward(self, x, asset_ids, mask=None):
        """
        Args:
            x: Input tensor [batch_size, seq_len, num_features]
            asset_ids: Asset identifier tensor [batch_size, seq_len]
            mask: Attention mask [batch_size, seq_len]
        """
        # Input projection and positional encoding
        x = self.input_projection(x)
        x = self.pos_encoding(x)
        
        # Apply transformer encoder
        encoded = self.transformer_encoder(x, src_key_padding_mask=mask)
        
        # Cross-asset attention
        cross_attended, cross_attention_weights = self.cross_asset_attention(encoded, asset_ids)
        
        # Final normalization
        output = self.layer_norm(self.dropout(cross_attended))
        
        return output, cross_attention_weights

class MarketPredictionHead(nn.Module):
    """
    Prediction head for various market prediction tasks
    """
    
    def __init__(self, d_model: int, prediction_horizon: int, num_targets: int = 5):
        super().__init__()
        self.d_model = d_model
        self.prediction_horizon = prediction_horizon
        self.num_targets = num_targets  # price, volume, volatility, trend, sentiment
        
        # Multi-task prediction heads
        self.price_head = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(d_model // 2, prediction_horizon)
        )
        
        self.volatility_head = nn.Sequential(
            nn.Linear(d_model, d_model // 4),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(d_model // 4, prediction_horizon),
            nn.Softplus()  # Ensure positive volatility
        )
        
        self.trend_head = nn.Sequential(
            nn.Linear(d_model, d_model // 4),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(d_model // 4, 3)  # bullish, bearish, sideways
        )
        
        self.volume_head = nn.Sequential(
            nn.Linear(d_model, d_model // 4),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(d_model // 4, prediction_horizon),
            nn.Softplus()  # Ensure positive volume
        )
        
        self.confidence_head = nn.Sequential(
            nn.Linear(d_model, d_model // 8),
            nn.ReLU(),
            nn.Linear(d_model // 8, 1),
            nn.Sigmoid()
        )
        
    def forward(self, x):
        """
        Args:
            x: Encoded features [batch_size, seq_len, d_model]
        """
        # Use last timestep for predictions
        last_hidden = x[:, -1, :]
        
        predictions = {
            'price': self.price_head(last_hidden),
            'volatility': self.volatility_head(last_hidden),
            'trend': self.trend_head(last_hidden),
            'volume': self.volume_head(last_hidden),
            'confidence': self.confidence_head(last_hidden)
        }
        
        return predictions

class MarketTransformer(nn.Module):
    """
    Complete transformer model for market analysis and prediction
    """
    
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        
        self.encoder = MarketTransformerEncoder(config)
        self.prediction_head = MarketPredictionHead(
            config.d_model, 
            config.prediction_horizon
        )
        
    def forward(self, x, asset_ids, mask=None):
        # Encode sequences
        encoded, attention_weights = self.encoder(x, asset_ids, mask)
        
        # Generate predictions
        predictions = self.prediction_head(encoded)
        
        return predictions, attention_weights

class MarketDataset(Dataset):
    """
    Dataset class for market data with proper preprocessing
    """
    
    def __init__(self, data: pd.DataFrame, config: ModelConfig, 
                 target_columns: List[str] = None):
        self.config = config
        self.data = data
        self.target_columns = target_columns or ['close', 'volume', 'volatility']
        
        # Prepare sequences
        self.sequences = self._prepare_sequences()
        
    def _prepare_sequences(self):
        sequences = []
        
        for i in range(len(self.data) - self.config.sequence_length - self.config.prediction_horizon):
            # Input sequence
            input_seq = self.data.iloc[i:i + self.config.sequence_length]
            
            # Target sequence  
            target_seq = self.data.iloc[
                i + self.config.sequence_length:
                i + self.config.sequence_length + self.config.prediction_horizon
            ]
            
            sequences.append({
                'input': input_seq,
                'target': target_seq,
                'start_idx': i
            })
        
        return sequences
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        sequence = self.sequences[idx]
        
        # Convert to tensors
        input_tensor = torch.FloatTensor(sequence['input'].values)
        target_tensor = torch.FloatTensor(sequence['target'][self.target_columns].values)
        
        # Asset IDs (assuming single asset for now)
        asset_ids = torch.zeros(self.config.sequence_length, dtype=torch.long)
        
        return {
            'input': input_tensor,
            'target': target_tensor,
            'asset_ids': asset_ids
        }

class TransformerTrainer:
    """
    Training manager for transformer models
    """
    
    def __init__(self, model: MarketTransformer, config: ModelConfig):
        self.model = model
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Move model to device
        self.model.to(self.device)
        
        # Optimizer and scheduler
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(), 
            lr=1e-4, 
            weight_decay=0.01
        )
        
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=100
        )
        
        # Loss functions for multi-task learning
        self.mse_loss = nn.MSELoss()
        self.ce_loss = nn.CrossEntropyLoss()
        
        logger.info(f"TransformerTrainer initialized on {self.device}")
    
    def train_epoch(self, train_loader: DataLoader) -> float:
        """Train for one epoch"""
        self.model.train()
        total_loss = 0.0
        num_batches = 0
        
        for batch in train_loader:
            # Move to device
            inputs = batch['input'].to(self.device)
            targets = batch['target'].to(self.device)
            asset_ids = batch['asset_ids'].to(self.device)
            
            # Forward pass
            predictions, attention_weights = self.model(inputs, asset_ids)
            
            # Calculate multi-task loss
            loss = self._calculate_loss(predictions, targets)
            
            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()
            
            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        avg_loss = total_loss / num_batches
        self.scheduler.step()
        
        return avg_loss
    
    def validate(self, val_loader: DataLoader) -> Dict[str, float]:
        """Validate the model"""
        self.model.eval()
        total_losses = {'total': 0.0, 'price': 0.0, 'volatility': 0.0, 'trend': 0.0}
        num_batches = 0
        
        with torch.no_grad():
            for batch in val_loader:
                inputs = batch['input'].to(self.device)
                targets = batch['target'].to(self.device)
                asset_ids = batch['asset_ids'].to(self.device)
                
                predictions, _ = self.model(inputs, asset_ids)
                
                # Calculate individual losses
                losses = self._calculate_detailed_loss(predictions, targets)
                
                for key in total_losses:
                    total_losses[key] += losses[key]
                num_batches += 1
        
        # Average losses
        avg_losses = {key: val / num_batches for key, val in total_losses.items()}
        
        return avg_losses
    
    def _calculate_loss(self, predictions: Dict, targets: torch.Tensor) -> torch.Tensor:
        """Calculate multi-task loss"""
        # Assuming targets contain [price, volume, volatility]
        price_loss = self.mse_loss(predictions['price'], targets[:, :, 0])
        volume_loss = self.mse_loss(predictions['volume'], targets[:, :, 1])
        volatility_loss = self.mse_loss(predictions['volatility'], targets[:, :, 2])
        
        # Weighted combination
        total_loss = (0.5 * price_loss + 
                     0.25 * volume_loss + 
                     0.25 * volatility_loss)
        
        return total_loss
    
    def _calculate_detailed_loss(self, predictions: Dict, targets: torch.Tensor) -> Dict[str, float]:
        """Calculate detailed losses for monitoring"""
        price_loss = self.mse_loss(predictions['price'], targets[:, :, 0]).item()
        volume_loss = self.mse_loss(predictions['volume'], targets[:, :, 1]).item()
        volatility_loss = self.mse_loss(predictions['volatility'], targets[:, :, 2]).item()
        
        total_loss = 0.5 * price_loss + 0.25 * volume_loss + 0.25 * volatility_loss
        
        return {
            'total': total_loss,
            'price': price_loss,
            'volume': volume_loss,
            'volatility': volatility_loss
        }

class TransformerInference:
    """
    Inference engine for transformer models
    """
    
    def __init__(self, model: MarketTransformer, config: ModelConfig):
        self.model = model
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        self.model.to(self.device)
        self.model.eval()
        
    async def predict(self, market_data: pd.DataFrame, symbol: str = "BTC/USDC") -> Dict[str, Any]:
        """
        Generate predictions for given market data
        
        Args:
            market_data: Recent market data (should contain at least sequence_length rows)
            symbol: Trading symbol for context
            
        Returns:
            Dictionary with predictions and confidence scores
        """
        try:
            # Prepare input data
            if len(market_data) < self.config.sequence_length:
                logger.warning(f"Insufficient data for prediction: {len(market_data)} < {self.config.sequence_length}")
                return self._empty_prediction()
            
            # Take last sequence_length rows
            input_data = market_data.tail(self.config.sequence_length)
            
            # Convert to tensor
            input_tensor = torch.FloatTensor(input_data.values).unsqueeze(0).to(self.device)
            asset_ids = torch.zeros(1, self.config.sequence_length, dtype=torch.long).to(self.device)
            
            with torch.no_grad():
                predictions, attention_weights = self.model(input_tensor, asset_ids)
            
            # Process predictions
            processed_predictions = self._process_predictions(predictions, attention_weights)
            
            return processed_predictions
            
        except Exception as e:
            logger.error(f"Error during transformer inference: {e}")
            return self._empty_prediction()
    
    def _process_predictions(self, predictions: Dict, attention_weights: torch.Tensor) -> Dict[str, Any]:
        """Process raw model predictions into interpretable format"""
        
        # Convert to numpy
        processed = {}
        for key, pred in predictions.items():
            if key == 'trend':
                # Convert trend logits to probabilities
                trend_probs = F.softmax(pred, dim=-1)
                processed[key] = {
                    'bullish_prob': trend_probs[0, 0].cpu().item(),
                    'bearish_prob': trend_probs[0, 1].cpu().item(),
                    'sideways_prob': trend_probs[0, 2].cpu().item()
                }
            else:
                processed[key] = pred.squeeze().cpu().numpy().tolist()
        
        # Add attention analysis
        attention_analysis = self._analyze_attention_weights(attention_weights)
        processed['attention_analysis'] = attention_analysis
        
        # Calculate overall confidence
        overall_confidence = predictions['confidence'].cpu().item()
        processed['overall_confidence'] = overall_confidence
        
        return processed
    
    def _analyze_attention_weights(self, attention_weights: torch.Tensor) -> Dict[str, Any]:
        """Analyze attention weights to understand model focus"""
        
        # Average attention across heads and batches
        avg_attention = attention_weights.mean(dim=1).squeeze().cpu().numpy()
        
        # Find most important timesteps
        importance_scores = avg_attention.mean(axis=0)
        top_timesteps = np.argsort(importance_scores)[-5:].tolist()
        
        return {
            'top_important_timesteps': top_timesteps,
            'attention_entropy': float(-np.sum(importance_scores * np.log(importance_scores + 1e-8))),
            'attention_focus': float(np.max(importance_scores))
        }
    
    def _empty_prediction(self) -> Dict[str, Any]:
        """Return empty prediction structure"""
        return {
            'price': [0.0] * self.config.prediction_horizon,
            'volatility': [0.0] * self.config.prediction_horizon,
            'volume': [0.0] * self.config.prediction_horizon,
            'trend': {'bullish_prob': 0.33, 'bearish_prob': 0.33, 'sideways_prob': 0.34},
            'overall_confidence': 0.0,
            'attention_analysis': {
                'top_important_timesteps': [],
                'attention_entropy': 0.0,
                'attention_focus': 0.0
            }
        }

# Factory functions for easy model creation
def create_market_transformer(config: ModelConfig = None) -> MarketTransformer:
    """Create a market transformer with default or custom configuration"""
    if config is None:
        config = ModelConfig()
    
    model = MarketTransformer(config)
    return model

def create_transformer_trainer(model: MarketTransformer, config: ModelConfig = None) -> TransformerTrainer:
    """Create a transformer trainer"""
    if config is None:
        config = ModelConfig()
    
    trainer = TransformerTrainer(model, config)
    return trainer
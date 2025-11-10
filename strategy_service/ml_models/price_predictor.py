"""
Price Prediction Model - BTCUSDC 1-Hour Ahead Predictions

This module implements a hybrid LSTM-Transformer model for predicting BTCUSDC prices
1 hour ahead. The model uses:
- Historical price data (OHLCV)
- Technical indicators (RSI, MACD, Bollinger Bands)
- Volume patterns
- Market sentiment

The predictions are used by trading strategies to enhance signal generation.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import numpy as np
import structlog

try:  # Optional dependency guard to support lightweight test environments
    import pandas as _pd
except ModuleNotFoundError:  # pragma: no cover - dependency resolution
    _pd = None

if TYPE_CHECKING:
    import pandas as pd  # type: ignore
elif _pd is None:
    class _PandasUnavailable:
        def __getattr__(self, name):  # pragma: no cover - simple guard
            raise RuntimeError(
                "pandas is required for strategy_service.ml_models.price_predictor. "
                "Install it via pip install -r strategy_service/requirements.txt before "
                "running price prediction workloads."
            )

    pd = _PandasUnavailable()
else:
    pd = _pd

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    structlog.get_logger().warning("PyTorch not available, using mock predictor")

logger = structlog.get_logger()


class PriceDataset(Dataset):
    """Dataset for price prediction training"""
    
    def __init__(self, sequences: np.ndarray, targets: np.ndarray):
        self.sequences = torch.FloatTensor(sequences)
        self.targets = torch.FloatTensor(targets)
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        return self.sequences[idx], self.targets[idx]


class LSTMTransformerPredictor(nn.Module):
    """
    Hybrid LSTM-Transformer model for price prediction
    
    Architecture:
    - LSTM layers to capture temporal dependencies
    - Multi-head attention for pattern recognition
    - Fully connected layers for prediction
    """
    
    def __init__(self, 
                 input_size: int = 20,  # OHLCV + indicators
                 hidden_size: int = 128,
                 num_layers: int = 2,
                 num_heads: int = 4,
                 dropout: float = 0.2):
        super(LSTMTransformerPredictor, self).__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        
        # LSTM layers for temporal processing
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True,
            bidirectional=True
        )
        
        # Transformer attention layer
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size * 2,  # bidirectional LSTM
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_size * 2, hidden_size)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(hidden_size, 64)
        self.fc3 = nn.Linear(64, 1)  # Predict price change %
        
        # Layer normalization
        self.layer_norm = nn.LayerNorm(hidden_size * 2)
    
    def forward(self, x):
        """
        Forward pass
        
        Args:
            x: Input tensor of shape (batch_size, sequence_length, input_size)
        
        Returns:
            Predicted price change percentage
        """
        # LSTM processing
        lstm_out, _ = self.lstm(x)  # (batch, seq, hidden*2)
        
        # Layer normalization
        lstm_out = self.layer_norm(lstm_out)
        
        # Self-attention
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        
        # Take the last time step
        last_hidden = attn_out[:, -1, :]  # (batch, hidden*2)
        
        # Fully connected layers
        out = self.fc1(last_hidden)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        out = self.relu(out)
        out = self.fc3(out)
        
        return out


class PricePredictor:
    """
    Price prediction service for BTCUSDC
    
    Features:
    - 1-hour ahead price predictions
    - Confidence intervals
    - Model retraining on new data
    - Performance tracking
    """
    
    def __init__(self, 
                 model_path: str = "/app/models/price_predictor.pt",
                 device: str = None):
        self.model_path = model_path
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Model configuration
        self.sequence_length = 60  # 60 hours of history
        self.input_features = 20   # OHLCV + 15 indicators
        self.prediction_horizon = 1  # 1 hour ahead
        
        # Model
        self.model = None
        self.scaler = None
        self.feature_names = [
            'open', 'high', 'low', 'close', 'volume',
            'rsi', 'macd', 'macd_signal', 'macd_hist',
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
            'sma_20', 'ema_20', 'atr',
            'volume_sma', 'price_change', 'volume_change', 'volatility'
        ]
        
        # Performance tracking
        self.predictions_made = 0
        self.mae_history = []
        self.mape_history = []
        
        # Initialize model
        if TORCH_AVAILABLE:
            self._initialize_model()
        else:
            logger.warning("PyTorch not available, predictions will be mocked")
    
    def _initialize_model(self):
        """Initialize or load the prediction model"""
        try:
            self.model = LSTMTransformerPredictor(
                input_size=self.input_features,
                hidden_size=128,
                num_layers=2,
                num_heads=4,
                dropout=0.2
            ).to(self.device)
            
            # Try to load existing model
            if os.path.exists(self.model_path):
                checkpoint = torch.load(self.model_path, map_location=self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self.scaler = checkpoint.get('scaler')
                logger.info(f"Loaded price prediction model from {self.model_path}")
            else:
                logger.info("No existing model found, will need training")
                # Initialize scaler
                from sklearn.preprocessing import StandardScaler
                self.scaler = StandardScaler()
            
            self.model.eval()
            
        except Exception as e:
            logger.error(f"Error initializing prediction model: {e}")
            self.model = None
    
    async def predict(self, 
                      historical_data: pd.DataFrame,
                      return_confidence: bool = True) -> Dict:
        """
        Predict BTCUSDC price 1 hour ahead
        
        Args:
            historical_data: DataFrame with columns [timestamp, open, high, low, close, volume]
                            Must have at least sequence_length rows
            return_confidence: Whether to return confidence intervals
        
        Returns:
            Dictionary with:
                - predicted_price: Predicted price
                - predicted_change_pct: Predicted percentage change
                - confidence_lower: Lower confidence bound (if requested)
                - confidence_upper: Upper confidence bound (if requested)
                - current_price: Current price
                - prediction_timestamp: When prediction was made
        """
        try:
            if not TORCH_AVAILABLE or self.model is None:
                # Mock prediction for development
                return self._mock_prediction(historical_data)
            
            # Prepare features
            features = self._prepare_features(historical_data)
            
            if len(features) < self.sequence_length:
                logger.warning(f"Insufficient data for prediction: {len(features)} < {self.sequence_length}")
                return self._mock_prediction(historical_data)
            
            # Get last sequence
            sequence = features[-self.sequence_length:]
            
            # Normalize
            if self.scaler is not None:
                sequence = self.scaler.transform(sequence)
            
            # Convert to tensor
            x = torch.FloatTensor(sequence).unsqueeze(0).to(self.device)  # (1, seq_len, features)
            
            # Predict
            self.model.eval()
            with torch.no_grad():
                prediction = self.model(x).item()  # Predicted % change
            
            # Calculate predicted price
            current_price = historical_data['close'].iloc[-1]
            predicted_price = current_price * (1 + prediction / 100)
            
            result = {
                'predicted_price': predicted_price,
                'predicted_change_pct': prediction,
                'current_price': current_price,
                'prediction_timestamp': datetime.now(timezone.utc),
                'model_version': 'lstm_transformer_v1',
                'confidence_score': self._calculate_confidence()
            }
            
            # Add confidence intervals if requested
            if return_confidence:
                std = np.std(self.mae_history[-100:]) if len(self.mae_history) > 10 else 0.02
                result['confidence_lower'] = predicted_price - (2 * std * current_price)
                result['confidence_upper'] = predicted_price + (2 * std * current_price)
            
            self.predictions_made += 1
            
            logger.info(
                "Price prediction made",
                current=current_price,
                predicted=predicted_price,
                change_pct=prediction,
                confidence=result['confidence_score']
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error making prediction: {e}")
            return self._mock_prediction(historical_data)
    
    def _prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Prepare feature matrix from historical data
        
        Calculates technical indicators and returns feature matrix
        """
        df = df.copy()
        
        # Calculate technical indicators
        # RSI
        df['rsi'] = self._calculate_rsi(df['close'])
        
        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])
        
        # Bollinger Bands
        df['bb_upper'], df['bb_middle'], df['bb_lower'], df['bb_width'] = self._calculate_bollinger_bands(df['close'])
        
        # Moving averages
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # ATR
        df['atr'] = self._calculate_atr(df)
        
        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        
        # Price changes
        df['price_change'] = df['close'].pct_change()
        df['volume_change'] = df['volume'].pct_change()
        
        # Volatility
        df['volatility'] = df['close'].rolling(window=20).std() / df['close'].rolling(window=20).mean()
        
        # Fill NaN values
        df = df.fillna(method='bfill').fillna(0)
        
        # Extract feature columns
        features = df[self.feature_names].values
        
        return features
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD indicator"""
        exp1 = prices.ewm(span=12, adjust=False).mean()
        exp2 = prices.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        return macd, signal, hist
    
    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (2 * std)
        lower = sma - (2 * std)
        width = (upper - lower) / sma
        return upper, sma, lower, width
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def _calculate_confidence(self) -> float:
        """Calculate prediction confidence based on recent performance"""
        if len(self.mape_history) < 10:
            return 0.5  # Low confidence initially
        
        # Recent MAPE (lower is better)
        recent_mape = np.mean(self.mape_history[-50:])
        
        # Convert MAPE to confidence score (0-1)
        # MAPE < 2% = high confidence (0.9+)
        # MAPE > 10% = low confidence (0.1-)
        if recent_mape < 2:
            confidence = 0.9
        elif recent_mape < 5:
            confidence = 0.7
        elif recent_mape < 10:
            confidence = 0.5
        else:
            confidence = 0.3
        
        return confidence
    
    def _mock_prediction(self, historical_data: pd.DataFrame) -> Dict:
        """Mock prediction for development/testing"""
        current_price = historical_data['close'].iloc[-1]
        
        # Simple trend-following mock: slight continuation of recent trend
        recent_change = historical_data['close'].pct_change().iloc[-5:].mean()
        predicted_change = recent_change * 0.5  # Dampen the trend
        predicted_price = current_price * (1 + predicted_change)
        
        return {
            'predicted_price': predicted_price,
            'predicted_change_pct': predicted_change * 100,
            'current_price': current_price,
            'prediction_timestamp': datetime.now(timezone.utc),
            'model_version': 'mock',
            'confidence_score': 0.5,
            'confidence_lower': predicted_price * 0.98,
            'confidence_upper': predicted_price * 1.02
        }
    
    async def train(self, 
                    historical_data: pd.DataFrame,
                    epochs: int = 50,
                    batch_size: int = 32,
                    learning_rate: float = 0.001) -> Dict:
        """
        Train the prediction model on historical data
        
        Args:
            historical_data: DataFrame with OHLCV data
            epochs: Number of training epochs
            batch_size: Training batch size
            learning_rate: Learning rate for optimizer
        
        Returns:
            Training metrics dictionary
        """
        if not TORCH_AVAILABLE or self.model is None:
            logger.warning("Training not available without PyTorch")
            return {'status': 'skipped', 'reason': 'pytorch_unavailable'}
        
        try:
            logger.info(f"Starting model training with {len(historical_data)} samples")
            
            # Prepare sequences and targets
            sequences, targets = self._prepare_training_data(historical_data)
            
            if len(sequences) < 100:
                logger.warning(f"Insufficient training data: {len(sequences)} sequences")
                return {'status': 'failed', 'reason': 'insufficient_data'}
            
            # Fit scaler
            all_features = sequences.reshape(-1, self.input_features)
            self.scaler.fit(all_features)
            sequences = self.scaler.transform(all_features).reshape(sequences.shape)
            
            # Create dataset and dataloader
            dataset = PriceDataset(sequences, targets)
            train_size = int(0.8 * len(dataset))
            val_size = len(dataset) - train_size
            train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
            
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=batch_size)
            
            # Training setup
            criterion = nn.MSELoss()
            optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
            scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=5)
            
            best_val_loss = float('inf')
            training_history = {'train_loss': [], 'val_loss': []}
            
            # Training loop
            self.model.train()
            for epoch in range(epochs):
                train_loss = 0.0
                for sequences_batch, targets_batch in train_loader:
                    sequences_batch = sequences_batch.to(self.device)
                    targets_batch = targets_batch.to(self.device)
                    
                    optimizer.zero_grad()
                    outputs = self.model(sequences_batch)
                    loss = criterion(outputs.squeeze(), targets_batch)
                    loss.backward()
                    optimizer.step()
                    
                    train_loss += loss.item()
                
                train_loss /= len(train_loader)
                
                # Validation
                val_loss = 0.0
                self.model.eval()
                with torch.no_grad():
                    for sequences_batch, targets_batch in val_loader:
                        sequences_batch = sequences_batch.to(self.device)
                        targets_batch = targets_batch.to(self.device)
                        outputs = self.model(sequences_batch)
                        loss = criterion(outputs.squeeze(), targets_batch)
                        val_loss += loss.item()
                
                val_loss /= len(val_loader)
                self.model.train()
                
                training_history['train_loss'].append(train_loss)
                training_history['val_loss'].append(val_loss)
                
                scheduler.step(val_loss)
                
                if (epoch + 1) % 10 == 0:
                    logger.info(f"Epoch {epoch+1}/{epochs} - Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}")
                
                # Save best model
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    self._save_model()
            
            logger.info(f"Training completed - Best Val Loss: {best_val_loss:.6f}")
            
            return {
                'status': 'completed',
                'epochs': epochs,
                'best_val_loss': best_val_loss,
                'final_train_loss': training_history['train_loss'][-1],
                'training_samples': train_size,
                'validation_samples': val_size
            }
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _prepare_training_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences and targets for training
        
        Returns:
            sequences: (num_samples, sequence_length, input_features)
            targets: (num_samples,) - % change after prediction_horizon
        """
        features = self._prepare_features(df)
        
        sequences = []
        targets = []
        
        for i in range(len(features) - self.sequence_length - self.prediction_horizon):
            seq = features[i:i + self.sequence_length]
            
            # Target is the % price change after prediction_horizon
            current_price = df['close'].iloc[i + self.sequence_length - 1]
            future_price = df['close'].iloc[i + self.sequence_length + self.prediction_horizon - 1]
            target = ((future_price - current_price) / current_price) * 100
            
            sequences.append(seq)
            targets.append(target)
        
        return np.array(sequences), np.array(targets)
    
    def _save_model(self):
        """Save model checkpoint"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            torch.save({
                'model_state_dict': self.model.state_dict(),
                'scaler': self.scaler,
                'config': {
                    'input_features': self.input_features,
                    'sequence_length': self.sequence_length,
                    'prediction_horizon': self.prediction_horizon
                }
            }, self.model_path)
            logger.info(f"Model saved to {self.model_path}")
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    async def update_performance(self, predicted_price: float, actual_price: float):
        """Update performance metrics with actual results"""
        error = abs(predicted_price - actual_price)
        mae = error
        mape = (error / actual_price) * 100
        
        self.mae_history.append(mae)
        self.mape_history.append(mape)
        
        # Keep last 1000 predictions
        if len(self.mae_history) > 1000:
            self.mae_history = self.mae_history[-1000:]
            self.mape_history = self.mape_history[-1000:]
        
        logger.info(f"Prediction performance updated - MAE: {mae:.2f}, MAPE: {mape:.2f}%")


class BTCUSDCPredictor(PricePredictor):
    """Specialized predictor for BTCUSDC pair"""
    
    def __init__(self):
        super().__init__(model_path="/app/models/btcusdc_predictor.pt")
        logger.info("BTCUSDC Price Predictor initialized")

#!/bin/bash

# Install ML Dependencies for Automatic Strategy Pipeline
# This script installs all required packages for:
# - Price prediction (LSTM/Transformer)
# - Strategy learning (Genetic Algorithm + RL)
# - Backtesting automation

set -e

echo "=================================================="
echo "Installing ML Dependencies for Strategy Service"
echo "=================================================="

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

echo ""
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel

echo ""
echo "Installing PyTorch (CPU version for local execution)..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

echo ""
echo "Installing core ML libraries..."
pip install numpy pandas scikit-learn scipy statsmodels

echo ""
echo "Installing deep learning libraries..."
pip install tensorflow keras transformers

echo ""
echo "Installing reinforcement learning libraries..."
pip install gymnasium stable-baselines3

echo ""
echo "Installing technical analysis libraries..."
pip install ta yfinance ccxt

echo ""
echo "Installing visualization libraries..."
pip install matplotlib seaborn plotly

echo ""
echo "Installing optimization libraries..."
pip install optuna

echo ""
echo "Installing high-performance computing libraries..."
pip install numba joblib dask

echo ""
echo "Installing model deployment libraries..."
pip install onnx onnxruntime mlflow

echo ""
echo "Installing time series libraries..."
pip install prophet

echo ""
echo "Installing remaining requirements..."
pip install -r requirements.txt

echo ""
echo "=================================================="
echo "Installation Complete!"
echo "=================================================="
echo ""
echo "Installed components:"
echo "  ✓ PyTorch (price prediction models)"
echo "  ✓ TensorFlow/Keras (alternative models)"
echo "  ✓ Scikit-learn (genetic algorithm, statistical analysis)"
echo "  ✓ Gymnasium/Stable-Baselines3 (reinforcement learning)"
echo "  ✓ Technical analysis libraries (TA-Lib, TA, CCXT)"
echo "  ✓ Optimization libraries (Optuna)"
echo "  ✓ Visualization (Matplotlib, Seaborn, Plotly)"
echo ""
echo "Next steps:"
echo "  1. Run: python3 -m pytest test_automatic_pipeline.py"
echo "  2. Start service: python3 main.py"
echo "  3. Monitor logs: tail -f /tmp/strategy_service.log"
echo ""

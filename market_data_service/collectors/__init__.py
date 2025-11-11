"""
Collectors Package

Data collectors for market data service:
- On-chain data collectors (Moralis, Glassnode, Nansen)
- Social sentiment collectors (Twitter, Reddit, LunarCrush)
- Institutional flow collectors (Kaiko, CoinMetrics)
"""

from .onchain_collector import OnChainCollector

__all__ = ["OnChainCollector"]

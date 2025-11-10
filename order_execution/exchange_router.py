"""
Exchange Router

Smart order routing across multiple exchanges:
- Best price routing
- Liquidity-based routing
- Fee optimization
- Latency consideration
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Order routing strategies"""
    BEST_PRICE = "best_price"
    BEST_LIQUIDITY = "best_liquidity"
    LOWEST_FEE = "lowest_fee"
    BALANCED = "balanced"


@dataclass
class ExchangeQuote:
    """Quote from an exchange"""
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    fee_bps: float
    latency_ms: float
    timestamp: datetime


@dataclass
class RoutingDecision:
    """Routing decision for an order"""
    exchange: str
    symbol: str
    expected_price: float
    expected_fee_bps: float
    liquidity_score: float
    routing_reason: str
    timestamp: datetime


class ExchangeSelector:
    """Selects best exchange for order execution"""
    
    def __init__(self, strategy: RoutingStrategy = RoutingStrategy.BALANCED):
        self.strategy = strategy
        self.exchange_quotes: Dict[str, Dict[str, ExchangeQuote]] = {}
        logger.info(f"ExchangeSelector initialized with {strategy.value} strategy")
    
    def update_quote(self, quote: ExchangeQuote):
        """Update quote from exchange"""
        if quote.exchange not in self.exchange_quotes:
            self.exchange_quotes[quote.exchange] = {}
        
        self.exchange_quotes[quote.exchange][quote.symbol] = quote
    
    def select_exchange(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        quantity: float,
    ) -> Optional[RoutingDecision]:
        """Select best exchange for order"""
        
        # Get all available quotes
        available_quotes = []
        for exchange, quotes in self.exchange_quotes.items():
            if symbol in quotes:
                available_quotes.append(quotes[symbol])
        
        if not available_quotes:
            logger.warning(f"No quotes available for {symbol}")
            return None
        
        # Apply routing strategy
        if self.strategy == RoutingStrategy.BEST_PRICE:
            selected = self._select_best_price(available_quotes, side)
        elif self.strategy == RoutingStrategy.BEST_LIQUIDITY:
            selected = self._select_best_liquidity(available_quotes, side, quantity)
        elif self.strategy == RoutingStrategy.LOWEST_FEE:
            selected = self._select_lowest_fee(available_quotes)
        else:  # BALANCED
            selected = self._select_balanced(available_quotes, side, quantity)
        
        if not selected:
            return None
        
        # Create decision
        price = selected.ask if side == "BUY" else selected.bid
        size = selected.ask_size if side == "BUY" else selected.bid_size
        
        decision = RoutingDecision(
            exchange=selected.exchange,
            symbol=symbol,
            expected_price=price,
            expected_fee_bps=selected.fee_bps,
            liquidity_score=min(100.0, (size / quantity) * 100),
            routing_reason=f"{self.strategy.value} strategy",
            timestamp=datetime.utcnow(),
        )
        
        logger.info(f"Routed {symbol} to {selected.exchange}: {decision.routing_reason}")
        return decision
    
    def _select_best_price(
        self,
        quotes: List[ExchangeQuote],
        side: str,
    ) -> Optional[ExchangeQuote]:
        """Select exchange with best price"""
        if side == "BUY":
            # Lowest ask
            return min(quotes, key=lambda q: q.ask)
        else:
            # Highest bid
            return max(quotes, key=lambda q: q.bid)
    
    def _select_best_liquidity(
        self,
        quotes: List[ExchangeQuote],
        side: str,
        quantity: float,
    ) -> Optional[ExchangeQuote]:
        """Select exchange with best liquidity"""
        if side == "BUY":
            # Most ask size
            valid_quotes = [q for q in quotes if q.ask_size >= quantity]
            if not valid_quotes:
                valid_quotes = quotes  # Fallback
            return max(valid_quotes, key=lambda q: q.ask_size)
        else:
            # Most bid size
            valid_quotes = [q for q in quotes if q.bid_size >= quantity]
            if not valid_quotes:
                valid_quotes = quotes
            return max(valid_quotes, key=lambda q: q.bid_size)
    
    def _select_lowest_fee(
        self,
        quotes: List[ExchangeQuote],
    ) -> Optional[ExchangeQuote]:
        """Select exchange with lowest fees"""
        return min(quotes, key=lambda q: q.fee_bps)
    
    def _select_balanced(
        self,
        quotes: List[ExchangeQuote],
        side: str,
        quantity: float,
    ) -> Optional[ExchangeQuote]:
        """Balanced selection considering price, liquidity, fees"""
        
        scores = []
        for quote in quotes:
            price = quote.ask if side == "BUY" else quote.bid
            size = quote.ask_size if side == "BUY" else quote.bid_size
            
            # Normalize metrics (0-100)
            if side == "BUY":
                price_score = 100.0 - ((price - min(q.ask for q in quotes)) /
                                      (max(q.ask for q in quotes) - min(q.ask for q in quotes) + 1e-8)) * 100
            else:
                price_score = ((price - min(q.bid for q in quotes)) /
                              (max(q.bid for q in quotes) - min(q.bid for q in quotes) + 1e-8)) * 100
            
            liquidity_score = min(100.0, (size / quantity) * 100)
            
            fee_score = 100.0 - ((quote.fee_bps - min(q.fee_bps for q in quotes)) /
                                (max(q.fee_bps for q in quotes) - min(q.fee_bps for q in quotes) + 1e-8)) * 100
            
            # Weighted average (price 50%, liquidity 30%, fees 20%)
            total_score = 0.5 * price_score + 0.3 * liquidity_score + 0.2 * fee_score
            
            scores.append((total_score, quote))
        
        # Select highest score
        best = max(scores, key=lambda x: x[0])
        return best[1]


class SmartOrderRouter:
    """
    Smart order router with split routing capability.
    
    Can split orders across multiple exchanges for best execution.
    """
    
    def __init__(self):
        self.selector = ExchangeSelector(RoutingStrategy.BALANCED)
        logger.info("SmartOrderRouter initialized")
    
    def route_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        allow_splits: bool = True,
    ) -> List[RoutingDecision]:
        """Route order, possibly split across exchanges"""
        
        if not allow_splits:
            # Single exchange routing
            decision = self.selector.select_exchange(symbol, side, quantity)
            return [decision] if decision else []
        
        # Multi-exchange routing
        return self._route_with_splits(symbol, side, quantity)
    
    def _route_with_splits(
        self,
        symbol: str,
        side: str,
        total_quantity: float,
    ) -> List[RoutingDecision]:
        """Split order across multiple exchanges"""
        
        # Get all quotes
        available_quotes = []
        for exchange, quotes in self.selector.exchange_quotes.items():
            if symbol in quotes:
                available_quotes.append(quotes[symbol])
        
        if not available_quotes:
            return []
        
        # Sort by price (best first)
        if side == "BUY":
            available_quotes.sort(key=lambda q: q.ask)
        else:
            available_quotes.sort(key=lambda q: q.bid, reverse=True)
        
        # Allocate quantity across exchanges
        decisions = []
        remaining = total_quantity
        
        for quote in available_quotes:
            if remaining <= 0:
                break
            
            available_size = quote.ask_size if side == "BUY" else quote.bid_size
            allocated = min(remaining, available_size)
            
            if allocated > 0:
                price = quote.ask if side == "BUY" else quote.bid
                
                decision = RoutingDecision(
                    exchange=quote.exchange,
                    symbol=symbol,
                    expected_price=price,
                    expected_fee_bps=quote.fee_bps,
                    liquidity_score=min(100.0, (allocated / total_quantity) * 100),
                    routing_reason=f"split routing ({allocated}/{total_quantity})",
                    timestamp=datetime.utcnow(),
                )
                decisions.append(decision)
                remaining -= allocated
        
        logger.info(f"Split {symbol} order across {len(decisions)} exchanges")
        return decisions
    
    def update_quote(self, quote: ExchangeQuote):
        """Update quote from exchange"""
        self.selector.update_quote(quote)

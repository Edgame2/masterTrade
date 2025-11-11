"""
Moralis On-Chain Data Collector

Collects whale transactions and DEX trade data from Moralis API:
- Whale wallet tracking (>1000 BTC/ETH)
- Large transaction detection
- DEX trade monitoring
- Wallet activity analysis

API Documentation: https://docs.moralis.io/web3-data-api/evm/reference
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import structlog
import aio_pika

from database import Database
from collectors.onchain_collector import OnChainCollector, CollectorStatus

# Import message schemas
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from shared.message_schemas import (
    WhaleAlertMessage,
    AlertType,
    serialize_message,
    RoutingKeys
)

logger = structlog.get_logger()


class MoralisCollector(OnChainCollector):
    """Collector for Moralis on-chain data"""
    
    # Whale thresholds
    WHALE_THRESHOLD_BTC = 1000  # BTC
    WHALE_THRESHOLD_ETH = 10000  # ETH
    WHALE_THRESHOLD_USD = 1_000_000  # USD
    
    # Token addresses for major cryptocurrencies
    TOKEN_ADDRESSES = {
        "BTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",  # WBTC on Ethereum
        "ETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH on Ethereum
        "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "BNB": "0xb8c77482e0a97f6d58a58c3b8c4d6d63c9e8f763",
    }
    
    # Watched whale wallets (example addresses)
    WATCHED_WALLETS = [
        "0x00000000219ab540356cbb839cbe05303d7705fa",  # Ethereum 2.0 deposit contract
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH contract
        # Add more whale addresses as identified
    ]
    
    def __init__(
        self,
        database: Database,
        api_key: str,
        rate_limit: float = 3.0,  # Moralis free tier: 3 req/s
        timeout: int = 30,
        rabbitmq_channel: Optional[aio_pika.Channel] = None
    ):
        """
        Initialize Moralis collector
        
        Args:
            database: Database instance
            api_key: Moralis API key
            rate_limit: Requests per second (default 3 for free tier)
            timeout: Request timeout in seconds
            rabbitmq_channel: Optional RabbitMQ channel for publishing alerts
        """
        super().__init__(
            database=database,
            api_key=api_key,
            api_url="https://deep-index.moralis.io/api/v2.2",
            collector_name="moralis",
            rate_limit=rate_limit,
            timeout=timeout
        )
        
        self.watched_wallets = set(self.WATCHED_WALLETS)
        self.rabbitmq_channel = rabbitmq_channel
        
    async def collect(self, symbols: List[str] = None, hours: int = 24) -> bool:
        """
        Collect on-chain data from Moralis
        
        Args:
            symbols: List of symbols to collect (default: all major tokens)
            hours: Hours of historical data to collect
            
        Returns:
            True if collection successful, False otherwise
        """
        if symbols is None:
            symbols = ["BTC", "ETH", "USDT", "USDC"]
            
        try:
            logger.info(
                "Starting Moralis data collection",
                symbols=symbols,
                hours=hours
            )
            
            collection_start = datetime.now(timezone.utc)
            
            # Collect data for each symbol
            for symbol in symbols:
                if symbol not in self.TOKEN_ADDRESSES:
                    logger.warning(f"Unknown token symbol: {symbol}")
                    continue
                    
                token_address = self.TOKEN_ADDRESSES[symbol]
                
                # Collect token transfers
                await self._collect_token_transfers(symbol, token_address, hours)
                
                # Collect whale wallet activity
                await self._collect_whale_activity(symbol, token_address, hours)
                
                # Small delay between symbols
                await asyncio.sleep(0.5)
                
            # Update collection stats
            self.stats["last_collection_time"] = collection_start.isoformat()
            
            # Log health status
            await self._log_health(CollectorStatus.HEALTHY, "Collection completed successfully")
            
            logger.info(
                "Moralis data collection completed",
                symbols=symbols,
                duration_seconds=(datetime.now(timezone.utc) - collection_start).total_seconds()
            )
            
            return True
            
        except Exception as e:
            logger.error("Moralis collection failed", error=str(e))
            await self._log_health(CollectorStatus.FAILED, str(e))
            return False
            
    async def _collect_token_transfers(
        self,
        symbol: str,
        token_address: str,
        hours: int
    ) -> int:
        """
        Collect token transfers for a specific token
        
        Args:
            symbol: Token symbol
            token_address: Token contract address
            hours: Hours of historical data
            
        Returns:
            Number of whale transactions detected
        """
        try:
            # Calculate from_date
            from_date = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Get token transfers
            endpoint = f"/erc20/{token_address}/transfers"
            params = {
                "chain": "eth",
                "from_date": from_date.isoformat(),
                "limit": 100
            }
            
            response = await self._make_request(endpoint, params=params)
            
            if not response or "result" not in response:
                logger.warning(f"No transfer data for {symbol}")
                return 0
                
            transfers = response["result"]
            whale_count = 0
            
            # Process transfers
            for transfer in transfers:
                # Check if transfer is a whale transaction
                if await self._is_whale_transaction(transfer, symbol):
                    whale_count += 1
                    
                    # Store whale transaction
                    await self._store_whale_transaction(transfer, symbol)
                    
            logger.info(
                f"Collected {symbol} transfers",
                total_transfers=len(transfers),
                whale_transactions=whale_count
            )
            
            self.stats["data_points_collected"] += len(transfers)
            
            return whale_count
            
        except Exception as e:
            logger.error(f"Failed to collect {symbol} transfers", error=str(e))
            return 0
            
    async def _collect_whale_activity(
        self,
        symbol: str,
        token_address: str,
        hours: int
    ) -> int:
        """
        Collect activity from known whale wallets
        
        Args:
            symbol: Token symbol
            token_address: Token contract address
            hours: Hours of historical data
            
        Returns:
            Number of whale activities detected
        """
        try:
            activity_count = 0
            
            for wallet_address in self.watched_wallets:
                # Get wallet token transfers
                endpoint = f"/{wallet_address}/erc20/transfers"
                params = {
                    "chain": "eth",
                    "limit": 50
                }
                
                response = await self._make_request(endpoint, params=params)
                
                if not response or "result" not in response:
                    continue
                    
                transfers = response["result"]
                
                # Filter for our token
                token_transfers = [
                    t for t in transfers
                    if t.get("address", "").lower() == token_address.lower()
                ]
                
                # Store whale activities
                for transfer in token_transfers:
                    await self._store_whale_transaction(transfer, symbol, whale_address=wallet_address)
                    activity_count += 1
                    
                # Small delay between wallet queries
                await asyncio.sleep(0.2)
                
            logger.info(
                f"Collected whale activity for {symbol}",
                whale_wallets=len(self.watched_wallets),
                activities=activity_count
            )
            
            return activity_count
            
        except Exception as e:
            logger.error(f"Failed to collect whale activity for {symbol}", error=str(e))
            return 0
            
    async def _is_whale_transaction(self, transfer: Dict, symbol: str) -> bool:
        """
        Determine if a transfer is a whale transaction
        
        Args:
            transfer: Transfer data from Moralis
            symbol: Token symbol
            
        Returns:
            True if whale transaction, False otherwise
        """
        try:
            # Get transfer value
            value_str = transfer.get("value", "0")
            decimals = int(transfer.get("token_decimals", 18))
            
            # Convert to float
            value = float(value_str) / (10 ** decimals)
            
            # Check against thresholds
            if symbol == "BTC":
                return value >= self.WHALE_THRESHOLD_BTC
            elif symbol == "ETH":
                return value >= self.WHALE_THRESHOLD_ETH
            elif symbol in ["USDT", "USDC"]:
                return value >= self.WHALE_THRESHOLD_USD
                
            return False
            
        except Exception as e:
            logger.error("Error checking whale transaction", error=str(e))
            return False
            
    async def _store_whale_transaction(
        self,
        transfer: Dict,
        symbol: str,
        whale_address: Optional[str] = None
    ):
        """
        Store whale transaction to database
        
        Args:
            transfer: Transfer data from Moralis
            symbol: Token symbol
            whale_address: Optional known whale address
        """
        try:
            # Parse transfer data
            value_str = transfer.get("value", "0")
            decimals = int(transfer.get("token_decimals", 18))
            value = float(value_str) / (10 ** decimals)
            
            tx_data = {
                "tx_hash": transfer.get("transaction_hash"),
                "symbol": symbol,
                "from_address": transfer.get("from_address"),
                "to_address": transfer.get("to_address"),
                "amount": value,
                "timestamp": transfer.get("block_timestamp"),
                "block_number": transfer.get("block_number"),
                "token_address": transfer.get("address"),
                "is_whale_wallet": whale_address is not None,
                "whale_address": whale_address,
                "source": "moralis",
                "metadata": {
                    "gas": transfer.get("gas"),
                    "gas_price": transfer.get("gas_price"),
                }
            }
            
            # Store in database
            success = await self.database.store_whale_transaction(tx_data)
            
            if success:
                logger.debug(
                    "Stored whale transaction",
                    symbol=symbol,
                    amount=value,
                    tx_hash=tx_data["tx_hash"]
                )
                
                # Publish to RabbitMQ if channel available
                if self.rabbitmq_channel:
                    await self._publish_whale_alert(tx_data, value)
            else:
                logger.warning(
                    "Failed to store whale transaction",
                    symbol=symbol,
                    tx_hash=tx_data["tx_hash"]
                )
                
        except Exception as e:
            logger.error("Error storing whale transaction", error=str(e))
            
    async def get_wallet_balance(self, wallet_address: str, token_address: str) -> Optional[float]:
        """
        Get current token balance for a wallet
        
        Args:
            wallet_address: Wallet address
            token_address: Token contract address
            
        Returns:
            Token balance or None if failed
        """
        try:
            endpoint = f"/{wallet_address}/erc20"
            params = {
                "chain": "eth",
                "token_addresses": [token_address]
            }
            
            response = await self._make_request(endpoint, params=params)
            
            if not response:
                return None
                
            # Parse balance
            for token in response:
                if token.get("token_address", "").lower() == token_address.lower():
                    balance_str = token.get("balance", "0")
                    decimals = int(token.get("decimals", 18))
                    return float(balance_str) / (10 ** decimals)
                    
            return None
            
        except Exception as e:
            logger.error("Error getting wallet balance", error=str(e))
            return None
            
    async def add_watched_wallet(self, wallet_address: str):
        """
        Add a wallet address to the watch list
        
        Args:
            wallet_address: Wallet address to watch
        """
        self.watched_wallets.add(wallet_address.lower())
        logger.info(f"Added wallet to watch list: {wallet_address}")
        
    async def remove_watched_wallet(self, wallet_address: str):
        """
        Remove a wallet address from the watch list
        
        Args:
            wallet_address: Wallet address to remove
        """
        self.watched_wallets.discard(wallet_address.lower())
        logger.info(f"Removed wallet from watch list: {wallet_address}")
    
    async def _publish_whale_alert(self, tx_data: Dict, amount: float):
        """
        Publish whale alert to RabbitMQ
        
        Args:
            tx_data: Transaction data dictionary
            amount: Transaction amount in native currency
        """
        try:
            # Estimate USD value (simplified - would need price feed in production)
            # For now, use rough estimates
            symbol = tx_data.get("symbol", "")
            if symbol == "BTC":
                amount_usd = amount * 50000  # Rough BTC price
            elif symbol == "ETH":
                amount_usd = amount * 3000   # Rough ETH price
            elif symbol in ["USDT", "USDC"]:
                amount_usd = amount
            else:
                amount_usd = amount * 1000  # Default multiplier
            
            # Determine alert type
            from_entity = self._identify_entity(tx_data.get("from_address", ""))
            to_entity = self._identify_entity(tx_data.get("to_address", ""))
            
            if "exchange" in from_entity.lower():
                alert_type = AlertType.EXCHANGE_OUTFLOW
            elif "exchange" in to_entity.lower():
                alert_type = AlertType.EXCHANGE_INFLOW
            elif tx_data.get("is_whale_wallet"):
                alert_type = AlertType.WHALE_ACCUMULATION if amount > 0 else AlertType.WHALE_DISTRIBUTION
            else:
                alert_type = AlertType.LARGE_TRANSFER
            
            # Calculate significance score (0-1)
            if amount_usd >= 10_000_000:
                significance = 1.0
            elif amount_usd >= 5_000_000:
                significance = 0.85
            elif amount_usd >= 1_000_000:
                significance = 0.7
            else:
                significance = 0.5
            
            # Create WhaleAlertMessage
            alert = WhaleAlertMessage(
                alert_id=f"moralis_{tx_data.get('tx_hash', '')}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                alert_type=alert_type,
                symbol=symbol,
                amount=amount,
                amount_usd=amount_usd,
                from_address=tx_data.get("from_address"),
                to_address=tx_data.get("to_address"),
                from_entity=from_entity,
                to_entity=to_entity,
                transaction_hash=tx_data.get("tx_hash"),
                blockchain="ethereum",
                significance_score=significance,
                market_impact_estimate=self._estimate_market_impact(amount_usd),
                timestamp=datetime.fromisoformat(tx_data.get("timestamp", "").replace("Z", "+00:00")) if tx_data.get("timestamp") else datetime.utcnow(),
                metadata=tx_data.get("metadata", {})
            )
            
            # Publish to RabbitMQ
            message = aio_pika.Message(
                body=serialize_message(alert).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            routing_key = (
                RoutingKeys.WHALE_ALERT_HIGH_PRIORITY 
                if amount_usd > 10_000_000 
                else RoutingKeys.WHALE_ALERT
            )
            
            await self.rabbitmq_channel.default_exchange.publish(
                message,
                routing_key=routing_key
            )
            
            logger.info(
                "Published whale alert",
                symbol=symbol,
                amount_usd=f"${amount_usd:,.0f}",
                alert_type=alert_type.value,
                significance=significance
            )
            
        except Exception as e:
            logger.error("Error publishing whale alert", error=str(e))
    
    def _identify_entity(self, address: str) -> str:
        """
        Identify entity from wallet address
        
        Args:
            address: Wallet address
            
        Returns:
            Entity name or "Unknown Wallet"
        """
        if not address:
            return "Unknown"
        
        address_lower = address.lower()
        
        # Known exchange addresses (simplified - would use comprehensive database in production)
        exchanges = {
            "0x00000000219ab540356cbb839cbe05303d7705fa": "Ethereum 2.0 Deposit",
            "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
            "0xd551234ae421e3bcba99a0da6d736074f22192ff": "Binance",
            "0x564286362092d8e7936f0549571a803b203aaced": "Binance",
            "0x0681d8db095565fe8a346fa0277bffde9c0edbbf": "Binance",
            "0xfe9e8709d3215310075d67e3ed32a380ccf451c8": "Coinbase",
            "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
            "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
            "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Coinbase",
        }
        
        if address_lower in exchanges:
            return exchanges[address_lower]
        
        # Check if it's a contract
        if address_lower.startswith("0xc0"):
            return "Smart Contract"
        
        return "Unknown Wallet"
    
    def _estimate_market_impact(self, amount_usd: float) -> float:
        """
        Estimate market impact percentage
        
        Args:
            amount_usd: Transaction amount in USD
            
        Returns:
            Estimated price impact percentage
        """
        # Simplified model - would use order book data in production
        if amount_usd >= 50_000_000:
            return -2.0  # -2% impact
        elif amount_usd >= 10_000_000:
            return -0.5  # -0.5% impact
        elif amount_usd >= 5_000_000:
            return -0.2  # -0.2% impact
        elif amount_usd >= 1_000_000:
            return -0.1  # -0.1% impact
        else:
            return -0.05  # Minimal impact
        
    async def get_watched_wallets(self) -> List[str]:
        """Get list of watched wallet addresses"""
        return list(self.watched_wallets)

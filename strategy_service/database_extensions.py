"""
Database extension methods for Strategy Review System

This module extends the existing Database class with methods specific to
strategy review functionality.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import structlog

logger = structlog.get_logger()

class StrategyReviewDatabaseMixin:
    """
    Mixin class to add strategy review database methods
    
    This should be mixed in with the existing Database class
    """
    
    async def get_active_strategies(self) -> List[Dict[str, Any]]:
        """Get all active strategies"""
        try:
            container = self.db.get_container_client('strategies')
            
            query = """
            SELECT * FROM c 
            WHERE c.status = 'active' 
            AND c.enabled = true
            """
            
            strategies = []
            async for item in container.query_items(query, enable_cross_partition_query=True):
                strategies.append(item)
            
            return strategies
            
        except Exception as e:
            logger.error(f"Error getting active strategies: {e}")
            return []
    
    async def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific strategy by ID"""
        try:
            container = self.db.get_container_client('strategies')
            
            item = await container.read_item(
                item=strategy_id,
                partition_key=strategy_id
            )
            
            return item
            
        except Exception as e:
            logger.error(f"Error getting strategy {strategy_id}: {e}")
            return None
    
    async def get_strategy_trades(self,
                                strategy_id: str,
                                start_date: datetime,
                                end_date: datetime) -> List[Dict[str, Any]]:
        """Get trades for a strategy within date range"""
        try:
            container = self.db.get_container_client('trades')
            
            query = """
            SELECT * FROM c 
            WHERE c.strategy_id = @strategy_id
            AND c.timestamp >= @start_date
            AND c.timestamp <= @end_date
            ORDER BY c.timestamp DESC
            """
            
            parameters = [
                {"name": "@strategy_id", "value": strategy_id},
                {"name": "@start_date", "value": start_date.isoformat()},
                {"name": "@end_date", "value": end_date.isoformat()}
            ]
            
            trades = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                # Convert timestamp string back to datetime
                if isinstance(item.get('timestamp'), str):
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                
                trades.append(item)
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting trades for strategy {strategy_id}: {e}")
            return []
    
    async def get_similar_strategies(self,
                                   strategy_type: str,
                                   symbols: List[str],
                                   timeframes: List[str]) -> List[Dict[str, Any]]:
        """Get strategies with similar characteristics"""
        try:
            container = self.db.get_container_client('strategies')
            
            query = """
            SELECT * FROM c 
            WHERE c.type = @strategy_type
            AND c.status = 'active'
            AND EXISTS(
                SELECT VALUE s FROM s IN c.symbols 
                WHERE s IN (@symbols)
            )
            """
            
            parameters = [
                {"name": "@strategy_type", "value": strategy_type},
                {"name": "@symbols", "value": symbols}
            ]
            
            strategies = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                strategies.append(item)
            
            return strategies
            
        except Exception as e:
            logger.error(f"Error getting similar strategies: {e}")
            return []
    
    async def update_strategy_status(self, strategy_id: str, status: str) -> bool:
        """Update strategy status"""
        try:
            container = self.db.get_container_client('strategies')
            
            # Get current strategy
            strategy = await container.read_item(
                item=strategy_id,
                partition_key=strategy_id
            )
            
            # Update status
            strategy['status'] = status
            strategy['last_updated'] = datetime.now(timezone.utc).isoformat()
            
            # Update in database
            await container.upsert_item(strategy)
            
            logger.info(f"Updated strategy {strategy_id} status to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating strategy status: {e}")
            return False
    
    async def update_strategy_parameters(self,
                                       strategy_id: str,
                                       parameters: Dict[str, Any]) -> bool:
        """Update strategy parameters"""
        try:
            container = self.db.get_container_client('strategies')
            
            # Get current strategy
            strategy = await container.read_item(
                item=strategy_id,
                partition_key=strategy_id
            )
            
            # Update parameters
            if 'configuration' not in strategy:
                strategy['configuration'] = {}
            
            strategy['configuration'].update(parameters)
            strategy['last_updated'] = datetime.now(timezone.utc).isoformat()
            strategy['parameters_updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Update in database
            await container.upsert_item(strategy)
            
            logger.info(f"Updated parameters for strategy {strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating strategy parameters: {e}")
            return False
    
    async def activate_replacement_strategy(self,
                                          old_strategy_id: str,
                                          new_strategy_id: str) -> bool:
        """Replace one strategy with another"""
        try:
            container = self.db.get_container_client('strategies')
            
            # Deactivate old strategy
            old_strategy = await container.read_item(
                item=old_strategy_id,
                partition_key=old_strategy_id
            )
            old_strategy['status'] = 'replaced'
            old_strategy['replaced_by'] = new_strategy_id
            old_strategy['replaced_at'] = datetime.now(timezone.utc).isoformat()
            
            await container.upsert_item(old_strategy)
            
            # Activate new strategy
            new_strategy = await container.read_item(
                item=new_strategy_id,
                partition_key=new_strategy_id
            )
            new_strategy['status'] = 'active'
            new_strategy['replaces'] = old_strategy_id
            new_strategy['activated_at'] = datetime.now(timezone.utc).isoformat()
            
            await container.upsert_item(new_strategy)
            
            logger.info(f"Replaced strategy {old_strategy_id} with {new_strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error replacing strategy: {e}")
            return False
    
    async def update_strategy_allocation(self,
                                       strategy_id: str,
                                       allocation_change: float) -> bool:
        """Update strategy allocation"""
        try:
            container = self.db.get_container_client('strategies')
            
            # Get current strategy
            strategy = await container.read_item(
                item=strategy_id,
                partition_key=strategy_id
            )
            
            # Update allocation
            current_allocation = strategy.get('allocation', 1.0)
            new_allocation = max(0.0, current_allocation * (1 + allocation_change))
            
            strategy['allocation'] = new_allocation
            strategy['allocation_updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Update in database
            await container.upsert_item(strategy)
            
            logger.info(
                f"Updated allocation for strategy {strategy_id} from {current_allocation:.2%} to {new_allocation:.2%}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error updating strategy allocation: {e}")
            return False
    
    async def store_strategy_review(self, review_data: Dict[str, Any]) -> bool:
        """Store strategy review result"""
        try:
            container = self.db.get_container_client('strategy_reviews')
            
            review_document = {
                'id': f"{review_data['strategy_id']}_{int(review_data['review_timestamp'].timestamp())}",
                'strategy_id': review_data['strategy_id'],
                'review_timestamp': review_data['review_timestamp'].isoformat(),
                'performance_grade': review_data['performance_grade'],
                'decision': review_data['decision'],
                'confidence_score': review_data['confidence_score'],
                'strengths': review_data['strengths'],
                'weaknesses': review_data['weaknesses'],
                'improvement_suggestions': review_data['improvement_suggestions'],
                'parameter_adjustments': review_data['parameter_adjustments'],
                'allocation_change': review_data['allocation_change'],
                'replacement_candidates': review_data['replacement_candidates'],
                'expected_future_performance': review_data['expected_future_performance'],
                'risk_assessment': review_data['risk_assessment'],
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            await container.create_item(review_document)
            
            logger.info(f"Stored review for strategy {review_data['strategy_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing strategy review: {e}")
            return False
    
    async def store_daily_review_summary(self, summary: Dict[str, Any]) -> bool:
        """Store daily review summary"""
        try:
            container = self.db.get_container_client('daily_review_summaries')
            
            summary_document = {
                'id': f"summary_{summary['review_date']}",
                'review_date': summary['review_date'].isoformat() if isinstance(summary['review_date'], datetime) else summary['review_date'],
                'total_strategies_reviewed': summary['total_strategies_reviewed'],
                'grade_distribution': summary['grade_distribution'],
                'decision_distribution': summary['decision_distribution'],
                'avg_confidence': summary['avg_confidence'],
                'top_performers': summary['top_performers'],
                'strategies_needing_attention': summary['strategies_needing_attention'],
                'market_regime': summary['market_regime'],
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            await container.upsert_item(summary_document)
            
            logger.info(f"Stored daily review summary for {summary['review_date']}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing daily review summary: {e}")
            return False
    
    async def get_strategy_backtest_results(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get backtest results for a strategy"""
        try:
            container = self.db.get_container_client('backtest_results')
            
            query = """
            SELECT * FROM c 
            WHERE c.strategy_id = @strategy_id
            ORDER BY c.created_at DESC
            OFFSET 0 LIMIT 1
            """
            
            parameters = [
                {"name": "@strategy_id", "value": strategy_id}
            ]
            
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                return item
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting backtest results for {strategy_id}: {e}")
            return None
    
    async def store_notification(self, notification: Dict[str, Any]) -> bool:
        """Store notification"""
        try:
            container = self.db.get_container_client('notifications')
            
            notification_doc = {
                'id': f"{notification['type']}_{int(notification['timestamp'].timestamp())}",
                'type': notification['type'],
                'timestamp': notification['timestamp'].isoformat(),
                'data': notification,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            await container.create_item(notification_doc)
            return True
            
        except Exception as e:
            logger.error(f"Error storing notification: {e}")
            return False
    
    async def get_strategy_review_history(self,
                                        strategy_id: str,
                                        limit: int = 10) -> List[Dict[str, Any]]:
        """Get review history for a strategy"""
        try:
            container = self.db.get_container_client('strategy_reviews')
            
            query = """
            SELECT * FROM c 
            WHERE c.strategy_id = @strategy_id
            ORDER BY c.review_timestamp DESC
            OFFSET 0 LIMIT @limit
            """
            
            parameters = [
                {"name": "@strategy_id", "value": strategy_id},
                {"name": "@limit", "value": limit}
            ]
            
            reviews = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                reviews.append(item)
            
            return reviews
            
        except Exception as e:
            logger.error(f"Error getting review history: {e}")
            return []
    
    async def get_daily_review_summary(self, date: str) -> Optional[Dict[str, Any]]:
        """Get daily review summary for a specific date"""
        try:
            container = self.db.get_container_client('daily_review_summaries')
            
            item = await container.read_item(
                item=f"summary_{date}",
                partition_key=f"summary_{date}"
            )
            
            return item
            
        except Exception as e:
            logger.error(f"Error getting daily summary for {date}: {e}")
            return None
    
    async def get_recent_strategy_reviews(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent strategy reviews across all strategies"""
        try:
            container = self.db.get_container_client('strategy_reviews')
            
            query = """
            SELECT * FROM c 
            ORDER BY c.review_timestamp DESC
            OFFSET 0 LIMIT @limit
            """
            
            parameters = [
                {"name": "@limit", "value": limit}
            ]
            
            reviews = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                reviews.append(item)
            
            return reviews
            
        except Exception as e:
            logger.error(f"Error getting recent reviews: {e}")
            return []


# Apply the mixin to the existing Database class
    async def get_strategy_trades(self, strategy_id: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get trades for a strategy within date range"""
        try:
            container = self.db.get_container_client('trades')
            
            query = """
            SELECT * FROM c 
            WHERE c.strategy_id = @strategy_id
            AND c.timestamp >= @start_date
            AND c.timestamp <= @end_date
            ORDER BY c.timestamp DESC
            """
            
            parameters = [
                {"name": "@strategy_id", "value": strategy_id},
                {"name": "@start_date", "value": start_date.isoformat()},
                {"name": "@end_date", "value": end_date.isoformat()}
            ]
            
            trades = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                # Convert timestamp string back to datetime if needed
                if isinstance(item.get('timestamp'), str):
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                trades.append(item)
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting strategy trades: {e}")
            return []
    
    async def get_strategy_backtest_results(self, strategy_id: str) -> Optional[Dict]:
        """Get backtest results for a strategy"""
        try:
            container = self.db.get_container_client('backtest_results')
            
            query = """
            SELECT * FROM c 
            WHERE c.strategy_id = @strategy_id
            ORDER BY c.created_at DESC
            OFFSET 0 LIMIT 1
            """
            
            parameters = [{"name": "@strategy_id", "value": strategy_id}]
            
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                return item
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting backtest results: {e}")
            return None
    
    async def store_notification(self, notification: Dict):
        """Store a notification in the database"""
        try:
            container = self.db.get_container_client('notifications')
            
            notification_doc = {
                'id': f"notification_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                'created_at': datetime.now(timezone.utc).isoformat(),
                **notification
            }
            
            await container.create_item(notification_doc)
            
        except Exception as e:
            logger.error(f"Error storing notification: {e}")
    
    async def get_current_active_strategies_count(self) -> int:
        """Get count of currently active strategies"""
        try:
            container = self.db.get_container_client('strategies')
            
            query = """
            SELECT VALUE COUNT(1) FROM c 
            WHERE c.status = 'active' 
            AND c.enabled = true
            """
            
            async for item in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                return item
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting active strategies count: {e}")
            return 0
    
    async def get_market_data_for_analysis(self, symbol: str, interval: str = "1h", hours_back: int = 168) -> List[Dict]:
        """Get market data for crypto analysis"""
        try:
            # This would connect to market_data_service database
            # For now, return placeholder data structure
            
            # In a real implementation, this would query the market_data container
            # from the market_data_service database
            
            from datetime import datetime, timezone, timedelta
            
            # Placeholder: Generate sample data points
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=hours_back)
            
            # This is a placeholder - in real implementation, query actual market data
            sample_data = []
            current_time = start_time
            base_price = 45000.0  # Starting price
            
            while current_time <= end_time:
                # Simulate price movement
                price_change = (hash(str(current_time)) % 200 - 100) / 100.0  # -1% to +1%
                base_price *= (1 + price_change / 100)
                
                sample_data.append({
                    'symbol': symbol,
                    'timestamp': current_time,
                    'close_price': base_price,
                    'volume': 1000000 + (hash(str(current_time)) % 5000000),
                    'quote_volume': base_price * (1000000 + (hash(str(current_time)) % 5000000)),
                    'interval': interval
                })
                
                current_time += timedelta(hours=1)
            
            logger.warning(f"Using placeholder market data for {symbol} - integrate with market_data_service")
            return sample_data
            
        except Exception as e:
            logger.error(f"Error getting market data for analysis: {e}")
            return []
    
    async def get_all_symbols(self, include_inactive: bool = False) -> List[Dict]:
        """Get all symbols from symbol tracking"""
        try:
            # This would query the market_data_service symbol_tracking container
            # For now, return a default set of crypto symbols
            
            default_symbols = [
                {
                    'id': 'BTCUSDC',
                    'symbol': 'BTCUSDC',
                    'base_asset': 'BTC',
                    'quote_asset': 'USDC',
                    'tracking': True,
                    'priority': 1,
                    'asset_type': 'crypto'
                },
                {
                    'id': 'ETHUSDC',
                    'symbol': 'ETHUSDC', 
                    'base_asset': 'ETH',
                    'quote_asset': 'USDC',
                    'tracking': True,
                    'priority': 1,
                    'asset_type': 'crypto'
                },
                {
                    'id': 'ADAUSDC',
                    'symbol': 'ADAUSDC',
                    'base_asset': 'ADA', 
                    'quote_asset': 'USDC',
                    'tracking': True,
                    'priority': 2,
                    'asset_type': 'crypto'
                }
            ]
            
            logger.warning("Using placeholder symbol data - integrate with market_data_service")
            return default_symbols
            
        except Exception as e:
            logger.error(f"Error getting all symbols: {e}")
            return []
    
    async def get_tracked_symbols(self, asset_type: str = None, exchange: str = None) -> List[Dict]:
        """Get tracked symbols (placeholder implementation)"""
        try:
            all_symbols = await self.get_all_symbols()
            
            filtered_symbols = []
            for symbol in all_symbols:
                if symbol.get('tracking', False):
                    if asset_type is None or symbol.get('asset_type') == asset_type:
                        if exchange is None or symbol.get('exchange', 'binance') == exchange:
                            filtered_symbols.append(symbol)
            
            return filtered_symbols
            
        except Exception as e:
            logger.error(f"Error getting tracked symbols: {e}")
            return []
    
    async def update_symbol_tracking(self, symbol: str, updates: Dict) -> bool:
        """Update symbol tracking (placeholder implementation)"""
        try:
            logger.info(f"Would update symbol {symbol} with {updates}")
            # In real implementation, this would update the market_data_service database
            return True
            
        except Exception as e:
            logger.error(f"Error updating symbol tracking for {symbol}: {e}")
            return False

async def extend_database_with_review_methods(database_instance):
    """
    Extend database instance with review methods
    
    This function adds all review-related methods to the existing database instance
    """
    # Get all methods from the mixin
    mixin_methods = [method for method in dir(StrategyReviewDatabaseMixin) 
                     if not method.startswith('_') and callable(getattr(StrategyReviewDatabaseMixin, method))]
    
    # Add each method to the database instance
    for method_name in mixin_methods:
        method = getattr(StrategyReviewDatabaseMixin, method_name)
        # Bind the method to the database instance
        bound_method = method.__get__(database_instance, database_instance.__class__)
        setattr(database_instance, method_name, bound_method)
    
    logger.info(f"Extended database with {len(mixin_methods)} review methods")
    
    return database_instance
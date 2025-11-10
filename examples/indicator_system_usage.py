"""
Example usage of the database-driven indicator configuration system
for strategy service integration.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List

from shared.market_data_indicator_client import MarketDataIndicatorClient, create_indicator_builder


class StrategyIndicatorManager:
    """Example strategy service integration with database-driven indicator system"""
    
    def __init__(self, strategy_id: str, strategy_name: str):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        
        # Initialize client
        self.indicator_client = MarketDataIndicatorClient(
            rabbitmq_url="amqp://mastertrade:password@localhost:5672/",
            api_base_url="http://localhost:8001"
        )
        
        # Track our configurations
        self.active_configurations: Dict[str, Dict] = {}
        
    async def initialize(self):
        """Initialize the indicator manager"""
        await self.indicator_client.connect()
        print(f"Initialized indicator manager for strategy: {self.strategy_name}")
        
    async def shutdown(self):
        """Cleanup resources"""
        await self.indicator_client.disconnect()
        
    async def setup_momentum_strategy_indicators(self, symbols: List[str], interval: str = "5m"):
        """Setup indicators for a momentum trading strategy"""
        print(f"Setting up momentum indicators for {len(symbols)} symbols...")
        
        all_indicators = []
        
        for symbol in symbols:
            # Create momentum-focused indicators
            builder = (create_indicator_builder(symbol, interval)
                      .set_strategy_id(self.strategy_id)
                      .add_rsi(14, priority=1)  # Primary momentum indicator
                      .add_rsi(21, priority=2)  # Secondary momentum 
                      .add_macd(12, 26, 9, priority=1)  # Trend confirmation
                      .add_ema(9, priority=2)   # Fast trend
                      .add_ema(21, priority=2)  # Medium trend
                      .add_sma(50, priority=3)) # Long term trend
            
            symbol_indicators = builder.build()
            all_indicators.extend(symbol_indicators)
            
            print(f"  - {symbol}: {len(symbol_indicators)} indicators configured")
        
        # Send bulk configuration request
        print("Sending bulk indicator configuration to market data service...")
        results = await self.indicator_client.request_bulk_indicators(
            strategy_id=self.strategy_id,
            indicators=all_indicators,
            wait_for_results=True,
            timeout=60.0
        )
        
        # Store configuration info
        for indicator in all_indicators:
            self.active_configurations[indicator['id']] = {
                'config': indicator,
                'last_result': None,
                'created_at': datetime.utcnow()
            }
        
        print(f"Successfully configured {len(all_indicators)} indicators, got {len(results)} results")
        return results
        
    async def setup_scalping_strategy_indicators(self, symbols: List[str], interval: str = "1m"):
        """Setup indicators for a scalping strategy (high frequency)"""
        print(f"Setting up scalping indicators for {len(symbols)} symbols...")
        
        all_indicators = []
        
        for symbol in symbols:
            # Create scalping-focused indicators (faster periods)
            builder = (create_indicator_builder(symbol, interval)
                      .set_strategy_id(self.strategy_id)
                      .add_rsi(7, priority=1)    # Very fast RSI
                      .add_ema(5, priority=1)    # Very fast EMA
                      .add_ema(13, priority=1)   # Fast EMA  
                      .add_macd(5, 13, 3, priority=1)  # Fast MACD
                      .add_bollinger_bands(10, 2.0, priority=2))  # Quick volatility
            
            symbol_indicators = builder.build()
            
            # Set high frequency updates for scalping
            for indicator in symbol_indicators:
                indicator['cache_duration_minutes'] = 1  # Very fresh cache
                indicator['update_frequency_seconds'] = 15  # Update every 15 seconds
                
            all_indicators.extend(symbol_indicators)
            print(f"  - {symbol}: {len(symbol_indicators)} high-frequency indicators")
        
        # Configure for immediate calculation
        results = await self.indicator_client.request_bulk_indicators(
            strategy_id=self.strategy_id,
            indicators=all_indicators,
            wait_for_results=True
        )
        
        print(f"Configured {len(all_indicators)} scalping indicators")
        return results
        
    async def update_indicator_parameters(self, symbol: str, indicator_type: str, new_params: Dict):
        """Update parameters for a specific indicator"""
        print(f"Updating {indicator_type} parameters for {symbol}: {new_params}")
        
        # Find matching configuration
        matching_config = None
        for config_id, config_info in self.active_configurations.items():
            config = config_info['config']
            if (config['symbol'] == symbol and 
                config['indicator_type'] == indicator_type):
                matching_config = (config_id, config)
                break
        
        if not matching_config:
            print(f"No matching configuration found for {symbol} {indicator_type}")
            return False
        
        config_id, config = matching_config
        
        # Update parameters via REST API
        import aiohttp
        async with aiohttp.ClientSession() as session:
            update_data = {
                'parameters': {p['name']: p['value'] for p in config['parameters']}
            }
            update_data['parameters'].update(new_params)
            
            # Convert back to parameter list format
            new_param_list = [
                {
                    'name': name,
                    'value': value,
                    'data_type': 'int' if isinstance(value, int) else 'float' if isinstance(value, float) else 'string'
                }
                for name, value in update_data['parameters'].items()
            ]
            
            url = f"http://localhost:8001/api/indicators/configurations/{config_id}"
            params = {'strategy_id': self.strategy_id}
            update_payload = {'parameters': update_data['parameters']}
            
            async with session.put(url, json=update_payload, params=params) as response:
                if response.status == 200:
                    print(f"Successfully updated {indicator_type} for {symbol}")
                    return True
                else:
                    error = await response.text()
                    print(f"Failed to update indicator: {error}")
                    return False
    
    async def get_latest_indicators(self, symbol: str) -> Dict[str, float]:
        """Get latest indicator values for a symbol"""
        # Use REST API to get cached results
        results = await self.indicator_client.get_cached_indicators_rest(
            symbol=symbol,
            interval="5m",
            indicator_types=["rsi", "macd", "ema", "sma"]
        )
        
        return results.get('cached_results', {})
    
    async def monitor_strategy_performance(self):
        """Monitor and adjust indicators based on strategy performance"""
        print("Starting indicator performance monitoring...")
        
        while True:
            try:
                # Check strategy performance metrics
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    # Get strategies overview
                    async with session.get("http://localhost:8001/api/indicators/strategies") as response:
                        if response.status == 200:
                            data = await response.json()
                            strategies = data.get('strategies', [])
                            
                            our_strategy = next(
                                (s for s in strategies if s['strategy_id'] == self.strategy_id),
                                None
                            )
                            
                            if our_strategy:
                                print(f"Strategy {self.strategy_name}:")
                                print(f"  - Configurations: {our_strategy['configuration_count']}")
                                print(f"  - Symbols: {len(our_strategy['symbols'])}")
                                print(f"  - Indicator types: {our_strategy['indicator_types']}")
                
                # Check for indicators that might need adjustment
                # (This would normally include performance analysis)
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                print(f"Error in performance monitoring: {e}")
                await asyncio.sleep(60)
    
    async def cleanup_old_configurations(self):
        """Remove old or unused indicator configurations"""
        print("Cleaning up old indicator configurations...")
        
        # This would implement logic to remove configurations
        # that are no longer needed by the strategy
        
        # Example: Remove configurations older than 24 hours that haven't been used
        cutoff_time = datetime.utcnow().timestamp() - (24 * 3600)
        
        configs_to_remove = []
        for config_id, config_info in self.active_configurations.items():
            if config_info['created_at'].timestamp() < cutoff_time:
                if not config_info.get('last_result'):  # Never got results
                    configs_to_remove.append(config_id)
        
        for config_id in configs_to_remove:
            config_info = self.active_configurations[config_id]
            symbol = config_info['config']['symbol']
            
            # Remove via REST API
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"http://localhost:8001/api/indicators/configurations/{config_id}"
                params = {'strategy_id': self.strategy_id}
                
                async with session.delete(url, params=params) as response:
                    if response.status == 200:
                        print(f"Removed unused configuration: {config_id} for {symbol}")
                        del self.active_configurations[config_id]
                    else:
                        print(f"Failed to remove configuration: {config_id}")


async def main():
    """Example usage of the database-driven indicator system"""
    
    # Create strategy manager
    momentum_strategy = StrategyIndicatorManager(
        strategy_id="momentum_v2",
        strategy_name="Enhanced Momentum Strategy"
    )
    
    scalping_strategy = StrategyIndicatorManager(
        strategy_id="scalping_v1", 
        strategy_name="High Frequency Scalping"
    )
    
    try:
        # Initialize both strategies
        await momentum_strategy.initialize()
        await scalping_strategy.initialize()
        
        # Test symbols
        test_symbols = ["BTCUSDC", "ETHUSDC", "ADAUSDC"]
        
        print("=== Testing Momentum Strategy Setup ===")
        momentum_results = await momentum_strategy.setup_momentum_strategy_indicators(
            symbols=test_symbols,
            interval="5m"
        )
        print(f"Momentum strategy got {len(momentum_results)} indicator results")
        
        print("\n=== Testing Scalping Strategy Setup ===")
        scalping_results = await scalping_strategy.setup_scalping_strategy_indicators(
            symbols=["BTCUSDC"],  # Just one symbol for scalping test
            interval="1m"
        )
        print(f"Scalping strategy got {len(scalping_results)} indicator results")
        
        print("\n=== Testing Parameter Updates ===")
        # Test updating RSI period from 14 to 21 for BTC momentum
        await momentum_strategy.update_indicator_parameters(
            symbol="BTCUSDC",
            indicator_type="rsi", 
            new_params={"period": 21}
        )
        
        print("\n=== Testing Latest Indicators Retrieval ===")
        # Get latest indicator values
        btc_indicators = await momentum_strategy.get_latest_indicators("BTCUSDC")
        print(f"Latest BTC indicators: {btc_indicators}")
        
        print("\n=== Running Performance Monitoring (5 minutes) ===")
        # Run monitoring for a short time
        monitor_task = asyncio.create_task(momentum_strategy.monitor_strategy_performance())
        
        # Let it run for a bit
        await asyncio.sleep(30)  # Run for 30 seconds in demo
        monitor_task.cancel()
        
        print("\n=== Testing Configuration Cleanup ===")
        await momentum_strategy.cleanup_old_configurations()
        
        print("\nDemo completed successfully!")
        
    except Exception as e:
        print(f"Error in demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        await momentum_strategy.shutdown()
        await scalping_strategy.shutdown()


if __name__ == "__main__":
    print("Database-Driven Indicator Configuration System Demo")
    print("=" * 60)
    asyncio.run(main())
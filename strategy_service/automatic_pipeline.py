"""
Automatic Strategy Generation and Backtesting Service

This service automatically:
1. Generates 500 new strategies daily at 3:00 AM UTC
2. Backtests all strategies within 3-hour window
3. Learns from results using genetic algorithm + RL + statistical analysis
4. Stores results in database for continuous improvement
5. Integrates price predictions from BTCUSDC model

Runs as part of the Strategy Service main loop.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import structlog

# Import backtesting and learning components
import sys
sys.path.append('..')
from backtest_engine import BacktestEngine
from data_utils import fetch_symbol_history
from ml_models.price_predictor import BTCUSDCPredictor
from ml_models.strategy_learner import StrategyLearner

logger = structlog.get_logger()


class AutomaticStrategyPipeline:
    """
    Fully automatic strategy generation and backtesting pipeline
    
    Daily Cycle (3:00 AM UTC):
    1. Generate 500 new strategies using learned patterns
    2. Backtest all strategies with historical data
    3. Filter realistic performers
    4. Store results in database
    5. Learn from results for next generation
    6. Promote best strategies to paper trading
    """
    
    def __init__(self, database, market_data_consumer):
        self.database = database
        self.market_data_consumer = market_data_consumer
        
        # Initialize components
        self.price_predictor = BTCUSDCPredictor()
        self.strategy_learner = StrategyLearner(database)
        self.backtest_engine = None  # Initialized per run
        
        # Pipeline configuration
        self.strategies_per_cycle = 500
        self.max_backtest_time_hours = 3
        self.backtest_history_days = 90
        
        # Performance thresholds for filtering
        self.min_sharpe_ratio = 0.5
        self.min_win_rate = 0.35
        self.min_total_return = -50  # %
        self.max_total_return = 500  # %
        self.min_trades = 10
        
        # Scheduling
        self.generation_hour = 3  # 3:00 AM UTC
        self.running = False
        self.last_generation = None
        
        logger.info(
            "Automatic Strategy Pipeline initialized",
            strategies_per_cycle=self.strategies_per_cycle,
            max_time_hours=self.max_backtest_time_hours,
            generation_time=f"{self.generation_hour}:00 UTC"
        )
    
    async def start(self):
        """Start the automatic pipeline scheduler"""
        self.running = True
        logger.info("Starting automatic strategy pipeline")
        
        # Load previous backtest results for learning
        await self._load_historical_backtests()
        
        # Train price prediction model if needed
        await self._initialize_price_predictor()
        
        # Start the scheduling loop
        asyncio.create_task(self._schedule_daily_generation())
    
    async def stop(self):
        """Stop the pipeline"""
        self.running = False
        logger.info("Stopping automatic strategy pipeline")
    
    async def _schedule_daily_generation(self):
        """Schedule daily strategy generation at 3:00 AM UTC"""
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Check if it's time for generation (3:00 AM UTC)
                if (current_time.hour == self.generation_hour and 
                    current_time.minute < 5):  # 5-minute window
                    
                    # Check if we've already run today
                    if self.last_generation is None or \
                       self.last_generation.date() < current_time.date():
                        
                        logger.info("Starting scheduled strategy generation and backtesting")
                        
                        try:
                            results = await self.run_full_cycle()
                            
                            logger.info(
                                "Strategy generation cycle completed",
                                generated=results['generated_count'],
                                backtested=results['backtested_count'],
                                passed=results['passed_count'],
                                duration_minutes=results['duration_minutes']
                            )
                            
                            self.last_generation = current_time
                            
                        except Exception as e:
                            logger.error(f"Error in strategy generation cycle: {e}", exc_info=True)
                
                # Sleep for 1 minute before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in generation scheduler: {e}")
                await asyncio.sleep(60)
    
    async def run_full_cycle(self) -> Dict:
        """
        Run complete generation → backtest → learn cycle
        
        Returns:
            Dictionary with cycle results and statistics
        """
        start_time = datetime.now(timezone.utc)
        logger.info(f"Starting full strategy cycle - Target: {self.strategies_per_cycle} strategies")
        
        try:
            # Step 1: Generate 500 new strategies
            logger.info("Step 1/5: Generating strategies...")
            strategies = await self.strategy_learner.generate_improved_strategies(
                count=self.strategies_per_cycle,
                use_genetic=True,
                use_learning=True
            )
            logger.info(f"Generated {len(strategies)} strategies")
            
            # Step 2: Get historical data for backtesting
            logger.info("Step 2/5: Fetching historical data...")
            historical_data = await self._fetch_backtest_data()
            
            # Step 3: Backtest all strategies
            logger.info(f"Step 3/5: Backtesting {len(strategies)} strategies...")
            backtest_results = await self._backtest_strategies(strategies, historical_data)
            logger.info(f"Completed {len(backtest_results)} backtests")
            
            # Step 4: Filter and store results
            logger.info("Step 4/5: Filtering and storing results...")
            passed_strategies = await self._filter_and_store(strategies, backtest_results)
            logger.info(f"{len(passed_strategies)} strategies passed filters")
            
            # Step 5: Learn from results
            logger.info("Step 5/5: Learning from backtest results...")
            learning_insights = await self.strategy_learner.learn_from_backtests(backtest_results)
            await self._store_learning_insights(learning_insights)
            
            # Calculate cycle duration
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds() / 60
            
            results = {
                'generated_count': len(strategies),
                'backtested_count': len(backtest_results),
                'passed_count': len(passed_strategies),
                'duration_minutes': duration,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'learning_insights': learning_insights,
                'top_strategies': passed_strategies[:10] if passed_strategies else []
            }
            
            # Log summary
            logger.info(
                "Full cycle completed successfully",
                duration_minutes=duration,
                success_rate=f"{(len(passed_strategies) / len(strategies) * 100):.1f}%"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error in full cycle: {e}", exc_info=True)
            raise
    
    async def _fetch_backtest_data(self) -> Dict[str, 'pd.DataFrame']:
        """
        Fetch historical data for backtesting
        
        Returns data for the past 90 days for multiple symbols
        """
        import pandas as pd
        
        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        historical_data = {}
        
        for symbol in symbols:
            try:
                # Fetch from database or market data service
                data = await fetch_symbol_history(
                    self.database,
                    symbol,
                    days=self.backtest_history_days,
                )
                historical_data[symbol] = data
                logger.info(f"Fetched {len(data)} data points for {symbol}")
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
        
        return historical_data
    
    
    async def _backtest_strategies(self, 
                                   strategies: List[Dict],
                                   historical_data: Dict) -> List[Dict]:
        """
        Backtest all strategies in parallel within time limit
        
        Uses concurrent processing to complete within 3 hours
        """
        logger.info(f"Starting parallel backtesting of {len(strategies)} strategies")
        
        # Calculate strategies per minute to meet deadline
        time_limit_minutes = self.max_backtest_time_hours * 60
        strategies_per_minute = len(strategies) / time_limit_minutes
        
        logger.info(f"Target rate: {strategies_per_minute:.1f} strategies/minute")
        
        # Create backtest tasks with concurrency limit
        max_concurrent = 10  # Run 10 backtests concurrently
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def backtest_with_limit(strategy):
            async with semaphore:
                return await self._backtest_single_strategy(strategy, historical_data)
        
        # Run backtests
        backtest_tasks = [backtest_with_limit(strategy) for strategy in strategies]
        results = await asyncio.gather(*backtest_tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = [r for r in results if isinstance(r, dict)]
        
        logger.info(f"Completed {len(valid_results)} successful backtests out of {len(strategies)}")
        
        return valid_results
    
    async def _backtest_single_strategy(self, 
                                       strategy: Dict,
                                       historical_data: Dict) -> Dict:
        """Backtest a single strategy"""
        try:
            # Get data for strategy's symbols
            symbol = strategy.get('symbols', ['BTCUSDT'])[0]
            data = historical_data.get(symbol)
            
            if data is None or len(data) < 100:
                logger.warning(f"Insufficient data for {symbol}")
                return None
            
            # Initialize backtest engine
            from backtest_engine import BacktestEngine
            
            engine = BacktestEngine(initial_capital=10000)
            hours_back = self.backtest_history_days * 24
            symbol_sentiment = []
            global_sentiment = []

            try:
                symbol_sentiment = await self.database.get_sentiment_entries(
                    symbol=symbol,
                    hours_back=hours_back,
                    limit=min(5000, hours_back * 4),
                )
            except Exception as sentiment_error:
                logger.warning(
                    "Failed to load symbol sentiment for backtest",
                    symbol=symbol,
                    error=str(sentiment_error),
                )

            try:
                global_sentiment = await self.database.get_sentiment_entries(
                    sentiment_types=[
                        'global_crypto_sentiment',
                        'global_market_sentiment',
                        'market_sentiment',
                        'fear_greed_index',
                    ],
                    hours_back=hours_back,
                    limit=min(5000, hours_back * 4),
                )
            except Exception as sentiment_error:
                logger.warning(
                    "Failed to load global sentiment for backtest",
                    error=str(sentiment_error),
                )
            
            # Run backtest
            result = await engine.run_backtest(
                strategy=strategy,
                historical_data=data,
                symbol_sentiment=symbol_sentiment,
                global_sentiment=global_sentiment,
            )
            
            # Add strategy info to result
            result['strategy_id'] = strategy['id']
            result['strategy_config'] = strategy
            result['strategy_type'] = strategy.get('type', 'unknown')
            result['timeframe'] = strategy.get('timeframe', '15m')
            
            # Get price prediction for this strategy
            if symbol == 'BTCUSDT':
                prediction = await self.price_predictor.predict(data, return_confidence=True)
                result['price_prediction'] = prediction
            
            return result
            
        except Exception as e:
            logger.error(f"Error backtesting strategy {strategy.get('id')}: {e}")
            return None
    
    async def _filter_and_store(self, 
                                strategies: List[Dict],
                                backtest_results: List[Dict]) -> List[Dict]:
        """
        Filter strategies based on performance criteria and store in database
        
        Returns strategies that passed filters
        """
        passed_strategies = []
        
        for result in backtest_results:
            if result is None:
                continue
            
            # Apply filters
            if not self._meets_criteria(result):
                continue
            
            # Add to passed list
            passed_strategies.append(result)
            
            # Store in database
            try:
                strategy_id = result['strategy_id']
                
                # Store strategy
                await self.database.create_strategy(result['strategy_config'])
                
                # Store backtest result
                await self.database.store_backtest_result(strategy_id, result)
                
                # If excellent performance, promote to paper trading
                if result.get('sharpe_ratio', 0) > 1.5:
                    await self.database.update_strategy_status(strategy_id, 'paper_trading')
                    logger.info(f"Promoted strategy {strategy_id} to paper trading")
                
            except Exception as e:
                logger.error(f"Error storing strategy {result.get('strategy_id')}: {e}")
        
        # Sort by performance
        passed_strategies.sort(key=lambda x: x.get('sharpe_ratio', 0), reverse=True)
        
        return passed_strategies
    
    def _meets_criteria(self, result: Dict) -> bool:
        """Check if backtest result meets performance criteria"""
        # Check all thresholds
        if result.get('sharpe_ratio', 0) < self.min_sharpe_ratio:
            return False
        
        if result.get('win_rate', 0) < self.min_win_rate:
            return False
        
        total_return = result.get('total_return', 0)
        if total_return < self.min_total_return or total_return > self.max_total_return:
            return False
        
        if result.get('total_trades', 0) < self.min_trades:
            return False
        
        return True
    
    async def _load_historical_backtests(self):
        """Load previous backtest results for learning"""
        try:
            # Query last 1000 backtest results
            results = await self.database.get_backtest_results(limit=1000)
            
            if results:
                await self.strategy_learner.learn_from_backtests(results)
                logger.info(f"Loaded {len(results)} historical backtest results for learning")
            else:
                logger.info("No historical backtests found, starting fresh")
                
        except Exception as e:
            logger.warning(f"Could not load historical backtests: {e}")
    
    async def _initialize_price_predictor(self):
        """Initialize and train price prediction model if needed"""
        try:
            # Check if model exists
            if not hasattr(self.price_predictor, 'model') or self.price_predictor.model is None:
                logger.info("Training price prediction model...")
                
                # Fetch BTCUSDC historical data
                btc_data = await self._fetch_symbol_history('BTCUSDT', days=365)
                
                # Train model
                training_result = await self.price_predictor.train(
                    historical_data=btc_data,
                    epochs=30,
                    batch_size=64
                )
                
                logger.info(f"Price predictor training completed: {training_result}")
            else:
                logger.info("Price predictor model already loaded")
                
        except Exception as e:
            logger.warning(f"Could not train price predictor: {e}")
            logger.info("Will use mock predictions")
    
    async def _store_learning_insights(self, insights: Dict):
        """Store learning insights in database"""
        try:
            await self.database.store_learning_insights({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'insights': insights,
                'generation_stats': self.strategy_learner.get_generation_stats()
            })
            logger.info("Learning insights stored in database")
        except Exception as e:
            logger.error(f"Error storing learning insights: {e}")
    
    async def trigger_manual_generation(self, count: int = 100) -> Dict:
        """
        Manually trigger strategy generation and backtesting
        
        Useful for testing or on-demand generation
        """
        logger.info(f"Manual trigger: Generating and backtesting {count} strategies")
        
        # Temporarily override count
        original_count = self.strategies_per_cycle
        self.strategies_per_cycle = count
        
        try:
            results = await self.run_full_cycle()
            return results
        finally:
            self.strategies_per_cycle = original_count
    
    def get_pipeline_status(self) -> Dict:
        """Get current pipeline status"""
        return {
            'running': self.running,
            'last_generation': self.last_generation.isoformat() if self.last_generation else None,
            'next_generation': self._calculate_next_generation().isoformat(),
            'strategies_per_cycle': self.strategies_per_cycle,
            'max_backtest_time_hours': self.max_backtest_time_hours,
            'generation_time_utc': f"{self.generation_hour}:00",
            'learning_stats': self.strategy_learner.get_generation_stats()
        }
    
    def _calculate_next_generation(self) -> datetime:
        """Calculate next scheduled generation time"""
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=self.generation_hour, minute=0, second=0, microsecond=0)
        
        if now.hour >= self.generation_hour:
            # Already passed today, schedule for tomorrow
            next_run += timedelta(days=1)
        
        return next_run

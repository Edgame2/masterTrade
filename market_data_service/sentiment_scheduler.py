"""
Sentiment Analysis Scheduler

Runs periodic sentiment analysis tasks:
1. Reddit sentiment collection (every 2 hours)
2. News sentiment collection (every hour)
3. Twitter sentiment collection (every 30 minutes if configured)
4. Telegram monitoring (every 15 minutes if configured)
5. On-chain metrics collection (every hour)
6. Sentiment aggregation (every 30 minutes)
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List
import structlog

from config import settings
from database import Database
from enhanced_sentiment_analyzer import ComprehensiveSentimentCollector
from sentiment_data_collector import SentimentDataCollector

logger = structlog.get_logger()


class SentimentScheduler:
    """Scheduler for sentiment analysis tasks"""
    
    def __init__(self):
        self.database: Database = None
        self.comprehensive_collector: ComprehensiveSentimentCollector = None
        self.basic_collector: SentimentDataCollector = None
        self.running = False
        self.crypto_symbols = ["BTC", "ETH", "BNB", "ADA", "SOL", "DOT", "AVAX", "MATIC", "LINK", "UNI"]
        self.stats = {
            "reddit_runs": 0,
            "news_runs": 0,
            "twitter_runs": 0,
            "aggregation_runs": 0,
            "errors": 0,
            "last_collection": None,
            "last_error": None
        }
    
    async def initialize(self):
        """Initialize database and collectors"""
        try:
            self.database = Database()
            await self.database.__aenter__()
            
            self.comprehensive_collector = ComprehensiveSentimentCollector(self.database)
            await self.comprehensive_collector.connect()
            
            self.basic_collector = SentimentDataCollector(self.database)
            await self.basic_collector.connect()
            
            logger.info("Sentiment scheduler initialized")
            
        except Exception as e:
            logger.error("Failed to initialize sentiment scheduler", error=str(e))
            raise
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.comprehensive_collector:
                await self.comprehensive_collector.disconnect()
            
            if self.basic_collector:
                await self.basic_collector.disconnect()
            
            if self.database:
                await self.database.__aexit__(None, None, None)
            
            logger.info("Sentiment scheduler cleaned up")
            
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))
    
    async def collect_reddit_sentiment(self):
        """Collect sentiment from Reddit"""
        try:
            logger.info("Starting Reddit sentiment collection")
            
            # Use comprehensive collector for Reddit
            results = await self.comprehensive_collector.collect_all_sentiment(self.crypto_symbols)
            
            self.stats["reddit_runs"] += 1
            self.stats["last_collection"] = datetime.utcnow().isoformat()
            
            reddit_count = len(results.get("reddit_sentiment", []))
            logger.info(
                "Reddit sentiment collection completed",
                items=reddit_count,
                total_runs=self.stats["reddit_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in Reddit sentiment collection", error=str(e))
    
    async def collect_news_sentiment(self):
        """Collect news sentiment"""
        try:
            logger.info("Starting news sentiment collection")
            
            # Use basic collector for news
            news_data = await self.basic_collector.collect_news_sentiment(self.crypto_symbols)
            
            self.stats["news_runs"] += 1
            
            logger.info(
                "News sentiment collection completed",
                items=len(news_data),
                total_runs=self.stats["news_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in news sentiment collection", error=str(e))
    
    async def collect_twitter_sentiment(self):
        """Collect Twitter sentiment"""
        try:
            if not hasattr(settings, 'TWITTER_BEARER_TOKEN') or not settings.TWITTER_BEARER_TOKEN:
                logger.debug("Twitter API not configured, skipping")
                return
            
            logger.info("Starting Twitter sentiment collection")
            
            # Use basic collector for Twitter
            twitter_data = await self.basic_collector.collect_social_sentiment(self.crypto_symbols)
            
            self.stats["twitter_runs"] += 1
            
            logger.info(
                "Twitter sentiment collection completed",
                items=len(twitter_data),
                total_runs=self.stats["twitter_runs"]
            )
            
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            logger.error("Error in Twitter sentiment collection", error=str(e))
    
    async def collect_fear_greed(self):
        """Collect Fear & Greed Index"""
        try:
            logger.info("Collecting Fear & Greed Index")
            
            fear_greed = await self.basic_collector.collect_fear_greed_index()
            
            if fear_greed:
                await self.database.upsert_market_data(fear_greed)
                logger.info(
                    "Fear & Greed Index collected",
                    value=fear_greed["value"],
                    classification=fear_greed["classification"]
                )
            
        except Exception as e:
            logger.error("Error collecting Fear & Greed Index", error=str(e))
    
    async def aggregate_sentiment(self):
        """Aggregate all sentiment sources"""
        try:
            logger.info("Aggregating sentiment data")
            
            # Get recent sentiment data from database
            for symbol in self.crypto_symbols:
                try:
                    query = """
                    SELECT * FROM c 
                    WHERE c.doc_type IN ('sentiment_data', 'aggregated_sentiment')
                    AND c.symbol = @symbol
                    AND c.timestamp > @since
                    ORDER BY c.timestamp DESC
                    """
                    
                    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
                    
                    results = list(self.database.container.query_items(
                        query=query,
                        parameters=[
                            {"name": "@symbol", "value": symbol},
                            {"name": "@since", "value": one_hour_ago}
                        ],
                        enable_cross_partition_query=True
                    ))
                    
                    if results:
                        # Calculate aggregated sentiment
                        sentiment_scores = []
                        sources = defaultdict(int)
                        
                        for item in results:
                            if "aggregated_sentiment" in item:
                                sentiment_scores.append(item["aggregated_sentiment"]["average_polarity"])
                                sources[item["source"]] += 1
                            elif "polarity" in item:
                                sentiment_scores.append(item["polarity"])
                                sources[item["source"]] += 1
                        
                        if sentiment_scores:
                            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
                            sentiment_score = int((avg_sentiment + 1) * 50)
                            
                            # Determine category
                            if sentiment_score >= 70:
                                category = "bullish"
                            elif sentiment_score <= 30:
                                category = "bearish"
                            else:
                                category = "neutral"
                            
                            # Store aggregated result
                            agg_doc = {
                                "id": f"sentiment_agg_{symbol}_{int(datetime.utcnow().timestamp())}",
                                "doc_type": "sentiment_aggregation",
                                "symbol": symbol,
                                "sentiment_score": sentiment_score,
                                "average_polarity": avg_sentiment,
                                "category": category,
                                "sources": dict(sources),
                                "sample_size": len(sentiment_scores),
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                                "created_at": datetime.utcnow().isoformat() + "Z"
                            }
                            
                            await self.database.upsert_market_data(agg_doc)
                            
                            logger.info(
                                "Sentiment aggregated",
                                symbol=symbol,
                                score=sentiment_score,
                                category=category,
                                sample_size=len(sentiment_scores)
                            )
                
                except Exception as e:
                    logger.error(f"Error aggregating sentiment for {symbol}", error=str(e))
            
            self.stats["aggregation_runs"] += 1
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error("Error in sentiment aggregation", error=str(e))
    
    async def run_scheduled_tasks(self):
        """Main scheduler loop"""
        self.running = True
        
        logger.info("Sentiment analysis scheduler started")
        
        # Initial collection
        await self.collect_fear_greed()
        await self.collect_news_sentiment()
        
        last_reddit = datetime.utcnow()
        last_news = datetime.utcnow()
        last_twitter = datetime.utcnow()
        last_fear_greed = datetime.utcnow()
        last_aggregation = datetime.utcnow()
        
        while self.running:
            try:
                now = datetime.utcnow()
                
                # Reddit sentiment - every 2 hours
                if (now - last_reddit).seconds >= 7200:  # 2 hours
                    await self.collect_reddit_sentiment()
                    last_reddit = now
                
                # News sentiment - every hour
                if (now - last_news).seconds >= 3600:  # 1 hour
                    await self.collect_news_sentiment()
                    last_news = now
                
                # Twitter sentiment - every 30 minutes (if configured)
                if (now - last_twitter).seconds >= 1800:  # 30 minutes
                    await self.collect_twitter_sentiment()
                    last_twitter = now
                
                # Fear & Greed - every 6 hours
                if (now - last_fear_greed).seconds >= 21600:  # 6 hours
                    await self.collect_fear_greed()
                    last_fear_greed = now
                
                # Sentiment aggregation - every 30 minutes
                if (now - last_aggregation).seconds >= 1800:  # 30 minutes
                    await self.aggregate_sentiment()
                    last_aggregation = now
                
                # Wait before next iteration
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)
                logger.error("Error in scheduler main loop", error=str(e))
                await asyncio.sleep(60)
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Sentiment scheduler stopping...")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        return {
            "running": self.running,
            "stats": self.stats,
            "tracked_symbols": len(self.crypto_symbols)
        }


async def main():
    """Main entry point"""
    scheduler = SentimentScheduler()
    
    try:
        await scheduler.initialize()
        await scheduler.run_scheduled_tasks()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error("Scheduler error", error=str(e))
    finally:
        await scheduler.stop()
        await scheduler.cleanup()


if __name__ == "__main__":
    from collections import defaultdict
    from datetime import timedelta
    asyncio.run(main())

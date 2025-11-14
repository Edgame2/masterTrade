"""
Sentiment Data Store - TimescaleDB-optimized storage for sentiment analysis data

This module provides high-performance access to sentiment data from multiple sources:
- Social media (Twitter, Reddit, LunarCrush)
- News articles
- Market sentiment indicators

Features:
- Real-time sentiment tracking
- Sentiment trend analysis
- Source-specific sentiment queries
- Sentiment aggregation (hourly, daily)
- Volume-weighted sentiment scores

Usage:
    store = SentimentDataStore(database)
    
    # Store sentiment data
    await store.store_sentiment(
        asset="BTC",
        source="twitter",
        sentiment_score=0.65,
        sentiment_label="bullish",
        volume=150,
        timestamp=datetime.now()
    )
    
    # Get sentiment trends
    trends = await store.get_sentiment_trend(
        asset="BTC",
        hours=24
    )
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
import structlog

from prometheus_client import Counter, Histogram

logger = structlog.get_logger()

# Metrics
sentiment_inserts = Counter('sentiment_data_inserts_total', 'Total sentiment inserts', ['asset', 'source'])
sentiment_queries = Counter('sentiment_data_queries_total', 'Total sentiment queries', ['query_type'])
sentiment_query_duration = Histogram('sentiment_query_seconds', 'Sentiment query duration', ['query_type'])


class SentimentDataStore:
    """
    TimescaleDB-optimized sentiment data storage
    
    Stores and aggregates sentiment data from multiple sources with:
    - Real-time sentiment scores (-1.0 to 1.0)
    - Sentiment labels (bearish, neutral, bullish)
    - Volume (mention count)
    - Engagement metrics
    - Hourly and daily aggregates
    """
    
    SENTIMENT_LABELS = {
        'bearish': (-1.0, -0.2),
        'neutral': (-0.2, 0.2),
        'bullish': (0.2, 1.0)
    }
    
    def __init__(self, database):
        """
        Initialize sentiment data store
        
        Args:
            database: Database connection instance
        """
        self.database = database
    
    def _classify_sentiment(self, score: float) -> str:
        """
        Classify sentiment score into label
        
        Args:
            score: Sentiment score (-1.0 to 1.0)
        
        Returns:
            Sentiment label (bearish, neutral, bullish)
        """
        if score <= -0.2:
            return 'bearish'
        elif score >= 0.2:
            return 'bullish'
        else:
            return 'neutral'
    
    async def store_sentiment(
        self,
        asset: str,
        source: str,
        timestamp: datetime,
        sentiment_score: float,
        sentiment_label: Optional[str] = None,
        volume: Optional[int] = None,
        engagement_score: Optional[float] = None,
        entities: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Store single sentiment data point
        
        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            source: Data source (twitter, reddit, news, lunarcrush)
            timestamp: Data timestamp
            sentiment_score: Sentiment score (-1.0 to 1.0)
            sentiment_label: Bearish/neutral/bullish (auto-classified if None)
            volume: Number of mentions/posts
            engagement_score: Engagement metric (likes, retweets, etc.)
            entities: Mentioned entities, hashtags
            metadata: Additional metadata
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Auto-classify sentiment if not provided
            if sentiment_label is None:
                sentiment_label = self._classify_sentiment(sentiment_score)
            
            query = """
                INSERT INTO sentiment_data (
                    time, asset, source, sentiment_score, sentiment_label,
                    volume, engagement_score, entities, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (time, asset, source)
                DO UPDATE SET
                    sentiment_score = EXCLUDED.sentiment_score,
                    sentiment_label = EXCLUDED.sentiment_label,
                    volume = EXCLUDED.volume,
                    engagement_score = EXCLUDED.engagement_score,
                    entities = EXCLUDED.entities,
                    metadata = EXCLUDED.metadata
            """
            
            await self.database.execute(
                query,
                timestamp, asset, source,
                Decimal(str(sentiment_score)),
                sentiment_label,
                volume,
                Decimal(str(engagement_score)) if engagement_score else None,
                entities,
                metadata
            )
            
            sentiment_inserts.labels(asset=asset, source=source).inc()
            
            logger.debug(
                "Stored sentiment data",
                asset=asset,
                source=source,
                score=sentiment_score,
                label=sentiment_label
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to store sentiment data",
                asset=asset,
                source=source,
                error=str(e),
                exc_info=True
            )
            return False
    
    async def store_sentiments_batch(
        self,
        sentiments: List[Dict[str, Any]]
    ) -> int:
        """
        Store multiple sentiment data points in batch
        
        Args:
            sentiments: List of sentiment dicts
        
        Returns:
            Number of records inserted
        """
        if not sentiments:
            return 0
        
        try:
            query = """
                INSERT INTO sentiment_data (
                    time, asset, source, sentiment_score, sentiment_label,
                    volume, engagement_score, entities, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (time, asset, source) DO NOTHING
            """
            
            batch_data = []
            for sent in sentiments:
                label = sent.get('sentiment_label') or self._classify_sentiment(sent['sentiment_score'])
                
                batch_data.append((
                    sent['timestamp'],
                    sent['asset'],
                    sent['source'],
                    Decimal(str(sent['sentiment_score'])),
                    label,
                    sent.get('volume'),
                    Decimal(str(sent['engagement_score'])) if sent.get('engagement_score') else None,
                    sent.get('entities'),
                    sent.get('metadata')
                ))
            
            await self.database.executemany(query, batch_data)
            
            for sent in sentiments:
                sentiment_inserts.labels(asset=sent['asset'], source=sent['source']).inc()
            
            logger.info(
                "Stored sentiment batch",
                count=len(sentiments)
            )
            
            return len(sentiments)
            
        except Exception as e:
            logger.error(
                "Failed to store sentiment batch",
                count=len(sentiments),
                error=str(e),
                exc_info=True
            )
            return 0
    
    async def get_sentiment(
        self,
        asset: str,
        start_time: datetime,
        end_time: datetime,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get raw sentiment data for time range
        
        Args:
            asset: Asset symbol
            start_time: Start of time range
            end_time: End of time range
            source: Filter by source (optional)
        
        Returns:
            List of sentiment data dicts
        """
        with sentiment_query_duration.labels(query_type='raw').time():
            try:
                if source:
                    query = """
                        SELECT 
                            time,
                            asset,
                            source,
                            sentiment_score,
                            sentiment_label,
                            volume,
                            engagement_score
                        FROM sentiment_data
                        WHERE asset = $1 
                            AND source = $2
                            AND time >= $3
                            AND time <= $4
                        ORDER BY time ASC
                    """
                    rows = await self.database.fetch(query, asset, source, start_time, end_time)
                else:
                    query = """
                        SELECT 
                            time,
                            asset,
                            source,
                            sentiment_score,
                            sentiment_label,
                            volume,
                            engagement_score
                        FROM sentiment_data
                        WHERE asset = $1 
                            AND time >= $2
                            AND time <= $3
                        ORDER BY time ASC
                    """
                    rows = await self.database.fetch(query, asset, start_time, end_time)
                
                sentiment_queries.labels(query_type='raw').inc()
                
                return [
                    {
                        'time': row['time'],
                        'asset': row['asset'],
                        'source': row['source'],
                        'sentiment_score': float(row['sentiment_score']),
                        'sentiment_label': row['sentiment_label'],
                        'volume': row['volume'],
                        'engagement_score': float(row['engagement_score']) if row.get('engagement_score') else None
                    }
                    for row in rows
                ]
                
            except Exception as e:
                logger.error(
                    "Failed to get sentiment data",
                    asset=asset,
                    error=str(e)
                )
                return []
    
    async def get_sentiment_aggregated(
        self,
        asset: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = '1h',
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated sentiment data (uses continuous aggregates)
        
        Args:
            asset: Asset symbol
            start_time: Start of time range
            end_time: End of time range
            interval: Aggregation interval ('1h' or '1d')
            source: Filter by source (optional)
        
        Returns:
            List of aggregated sentiment dicts
        """
        with sentiment_query_duration.labels(query_type='aggregated').time():
            try:
                view_name = 'sentiment_hourly' if interval == '1h' else 'sentiment_daily'
                
                if source:
                    query = f"""
                        SELECT 
                            bucket as time,
                            asset,
                            source,
                            avg_sentiment,
                            sentiment_volatility,
                            total_mentions,
                            total_engagement,
                            data_points
                        FROM {view_name}
                        WHERE asset = $1 
                            AND source = $2
                            AND bucket >= $3
                            AND bucket <= $4
                        ORDER BY bucket ASC
                    """
                    rows = await self.database.fetch(query, asset, source, start_time, end_time)
                else:
                    query = f"""
                        SELECT 
                            bucket as time,
                            asset,
                            source,
                            avg_sentiment,
                            sentiment_volatility,
                            total_mentions,
                            total_engagement,
                            data_points
                        FROM {view_name}
                        WHERE asset = $1 
                            AND bucket >= $2
                            AND bucket <= $3
                        ORDER BY bucket ASC
                    """
                    rows = await self.database.fetch(query, asset, start_time, end_time)
                
                sentiment_queries.labels(query_type='aggregated').inc()
                
                return [
                    {
                        'time': row['time'],
                        'asset': row['asset'],
                        'source': row['source'],
                        'avg_sentiment': float(row['avg_sentiment']),
                        'sentiment_volatility': float(row['sentiment_volatility']) if row['sentiment_volatility'] else 0,
                        'total_mentions': row['total_mentions'],
                        'total_engagement': float(row['total_engagement']) if row['total_engagement'] else 0,
                        'data_points': row['data_points']
                    }
                    for row in rows
                ]
                
            except Exception as e:
                logger.error(
                    "Failed to get aggregated sentiment",
                    asset=asset,
                    interval=interval,
                    error=str(e)
                )
                return []
    
    async def get_sentiment_trend(
        self,
        asset: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get sentiment trend with current vs historical comparison
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
        
        Returns:
            Dict with current sentiment, change, trend direction
        """
        with sentiment_query_duration.labels(query_type='trend').time():
            try:
                query = """
                    WITH recent AS (
                        SELECT AVG(sentiment_score) as recent_sentiment
                        FROM sentiment_data
                        WHERE asset = $1
                            AND time >= NOW() - INTERVAL '1 hour'
                    ),
                    historical AS (
                        SELECT AVG(sentiment_score) as historical_sentiment
                        FROM sentiment_data
                        WHERE asset = $1
                            AND time >= NOW() - ($2 || ' hours')::INTERVAL
                            AND time < NOW() - INTERVAL '1 hour'
                    )
                    SELECT 
                        recent_sentiment,
                        historical_sentiment,
                        (recent_sentiment - historical_sentiment) as sentiment_change,
                        CASE 
                            WHEN (recent_sentiment - historical_sentiment) > 0.1 THEN 'improving'
                            WHEN (recent_sentiment - historical_sentiment) < -0.1 THEN 'declining'
                            ELSE 'stable'
                        END as trend
                    FROM recent, historical
                """
                
                row = await self.database.fetchrow(query, asset, hours)
                
                sentiment_queries.labels(query_type='trend').inc()
                
                if not row:
                    return {}
                
                return {
                    'asset': asset,
                    'recent_sentiment': float(row['recent_sentiment']) if row['recent_sentiment'] else 0,
                    'historical_sentiment': float(row['historical_sentiment']) if row['historical_sentiment'] else 0,
                    'sentiment_change': float(row['sentiment_change']) if row['sentiment_change'] else 0,
                    'trend': row['trend']
                }
                
            except Exception as e:
                logger.error(
                    "Failed to get sentiment trend",
                    asset=asset,
                    error=str(e)
                )
                return {}
    
    async def get_sentiment_by_source(
        self,
        asset: str,
        hours: int = 24
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get sentiment breakdown by source
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
        
        Returns:
            Dict mapping source name to sentiment metrics
        """
        with sentiment_query_duration.labels(query_type='by_source').time():
            try:
                query = """
                    SELECT 
                        source,
                        AVG(sentiment_score) as avg_sentiment,
                        STDDEV(sentiment_score) as sentiment_stddev,
                        SUM(volume) as total_mentions,
                        SUM(engagement_score) as total_engagement,
                        COUNT(*) as data_points
                    FROM sentiment_data
                    WHERE asset = $1
                        AND time >= NOW() - ($2 || ' hours')::INTERVAL
                    GROUP BY source
                    ORDER BY total_mentions DESC
                """
                
                rows = await self.database.fetch(query, asset, hours)
                
                sentiment_queries.labels(query_type='by_source').inc()
                
                return {
                    row['source']: {
                        'avg_sentiment': float(row['avg_sentiment']),
                        'sentiment_stddev': float(row['sentiment_stddev']) if row['sentiment_stddev'] else 0,
                        'total_mentions': row['total_mentions'],
                        'total_engagement': float(row['total_engagement']) if row['total_engagement'] else 0,
                        'data_points': row['data_points']
                    }
                    for row in rows
                }
                
            except Exception as e:
                logger.error(
                    "Failed to get sentiment by source",
                    asset=asset,
                    error=str(e)
                )
                return {}
    
    async def get_sentiment_distribution(
        self,
        asset: str,
        hours: int = 24
    ) -> Dict[str, int]:
        """
        Get distribution of sentiment labels
        
        Args:
            asset: Asset symbol
            hours: Hours to analyze
        
        Returns:
            Dict with counts for bearish, neutral, bullish
        """
        with sentiment_query_duration.labels(query_type='distribution').time():
            try:
                query = """
                    SELECT 
                        sentiment_label,
                        COUNT(*) as count
                    FROM sentiment_data
                    WHERE asset = $1
                        AND time >= NOW() - ($2 || ' hours')::INTERVAL
                    GROUP BY sentiment_label
                """
                
                rows = await self.database.fetch(query, asset, hours)
                
                sentiment_queries.labels(query_type='distribution').inc()
                
                distribution = {'bearish': 0, 'neutral': 0, 'bullish': 0}
                for row in rows:
                    distribution[row['sentiment_label']] = row['count']
                
                return distribution
                
            except Exception as e:
                logger.error(
                    "Failed to get sentiment distribution",
                    asset=asset,
                    error=str(e)
                )
                return {'bearish': 0, 'neutral': 0, 'bullish': 0}
    
    async def get_latest_sentiment(
        self,
        asset: str,
        source: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest sentiment reading
        
        Args:
            asset: Asset symbol
            source: Filter by source (optional)
        
        Returns:
            Dict with latest sentiment data or None
        """
        try:
            if source:
                query = """
                    SELECT 
                        time,
                        asset,
                        source,
                        sentiment_score,
                        sentiment_label,
                        volume,
                        engagement_score
                    FROM sentiment_data
                    WHERE asset = $1 AND source = $2
                    ORDER BY time DESC
                    LIMIT 1
                """
                row = await self.database.fetchrow(query, asset, source)
            else:
                query = """
                    SELECT 
                        time,
                        asset,
                        source,
                        sentiment_score,
                        sentiment_label,
                        volume,
                        engagement_score
                    FROM sentiment_data
                    WHERE asset = $1
                    ORDER BY time DESC
                    LIMIT 1
                """
                row = await self.database.fetchrow(query, asset)
            
            if not row:
                return None
            
            return {
                'time': row['time'],
                'asset': row['asset'],
                'source': row['source'],
                'sentiment_score': float(row['sentiment_score']),
                'sentiment_label': row['sentiment_label'],
                'volume': row['volume'],
                'engagement_score': float(row['engagement_score']) if row.get('engagement_score') else None
            }
            
        except Exception as e:
            logger.error(
                "Failed to get latest sentiment",
                asset=asset,
                error=str(e)
            )
            return None

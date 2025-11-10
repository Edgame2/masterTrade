"""
Enhanced Historical Data Collection System

Comprehensive system for collecting and managing historical data across all timeframes
for backtesting and strategy analysis.

Features:
- Support for all timeframes from 1m to 1M (monthly)
- Parallel data collection for multiple symbols
- Gap detection and automatic backfilling
- Data validation and quality checks
- Progress tracking and resumable downloads
- Efficient batch storage and indexing
- Export capabilities for backtesting engines
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
import time
import structlog
from dataclasses import dataclass, asdict
from enum import Enum
import pandas as pd
import numpy as np

from config import settings
from database import Database
from historical_data_collector import HistoricalDataCollector

logger = structlog.get_logger()

class TimeframeType(Enum):
    """All supported timeframes"""
    TICK = "tick"          # Tick data (not from Binance)
    ONE_SECOND = "1s"      # 1 second
    ONE_MINUTE = "1m"      # 1 minute
    THREE_MINUTE = "3m"    # 3 minutes
    FIVE_MINUTE = "5m"     # 5 minutes
    FIFTEEN_MINUTE = "15m" # 15 minutes
    THIRTY_MINUTE = "30m"  # 30 minutes
    ONE_HOUR = "1h"        # 1 hour
    TWO_HOUR = "2h"        # 2 hours
    FOUR_HOUR = "4h"       # 4 hours
    SIX_HOUR = "6h"        # 6 hours
    EIGHT_HOUR = "8h"      # 8 hours
    TWELVE_HOUR = "12h"    # 12 hours
    ONE_DAY = "1d"         # 1 day
    THREE_DAY = "3d"       # 3 days
    ONE_WEEK = "1w"        # 1 week
    ONE_MONTH = "1M"       # 1 month

@dataclass
class CollectionProgress:
    """Track collection progress"""
    symbol: str
    timeframe: str
    total_expected: int
    total_collected: int
    start_time: datetime
    end_time: Optional[datetime]
    status: str  # 'in_progress', 'completed', 'failed'
    error_message: Optional[str] = None
    
@dataclass
class DataQualityMetrics:
    """Data quality assessment"""
    symbol: str
    timeframe: str
    total_records: int
    missing_gaps: int
    duplicate_records: int
    invalid_records: int
    completeness_pct: float
    quality_score: float  # 0-100
    last_check: datetime

class EnhancedHistoricalDataCollector:
    """
    Enhanced historical data collection with comprehensive timeframe support
    """
    
    # All Binance supported intervals
    BINANCE_INTERVALS = [
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M"
    ]
    
    # Maximum lookback days for each timeframe
    MAX_LOOKBACK_DAYS = {
        "1m": 90,      # 1 minute: 90 days
        "3m": 180,     # 3 minutes: 180 days
        "5m": 180,     # 5 minutes: 180 days
        "15m": 365,    # 15 minutes: 1 year
        "30m": 365,    # 30 minutes: 1 year
        "1h": 730,     # 1 hour: 2 years
        "2h": 730,     # 2 hours: 2 years
        "4h": 1095,    # 4 hours: 3 years
        "6h": 1095,    # 6 hours: 3 years
        "8h": 1095,    # 8 hours: 3 years
        "12h": 1460,   # 12 hours: 4 years
        "1d": 1825,    # 1 day: 5 years
        "3d": 1825,    # 3 days: 5 years
        "1w": 1825,    # 1 week: 5 years
        "1M": 1825,    # 1 month: 5 years
    }
    
    def __init__(self, database: Database):
        self.database = database
        self.base_collector = HistoricalDataCollector(database)
        self.progress_tracker: Dict[str, CollectionProgress] = {}
        self.quality_metrics: Dict[str, DataQualityMetrics] = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.base_collector.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.base_collector.disconnect()
    
    async def collect_comprehensive_historical_data(
        self,
        symbols: List[str],
        timeframes: List[str] = None,
        days_back: Dict[str, int] = None,
        parallel_symbols: int = 3,
        parallel_timeframes: int = 2
    ) -> Dict[str, Dict[str, int]]:
        """
        Collect comprehensive historical data for multiple symbols and timeframes
        
        Args:
            symbols: List of trading symbols
            timeframes: List of timeframes (default: all Binance intervals)
            days_back: Dictionary of timeframe -> days to collect
            parallel_symbols: Number of symbols to process in parallel
            parallel_timeframes: Number of timeframes per symbol in parallel
            
        Returns:
            Dictionary with collection statistics
        """
        if timeframes is None:
            timeframes = self.BINANCE_INTERVALS
            
        if days_back is None:
            days_back = self.MAX_LOOKBACK_DAYS
            
        logger.info(
            "Starting comprehensive historical data collection",
            total_symbols=len(symbols),
            total_timeframes=len(timeframes),
            parallel_symbols=parallel_symbols,
            parallel_timeframes=parallel_timeframes
        )
        
        results = {}
        
        # Process symbols in batches
        for i in range(0, len(symbols), parallel_symbols):
            symbol_batch = symbols[i:i + parallel_symbols]
            
            # Collect data for this batch of symbols
            batch_tasks = [
                self._collect_symbol_all_timeframes(
                    symbol, timeframes, days_back, parallel_timeframes
                )
                for symbol in symbol_batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Store results
            for symbol, result in zip(symbol_batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error collecting data for {symbol}: {result}")
                    results[symbol] = {}
                else:
                    results[symbol] = result
                    
            # Delay between symbol batches to avoid rate limiting
            await asyncio.sleep(5)
            
        # Generate summary report
        await self._generate_collection_report(results)
        
        return results
    
    async def _collect_symbol_all_timeframes(
        self,
        symbol: str,
        timeframes: List[str],
        days_back: Dict[str, int],
        parallel_timeframes: int
    ) -> Dict[str, int]:
        """Collect data for all timeframes of a single symbol"""
        
        logger.info(f"Starting collection for {symbol}")
        
        results = {}
        
        # Process timeframes in batches
        for i in range(0, len(timeframes), parallel_timeframes):
            timeframe_batch = timeframes[i:i + parallel_timeframes]
            
            batch_tasks = [
                self._collect_with_progress_tracking(
                    symbol, tf, days_back.get(tf, 365)
                )
                for tf in timeframe_batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for tf, result in zip(timeframe_batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error collecting {symbol} {tf}: {result}")
                    results[tf] = 0
                else:
                    results[tf] = result
                    
            # Small delay between timeframe batches
            await asyncio.sleep(2)
            
        return results
    
    async def _collect_with_progress_tracking(
        self,
        symbol: str,
        timeframe: str,
        days_back: int
    ) -> int:
        """Collect data with progress tracking"""
        
        progress_key = f"{symbol}_{timeframe}"
        
        # Calculate expected records
        interval_minutes = self._interval_to_minutes(timeframe)
        expected_records = int((days_back * 24 * 60) / interval_minutes)
        
        # Initialize progress tracker
        self.progress_tracker[progress_key] = CollectionProgress(
            symbol=symbol,
            timeframe=timeframe,
            total_expected=expected_records,
            total_collected=0,
            start_time=datetime.utcnow(),
            end_time=None,
            status='in_progress'
        )
        
        try:
            # Collect data
            record_count = await self.base_collector.collect_historical_data_for_symbol(
                symbol=symbol,
                interval=timeframe,
                days_back=days_back
            )
            
            # Update progress
            self.progress_tracker[progress_key].total_collected = record_count
            self.progress_tracker[progress_key].end_time = datetime.utcnow()
            self.progress_tracker[progress_key].status = 'completed'
            
            # Run data quality check
            await self._check_data_quality(symbol, timeframe)
            
            return record_count
            
        except Exception as e:
            self.progress_tracker[progress_key].status = 'failed'
            self.progress_tracker[progress_key].error_message = str(e)
            self.progress_tracker[progress_key].end_time = datetime.utcnow()
            raise
    
    def _interval_to_minutes(self, interval: str) -> int:
        """Convert interval string to minutes"""
        mapping = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
            "1d": 1440, "3d": 4320, "1w": 10080, "1M": 43200
        }
        return mapping.get(interval, 1)
    
    async def _check_data_quality(self, symbol: str, timeframe: str) -> DataQualityMetrics:
        """Check data quality and completeness"""
        
        logger.info(f"Checking data quality for {symbol} {timeframe}")
        
        # Get all data for this symbol/timeframe
        data = await self.database.get_market_data_for_analysis(
            symbol=symbol,
            interval=timeframe,
            hours_back=self.MAX_LOOKBACK_DAYS.get(timeframe, 365) * 24
        )
        
        if not data:
            return DataQualityMetrics(
                symbol=symbol,
                timeframe=timeframe,
                total_records=0,
                missing_gaps=0,
                duplicate_records=0,
                invalid_records=0,
                completeness_pct=0.0,
                quality_score=0.0,
                last_check=datetime.utcnow()
            )
        
        total_records = len(data)
        
        # Check for duplicates
        timestamps = [item['timestamp'] for item in data]
        duplicate_records = len(timestamps) - len(set(timestamps))
        
        # Check for invalid data
        invalid_records = sum(1 for item in data if not self._validate_record(item))
        
        # Check for gaps
        missing_gaps = await self._count_missing_gaps(symbol, timeframe, data)
        
        # Calculate completeness
        interval_minutes = self._interval_to_minutes(timeframe)
        expected_records = self.progress_tracker[f"{symbol}_{timeframe}"].total_expected
        completeness_pct = (total_records / expected_records * 100) if expected_records > 0 else 0
        
        # Calculate quality score (0-100)
        quality_score = self._calculate_quality_score(
            total_records, missing_gaps, duplicate_records, invalid_records, completeness_pct
        )
        
        metrics = DataQualityMetrics(
            symbol=symbol,
            timeframe=timeframe,
            total_records=total_records,
            missing_gaps=missing_gaps,
            duplicate_records=duplicate_records,
            invalid_records=invalid_records,
            completeness_pct=completeness_pct,
            quality_score=quality_score,
            last_check=datetime.utcnow()
        )
        
        self.quality_metrics[f"{symbol}_{timeframe}"] = metrics
        
        # Store metrics in database
        await self._store_quality_metrics(metrics)
        
        logger.info(
            f"Data quality check completed for {symbol} {timeframe}",
            quality_score=quality_score,
            completeness=completeness_pct
        )
        
        return metrics
    
    def _validate_record(self, record: Dict) -> bool:
        """Validate a single data record"""
        try:
            # Check required fields
            required_fields = ['open_price', 'high_price', 'low_price', 'close_price', 'volume']
            if not all(field in record for field in required_fields):
                return False
                
            # Check price relationships
            high = float(record['high_price'])
            low = float(record['low_price'])
            open_price = float(record['open_price'])
            close = float(record['close_price'])
            
            if high < low or high < open_price or high < close or low > open_price or low > close:
                return False
                
            # Check for zero or negative values
            if any(float(record[field]) <= 0 for field in required_fields):
                return False
                
            return True
        except (ValueError, KeyError):
            return False
    
    async def _count_missing_gaps(self, symbol: str, timeframe: str, data: List[Dict]) -> int:
        """Count missing data gaps"""
        if len(data) < 2:
            return 0
            
        timestamps = sorted([datetime.fromisoformat(item['timestamp'].rstrip('Z')) for item in data])
        interval_seconds = self._interval_to_minutes(timeframe) * 60
        
        gaps = 0
        for i in range(len(timestamps) - 1):
            expected_next = timestamps[i] + timedelta(seconds=interval_seconds)
            if (timestamps[i + 1] - expected_next).total_seconds() > interval_seconds:
                gaps += 1
                
        return gaps
    
    def _calculate_quality_score(
        self,
        total: int,
        gaps: int,
        duplicates: int,
        invalid: int,
        completeness: float
    ) -> float:
        """Calculate overall quality score"""
        if total == 0:
            return 0.0
            
        # Penalties
        gap_penalty = (gaps / total) * 30
        duplicate_penalty = (duplicates / total) * 20
        invalid_penalty = (invalid / total) * 30
        completeness_score = completeness * 0.2
        
        score = 100 - gap_penalty - duplicate_penalty - invalid_penalty + completeness_score
        return max(0.0, min(100.0, score))
    
    async def _store_quality_metrics(self, metrics: DataQualityMetrics):
        """Store quality metrics in database"""
        try:
            quality_doc = {
                "id": f"quality_{metrics.symbol}_{metrics.timeframe}_{int(metrics.last_check.timestamp())}",
                "type": "data_quality",
                **asdict(metrics),
                "last_check": metrics.last_check.isoformat() + "Z"
            }
            await self.database.upsert_item(quality_doc, container_name="DataQuality")
        except Exception as e:
            logger.error(f"Failed to store quality metrics: {e}")
    
    async def _generate_collection_report(self, results: Dict[str, Dict[str, int]]):
        """Generate comprehensive collection report"""
        
        logger.info("=" * 80)
        logger.info("HISTORICAL DATA COLLECTION REPORT")
        logger.info("=" * 80)
        
        total_records = 0
        total_timeframes = 0
        
        for symbol, timeframes in results.items():
            symbol_total = sum(timeframes.values())
            total_records += symbol_total
            total_timeframes += len(timeframes)
            
            logger.info(f"\n{symbol}: {symbol_total:,} records across {len(timeframes)} timeframes")
            for tf, count in sorted(timeframes.items()):
                progress_key = f"{symbol}_{tf}"
                progress = self.progress_tracker.get(progress_key)
                quality = self.quality_metrics.get(progress_key)
                
                status_icon = "✓" if progress and progress.status == 'completed' else "✗"
                quality_icon = "🟢" if quality and quality.quality_score > 90 else "🟡" if quality and quality.quality_score > 70 else "🔴"
                
                logger.info(f"  {status_icon} {tf:6s}: {count:8,} records {quality_icon}")
                
                if quality:
                    logger.info(f"    Quality: {quality.quality_score:.1f}/100, Completeness: {quality.completeness_pct:.1f}%")
        
        logger.info(f"\nTotal: {total_records:,} records collected")
        logger.info(f"Total timeframes processed: {total_timeframes}")
        logger.info("=" * 80)
        
    async def export_to_parquet(
        self,
        symbol: str,
        timeframe: str,
        output_path: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ):
        """Export historical data to Parquet format for backtesting"""
        
        logger.info(f"Exporting {symbol} {timeframe} to Parquet: {output_path}")
        
        # Get data
        hours_back = None
        if start_date and end_date:
            hours_back = int((end_date - start_date).total_seconds() / 3600)
        else:
            hours_back = self.MAX_LOOKBACK_DAYS.get(timeframe, 365) * 24
            
        data = await self.database.get_market_data_for_analysis(
            symbol=symbol,
            interval=timeframe,
            hours_back=hours_back
        )
        
        if not data:
            logger.warning(f"No data found for {symbol} {timeframe}")
            return
            
        # Convert to DataFrame
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')
        
        # Convert price columns to float
        for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume']:
            df[col] = df[col].astype(float)
            
        # Sort by timestamp
        df = df.sort_index()
        
        # Save to Parquet
        df.to_parquet(output_path, compression='snappy')
        
        logger.info(f"Exported {len(df)} records to {output_path}")
    
    async def get_collection_status(self) -> Dict:
        """Get current collection status"""
        in_progress = [p for p in self.progress_tracker.values() if p.status == 'in_progress']
        completed = [p for p in self.progress_tracker.values() if p.status == 'completed']
        failed = [p for p in self.progress_tracker.values() if p.status == 'failed']
        
        return {
            "in_progress": len(in_progress),
            "completed": len(completed),
            "failed": len(failed),
            "total": len(self.progress_tracker),
            "details": {
                "in_progress": [asdict(p) for p in in_progress],
                "completed": [asdict(p) for p in completed],
                "failed": [asdict(p) for p in failed]
            }
        }


# CLI Tool for historical data collection
async def main():
    """Main entry point for historical data collection"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Historical Data Collection")
    parser.add_argument("--symbols", nargs="+", help="Symbols to collect (default: all configured)")
    parser.add_argument("--timeframes", nargs="+", help="Timeframes to collect (default: all)")
    parser.add_argument("--days", type=int, help="Days back to collect")
    parser.add_argument("--parallel-symbols", type=int, default=3, help="Parallel symbols")
    parser.add_argument("--parallel-timeframes", type=int, default=2, help="Parallel timeframes")
    parser.add_argument("--export", help="Export to Parquet directory")
    
    args = parser.parse_args()
    
    database = Database()
    
    async with database, EnhancedHistoricalDataCollector(database) as collector:
        symbols = args.symbols or settings.DEFAULT_SYMBOLS
        timeframes = args.timeframes or collector.BINANCE_INTERVALS
        
        days_back = None
        if args.days:
            days_back = {tf: args.days for tf in timeframes}
        
        # Collect data
        results = await collector.collect_comprehensive_historical_data(
            symbols=symbols,
            timeframes=timeframes,
            days_back=days_back,
            parallel_symbols=args.parallel_symbols,
            parallel_timeframes=args.parallel_timeframes
        )
        
        # Export if requested
        if args.export:
            import os
            os.makedirs(args.export, exist_ok=True)
            
            for symbol in symbols:
                for timeframe in timeframes:
                    output_file = os.path.join(args.export, f"{symbol}_{timeframe}.parquet")
                    await collector.export_to_parquet(symbol, timeframe, output_file)
        
        # Print final status
        status = await collector.get_collection_status()
        print(f"\nCollection completed:")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")

if __name__ == "__main__":
    asyncio.run(main())

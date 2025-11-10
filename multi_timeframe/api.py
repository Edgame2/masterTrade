"""
Multi-Timeframe Analysis REST API

Provides endpoints for:
- Timeframe synchronization
- Trend analysis across timeframes
- Confluence detection
- Divergence identification
- Aggregated signal generation
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List, Optional
import logging

from .timeframe_synchronizer import (
    Timeframe,
    TimeframeBar,
    TimeframeSynchronizer,
)
from .trend_analyzer import TrendAnalyzer
from .confluence_detector import ConfluenceDetector
from .divergence_detector import DivergenceDetector
from .signal_aggregator import SignalAggregator

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/multi-timeframe", tags=["Multi-Timeframe Analysis"])

# Initialize components
synchronizer = TimeframeSynchronizer()
trend_analyzer = TrendAnalyzer(synchronizer)
confluence_detector = ConfluenceDetector(trend_analyzer)
divergence_detector = DivergenceDetector(trend_analyzer)
signal_aggregator = SignalAggregator(
    synchronizer,
    trend_analyzer,
    confluence_detector,
    divergence_detector,
)


# Request/Response Models
class AddBarRequest(BaseModel):
    """Request to add a bar"""
    symbol: str
    timeframe: str  # e.g., "1m", "5m", "1h"
    timestamp: str  # ISO format
    open: float
    high: float
    low: float
    close: float
    volume: float


class AggregateRequest(BaseModel):
    """Request to aggregate to higher timeframe"""
    symbol: str
    from_timeframe: str
    to_timeframe: str
    count: int = 100


class AnalyzeTrendRequest(BaseModel):
    """Request to analyze trend"""
    symbol: str
    timeframe: str
    lookback_periods: int = 50


class DetectConfluenceRequest(BaseModel):
    """Request to detect confluence"""
    symbol: str
    timeframes: List[str]
    reference_direction: Optional[str] = None


class DetectDivergenceRequest(BaseModel):
    """Request to detect divergence"""
    symbol: str
    higher_timeframe: str
    lower_timeframe: str


class GenerateSignalRequest(BaseModel):
    """Request to generate aggregated signal"""
    symbol: str
    timeframes: Optional[List[str]] = None


class GenerateEntrySignalRequest(BaseModel):
    """Request to generate entry signal"""
    symbol: str
    higher_timeframes: Optional[List[str]] = None
    lower_timeframes: Optional[List[str]] = None


# Helper functions
def parse_timeframe(tf_str: str) -> Timeframe:
    """Parse timeframe string to Timeframe enum"""
    mapping = {
        "1m": Timeframe.M1,
        "5m": Timeframe.M5,
        "15m": Timeframe.M15,
        "30m": Timeframe.M30,
        "1h": Timeframe.H1,
        "4h": Timeframe.H4,
        "1d": Timeframe.D1,
        "1w": Timeframe.W1,
    }
    
    tf = mapping.get(tf_str.lower())
    if not tf:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe: {tf_str}. Valid: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"
        )
    return tf


def parse_timeframes(tf_list: List[str]) -> List[Timeframe]:
    """Parse list of timeframe strings"""
    return [parse_timeframe(tf) for tf in tf_list]


# Endpoints

# Timeframe Synchronization
@router.post("/bars/add")
async def add_bar(request: AddBarRequest):
    """Add a bar to the synchronizer"""
    try:
        timeframe = parse_timeframe(request.timeframe)
        
        # Parse timestamp
        timestamp = datetime.fromisoformat(request.timestamp.replace('Z', '+00:00'))
        
        bar = TimeframeBar(
            symbol=request.symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open=request.open,
            high=request.high,
            low=request.low,
            close=request.close,
            volume=request.volume,
        )
        
        synchronizer.add_bar(bar)
        
        return {
            "success": True,
            "message": f"Bar added for {request.symbol} {request.timeframe}",
        }
    
    except Exception as e:
        logger.error(f"Error adding bar: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bars/{symbol}/{timeframe}")
async def get_bars(
    symbol: str,
    timeframe: str,
    count: Optional[int] = Query(None, description="Number of bars to return")
):
    """Get bars for a symbol and timeframe"""
    try:
        tf = parse_timeframe(timeframe)
        bars = synchronizer.get_bars(symbol, tf, count=count)
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(bars),
            "bars": [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "is_bullish": bar.is_bullish,
                }
                for bar in bars
            ],
        }
    
    except Exception as e:
        logger.error(f"Error getting bars: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bars/aggregate")
async def aggregate_bars(request: AggregateRequest):
    """Aggregate lower timeframe bars to higher timeframe"""
    try:
        from_tf = parse_timeframe(request.from_timeframe)
        to_tf = parse_timeframe(request.to_timeframe)
        
        aggregated = synchronizer.aggregate_to_higher_timeframe(
            request.symbol,
            from_tf,
            to_tf,
            count=request.count,
        )
        
        return {
            "symbol": request.symbol,
            "from_timeframe": request.from_timeframe,
            "to_timeframe": request.to_timeframe,
            "count": len(aggregated),
            "bars": [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in aggregated
            ],
        }
    
    except Exception as e:
        logger.error(f"Error aggregating bars: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-quality/{symbol}")
async def get_sync_quality(
    symbol: str,
    timeframes: List[str] = Query(..., description="Timeframes to check")
):
    """Get synchronization quality across timeframes"""
    try:
        tfs = parse_timeframes(timeframes)
        quality = synchronizer.get_timeframe_alignment_quality(symbol, tfs)
        
        return {
            "symbol": symbol,
            "timeframes": timeframes,
            "completeness": quality["completeness"],
            "synchronization": quality["synchronization"],
            "quality_score": quality["quality_score"],
        }
    
    except Exception as e:
        logger.error(f"Error checking sync quality: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Trend Analysis
@router.post("/trend/analyze")
async def analyze_trend(request: AnalyzeTrendRequest):
    """Analyze trend for a single timeframe"""
    try:
        timeframe = parse_timeframe(request.timeframe)
        
        trend = trend_analyzer.analyze_trend(
            request.symbol,
            timeframe,
            lookback_periods=request.lookback_periods,
        )
        
        if not trend:
            return {
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "trend": None,
                "message": "Insufficient data for trend analysis",
            }
        
        return {
            "symbol": trend.symbol,
            "timeframe": trend.timeframe.value,
            "timestamp": trend.timestamp.isoformat(),
            "direction": trend.direction.value,
            "strength": trend.strength.value,
            "strength_score": trend.strength_score,
            "ema_short": trend.ema_short,
            "ema_long": trend.ema_long,
            "slope": trend.slope,
            "r_squared": trend.r_squared,
            "current_price": trend.current_price,
            "support_level": trend.support_level,
            "resistance_level": trend.resistance_level,
            "momentum_score": trend.momentum_score,
            "is_bullish": trend.is_bullish(),
            "is_bearish": trend.is_bearish(),
            "is_strong": trend.is_strong_trend(),
        }
    
    except Exception as e:
        logger.error(f"Error analyzing trend: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend/multiple/{symbol}")
async def analyze_multiple_timeframes(
    symbol: str,
    timeframes: List[str] = Query(..., description="Timeframes to analyze")
):
    """Analyze trends across multiple timeframes"""
    try:
        tfs = parse_timeframes(timeframes)
        trends = trend_analyzer.analyze_multiple_timeframes(symbol, tfs)
        
        return {
            "symbol": symbol,
            "timeframes": timeframes,
            "trends": {
                tf.value: {
                    "direction": trend.direction.value,
                    "strength": trend.strength.value,
                    "strength_score": trend.strength_score,
                    "momentum": trend.momentum_score,
                    "current_price": trend.current_price,
                }
                for tf, trend in trends.items()
            },
        }
    
    except Exception as e:
        logger.error(f"Error analyzing multiple timeframes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend/alignment/{symbol}")
async def check_trend_alignment(
    symbol: str,
    timeframes: List[str] = Query(..., description="Timeframes to check")
):
    """Check trend alignment across timeframes"""
    try:
        tfs = parse_timeframes(timeframes)
        alignment = trend_analyzer.check_trend_alignment(symbol, tfs)
        
        return {
            "symbol": symbol,
            "timeframes": timeframes,
            "alignment_score": alignment["alignment_score"],
            "aligned_direction": alignment["aligned_direction"].value if alignment["aligned_direction"] else None,
            "bullish_count": alignment["bullish_count"],
            "bearish_count": alignment["bearish_count"],
            "sideways_count": alignment["sideways_count"],
        }
    
    except Exception as e:
        logger.error(f"Error checking alignment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Confluence Detection
@router.post("/confluence/detect")
async def detect_confluence(request: DetectConfluenceRequest):
    """Detect confluence across timeframes"""
    try:
        timeframes = parse_timeframes(request.timeframes)
        
        reference_dir = None
        if request.reference_direction:
            from .trend_analyzer import TrendDirection
            reference_dir = TrendDirection(request.reference_direction)
        
        confluence = confluence_detector.detect_confluence(
            request.symbol,
            timeframes,
            reference_direction=reference_dir,
        )
        
        return confluence.to_dict()
    
    except Exception as e:
        logger.error(f"Error detecting confluence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confluence/entry")
async def detect_entry_confluence(
    symbol: str,
    higher_timeframes: List[str] = Query(...),
    lower_timeframes: List[str] = Query(...)
):
    """Detect entry signal using multi-timeframe confluence"""
    try:
        higher_tfs = parse_timeframes(higher_timeframes)
        lower_tfs = parse_timeframes(lower_timeframes)
        
        confluence = confluence_detector.detect_multi_timeframe_entry(
            symbol,
            higher_tfs,
            lower_tfs,
        )
        
        if not confluence:
            return {
                "symbol": symbol,
                "entry_signal": None,
                "message": "No clear entry signal detected",
            }
        
        return {
            "symbol": symbol,
            "entry_signal": confluence.to_dict(),
        }
    
    except Exception as e:
        logger.error(f"Error detecting entry confluence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Divergence Detection
@router.post("/divergence/detect")
async def detect_divergence(request: DetectDivergenceRequest):
    """Detect divergence between two timeframes"""
    try:
        higher_tf = parse_timeframe(request.higher_timeframe)
        lower_tf = parse_timeframe(request.lower_timeframe)
        
        divergence = divergence_detector.detect_divergence(
            request.symbol,
            higher_tf,
            lower_tf,
        )
        
        if not divergence:
            return {
                "symbol": request.symbol,
                "divergence": None,
                "message": "No significant divergence detected",
            }
        
        return divergence.to_dict()
    
    except Exception as e:
        logger.error(f"Error detecting divergence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/divergence/all/{symbol}")
async def detect_all_divergences(
    symbol: str,
    timeframes: List[str] = Query(..., description="Timeframes to analyze")
):
    """Detect all divergences across timeframes"""
    try:
        tfs = parse_timeframes(timeframes)
        divergences = divergence_detector.detect_all_divergences(symbol, tfs)
        
        return {
            "symbol": symbol,
            "timeframes": timeframes,
            "divergences": [d.to_dict() for d in divergences],
            "count": len(divergences),
            "significant_count": sum(1 for d in divergences if d.is_significant),
        }
    
    except Exception as e:
        logger.error(f"Error detecting divergences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Signal Aggregation
@router.post("/signal/generate")
async def generate_signal(request: GenerateSignalRequest):
    """Generate comprehensive multi-timeframe signal"""
    try:
        timeframes = None
        if request.timeframes:
            timeframes = parse_timeframes(request.timeframes)
        
        signal = signal_aggregator.generate_signal(
            request.symbol,
            timeframes=timeframes,
        )
        
        return signal.to_dict()
    
    except Exception as e:
        logger.error(f"Error generating signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signal/entry")
async def generate_entry_signal(request: GenerateEntrySignalRequest):
    """Generate entry signal using multi-timeframe strategy"""
    try:
        higher_tfs = None
        lower_tfs = None
        
        if request.higher_timeframes:
            higher_tfs = parse_timeframes(request.higher_timeframes)
        
        if request.lower_timeframes:
            lower_tfs = parse_timeframes(request.lower_timeframes)
        
        signal = signal_aggregator.generate_entry_signal(
            request.symbol,
            higher_timeframes=higher_tfs,
            lower_timeframes=lower_tfs,
        )
        
        if not signal:
            return {
                "symbol": request.symbol,
                "entry_signal": None,
                "message": "No clear entry signal detected",
            }
        
        return {
            "symbol": request.symbol,
            "entry_signal": signal.to_dict(),
        }
    
    except Exception as e:
        logger.error(f"Error generating entry signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health Check
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Multi-Timeframe Analysis",
        "components": {
            "synchronizer": "active",
            "trend_analyzer": "active",
            "confluence_detector": "active",
            "divergence_detector": "active",
            "signal_aggregator": "active",
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# Get current component instances (for integration)
def get_synchronizer() -> TimeframeSynchronizer:
    """Get the synchronizer instance"""
    return synchronizer


def get_trend_analyzer() -> TrendAnalyzer:
    """Get the trend analyzer instance"""
    return trend_analyzer


def get_confluence_detector() -> ConfluenceDetector:
    """Get the confluence detector instance"""
    return confluence_detector


def get_divergence_detector() -> DivergenceDetector:
    """Get the divergence detector instance"""
    return divergence_detector


def get_signal_aggregator() -> SignalAggregator:
    """Get the signal aggregator instance"""
    return signal_aggregator

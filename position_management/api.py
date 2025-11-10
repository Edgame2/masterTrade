"""
Position Management API

REST API endpoints for position management operations
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
import logging

from .position_manager import PositionManager, PositionSide, PositionStatus
from .scale_manager import ScaleManager, ScaleConfig, ScaleStrategy
from .trailing_stops import TrailingStopManager, TrailingStopType
from .exit_manager import ExitManager
from .hedge_manager import HedgeManager, HedgeType

router = APIRouter(prefix="/api/positions", tags=["positions"])
logger = logging.getLogger(__name__)

# Global managers (would be dependency-injected in production)
position_manager = PositionManager()
scale_manager = ScaleManager()
trailing_stop_manager = TrailingStopManager()
exit_manager = ExitManager()
hedge_manager = HedgeManager()


# Request/Response Models

class OpenPositionRequest(BaseModel):
    """Request to open position"""
    position_id: str
    symbol: str
    strategy_id: str
    side: str  # long/short
    entry_price: float
    size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    tags: Optional[Dict[str, str]] = None


class ScaleInRequest(BaseModel):
    """Request to scale into position"""
    position_id: str
    total_size: float
    num_levels: int
    strategy: str  # equal, increasing, decreasing, pyramid
    price_spacing_pct: float


class ScaleOutRequest(BaseModel):
    """Request to scale out of position"""
    position_id: str
    target_percentages: List[float]
    size_distribution: List[float]


class TrailingStopRequest(BaseModel):
    """Request to add trailing stop"""
    position_id: str
    stop_type: str  # percentage, atr, chandelier, parabolic_sar
    trail_percent: Optional[float] = None
    atr_multiplier: Optional[float] = None
    initial_atr: Optional[float] = None


class ProfitTargetsRequest(BaseModel):
    """Request to add profit targets"""
    position_id: str
    targets: List[tuple]  # [(price, size), ...]


class HedgeRequest(BaseModel):
    """Request to hedge position"""
    position_id: str
    hedge_type: str  # simple, pairs
    hedge_ratio: float = 1.0
    hedge_symbol: Optional[str] = None
    correlation: Optional[float] = None


# API Endpoints

@router.post("/open")
async def open_position(request: OpenPositionRequest):
    """Open a new position"""
    try:
        side = PositionSide.LONG if request.side.lower() == "long" else PositionSide.SHORT
        
        position = position_manager.open_position(
            position_id=request.position_id,
            symbol=request.symbol,
            strategy_id=request.strategy_id,
            side=side,
            entry_price=request.entry_price,
            size=request.size,
            entry_time=datetime.now(),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            tags=request.tags
        )
        
        return {
            "status": "success",
            "position": position.to_dict()
        }
    
    except Exception as e:
        logger.error(f"Error opening position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_positions(
    symbol: Optional[str] = Query(None),
    strategy_id: Optional[str] = Query(None),
    status: str = Query("open")
):
    """List positions"""
    try:
        if status == "open":
            positions = position_manager.get_open_positions(symbol, strategy_id)
        else:
            positions = position_manager.get_closed_positions(symbol, strategy_id)
        
        return {
            "positions": [p.to_dict() for p in positions],
            "count": len(positions)
        }
    
    except Exception as e:
        logger.error(f"Error listing positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{position_id}")
async def get_position(position_id: str):
    """Get position details"""
    try:
        position = position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        return position.to_dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/scale-in")
async def create_scale_in(position_id: str, request: ScaleInRequest):
    """Create scale-in strategy"""
    try:
        position = position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        config = ScaleConfig(
            total_size=request.total_size,
            num_levels=request.num_levels,
            strategy=ScaleStrategy(request.strategy),
            price_spacing_pct=request.price_spacing_pct
        )
        
        strategy = scale_manager.create_scale_in(
            position_id=position_id,
            config=config,
            entry_price=position.average_entry_price,
            is_long=position.side == PositionSide.LONG
        )
        
        return {
            "status": "success",
            "num_levels": len(strategy.levels),
            "levels": [
                {
                    "level_id": l.level_id,
                    "price_trigger": l.price_trigger,
                    "size": l.size
                }
                for l in strategy.levels
            ]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating scale-in: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/scale-out")
async def create_scale_out(position_id: str, request: ScaleOutRequest):
    """Create scale-out strategy"""
    try:
        position = position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        # Create exit strategy with profit targets
        exit_strategy = exit_manager.create_profit_targets(
            position_id=position_id,
            entry_price=position.average_entry_price,
            targets=[],
            is_long=position.side == PositionSide.LONG
        )
        
        # Add percentage targets
        exit_strategy.add_percentage_targets(
            request.target_percentages,
            request.size_distribution
        )
        
        return {
            "status": "success",
            "num_targets": len(exit_strategy.targets)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating scale-out: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/trailing-stop")
async def add_trailing_stop(position_id: str, request: TrailingStopRequest):
    """Add trailing stop to position"""
    try:
        position = position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        is_long = position.side == PositionSide.LONG
        
        if request.stop_type == "percentage":
            if not request.trail_percent:
                raise HTTPException(status_code=400, detail="trail_percent required")
            
            stop = trailing_stop_manager.create_percentage_stop(
                position_id=position_id,
                trail_percent=request.trail_percent,
                entry_price=position.average_entry_price,
                is_long=is_long
            )
        
        elif request.stop_type == "atr":
            if not request.atr_multiplier or not request.initial_atr:
                raise HTTPException(status_code=400, detail="atr_multiplier and initial_atr required")
            
            stop = trailing_stop_manager.create_atr_stop(
                position_id=position_id,
                atr_multiplier=request.atr_multiplier,
                entry_price=position.average_entry_price,
                initial_atr=request.initial_atr,
                is_long=is_long
            )
        
        elif request.stop_type == "chandelier":
            if not request.atr_multiplier or not request.initial_atr:
                raise HTTPException(status_code=400, detail="atr_multiplier and initial_atr required")
            
            stop = trailing_stop_manager.create_chandelier_stop(
                position_id=position_id,
                atr_multiplier=request.atr_multiplier,
                entry_price=position.average_entry_price,
                initial_atr=request.initial_atr,
                is_long=is_long
            )
        
        elif request.stop_type == "parabolic_sar":
            stop = trailing_stop_manager.create_parabolic_sar_stop(
                position_id=position_id,
                entry_price=position.average_entry_price,
                is_long=is_long
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown stop type: {request.stop_type}")
        
        return {
            "status": "success",
            "stop_type": request.stop_type,
            "initial_stop_price": stop.stop_price if hasattr(stop, 'stop_price') else stop.sar
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding trailing stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/hedge")
async def hedge_position(position_id: str, request: HedgeRequest):
    """Hedge a position"""
    try:
        position = position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        if request.hedge_type == "simple":
            hedge = hedge_manager.create_simple_hedge(
                position_id=position_id,
                symbol=position.symbol,
                size=position.current_size,
                side=position.side.value,
                current_price=position.current_price,
                hedge_ratio=request.hedge_ratio
            )
        
        elif request.hedge_type == "pairs":
            if not request.hedge_symbol or not request.correlation:
                raise HTTPException(
                    status_code=400,
                    detail="hedge_symbol and correlation required for pairs hedge"
                )
            
            # Would need to fetch hedge asset price
            hedge_asset_price = position.current_price  # Placeholder
            
            hedge = hedge_manager.create_pairs_hedge(
                position_id=position_id,
                symbol=position.symbol,
                size=position.current_size,
                side=position.side.value,
                hedge_symbol=request.hedge_symbol,
                correlation=request.correlation,
                current_price=position.current_price,
                hedge_asset_price=hedge_asset_price,
                hedge_ratio=request.hedge_ratio
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown hedge type: {request.hedge_type}")
        
        return {
            "status": "success",
            "hedge_id": hedge.hedge_id,
            "hedge_size": hedge.hedge_size,
            "hedge_side": hedge.hedge_side
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error hedging position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/close")
async def close_position(
    position_id: str,
    price: float,
    size: Optional[float] = None
):
    """Close position (full or partial)"""
    try:
        position = position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        fill_id = f"{position_id}_close_{datetime.now().timestamp()}"
        
        if size is None:
            # Full close
            pnl, pnl_pct = position_manager.close_position(
                position_id=position_id,
                fill_id=fill_id,
                price=price,
                fee=0.0,  # Would calculate actual fee
                timestamp=datetime.now()
            )
        else:
            # Partial close
            pnl, pnl_pct = position_manager.reduce_position(
                position_id=position_id,
                fill_id=fill_id,
                price=price,
                size=size,
                fee=0.0,
                timestamp=datetime.now()
            )
        
        return {
            "status": "success",
            "realized_pnl": pnl,
            "realized_pnl_pct": pnl_pct,
            "remaining_size": position.current_size
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_position_stats():
    """Get position statistics"""
    try:
        open_positions = position_manager.get_open_positions()
        
        total_exposure = position_manager.get_total_exposure()
        total_unrealized_pnl = position_manager.get_total_unrealized_pnl()
        total_realized_pnl = position_manager.get_total_realized_pnl()
        
        return {
            "open_positions": len(open_positions),
            "total_exposure": total_exposure,
            "unrealized_pnl": total_unrealized_pnl,
            "realized_pnl": total_realized_pnl,
            "total_pnl": total_unrealized_pnl + total_realized_pnl
        }
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "service": "position_management",
        "features": [
            "position_tracking",
            "partial_closes",
            "scale_in_out",
            "trailing_stops",
            "profit_targets",
            "hedging"
        ]
    }

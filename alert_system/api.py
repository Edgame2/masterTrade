"""
Alert System REST API

Provides endpoints for:
- Creating alerts
- Querying alerts
- Acknowledging alerts
- Managing alert conditions
- Configuring notification channels
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from alert_manager import (
    AlertManager,
    Alert,
    AlertType,
    AlertPriority,
    AlertStatus,
    AlertChannel,
)

from alert_conditions import (
    PriceAlertCondition,
    PerformanceAlertCondition,
    RiskAlertCondition,
    SystemHealthAlertCondition,
    MilestoneAlertCondition,
    ComparisonOperator,
)

from alert_templates import TemplateType, TemplateRenderer

# Initialize global instances (would use dependency injection in production)
alert_manager = AlertManager()
template_renderer = TemplateRenderer()

alert_router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateAlertRequest(BaseModel):
    """Request to create an alert"""
    alert_type: str
    priority: str
    title: str
    message: str
    channels: List[str]
    symbol: Optional[str] = None
    strategy_id: Optional[str] = None
    position_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    throttle_minutes: int = Field(default=5, ge=1)
    max_triggers: int = Field(default=10, ge=1)
    expires_in_hours: Optional[int] = Field(default=None, ge=1)


class CreatePriceAlertRequest(BaseModel):
    """Request to create a price alert"""
    symbol: str
    operator: str  # ">", "<", ">=", "<=", "crosses_above", "crosses_below"
    threshold: float
    channels: List[str]
    priority: str = "high"


class CreatePerformanceAlertRequest(BaseModel):
    """Request to create a performance alert"""
    strategy_id: str
    metric: str  # "win_rate", "pnl", "drawdown", "sharpe_ratio", "streak"
    operator: str
    threshold: float
    channels: List[str]
    priority: str = "medium"
    streak_type: Optional[str] = None  # "winning" or "losing"
    streak_length: Optional[int] = None


class CreateRiskAlertRequest(BaseModel):
    """Request to create a risk alert"""
    risk_metric: str  # "drawdown", "position_size", "leverage", "margin", "exposure"
    operator: str
    threshold: float
    channels: List[str]
    priority: str = "high"
    symbol: Optional[str] = None
    position_id: Optional[str] = None


class CreateHealthAlertRequest(BaseModel):
    """Request to create a system health alert"""
    service_name: str
    health_metric: str  # "uptime", "error_rate", "latency", "cpu", "memory"
    operator: str
    threshold: float
    channels: List[str]
    priority: str = "critical"
    consecutive_failures: int = 3


class CreateTemplatedAlertRequest(BaseModel):
    """Request to create an alert from template"""
    template_type: str
    variables: Dict[str, Any]
    channels: List[str]
    symbol: Optional[str] = None
    strategy_id: Optional[str] = None


class SuppressAlertsRequest(BaseModel):
    """Request to suppress alerts"""
    symbol: str
    duration_minutes: int = Field(ge=1, le=1440)  # Max 24 hours


class AlertResponse(BaseModel):
    """Alert response"""
    alert_id: str
    alert_type: str
    priority: str
    title: str
    message: str
    status: str
    created_at: str
    triggered_at: Optional[str] = None
    sent_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    trigger_count: int
    channels: List[str]
    symbol: Optional[str] = None
    strategy_id: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@alert_router.post("/create", response_model=AlertResponse)
async def create_alert(request: CreateAlertRequest):
    """
    Create a new alert.
    
    Args:
        request: Alert details
        
    Returns:
        Created alert
    """
    try:
        # Parse enums
        alert_type = AlertType(request.alert_type)
        priority = AlertPriority[request.priority.upper()]
        channels = [AlertChannel(c) for c in request.channels]
        
        # Create alert
        alert = alert_manager.create_alert(
            alert_type=alert_type,
            priority=priority,
            title=request.title,
            message=request.message,
            channels=channels,
            symbol=request.symbol,
            strategy_id=request.strategy_id,
            position_id=request.position_id,
            data=request.data,
            throttle_minutes=request.throttle_minutes,
            max_triggers=request.max_triggers,
            expires_in_hours=request.expires_in_hours,
        )
        
        return AlertResponse(
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            priority=alert.priority.name,
            title=alert.title,
            message=alert.message,
            status=alert.status.value,
            created_at=alert.created_at.isoformat(),
            trigger_count=alert.trigger_count,
            channels=[c.value for c in alert.channels],
            symbol=alert.symbol,
            strategy_id=alert.strategy_id,
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.post("/price", response_model=AlertResponse)
async def create_price_alert(request: CreatePriceAlertRequest):
    """Create a price alert condition"""
    try:
        operator = ComparisonOperator(request.operator)
        priority = AlertPriority[request.priority.upper()]
        channels = [AlertChannel(c) for c in request.channels]
        
        # Create alert
        alert = alert_manager.create_alert(
            alert_type=AlertType.PRICE,
            priority=priority,
            title=f"{request.symbol} Price Alert",
            message=f"{request.symbol} price {request.operator} ${request.threshold:.2f}",
            channels=channels,
            symbol=request.symbol,
            data={
                "operator": request.operator,
                "threshold": request.threshold,
            },
        )
        
        # Create condition
        condition = PriceAlertCondition(
            condition_id=f"price_{alert.alert_id}",
            symbol=request.symbol,
            operator=operator,
            threshold=request.threshold,
        )
        
        alert_manager.conditions[condition.condition_id] = condition
        
        return AlertResponse(
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            priority=alert.priority.name,
            title=alert.title,
            message=alert.message,
            status=alert.status.value,
            created_at=alert.created_at.isoformat(),
            trigger_count=alert.trigger_count,
            channels=[c.value for c in alert.channels],
            symbol=alert.symbol,
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.post("/performance", response_model=AlertResponse)
async def create_performance_alert(request: CreatePerformanceAlertRequest):
    """Create a strategy performance alert"""
    try:
        operator = ComparisonOperator(request.operator)
        priority = AlertPriority[request.priority.upper()]
        channels = [AlertChannel(c) for c in request.channels]
        
        alert = alert_manager.create_alert(
            alert_type=AlertType.PERFORMANCE,
            priority=priority,
            title=f"Performance Alert: {request.strategy_id}",
            message=f"{request.strategy_id} {request.metric} {request.operator} {request.threshold}",
            channels=channels,
            strategy_id=request.strategy_id,
            data={
                "metric": request.metric,
                "operator": request.operator,
                "threshold": request.threshold,
            },
        )
        
        # Create condition
        condition = PerformanceAlertCondition(
            condition_id=f"perf_{alert.alert_id}",
            strategy_id=request.strategy_id,
            metric=request.metric,
            operator=operator,
            threshold=request.threshold,
            streak_type=request.streak_type,
            streak_length=request.streak_length,
        )
        
        alert_manager.conditions[condition.condition_id] = condition
        
        return AlertResponse(
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            priority=alert.priority.name,
            title=alert.title,
            message=alert.message,
            status=alert.status.value,
            created_at=alert.created_at.isoformat(),
            trigger_count=alert.trigger_count,
            channels=[c.value for c in alert.channels],
            strategy_id=alert.strategy_id,
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.post("/risk", response_model=AlertResponse)
async def create_risk_alert(request: CreateRiskAlertRequest):
    """Create a risk management alert"""
    try:
        operator = ComparisonOperator(request.operator)
        priority = AlertPriority[request.priority.upper()]
        channels = [AlertChannel(c) for c in request.channels]
        
        alert = alert_manager.create_alert(
            alert_type=AlertType.RISK,
            priority=priority,
            title=f"Risk Alert: {request.risk_metric}",
            message=f"{request.risk_metric} {request.operator} {request.threshold}",
            channels=channels,
            symbol=request.symbol,
            data={
                "risk_metric": request.risk_metric,
                "operator": request.operator,
                "threshold": request.threshold,
            },
        )
        
        # Create condition
        condition = RiskAlertCondition(
            condition_id=f"risk_{alert.alert_id}",
            risk_metric=request.risk_metric,
            operator=operator,
            threshold=request.threshold,
            symbol=request.symbol,
            position_id=request.position_id,
        )
        
        alert_manager.conditions[condition.condition_id] = condition
        
        return AlertResponse(
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            priority=alert.priority.name,
            title=alert.title,
            message=alert.message,
            status=alert.status.value,
            created_at=alert.created_at.isoformat(),
            trigger_count=alert.trigger_count,
            channels=[c.value for c in alert.channels],
            symbol=alert.symbol,
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.post("/templated", response_model=AlertResponse)
async def create_templated_alert(request: CreateTemplatedAlertRequest):
    """Create an alert from a template"""
    try:
        template_type = TemplateType(request.template_type)
        channels = [AlertChannel(c) for c in request.channels]
        
        # Get template
        template = template_renderer.get_template(template_type)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template not found: {request.template_type}")
        
        # Render template
        rendered = template.render(request.variables)
        
        # Create alert
        alert = alert_manager.create_alert(
            alert_type=template.alert_type,
            priority=template.priority,
            title=rendered["title"],
            message=rendered["message"],
            channels=channels,
            symbol=request.symbol,
            strategy_id=request.strategy_id,
            data=request.variables,
        )
        
        return AlertResponse(
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            priority=alert.priority.name,
            title=alert.title,
            message=alert.message,
            status=alert.status.value,
            created_at=alert.created_at.isoformat(),
            trigger_count=alert.trigger_count,
            channels=[c.value for c in alert.channels],
            symbol=alert.symbol,
            strategy_id=alert.strategy_id,
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.post("/trigger/{alert_id}")
async def trigger_alert(alert_id: str):
    """Manually trigger an alert"""
    success = alert_manager.trigger_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Alert could not be triggered (throttled or expired)")
    
    return {"message": "Alert triggered successfully", "alert_id": alert_id}


@alert_router.post("/acknowledge/{alert_id}")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert"""
    alert_manager.acknowledge_alert(alert_id)
    return {"message": "Alert acknowledged", "alert_id": alert_id}


@alert_router.post("/resolve/{alert_id}")
async def resolve_alert(alert_id: str):
    """Resolve an alert"""
    alert_manager.resolve_alert(alert_id)
    return {"message": "Alert resolved", "alert_id": alert_id}


@alert_router.post("/suppress")
async def suppress_alerts(request: SuppressAlertsRequest):
    """Suppress alerts for a symbol temporarily"""
    alert_manager.suppress_alerts(request.symbol, request.duration_minutes)
    return {
        "message": f"Alerts suppressed for {request.symbol}",
        "duration_minutes": request.duration_minutes,
    }


@alert_router.post("/{alert_id}/snooze")
async def snooze_alert(alert_id: str, duration_minutes: int = Query(60, ge=1, le=1440)):
    """
    Snooze an alert for specified duration.
    
    Args:
        alert_id: Alert ID to snooze
        duration_minutes: Duration in minutes (default 60, max 24 hours)
        
    Returns:
        Success message
    """
    try:
        alert = alert_manager.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        # Update alert status to suppressed
        alert.status = AlertStatus.SUPPRESSED
        
        return {
            "message": f"Alert snoozed for {duration_minutes} minutes",
            "alert_id": alert_id,
            "duration_minutes": duration_minutes,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.delete("/{alert_id}")
async def delete_alert(alert_id: str):
    """
    Delete an alert.
    
    Args:
        alert_id: Alert ID to delete
        
    Returns:
        Success message
    """
    try:
        alert = alert_manager.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        # Remove alert from manager
        if alert_id in alert_manager.alerts:
            del alert_manager.alerts[alert_id]
        
        return {
            "message": "Alert deleted successfully",
            "alert_id": alert_id,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.get("/list", response_model=List[AlertResponse])
async def list_alerts(
    alert_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    strategy_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    List alerts with filters.
    
    Args:
        alert_type: Filter by type
        priority: Filter by priority
        status: Filter by status
        symbol: Filter by symbol
        strategy_id: Filter by strategy
        limit: Max results
        
    Returns:
        List of alerts
    """
    try:
        # Parse filters
        alert_type_enum = AlertType(alert_type) if alert_type else None
        priority_enum = AlertPriority[priority.upper()] if priority else None
        status_enum = AlertStatus(status) if status else None
        
        # Query alerts
        alerts = alert_manager.get_alerts(
            alert_type=alert_type_enum,
            priority=priority_enum,
            status=status_enum,
            symbol=symbol,
            strategy_id=strategy_id,
            limit=limit,
        )
        
        return [
            AlertResponse(
                alert_id=alert.alert_id,
                alert_type=alert.alert_type.value,
                priority=alert.priority.name,
                title=alert.title,
                message=alert.message,
                status=alert.status.value,
                created_at=alert.created_at.isoformat(),
                triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
                sent_at=alert.sent_at.isoformat() if alert.sent_at else None,
                acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                trigger_count=alert.trigger_count,
                channels=[c.value for c in alert.channels],
                symbol=alert.symbol,
                strategy_id=alert.strategy_id,
            )
            for alert in alerts
        ]
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@alert_router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str):
    """Get specific alert details"""
    alert = alert_manager.get_alert(alert_id)
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        alert_id=alert.alert_id,
        alert_type=alert.alert_type.value,
        priority=alert.priority.name,
        title=alert.title,
        message=alert.message,
        status=alert.status.value,
        created_at=alert.created_at.isoformat(),
        triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
        sent_at=alert.sent_at.isoformat() if alert.sent_at else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        trigger_count=alert.trigger_count,
        channels=[c.value for c in alert.channels],
        symbol=alert.symbol,
        strategy_id=alert.strategy_id,
    )


@alert_router.get("/stats/summary")
async def get_statistics():
    """Get alert statistics"""
    return alert_manager.get_statistics()


@alert_router.get("/templates/list")
async def list_templates():
    """List available alert templates"""
    templates = []
    for template_type, template in template_renderer.templates.items():
        templates.append({
            "template_type": template_type.value,
            "title_template": template.title_template,
            "message_template": template.message_template,
            "priority": template.priority.name,
            "alert_type": template.alert_type.value,
        })
    
    return {"templates": templates}


@alert_router.post("/cleanup")
async def cleanup_old_alerts(days: int = Query(7, ge=1, le=365)):
    """Clean up old resolved/expired alerts"""
    alert_manager.cleanup_old_alerts(days=days)
    return {"message": f"Cleaned up alerts older than {days} days"}


@alert_router.get("/health")
async def health_check():
    """Health check endpoint"""
    stats = alert_manager.get_statistics()
    
    return {
        "status": "healthy",
        "service": "alert_system",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats,
    }

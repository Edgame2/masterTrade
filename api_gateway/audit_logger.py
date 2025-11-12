"""
Audit Logger Module for API Gateway

Provides comprehensive audit logging for user actions across the system.
Logs: Who changed what, when, old value, new value.
Actions: Strategy enable/disable, data source config, goal changes, etc.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

import structlog

logger = structlog.get_logger()


class AuditAction(str, Enum):
    """Audit action types"""
    # User actions
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_PASSWORD_RESET = "user_password_reset"
    
    # Strategy actions
    STRATEGY_CREATE = "strategy_create"
    STRATEGY_UPDATE = "strategy_update"
    STRATEGY_DELETE = "strategy_delete"
    STRATEGY_ENABLE = "strategy_enable"
    STRATEGY_DISABLE = "strategy_disable"
    STRATEGY_PAUSE = "strategy_pause"
    STRATEGY_RESUME = "strategy_resume"
    STRATEGY_ACTIVATE = "strategy_activate"
    STRATEGY_DEACTIVATE = "strategy_deactivate"
    
    # Data source actions
    DATASOURCE_CREATE = "datasource_create"
    DATASOURCE_UPDATE = "datasource_update"
    DATASOURCE_ENABLE = "datasource_enable"
    DATASOURCE_DISABLE = "datasource_disable"
    DATASOURCE_CONFIG_UPDATE = "datasource_config_update"
    
    # Goal actions
    GOAL_CREATE = "goal_create"
    GOAL_UPDATE = "goal_update"
    GOAL_DELETE = "goal_delete"
    GOAL_ACTIVATE = "goal_activate"
    GOAL_COMPLETE = "goal_complete"
    
    # Order actions
    ORDER_CREATE = "order_create"
    ORDER_MODIFY = "order_modify"
    ORDER_CANCEL = "order_cancel"
    
    # Risk management actions
    RISK_LIMIT_UPDATE = "risk_limit_update"
    RISK_OVERRIDE = "risk_override"
    RISK_EMERGENCY_STOP = "risk_emergency_stop"
    
    # Alert actions
    ALERT_CREATE = "alert_create"
    ALERT_UPDATE = "alert_update"
    ALERT_DELETE = "alert_delete"
    ALERT_ACKNOWLEDGE = "alert_acknowledge"
    ALERT_RESOLVE = "alert_resolve"
    
    # System actions
    SYSTEM_CONFIG_UPDATE = "system_config_update"
    SYSTEM_BACKUP = "system_backup"
    SYSTEM_RESTORE = "system_restore"


class ResourceType(str, Enum):
    """Resource types for audit logging"""
    USER = "user"
    STRATEGY = "strategy"
    DATASOURCE = "datasource"
    GOAL = "goal"
    ORDER = "order"
    RISK = "risk"
    ALERT = "alert"
    SYSTEM = "system"


class AuditLogger:
    """Comprehensive audit logging service"""
    
    def __init__(self, user_service):
        """
        Initialize audit logger
        
        Args:
            user_service: UserManagementService instance
        """
        self.user_service = user_service
        self.logger = structlog.get_logger()
    
    async def log_user_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: Optional[str] = None,
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict] = None
    ):
        """
        Log a user action for audit trail
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user performing action
            action: Action being performed
            resource_type: Type of resource being acted upon
            resource_id: ID of resource (optional)
            old_value: Previous value before change
            new_value: New value after change
            ip_address: Client IP address
            details: Additional details about the action
        """
        try:
            # Log to audit_logs table via user_service
            await self.user_service.log_audit(
                user_id=user_id,
                user_email=user_email,
                action=action.value,
                resource_type=resource_type.value,
                resource_id=resource_id,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address
            )
            
            # Also log to user_activities for user-specific tracking
            activity_details = {
                "action": action.value,
                "resource_type": resource_type.value,
                "resource_id": resource_id,
            }
            if details:
                activity_details.update(details)
            
            await self.user_service.log_activity(
                user_id=user_id,
                action=action.value,
                details=activity_details,
                ip_address=ip_address
            )
            
            # Structured logging
            self.logger.info(
                "audit_log",
                user_id=user_id,
                user_email=user_email,
                action=action.value,
                resource_type=resource_type.value,
                resource_id=resource_id,
                has_old_value=old_value is not None,
                has_new_value=new_value is not None,
                ip_address=ip_address
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to log audit: {e}",
                user_id=user_id,
                action=action.value
            )
    
    async def log_strategy_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        strategy_id: str,
        old_state: Optional[Dict] = None,
        new_state: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log strategy-related action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: Strategy action (enable, disable, pause, etc.)
            strategy_id: ID of strategy
            old_state: Previous strategy state
            new_state: New strategy state
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.STRATEGY,
            resource_id=strategy_id,
            old_value=old_state,
            new_value=new_state,
            ip_address=ip_address
        )
    
    async def log_datasource_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        datasource_id: str,
        old_config: Optional[Dict] = None,
        new_config: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log data source configuration action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: Data source action
            datasource_id: ID of data source
            old_config: Previous configuration
            new_config: New configuration
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.DATASOURCE,
            resource_id=datasource_id,
            old_value=old_config,
            new_value=new_config,
            ip_address=ip_address
        )
    
    async def log_goal_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        goal_id: str,
        old_goal: Optional[Dict] = None,
        new_goal: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log goal-related action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: Goal action
            goal_id: ID of goal
            old_goal: Previous goal state
            new_goal: New goal state
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.GOAL,
            resource_id=goal_id,
            old_value=old_goal,
            new_value=new_goal,
            ip_address=ip_address
        )
    
    async def log_order_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        order_id: str,
        order_details: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log order execution action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: Order action (create, modify, cancel)
            order_id: ID of order
            order_details: Order details
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.ORDER,
            resource_id=order_id,
            new_value=order_details,
            ip_address=ip_address
        )
    
    async def log_risk_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        risk_parameter: str,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log risk management action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: Risk action
            risk_parameter: Risk parameter being changed
            old_value: Previous value
            new_value: New value
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.RISK,
            resource_id=risk_parameter,
            old_value={"value": old_value} if old_value is not None else None,
            new_value={"value": new_value} if new_value is not None else None,
            ip_address=ip_address
        )
    
    async def log_alert_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        alert_id: str,
        alert_details: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log alert-related action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: Alert action
            alert_id: ID of alert
            alert_details: Alert details
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.ALERT,
            resource_id=alert_id,
            new_value=alert_details,
            ip_address=ip_address
        )
    
    async def log_system_action(
        self,
        user_id: str,
        user_email: str,
        action: AuditAction,
        config_key: str,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log system configuration action
        
        Args:
            user_id: ID of user performing action
            user_email: Email of user
            action: System action
            config_key: Configuration key being changed
            old_value: Previous value
            new_value: New value
            ip_address: Client IP
        """
        await self.log_user_action(
            user_id=user_id,
            user_email=user_email,
            action=action,
            resource_type=ResourceType.SYSTEM,
            resource_id=config_key,
            old_value={"value": old_value} if old_value is not None else None,
            new_value={"value": new_value} if new_value is not None else None,
            ip_address=ip_address
        )
    
    async def get_recent_actions(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[ResourceType] = None,
        action: Optional[AuditAction] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get recent audit log entries with filters
        
        Args:
            user_id: Filter by user ID
            resource_type: Filter by resource type
            action: Filter by action type
            limit: Maximum number of entries
            
        Returns:
            List of audit log entries
        """
        try:
            resource_type_str = resource_type.value if resource_type else None
            
            # Get audit logs from user service
            logs = await self.user_service.get_audit_logs(
                user_id=user_id,
                resource_type=resource_type_str,
                limit=limit
            )
            
            # Filter by action if specified
            if action:
                logs = [log for log in logs if log.action == action.value]
            
            return [log.dict() for log in logs]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent actions: {e}")
            return []
    
    async def get_user_activity_summary(
        self,
        user_id: str,
        hours: int = 24
    ) -> Dict:
        """
        Get summary of user activity for the specified time period
        
        Args:
            user_id: User ID
            hours: Number of hours to look back
            
        Returns:
            Dict with activity summary
        """
        try:
            activities = await self.user_service.get_user_activities(user_id, limit=1000)
            
            # Count actions by type
            action_counts = {}
            for activity in activities:
                action = activity.action
                action_counts[action] = action_counts.get(action, 0) + 1
            
            return {
                "user_id": user_id,
                "period_hours": hours,
                "total_actions": len(activities),
                "action_counts": action_counts,
                "most_recent": activities[0].dict() if activities else None
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get user activity summary: {e}", user_id=user_id)
            return {
                "user_id": user_id,
                "period_hours": hours,
                "total_actions": 0,
                "action_counts": {},
                "error": str(e)
            }

"""
RBAC (Role-Based Access Control) Middleware for API Gateway

Provides authentication and authorization middleware for FastAPI endpoints.
Enforces role-based permissions at the API Gateway level.
"""

from typing import Callable, List, Optional
from functools import wraps
from datetime import datetime, timedelta

import structlog
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from user_management import UserRole, UserStatus

logger = structlog.get_logger()

# Security scheme for JWT bearer tokens
security = HTTPBearer()


class Permission:
    """Permission definitions for different resource actions"""
    
    # User management permissions
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"
    
    # Strategy management permissions
    STRATEGY_CREATE = "strategy:create"
    STRATEGY_READ = "strategy:read"
    STRATEGY_UPDATE = "strategy:update"
    STRATEGY_DELETE = "strategy:delete"
    STRATEGY_ACTIVATE = "strategy:activate"
    STRATEGY_PAUSE = "strategy:pause"
    STRATEGY_LIST = "strategy:list"
    
    # Data source permissions
    DATASOURCE_READ = "datasource:read"
    DATASOURCE_UPDATE = "datasource:update"
    DATASOURCE_LIST = "datasource:list"
    
    # Order execution permissions
    ORDER_CREATE = "order:create"
    ORDER_READ = "order:read"
    ORDER_CANCEL = "order:cancel"
    ORDER_LIST = "order:list"
    
    # Risk management permissions
    RISK_READ = "risk:read"
    RISK_UPDATE = "risk:update"
    RISK_OVERRIDE = "risk:override"
    
    # Goal management permissions
    GOAL_READ = "goal:read"
    GOAL_UPDATE = "goal:update"
    GOAL_CREATE = "goal:create"
    
    # Alert management permissions
    ALERT_READ = "alert:read"
    ALERT_CREATE = "alert:create"
    ALERT_UPDATE = "alert:update"
    ALERT_DELETE = "alert:delete"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    
    # System permissions
    SYSTEM_HEALTH = "system:health"
    SYSTEM_METRICS = "system:metrics"
    SYSTEM_LOGS = "system:logs"
    SYSTEM_CONFIG = "system:config"
    
    # Audit log permissions
    AUDIT_READ = "audit:read"


# Role-to-Permissions mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        # Full system access
        Permission.USER_CREATE, Permission.USER_READ, Permission.USER_UPDATE, 
        Permission.USER_DELETE, Permission.USER_LIST,
        Permission.STRATEGY_CREATE, Permission.STRATEGY_READ, Permission.STRATEGY_UPDATE,
        Permission.STRATEGY_DELETE, Permission.STRATEGY_ACTIVATE, Permission.STRATEGY_PAUSE,
        Permission.STRATEGY_LIST,
        Permission.DATASOURCE_READ, Permission.DATASOURCE_UPDATE, Permission.DATASOURCE_LIST,
        Permission.ORDER_CREATE, Permission.ORDER_READ, Permission.ORDER_CANCEL, Permission.ORDER_LIST,
        Permission.RISK_READ, Permission.RISK_UPDATE, Permission.RISK_OVERRIDE,
        Permission.GOAL_READ, Permission.GOAL_UPDATE, Permission.GOAL_CREATE,
        Permission.ALERT_READ, Permission.ALERT_CREATE, Permission.ALERT_UPDATE,
        Permission.ALERT_DELETE, Permission.ALERT_ACKNOWLEDGE,
        Permission.SYSTEM_HEALTH, Permission.SYSTEM_METRICS, Permission.SYSTEM_LOGS,
        Permission.SYSTEM_CONFIG,
        Permission.AUDIT_READ,
    ],
    UserRole.OPERATOR: [
        # Manage strategies and positions
        Permission.USER_READ,  # Can view users
        Permission.STRATEGY_READ, Permission.STRATEGY_UPDATE, Permission.STRATEGY_ACTIVATE,
        Permission.STRATEGY_PAUSE, Permission.STRATEGY_LIST,
        Permission.DATASOURCE_READ, Permission.DATASOURCE_UPDATE, Permission.DATASOURCE_LIST,
        Permission.ORDER_CREATE, Permission.ORDER_READ, Permission.ORDER_CANCEL, Permission.ORDER_LIST,
        Permission.RISK_READ, Permission.RISK_UPDATE,
        Permission.GOAL_READ,
        Permission.ALERT_READ, Permission.ALERT_CREATE, Permission.ALERT_ACKNOWLEDGE,
        Permission.SYSTEM_HEALTH, Permission.SYSTEM_METRICS,
    ],
    UserRole.QUANT: [
        # View trading data, run backtests
        Permission.USER_READ,  # Can view users
        Permission.STRATEGY_READ, Permission.STRATEGY_LIST, Permission.STRATEGY_CREATE,
        Permission.DATASOURCE_READ, Permission.DATASOURCE_LIST,
        Permission.ORDER_READ, Permission.ORDER_LIST,
        Permission.RISK_READ,
        Permission.GOAL_READ,
        Permission.ALERT_READ,
        Permission.SYSTEM_HEALTH, Permission.SYSTEM_METRICS,
    ],
    UserRole.VIEWER: [
        # Dashboard view only
        Permission.STRATEGY_READ, Permission.STRATEGY_LIST,
        Permission.DATASOURCE_READ, Permission.DATASOURCE_LIST,
        Permission.ORDER_READ, Permission.ORDER_LIST,
        Permission.RISK_READ,
        Permission.GOAL_READ,
        Permission.ALERT_READ,
        Permission.SYSTEM_HEALTH,
    ],
}


class RBACMiddleware:
    """RBAC Middleware for enforcing role-based access control"""
    
    def __init__(self, user_service):
        """
        Initialize RBAC middleware
        
        Args:
            user_service: UserManagementService instance
        """
        self.user_service = user_service
        self.logger = structlog.get_logger()
    
    def has_permission(self, role: UserRole, permission: str) -> bool:
        """
        Check if a role has a specific permission
        
        Args:
            role: User role
            permission: Permission string
            
        Returns:
            True if role has permission, False otherwise
        """
        return permission in ROLE_PERMISSIONS.get(role, [])
    
    def get_user_permissions(self, role: UserRole) -> List[str]:
        """
        Get all permissions for a role
        
        Args:
            role: User role
            
        Returns:
            List of permission strings
        """
        return ROLE_PERMISSIONS.get(role, [])
    
    async def authenticate_request(self, request: Request) -> dict:
        """
        Authenticate a request and return user info
        
        Args:
            request: FastAPI request object
            
        Returns:
            Dict with user_id, email, role, status
            
        Raises:
            HTTPException: If authentication fails
        """
        try:
            # Get user_id from header (simplified for now)
            # In production, this would validate JWT tokens
            user_id = request.headers.get("X-User-ID")
            
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing authentication credentials"
                )
            
            # Get user from database
            user = await self.user_service.get_user(user_id)
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid user credentials"
                )
            
            # Check user status
            if user.status != UserStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User account is {user.status.value}"
                )
            
            # Update last seen
            await self.user_service.update_last_seen(user_id)
            
            return {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "status": user.status,
            }
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )
    
    async def authorize_request(
        self,
        request: Request,
        required_permissions: List[str]
    ) -> dict:
        """
        Authorize a request based on required permissions
        
        Args:
            request: FastAPI request object
            required_permissions: List of required permission strings
            
        Returns:
            Dict with user info
            
        Raises:
            HTTPException: If authorization fails
        """
        # Authenticate user
        user_info = await self.authenticate_request(request)
        
        # Check permissions
        user_role = UserRole(user_info["role"])
        
        for permission in required_permissions:
            if not self.has_permission(user_role, permission):
                self.logger.warning(
                    f"Access denied for user",
                    user_id=user_info["user_id"],
                    role=user_role.value,
                    required_permission=permission
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {permission}"
                )
        
        return user_info
    
    async def log_access(
        self,
        user_info: dict,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        success: bool = True,
        ip_address: Optional[str] = None
    ):
        """
        Log access attempt for audit trail
        
        Args:
            user_info: Dict with user info from authenticate_request
            action: Action performed (e.g., "read", "update", "delete")
            resource_type: Type of resource accessed
            resource_id: ID of resource (optional)
            success: Whether access was successful
            ip_address: Client IP address
        """
        try:
            await self.user_service.log_activity(
                user_id=user_info["user_id"],
                action=f"{action}_{resource_type}",
                details={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "success": success,
                    "role": user_info["role"],
                },
                ip_address=ip_address
            )
        except Exception as e:
            self.logger.error(f"Failed to log access: {e}")


def require_permissions(*permissions: str):
    """
    Decorator to require specific permissions for an endpoint
    
    Usage:
        @app.get("/strategies")
        @require_permissions(Permission.STRATEGY_LIST)
        async def list_strategies(request: Request):
            ...
    
    Args:
        *permissions: Variable number of required permission strings
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get RBAC middleware from app state
            rbac: RBACMiddleware = request.app.state.rbac
            
            # Authorize request
            user_info = await rbac.authorize_request(request, list(permissions))
            
            # Add user info to request state for use in endpoint
            request.state.user = user_info
            
            # Get client IP
            ip_address = request.client.host if request.client else None
            
            try:
                # Execute endpoint
                result = await func(request, *args, **kwargs)
                
                # Log successful access
                await rbac.log_access(
                    user_info=user_info,
                    action="access",
                    resource_type=func.__name__,
                    success=True,
                    ip_address=ip_address
                )
                
                return result
                
            except Exception as e:
                # Log failed access
                await rbac.log_access(
                    user_info=user_info,
                    action="access",
                    resource_type=func.__name__,
                    success=False,
                    ip_address=ip_address
                )
                raise
        
        return wrapper
    return decorator


def require_role(*roles: UserRole):
    """
    Decorator to require specific role(s) for an endpoint
    
    Usage:
        @app.delete("/users/{user_id}")
        @require_role(UserRole.ADMIN)
        async def delete_user(request: Request, user_id: str):
            ...
    
    Args:
        *roles: Variable number of allowed UserRole enums
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get RBAC middleware from app state
            rbac: RBACMiddleware = request.app.state.rbac
            
            # Authenticate user
            user_info = await rbac.authenticate_request(request)
            
            # Check role
            user_role = UserRole(user_info["role"])
            if user_role not in roles:
                logger.warning(
                    f"Access denied - insufficient role",
                    user_id=user_info["user_id"],
                    user_role=user_role.value,
                    required_roles=[r.value for r in roles]
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required role: {', '.join(r.value for r in roles)}"
                )
            
            # Add user info to request state
            request.state.user = user_info
            
            # Get client IP
            ip_address = request.client.host if request.client else None
            
            try:
                # Execute endpoint
                result = await func(request, *args, **kwargs)
                
                # Log successful access
                await rbac.log_access(
                    user_info=user_info,
                    action="access",
                    resource_type=func.__name__,
                    success=True,
                    ip_address=ip_address
                )
                
                return result
                
            except Exception as e:
                # Log failed access
                await rbac.log_access(
                    user_info=user_info,
                    action="access",
                    resource_type=func.__name__,
                    success=False,
                    ip_address=ip_address
                )
                raise
        
        return wrapper
    return decorator

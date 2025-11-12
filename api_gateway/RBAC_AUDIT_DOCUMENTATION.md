# RBAC and Audit Logging System Documentation

## Overview

The MasterTrade API Gateway now includes a comprehensive Role-Based Access Control (RBAC) system and audit logging infrastructure. This document explains how to use these features.

## RBAC System

### Roles and Permissions

The system defines four user roles with hierarchical permissions:

#### 1. **Admin** (Full System Access)
- User management: Create, read, update, delete users
- Strategy management: Full control (create, update, delete, activate, pause)
- Data sources: Full configuration control
- Orders: Create, modify, cancel orders
- Risk management: Update limits, override settings, emergency stop
- Goals: Full management (create, update, delete)
- Alerts: Full management (create, update, delete, acknowledge, resolve)
- System: Configuration updates, backups, restore
- Audit logs: Full read access

#### 2. **Operator** (Manage Strategies and Positions)
- User management: Read-only (view users)
- Strategy management: Update, activate, pause (no delete)
- Data sources: Update configuration (no create/delete)
- Orders: Full control (create, modify, cancel)
- Risk management: Update limits (no override or emergency stop)
- Goals: Read-only
- Alerts: Create and acknowledge (no delete)
- System: View health and metrics
- Audit logs: No access

#### 3. **Quant** (View Trading Data, Run Backtests)
- User management: Read-only (view users)
- Strategy management: Create and read (no activate or delete)
- Data sources: Read-only
- Orders: Read-only
- Risk management: Read-only
- Goals: Read-only
- Alerts: Read-only
- System: View health and metrics
- Audit logs: No access

#### 4. **Viewer** (Dashboard View Only)
- Strategy management: Read-only
- Data sources: Read-only
- Orders: Read-only
- Risk management: Read-only
- Goals: Read-only
- Alerts: Read-only
- System: Health check only
- Audit logs: No access

### Using RBAC in Endpoints

#### Permission-Based Protection

```python
from rbac_middleware import require_permissions, Permission

@app.get("/api/v1/strategies")
@require_permissions(Permission.STRATEGY_LIST)
async def list_strategies(request: Request):
    # Automatically checks if user has STRATEGY_LIST permission
    # User info available in request.state.user
    user_info = request.state.user  # {user_id, email, role, status}
    ...
```

#### Role-Based Protection

```python
from rbac_middleware import require_role, UserRole

@app.delete("/api/v1/users/{user_id}")
@require_role(UserRole.ADMIN)  # Only admins can delete users
async def delete_user(request: Request, user_id: str):
    # Only ADMIN role can access this endpoint
    ...
```

#### Multiple Permissions

```python
@app.post("/api/v1/orders")
@require_permissions(Permission.ORDER_CREATE, Permission.RISK_READ)
async def create_order(request: Request, order_data: OrderRequest):
    # Requires both ORDER_CREATE and RISK_READ permissions
    ...
```

### Authentication

Currently using simplified header-based authentication:

```bash
# Include X-User-ID header in requests
curl -H "X-User-ID: 1" http://localhost:8080/api/v1/users
```

**Note**: This will be replaced with JWT token authentication in production.

### Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Missing authentication credentials"
}
```

#### 403 Forbidden
```json
{
  "detail": "Insufficient permissions. Required: strategy:activate"
}
```

#### 403 Forbidden (User Status)
```json
{
  "detail": "User account is suspended"
}
```

## Audit Logging System

### What Gets Logged

Every action is logged with:
- **Who**: User ID and email
- **What**: Action type (create, update, delete, etc.)
- **When**: Timestamp (UTC)
- **Where**: IP address
- **Old Value**: Previous state (for updates)
- **New Value**: New state (for updates)
- **Resource**: Resource type and ID

### Action Types

The system logs 40+ action types across 8 resource categories:

1. **User Actions**: login, logout, create, update, delete, password_reset
2. **Strategy Actions**: create, update, delete, enable, disable, pause, resume, activate, deactivate
3. **Data Source Actions**: create, update, enable, disable, config_update
4. **Goal Actions**: create, update, delete, activate, complete
5. **Order Actions**: create, modify, cancel
6. **Risk Actions**: limit_update, override, emergency_stop
7. **Alert Actions**: create, update, delete, acknowledge, resolve
8. **System Actions**: config_update, backup, restore

### Using Audit Logger

#### In Endpoint Code

```python
from audit_logger import AuditAction, ResourceType

@app.put("/api/v1/strategies/{strategy_id}/enable")
async def enable_strategy(request: Request, strategy_id: str):
    # Get user info from RBAC
    user_info = request.state.user
    
    # Get old state
    old_state = await get_strategy_state(strategy_id)
    
    # Enable strategy
    await enable_strategy_internal(strategy_id)
    
    # Get new state
    new_state = await get_strategy_state(strategy_id)
    
    # Log action
    await request.app.state.audit_logger.log_strategy_action(
        user_id=user_info["user_id"],
        user_email=user_info["email"],
        action=AuditAction.STRATEGY_ENABLE,
        strategy_id=strategy_id,
        old_state=old_state,
        new_state=new_state,
        ip_address=request.client.host
    )
    
    return {"success": True}
```

#### Specialized Logging Methods

```python
# Strategy actions
await audit_logger.log_strategy_action(
    user_id, user_email, action, strategy_id, old_state, new_state, ip
)

# Data source actions
await audit_logger.log_datasource_action(
    user_id, user_email, action, datasource_id, old_config, new_config, ip
)

# Goal actions
await audit_logger.log_goal_action(
    user_id, user_email, action, goal_id, old_goal, new_goal, ip
)

# Order actions
await audit_logger.log_order_action(
    user_id, user_email, action, order_id, order_details, ip
)

# Risk actions
await audit_logger.log_risk_action(
    user_id, user_email, action, risk_parameter, old_value, new_value, ip
)

# Alert actions
await audit_logger.log_alert_action(
    user_id, user_email, action, alert_id, alert_details, ip
)

# System actions
await audit_logger.log_system_action(
    user_id, user_email, action, config_key, old_value, new_value, ip
)
```

### Querying Audit Logs

#### REST API Endpoints

```bash
# Get all audit logs
GET /api/v1/audit-logs?limit=100
Headers: X-User-ID: 1  # Requires AUDIT_READ permission

# Filter by user
GET /api/v1/audit-logs?user_id=5&limit=50

# Filter by resource type
GET /api/v1/audit-logs?resource_type=strategy&limit=50

# Get recent actions with filters
GET /api/v1/audit/recent-actions?user_id=5&resource_type=strategy&action=strategy_enable

# Get user activity summary
GET /api/v1/audit/user-activity-summary/5?hours=24

# Get system-wide audit statistics (Admin only)
GET /api/v1/audit/statistics?days=7
```

#### Response Examples

**Audit Log Entry**:
```json
{
  "id": "12345",
  "user_id": "5",
  "user_email": "operator@example.com",
  "action": "strategy_enable",
  "resource_type": "strategy",
  "resource_id": "strategy_42",
  "old_value": {
    "status": "paused",
    "enabled": false
  },
  "new_value": {
    "status": "active",
    "enabled": true
  },
  "timestamp": "2025-11-12T14:30:00Z",
  "ip_address": "192.168.1.100"
}
```

**User Activity Summary**:
```json
{
  "user_id": "5",
  "period_hours": 24,
  "total_actions": 45,
  "action_counts": {
    "strategy_enable": 5,
    "strategy_pause": 3,
    "order_create": 20,
    "alert_acknowledge": 12,
    "datasource_update": 5
  },
  "most_recent": {
    "action": "strategy_enable",
    "timestamp": "2025-11-12T14:30:00Z"
  }
}
```

**Audit Statistics**:
```json
{
  "period_days": 7,
  "total_actions": 1250,
  "actions_by_type": {
    "order_create": 450,
    "strategy_enable": 80,
    "alert_acknowledge": 120,
    ...
  },
  "actions_by_user": {
    "operator@example.com": 600,
    "admin@example.com": 350,
    ...
  },
  "actions_by_resource": {
    "order": 500,
    "strategy": 200,
    "alert": 150,
    ...
  },
  "top_users": [
    ["operator@example.com", 600],
    ["admin@example.com", 350],
    ...
  ],
  "top_actions": [
    ["order_create", 450],
    ["alert_acknowledge", 120],
    ...
  ]
}
```

## Database Schema

### audit_logs Table
```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    user_email VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255),
    old_value JSONB,
    new_value JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(45)
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
```

### user_activities Table
```sql
CREATE TABLE user_activities (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    details JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(45)
);

CREATE INDEX idx_user_activities_user_id ON user_activities(user_id);
CREATE INDEX idx_user_activities_timestamp ON user_activities(user_id, timestamp DESC);
```

## Security Best Practices

1. **Never Log Sensitive Data**: Passwords, API keys, tokens should never appear in audit logs
2. **Validate User Status**: Always check user is active before processing requests
3. **IP Tracking**: Log IP addresses for security analysis
4. **Regular Reviews**: Audit logs should be reviewed regularly for suspicious activity
5. **Retention Policy**: Implement data retention policy (e.g., 90 days for audit logs)
6. **Access Control**: Limit audit log access to Admin users only
7. **Immutable Logs**: Never allow modification or deletion of audit logs

## Testing RBAC

### Create Test Users

```python
# Admin user
POST /api/v1/users
{
  "email": "admin@example.com",
  "name": "Admin User",
  "role": "admin",
  "password": "securepassword"
}

# Operator user
POST /api/v1/users
{
  "email": "operator@example.com",
  "name": "Operator User",
  "role": "operator",
  "password": "securepassword"
}

# Quant user
POST /api/v1/users
{
  "email": "quant@example.com",
  "name": "Quant User",
  "role": "quant",
  "password": "securepassword"
}

# Viewer user
POST /api/v1/users
{
  "email": "viewer@example.com",
  "name": "Viewer User",
  "role": "viewer",
  "password": "securepassword"
}
```

### Test Permission Enforcement

```bash
# Should succeed (Admin has USER_LIST permission)
curl -H "X-User-ID: 1" http://localhost:8080/api/v1/users

# Should fail (Viewer doesn't have USER_LIST permission)
curl -H "X-User-ID: 4" http://localhost:8080/api/v1/users
# Response: 403 Forbidden

# Should succeed (Operator has STRATEGY_ACTIVATE permission)
curl -H "X-User-ID: 2" -X POST http://localhost:8080/api/v1/strategies/123/activate

# Should fail (Quant doesn't have STRATEGY_ACTIVATE permission)
curl -H "X-User-ID: 3" -X POST http://localhost:8080/api/v1/strategies/123/activate
# Response: 403 Forbidden
```

## Future Enhancements

1. **JWT Authentication**: Replace X-User-ID header with JWT tokens
2. **Permission Caching**: Cache user permissions in Redis for performance
3. **Dynamic Permissions**: Allow custom permission assignment beyond default roles
4. **Permission UI**: Management interface for viewing and editing role permissions
5. **Audit Log Visualization**: Dashboard for audit log analysis
6. **Real-time Alerts**: Alert on suspicious audit patterns (e.g., multiple failed access attempts)
7. **Compliance Reports**: Automated compliance report generation from audit logs
8. **Audit Log Export**: Export audit logs to external SIEM systems

## Troubleshooting

### Issue: 401 Unauthorized
**Cause**: Missing or invalid X-User-ID header
**Solution**: Ensure X-User-ID header is included and user exists

### Issue: 403 Forbidden
**Cause**: User doesn't have required permission or account is inactive
**Solution**: Check user role and status, ensure user has necessary permissions

### Issue: Audit logs not appearing
**Cause**: Database connection issue or audit_logger not initialized
**Solution**: Check api_gateway logs, verify database connection, ensure audit_logger in app.state

### Issue: Performance degradation
**Cause**: Too many audit log queries or slow database
**Solution**: Add database indexes, implement audit log caching, archive old logs

## Support

For issues or questions:
- Check api_gateway logs: `docker logs mastertrade_api_gateway`
- Review database schema: Ensure audit_logs and user_activities tables exist
- Contact system administrator for permission issues

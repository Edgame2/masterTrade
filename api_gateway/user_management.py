"""
User Management Module for API Gateway

Provides user CRUD operations, role management, and audit logging.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional
from enum import Enum

import structlog
from pydantic import BaseModel, EmailStr, validator

logger = structlog.get_logger()


class UserRole(str, Enum):
    """User roles with hierarchical permissions"""
    ADMIN = "admin"  # Full system access
    OPERATOR = "operator"  # Manage strategies and positions
    QUANT = "quant"  # View trading data, run backtests
    VIEWER = "viewer"  # Dashboard view only


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(BaseModel):
    """User model"""
    id: Optional[str] = None
    email: EmailStr
    name: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    preferences: Dict = {}

    class Config:
        use_enum_values = True


class CreateUserRequest(BaseModel):
    """Request model for creating a user"""
    email: EmailStr
    name: str
    role: UserRole
    password: str

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    class Config:
        use_enum_values = True


class UpdateUserRequest(BaseModel):
    """Request model for updating a user"""
    name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    preferences: Optional[Dict] = None

    class Config:
        use_enum_values = True


class UserActivity(BaseModel):
    """User activity log entry"""
    id: Optional[str] = None
    user_id: str
    action: str
    details: Dict
    timestamp: datetime
    ip_address: Optional[str] = None


class AuditLog(BaseModel):
    """Audit log entry for tracking user actions"""
    id: Optional[str] = None
    user_id: str
    user_email: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    old_value: Optional[Dict] = None
    new_value: Optional[Dict] = None
    timestamp: datetime
    ip_address: Optional[str] = None


class UserManagementService:
    """Service for managing users, roles, and audit logs"""

    def __init__(self, database):
        self.db = database
        self.logger = structlog.get_logger(__name__)

    async def _ensure_connection(self):
        """Ensure database is connected"""
        if not self.db._connected:
            await self.db.connect()

    async def initialize(self):
        """Initialize user management tables"""
        try:
            await self._ensure_connection()
            
            # Create users table
            await self.db._postgres.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    status VARCHAR(50) DEFAULT 'active',
                    last_seen TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    preferences JSONB DEFAULT '{}'
                )
            """)

            # Create user_activities table
            await self.db._postgres.execute("""
                CREATE TABLE IF NOT EXISTS user_activities (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    action VARCHAR(100) NOT NULL,
                    details JSONB,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    ip_address VARCHAR(50)
                )
            """)

            # Create audit_logs table
            await self.db._postgres.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    user_email VARCHAR(255) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    resource_type VARCHAR(100),
                    resource_id VARCHAR(255),
                    old_value JSONB,
                    new_value JSONB,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    ip_address VARCHAR(50)
                )
            """)

            # Create indexes
            await self.db._postgres.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
                CREATE INDEX IF NOT EXISTS idx_user_activities_user_id ON user_activities(user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
            """)

            self.logger.info("User management tables initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize user management: {e}")
            raise

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA256"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"{salt}${pwd_hash}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            salt, pwd_hash = password_hash.split('$')
            check_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
            return check_hash == pwd_hash
        except:
            return False

    async def create_user(self, request: CreateUserRequest, created_by: Optional[str] = None) -> User:
        """Create a new user"""
        try:
            await self._ensure_connection()
            password_hash = self.hash_password(request.password)
            
            result = await self.db._postgres.fetchrow("""
                INSERT INTO users (email, name, password_hash, role, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
                RETURNING id, email, name, role, status, last_seen, created_at, updated_at, preferences
            """, request.email, request.name, password_hash, request.role.value, UserStatus.ACTIVE.value)

            user = User(
                id=str(result['id']),
                email=result['email'],
                name=result['name'],
                role=UserRole(result['role']),
                status=UserStatus(result['status']),
                last_seen=result['last_seen'],
                created_at=result['created_at'],
                updated_at=result['updated_at'],
                preferences=result['preferences'] or {}
            )

            # Log audit
            if created_by:
                await self.log_audit(
                    user_id=created_by,
                    user_email="system",
                    action="create_user",
                    resource_type="user",
                    resource_id=user.id,
                    new_value={"email": user.email, "name": user.name, "role": user.role.value}
                )

            self.logger.info(f"Created user: {user.email}", user_id=user.id, role=user.role.value)
            return user

        except Exception as e:
            self.logger.error(f"Failed to create user: {e}")
            raise

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        try:
            result = await self.db._postgres.fetchrow("""
                SELECT id, email, name, role, status, last_seen, created_at, updated_at, preferences
                FROM users WHERE id = $1
            """, int(user_id))

            if not result:
                return None

            return User(
                id=str(result['id']),
                email=result['email'],
                name=result['name'],
                role=UserRole(result['role']),
                status=UserStatus(result['status']),
                last_seen=result['last_seen'],
                created_at=result['created_at'],
                updated_at=result['updated_at'],
                preferences=result['preferences'] or {}
            )

        except Exception as e:
            self.logger.error(f"Failed to get user: {e}", user_id=user_id)
            return None

    async def list_users(
        self,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[User]:
        """List users with optional filters"""
        try:
            query = "SELECT id, email, name, role, status, last_seen, created_at, updated_at, preferences FROM users WHERE 1=1"
            params = []
            param_count = 0

            if role:
                param_count += 1
                query += f" AND role = ${param_count}"
                params.append(role.value)

            if status:
                param_count += 1
                query += f" AND status = ${param_count}"
                params.append(status.value)

            param_count += 1
            query += f" ORDER BY created_at DESC LIMIT ${param_count}"
            params.append(limit)

            param_count += 1
            query += f" OFFSET ${param_count}"
            params.append(offset)

            results = await self.db._postgres.fetch(query, *params)

            return [
                User(
                    id=str(row['id']),
                    email=row['email'],
                    name=row['name'],
                    role=UserRole(row['role']),
                    status=UserStatus(row['status']),
                    last_seen=row['last_seen'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    preferences=row['preferences'] or {}
                )
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Failed to list users: {e}")
            return []

    async def update_user(self, user_id: str, request: UpdateUserRequest, updated_by: Optional[str] = None) -> Optional[User]:
        """Update user"""
        try:
            # Get current user for audit log
            old_user = await self.get_user(user_id)
            if not old_user:
                return None

            # Build update query
            updates = []
            params = []
            param_count = 0

            if request.name is not None:
                param_count += 1
                updates.append(f"name = ${param_count}")
                params.append(request.name)

            if request.role is not None:
                param_count += 1
                updates.append(f"role = ${param_count}")
                params.append(request.role.value)

            if request.status is not None:
                param_count += 1
                updates.append(f"status = ${param_count}")
                params.append(request.status.value)

            if request.preferences is not None:
                param_count += 1
                updates.append(f"preferences = ${param_count}")
                params.append(request.preferences)

            if not updates:
                return old_user

            updates.append("updated_at = NOW()")
            param_count += 1
            params.append(int(user_id))

            query = f"UPDATE users SET {', '.join(updates)} WHERE id = ${param_count} RETURNING id, email, name, role, status, last_seen, created_at, updated_at, preferences"

            result = await self.db._postgres.fetchrow(query, *params)

            user = User(
                id=str(result['id']),
                email=result['email'],
                name=result['name'],
                role=UserRole(result['role']),
                status=UserStatus(result['status']),
                last_seen=result['last_seen'],
                created_at=result['created_at'],
                updated_at=result['updated_at'],
                preferences=result['preferences'] or {}
            )

            # Log audit
            if updated_by:
                old_value = {"name": old_user.name, "role": old_user.role.value, "status": old_user.status.value}
                new_value = {"name": user.name, "role": user.role.value, "status": user.status.value}
                
                await self.log_audit(
                    user_id=updated_by,
                    user_email="system",
                    action="update_user",
                    resource_type="user",
                    resource_id=user_id,
                    old_value=old_value,
                    new_value=new_value
                )

            self.logger.info(f"Updated user: {user.email}", user_id=user_id)
            return user

        except Exception as e:
            self.logger.error(f"Failed to update user: {e}", user_id=user_id)
            return None

    async def delete_user(self, user_id: str, deleted_by: Optional[str] = None) -> bool:
        """Soft delete user by setting status to inactive"""
        try:
            user = await self.get_user(user_id)
            if not user:
                return False

            await self.db._postgres.execute("""
                UPDATE users SET status = $1, updated_at = NOW()
                WHERE id = $2
            """, UserStatus.INACTIVE.value, int(user_id))

            # Log audit
            if deleted_by:
                await self.log_audit(
                    user_id=deleted_by,
                    user_email="system",
                    action="delete_user",
                    resource_type="user",
                    resource_id=user_id,
                    old_value={"status": user.status.value},
                    new_value={"status": UserStatus.INACTIVE.value}
                )

            self.logger.info(f"Deleted user: {user.email}", user_id=user_id)
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete user: {e}", user_id=user_id)
            return False

    async def log_activity(
        self,
        user_id: str,
        action: str,
        details: Dict,
        ip_address: Optional[str] = None
    ):
        """Log user activity"""
        try:
            await self.db._postgres.execute("""
                INSERT INTO user_activities (user_id, action, details, timestamp, ip_address)
                VALUES ($1, $2, $3, NOW(), $4)
            """, int(user_id), action, details, ip_address)

        except Exception as e:
            self.logger.error(f"Failed to log activity: {e}", user_id=user_id, action=action)

    async def get_user_activities(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[UserActivity]:
        """Get recent user activities"""
        try:
            results = await self.db._postgres.fetch("""
                SELECT id, user_id, action, details, timestamp, ip_address
                FROM user_activities
                WHERE user_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
            """, int(user_id), limit)

            return [
                UserActivity(
                    id=str(row['id']),
                    user_id=str(row['user_id']),
                    action=row['action'],
                    details=row['details'] or {},
                    timestamp=row['timestamp'],
                    ip_address=row['ip_address']
                )
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Failed to get user activities: {e}", user_id=user_id)
            return []

    async def log_audit(
        self,
        user_id: str,
        user_email: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ):
        """Log audit entry"""
        try:
            await self.db._postgres.execute("""
                INSERT INTO audit_logs (user_id, user_email, action, resource_type, resource_id, old_value, new_value, timestamp, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
            """, int(user_id) if user_id else None, user_email, action, resource_type, resource_id, old_value, new_value, ip_address)

            self.logger.info(f"Audit log: {action}", user_id=user_id, resource_type=resource_type, resource_id=resource_id)

        except Exception as e:
            self.logger.error(f"Failed to log audit: {e}", user_id=user_id, action=action)

    async def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get audit logs with optional filters"""
        try:
            query = "SELECT id, user_id, user_email, action, resource_type, resource_id, old_value, new_value, timestamp, ip_address FROM audit_logs WHERE 1=1"
            params = []
            param_count = 0

            if user_id:
                param_count += 1
                query += f" AND user_id = ${param_count}"
                params.append(int(user_id))

            if resource_type:
                param_count += 1
                query += f" AND resource_type = ${param_count}"
                params.append(resource_type)

            param_count += 1
            query += f" ORDER BY timestamp DESC LIMIT ${param_count}"
            params.append(limit)

            results = await self.db._postgres.fetch(query, *params)

            return [
                AuditLog(
                    id=str(row['id']),
                    user_id=str(row['user_id']) if row['user_id'] else None,
                    user_email=row['user_email'],
                    action=row['action'],
                    resource_type=row['resource_type'],
                    resource_id=row['resource_id'],
                    old_value=row['old_value'],
                    new_value=row['new_value'],
                    timestamp=row['timestamp'],
                    ip_address=row['ip_address']
                )
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Failed to get audit logs: {e}")
            return []

    async def update_last_seen(self, user_id: str):
        """Update user's last seen timestamp"""
        try:
            await self.db._postgres.execute("""
                UPDATE users SET last_seen = NOW() WHERE id = $1
            """, int(user_id))

        except Exception as e:
            self.logger.error(f"Failed to update last seen: {e}", user_id=user_id)

"""
Strategy Version Manager

Manages strategy versions with Git-like semantics:
- Version tagging (major.minor.patch)
- Version history
- Rollback capability
- Parameter change tracking
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class VersionStatus(Enum):
    """Strategy version status"""
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


@dataclass
class StrategyVersion:
    """A specific version of a trading strategy"""
    strategy_id: str
    version: str  # Semantic version: major.minor.patch
    parameters: Dict[str, Any]
    code_hash: str
    status: VersionStatus
    created_at: datetime
    created_by: str
    
    # Metadata
    description: str = ""
    changes: List[str] = field(default_factory=list)
    parent_version: Optional[str] = None
    
    # Performance tracking
    trades_count: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: Optional[float] = None
    
    # Deployment
    deployed_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "parameters": self.parameters,
            "code_hash": self.code_hash,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "description": self.description,
            "changes": self.changes,
            "parent_version": self.parent_version,
            "trades_count": self.trades_count,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
        }
    
    def is_production_ready(self) -> bool:
        """Check if version is ready for production"""
        return self.status == VersionStatus.ACTIVE


class VersionManager:
    """
    Manages strategy versions with Git-like version control.
    
    Features:
    - Semantic versioning (major.minor.patch)
    - Version history and lineage
    - Parameter change tracking
    - Rollback capability
    """
    
    def __init__(self):
        self.versions: Dict[str, Dict[str, StrategyVersion]] = {}  # {strategy_id: {version: StrategyVersion}}
        logger.info("VersionManager initialized")
    
    def create_version(
        self,
        strategy_id: str,
        parameters: Dict[str, Any],
        code: str,
        created_by: str,
        description: str = "",
        changes: Optional[List[str]] = None,
        version_increment: str = "patch",  # "major", "minor", "patch"
    ) -> StrategyVersion:
        """Create a new strategy version"""
        
        # Calculate code hash
        code_hash = self._calculate_hash(code)
        
        # Determine version number
        if strategy_id not in self.versions or not self.versions[strategy_id]:
            version = "1.0.0"
            parent_version = None
        else:
            latest = self.get_latest_version(strategy_id)
            version = self._increment_version(latest.version, version_increment)
            parent_version = latest.version
        
        # Create version
        strategy_version = StrategyVersion(
            strategy_id=strategy_id,
            version=version,
            parameters=parameters,
            code_hash=code_hash,
            status=VersionStatus.DRAFT,
            created_at=datetime.utcnow(),
            created_by=created_by,
            description=description,
            changes=changes or [],
            parent_version=parent_version,
        )
        
        # Store version
        if strategy_id not in self.versions:
            self.versions[strategy_id] = {}
        
        self.versions[strategy_id][version] = strategy_version
        
        logger.info(f"Created version {version} for strategy {strategy_id}")
        return strategy_version
    
    def get_version(self, strategy_id: str, version: str) -> Optional[StrategyVersion]:
        """Get specific version"""
        if strategy_id not in self.versions:
            return None
        return self.versions[strategy_id].get(version)
    
    def get_latest_version(self, strategy_id: str) -> Optional[StrategyVersion]:
        """Get latest version of strategy"""
        if strategy_id not in self.versions or not self.versions[strategy_id]:
            return None
        
        versions = list(self.versions[strategy_id].values())
        versions.sort(key=lambda v: self._version_to_tuple(v.version), reverse=True)
        return versions[0]
    
    def get_active_version(self, strategy_id: str) -> Optional[StrategyVersion]:
        """Get currently active version"""
        if strategy_id not in self.versions:
            return None
        
        for version in self.versions[strategy_id].values():
            if version.status == VersionStatus.ACTIVE:
                return version
        
        return None
    
    def list_versions(
        self,
        strategy_id: str,
        status: Optional[VersionStatus] = None,
    ) -> List[StrategyVersion]:
        """List all versions of a strategy"""
        if strategy_id not in self.versions:
            return []
        
        versions = list(self.versions[strategy_id].values())
        
        if status:
            versions = [v for v in versions if v.status == status]
        
        # Sort by version number (newest first)
        versions.sort(key=lambda v: self._version_to_tuple(v.version), reverse=True)
        return versions
    
    def promote_version(
        self,
        strategy_id: str,
        version: str,
        new_status: VersionStatus,
    ) -> bool:
        """Promote version to new status"""
        strategy_version = self.get_version(strategy_id, version)
        if not strategy_version:
            logger.warning(f"Version {version} not found for strategy {strategy_id}")
            return False
        
        old_status = strategy_version.status
        strategy_version.status = new_status
        
        # If promoting to ACTIVE, demote other active versions
        if new_status == VersionStatus.ACTIVE:
            for v in self.versions[strategy_id].values():
                if v.version != version and v.status == VersionStatus.ACTIVE:
                    v.status = VersionStatus.DEPRECATED
                    logger.info(f"Deprecated version {v.version} of strategy {strategy_id}")
            
            strategy_version.deployed_at = datetime.utcnow()
        
        # If retiring, set retired timestamp
        if new_status == VersionStatus.RETIRED:
            strategy_version.retired_at = datetime.utcnow()
        
        logger.info(f"Promoted {strategy_id} v{version}: {old_status.value} -> {new_status.value}")
        return True
    
    def rollback_to_version(
        self,
        strategy_id: str,
        target_version: str,
    ) -> bool:
        """Rollback to a previous version"""
        target = self.get_version(strategy_id, target_version)
        if not target:
            logger.warning(f"Target version {target_version} not found")
            return False
        
        # Demote current active version
        current_active = self.get_active_version(strategy_id)
        if current_active:
            current_active.status = VersionStatus.DEPRECATED
        
        # Activate target version
        target.status = VersionStatus.ACTIVE
        target.deployed_at = datetime.utcnow()
        
        logger.info(f"Rolled back {strategy_id} to version {target_version}")
        return True
    
    def compare_versions(
        self,
        strategy_id: str,
        version1: str,
        version2: str,
    ) -> Dict[str, Any]:
        """Compare two versions"""
        v1 = self.get_version(strategy_id, version1)
        v2 = self.get_version(strategy_id, version2)
        
        if not v1 or not v2:
            return {"error": "One or both versions not found"}
        
        # Compare parameters
        param_changes = self._compare_parameters(v1.parameters, v2.parameters)
        
        # Compare performance
        perf_comparison = {
            "version1": {
                "trades": v1.trades_count,
                "pnl": v1.total_pnl,
                "win_rate": v1.win_rate,
                "sharpe": v1.sharpe_ratio,
            },
            "version2": {
                "trades": v2.trades_count,
                "pnl": v2.total_pnl,
                "win_rate": v2.win_rate,
                "sharpe": v2.sharpe_ratio,
            },
        }
        
        return {
            "strategy_id": strategy_id,
            "version1": version1,
            "version2": version2,
            "code_changed": v1.code_hash != v2.code_hash,
            "parameter_changes": param_changes,
            "performance_comparison": perf_comparison,
        }
    
    def get_version_lineage(self, strategy_id: str, version: str) -> List[StrategyVersion]:
        """Get the lineage (ancestry) of a version"""
        lineage = []
        current_version = version
        
        while current_version:
            v = self.get_version(strategy_id, current_version)
            if not v:
                break
            
            lineage.append(v)
            current_version = v.parent_version
        
        return lineage
    
    def update_performance(
        self,
        strategy_id: str,
        version: str,
        trades_count: int,
        total_pnl: float,
        win_rate: float,
        sharpe_ratio: Optional[float] = None,
    ):
        """Update performance metrics for a version"""
        strategy_version = self.get_version(strategy_id, version)
        if not strategy_version:
            return
        
        strategy_version.trades_count = trades_count
        strategy_version.total_pnl = total_pnl
        strategy_version.win_rate = win_rate
        strategy_version.sharpe_ratio = sharpe_ratio
        
        logger.debug(f"Updated performance for {strategy_id} v{version}")
    
    def _calculate_hash(self, code: str) -> str:
        """Calculate SHA256 hash of code"""
        return hashlib.sha256(code.encode()).hexdigest()[:16]
    
    def _increment_version(self, version: str, increment: str) -> str:
        """Increment version number"""
        major, minor, patch = map(int, version.split('.'))
        
        if increment == "major":
            major += 1
            minor = 0
            patch = 0
        elif increment == "minor":
            minor += 1
            patch = 0
        else:  # patch
            patch += 1
        
        return f"{major}.{minor}.{patch}"
    
    def _version_to_tuple(self, version: str) -> tuple:
        """Convert version string to tuple for comparison"""
        return tuple(map(int, version.split('.')))
    
    def _compare_parameters(
        self,
        params1: Dict[str, Any],
        params2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare two parameter dictionaries"""
        changes = {
            "added": {},
            "removed": {},
            "changed": {},
        }
        
        # Find added and changed
        for key, value2 in params2.items():
            if key not in params1:
                changes["added"][key] = value2
            elif params1[key] != value2:
                changes["changed"][key] = {
                    "from": params1[key],
                    "to": value2,
                }
        
        # Find removed
        for key, value1 in params1.items():
            if key not in params2:
                changes["removed"][key] = value1
        
        return changes

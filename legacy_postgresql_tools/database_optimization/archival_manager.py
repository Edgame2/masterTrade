"""
Archival Manager

Intelligent data archival system with automatic policy enforcement,
compression, and lifecycle management for historical data.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import gzip
import lzma
import bz2
import zlib

try:
    import asyncpg
    import pandas as pd
    import numpy as np
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logging.warning("AsyncPG not available for PostgreSQL operations")

try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logging.warning("Boto3 not available for S3 operations")

logger = logging.getLogger(__name__)


class CompressionType(Enum):
    """Supported compression algorithms"""
    GZIP = "gzip"
    LZMA = "lzma"
    BZIP2 = "bzip2"
    ZLIB = "zlib"
    NONE = "none"


class ArchivalStatus(Enum):
    """Archival operation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORED = "restored"


class StorageLocation(Enum):
    """Storage location types"""
    LOCAL_DISK = "local_disk"
    S3 = "s3"
    AZURE_BLOB = "azure_blob"
    GCS = "gcs"
    TAPE = "tape"


@dataclass
class ArchivalRule:
    """Archival rule configuration"""
    rule_id: str
    table_name: str
    retention_days: int
    date_column: str = "created_at"
    compression_type: CompressionType = CompressionType.GZIP
    storage_location: StorageLocation = StorageLocation.LOCAL_DISK
    storage_config: Dict[str, Any] = field(default_factory=dict)
    partition_column: Optional[str] = None
    where_clause: Optional[str] = None
    priority: int = 1
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_eligible_for_archival(self, record_date: datetime) -> bool:
        """Check if record is eligible for archival"""
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        return record_date < cutoff_date
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "rule_id": self.rule_id,
            "table_name": self.table_name,
            "retention_days": self.retention_days,
            "date_column": self.date_column,
            "compression_type": self.compression_type.value,
            "storage_location": self.storage_location.value,
            "storage_config": self.storage_config,
            "partition_column": self.partition_column,
            "where_clause": self.where_clause,
            "priority": self.priority,
            "enabled": self.enabled,
            "metadata": self.metadata
        }


@dataclass
class ArchivalPolicy:
    """Archival policy containing multiple rules"""
    policy_id: str
    name: str
    description: str
    rules: List[ArchivalRule] = field(default_factory=list)
    schedule_cron: str = "0 2 * * *"  # Daily at 2 AM
    max_concurrent_operations: int = 3
    notification_emails: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def get_rules_for_table(self, table_name: str) -> List[ArchivalRule]:
        """Get archival rules for specific table"""
        return [rule for rule in self.rules if rule.table_name == table_name and rule.enabled]
    
    def add_rule(self, rule: ArchivalRule):
        """Add archival rule to policy"""
        self.rules.append(rule)
        self.updated_at = datetime.utcnow()
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove archival rule from policy"""
        for i, rule in enumerate(self.rules):
            if rule.rule_id == rule_id:
                del self.rules[i]
                self.updated_at = datetime.utcnow()
                return True
        return False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "rules": [rule.to_dict() for rule in self.rules],
            "schedule_cron": self.schedule_cron,
            "max_concurrent_operations": self.max_concurrent_operations,
            "notification_emails": self.notification_emails,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class ArchivalOperation:
    """Archival operation tracking"""
    operation_id: str
    rule_id: str
    table_name: str
    status: ArchivalStatus = ArchivalStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    records_processed: int = 0
    records_archived: int = 0
    data_size_bytes: int = 0
    compressed_size_bytes: int = 0
    storage_path: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio"""
        if self.data_size_bytes > 0 and self.compressed_size_bytes > 0:
            return self.data_size_bytes / self.compressed_size_bytes
        return 1.0
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate operation duration"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "operation_id": self.operation_id,
            "rule_id": self.rule_id,
            "table_name": self.table_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "records_processed": self.records_processed,
            "records_archived": self.records_archived,
            "data_size_bytes": self.data_size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "compression_ratio": self.compression_ratio,
            "duration_seconds": self.duration_seconds,
            "storage_path": self.storage_path,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


class DataCompressor:
    """Data compression utilities"""
    
    @staticmethod
    def compress_data(data: bytes, compression_type: CompressionType, level: int = 6) -> bytes:
        """Compress data using specified algorithm"""
        
        if compression_type == CompressionType.GZIP:
            return gzip.compress(data, compresslevel=level)
        elif compression_type == CompressionType.LZMA:
            return lzma.compress(data, preset=level)
        elif compression_type == CompressionType.BZIP2:
            return bz2.compress(data, compresslevel=level)
        elif compression_type == CompressionType.ZLIB:
            return zlib.compress(data, level)
        else:
            return data
    
    @staticmethod
    def decompress_data(data: bytes, compression_type: CompressionType) -> bytes:
        """Decompress data using specified algorithm"""
        
        if compression_type == CompressionType.GZIP:
            return gzip.decompress(data)
        elif compression_type == CompressionType.LZMA:
            return lzma.decompress(data)
        elif compression_type == CompressionType.BZIP2:
            return bz2.decompress(data)
        elif compression_type == CompressionType.ZLIB:
            return zlib.decompress(data)
        else:
            return data
    
    @staticmethod
    def estimate_compression_ratio(sample_data: bytes, compression_type: CompressionType) -> float:
        """Estimate compression ratio using sample data"""
        
        if len(sample_data) == 0:
            return 1.0
        
        try:
            compressed = DataCompressor.compress_data(sample_data, compression_type)
            return len(sample_data) / len(compressed)
        except Exception:
            return 1.0


class StorageManager:
    """Storage backend management"""
    
    def __init__(self):
        self.s3_client = None
        if S3_AVAILABLE:
            try:
                self.s3_client = boto3.client('s3')
            except Exception:
                logger.warning("Failed to initialize S3 client")
    
    async def store_data(
        self,
        data: bytes,
        storage_location: StorageLocation,
        storage_config: Dict[str, Any],
        file_path: str
    ) -> str:
        """Store data to specified storage backend"""
        
        if storage_location == StorageLocation.LOCAL_DISK:
            return await self._store_local(data, storage_config, file_path)
        elif storage_location == StorageLocation.S3:
            return await self._store_s3(data, storage_config, file_path)
        else:
            raise ValueError(f"Unsupported storage location: {storage_location}")
    
    async def _store_local(self, data: bytes, config: Dict, file_path: str) -> str:
        """Store data to local disk"""
        
        base_path = Path(config.get('base_path', '/tmp/archives'))
        base_path.mkdir(parents=True, exist_ok=True)
        
        full_path = base_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'wb') as f:
            f.write(data)
        
        return str(full_path)
    
    async def _store_s3(self, data: bytes, config: Dict, file_path: str) -> str:
        """Store data to Amazon S3"""
        
        if not self.s3_client:
            raise RuntimeError("S3 client not available")
        
        bucket = config['bucket']
        key = f"{config.get('prefix', 'archives')}/{file_path}"
        
        try:
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                StorageClass=config.get('storage_class', 'STANDARD_IA'),
                ServerSideEncryption=config.get('encryption', 'AES256')
            )
            
            return f"s3://{bucket}/{key}"
        
        except ClientError as e:
            logger.error(f"S3 storage failed: {e}")
            raise
    
    async def retrieve_data(
        self,
        storage_path: str,
        storage_location: StorageLocation,
        storage_config: Dict[str, Any]
    ) -> bytes:
        """Retrieve data from storage"""
        
        if storage_location == StorageLocation.LOCAL_DISK:
            return await self._retrieve_local(storage_path)
        elif storage_location == StorageLocation.S3:
            return await self._retrieve_s3(storage_path, storage_config)
        else:
            raise ValueError(f"Unsupported storage location: {storage_location}")
    
    async def _retrieve_local(self, file_path: str) -> bytes:
        """Retrieve data from local disk"""
        
        with open(file_path, 'rb') as f:
            return f.read()
    
    async def _retrieve_s3(self, s3_path: str, config: Dict) -> bytes:
        """Retrieve data from Amazon S3"""
        
        if not self.s3_client:
            raise RuntimeError("S3 client not available")
        
        # Parse S3 path
        if s3_path.startswith('s3://'):
            s3_path = s3_path[5:]
        
        bucket, key = s3_path.split('/', 1)
        
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
        
        except ClientError as e:
            logger.error(f"S3 retrieval failed: {e}")
            raise


class ArchivalManager:
    """
    Intelligent data archival system
    
    Manages automatic data archival with policy-based retention,
    compression, and storage lifecycle management.
    """
    
    def __init__(
        self,
        db_connection_string: str,
        policies_dir: str = "policies",
        max_concurrent_operations: int = 3
    ):
        self.db_connection_string = db_connection_string
        self.policies_dir = Path(policies_dir)
        self.policies_dir.mkdir(exist_ok=True)
        
        self.max_concurrent_operations = max_concurrent_operations
        self.policies: Dict[str, ArchivalPolicy] = {}
        self.active_operations: Dict[str, ArchivalOperation] = {}
        self.operation_history: List[ArchivalOperation] = []
        
        # Components
        self.storage_manager = StorageManager()
        self.compressor = DataCompressor()
        
        # Load existing policies
        self._load_policies()
        
        # Scheduler state
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
    
    def _load_policies(self):
        """Load archival policies from storage"""
        
        try:
            for policy_file in self.policies_dir.glob("*.json"):
                with open(policy_file, 'r') as f:
                    policy_dict = json.load(f)
                
                policy = self._dict_to_policy(policy_dict)
                self.policies[policy.policy_id] = policy
                
                logger.info(f"Loaded archival policy: {policy.policy_id}")
        
        except Exception as e:
            logger.error(f"Failed to load policies: {e}")
    
    def _dict_to_policy(self, policy_dict: Dict) -> ArchivalPolicy:
        """Convert dictionary to ArchivalPolicy"""
        
        rules = []
        for rule_dict in policy_dict.get("rules", []):
            rule = ArchivalRule(
                rule_id=rule_dict["rule_id"],
                table_name=rule_dict["table_name"],
                retention_days=rule_dict["retention_days"],
                date_column=rule_dict.get("date_column", "created_at"),
                compression_type=CompressionType(rule_dict.get("compression_type", "gzip")),
                storage_location=StorageLocation(rule_dict.get("storage_location", "local_disk")),
                storage_config=rule_dict.get("storage_config", {}),
                partition_column=rule_dict.get("partition_column"),
                where_clause=rule_dict.get("where_clause"),
                priority=rule_dict.get("priority", 1),
                enabled=rule_dict.get("enabled", True),
                metadata=rule_dict.get("metadata", {})
            )
            rules.append(rule)
        
        return ArchivalPolicy(
            policy_id=policy_dict["policy_id"],
            name=policy_dict["name"],
            description=policy_dict["description"],
            rules=rules,
            schedule_cron=policy_dict.get("schedule_cron", "0 2 * * *"),
            max_concurrent_operations=policy_dict.get("max_concurrent_operations", 3),
            notification_emails=policy_dict.get("notification_emails", []),
            created_at=datetime.fromisoformat(policy_dict.get("created_at", datetime.utcnow().isoformat())),
            updated_at=datetime.fromisoformat(policy_dict.get("updated_at", datetime.utcnow().isoformat()))
        )
    
    def create_policy(
        self,
        policy_id: str,
        name: str,
        description: str,
        rules: List[ArchivalRule],
        schedule_cron: str = "0 2 * * *"
    ) -> ArchivalPolicy:
        """Create new archival policy"""
        
        policy = ArchivalPolicy(
            policy_id=policy_id,
            name=name,
            description=description,
            rules=rules,
            schedule_cron=schedule_cron
        )
        
        self.policies[policy_id] = policy
        self._save_policy(policy)
        
        logger.info(f"Created archival policy: {policy_id}")
        return policy
    
    def _save_policy(self, policy: ArchivalPolicy) -> bool:
        """Save archival policy to storage"""
        
        try:
            policy_file = self.policies_dir / f"{policy.policy_id}.json"
            with open(policy_file, 'w') as f:
                json.dump(policy.to_dict(), f, indent=2, default=str)
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to save policy {policy.policy_id}: {e}")
            return False
    
    def add_rule_to_policy(self, policy_id: str, rule: ArchivalRule) -> bool:
        """Add archival rule to existing policy"""
        
        if policy_id not in self.policies:
            logger.error(f"Policy not found: {policy_id}")
            return False
        
        policy = self.policies[policy_id]
        policy.add_rule(rule)
        
        return self._save_policy(policy)
    
    async def start_scheduler(self):
        """Start the archival scheduler"""
        
        if self._running:
            logger.warning("Archival scheduler already running")
            return
        
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("Archival scheduler started")
    
    async def stop_scheduler(self):
        """Stop the archival scheduler"""
        
        self._running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Archival scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        
        while self._running:
            try:
                # Check and execute archival operations
                await self._process_archival_policies()
                
                # Clean up completed operations
                self._cleanup_operations()
                
                # Sleep for 1 hour
                await asyncio.sleep(3600)
            
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(3600)
    
    async def _process_archival_policies(self):
        """Process all archival policies"""
        
        for policy in self.policies.values():
            try:
                # Check if it's time to run this policy (simplified - would use cron parsing)
                await self._execute_archival_policy(policy)
            
            except Exception as e:
                logger.error(f"Failed to process policy {policy.policy_id}: {e}")
    
    async def _execute_archival_policy(self, policy: ArchivalPolicy):
        """Execute archival policy"""
        
        # Check concurrent operations limit
        active_count = len([op for op in self.active_operations.values() 
                           if op.status == ArchivalStatus.IN_PROGRESS])
        
        if active_count >= self.max_concurrent_operations:
            logger.info("Maximum concurrent operations reached")
            return
        
        # Execute rules by priority
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if not rule.enabled:
                continue
            
            # Check if we can start another operation
            if len(self.active_operations) >= self.max_concurrent_operations:
                break
            
            try:
                await self._execute_archival_rule(rule)
            
            except Exception as e:
                logger.error(f"Failed to execute rule {rule.rule_id}: {e}")
    
    async def _execute_archival_rule(self, rule: ArchivalRule):
        """Execute individual archival rule"""
        
        if not ASYNCPG_AVAILABLE:
            logger.error("AsyncPG not available for database operations")
            return
        
        operation_id = f"{rule.rule_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        operation = ArchivalOperation(
            operation_id=operation_id,
            rule_id=rule.rule_id,
            table_name=rule.table_name,
            status=ArchivalStatus.PENDING
        )
        
        self.active_operations[operation_id] = operation
        
        try:
            operation.status = ArchivalStatus.IN_PROGRESS
            operation.started_at = datetime.utcnow()
            
            logger.info(f"Starting archival operation: {operation_id}")
            
            # Connect to database
            conn = await asyncpg.connect(self.db_connection_string)
            
            try:
                # Calculate cutoff date
                cutoff_date = datetime.utcnow() - timedelta(days=rule.retention_days)
                
                # Build query to identify archival candidates
                where_conditions = [f"{rule.date_column} < $1"]
                if rule.where_clause:
                    where_conditions.append(rule.where_clause)
                
                where_clause = " AND ".join(where_conditions)
                
                # Count records to archive
                count_query = f"""
                    SELECT COUNT(*) 
                    FROM {rule.table_name} 
                    WHERE {where_clause}
                """
                
                record_count = await conn.fetchval(count_query, cutoff_date)
                operation.records_processed = record_count
                
                if record_count == 0:
                    logger.info(f"No records to archive for rule {rule.rule_id}")
                    operation.status = ArchivalStatus.COMPLETED
                    operation.completed_at = datetime.utcnow()
                    return
                
                # Extract data for archival
                select_query = f"""
                    SELECT * 
                    FROM {rule.table_name} 
                    WHERE {where_clause}
                    ORDER BY {rule.date_column}
                """
                
                # Fetch data in chunks to avoid memory issues
                chunk_size = 10000
                archived_records = 0
                
                async with conn.transaction():
                    cursor = await conn.cursor(select_query, cutoff_date)
                    
                    chunk_number = 0
                    while True:
                        rows = await cursor.fetch(chunk_size)
                        if not rows:
                            break
                        
                        # Convert to DataFrame for easier handling
                        df = pd.DataFrame(rows)
                        
                        # Archive this chunk
                        storage_path = await self._archive_data_chunk(
                            df, rule, operation_id, chunk_number
                        )
                        
                        if storage_path:
                            # Delete archived records from main table
                            ids_to_delete = [row['id'] for row in rows if 'id' in row]
                            if ids_to_delete:
                                delete_query = f"DELETE FROM {rule.table_name} WHERE id = ANY($1)"
                                await conn.execute(delete_query, ids_to_delete)
                            
                            archived_records += len(rows)
                        
                        chunk_number += 1
                
                operation.records_archived = archived_records
                operation.status = ArchivalStatus.COMPLETED
                operation.completed_at = datetime.utcnow()
                
                logger.info(f"Archival operation completed: {operation_id} ({archived_records} records)")
            
            finally:
                await conn.close()
        
        except Exception as e:
            operation.status = ArchivalStatus.FAILED
            operation.error_message = str(e)
            operation.completed_at = datetime.utcnow()
            
            logger.error(f"Archival operation failed: {operation_id} - {e}")
        
        finally:
            # Move to history
            self.operation_history.append(operation)
            if operation_id in self.active_operations:
                del self.active_operations[operation_id]
    
    async def _archive_data_chunk(
        self,
        df: pd.DataFrame,
        rule: ArchivalRule,
        operation_id: str,
        chunk_number: int
    ) -> Optional[str]:
        """Archive a chunk of data"""
        
        try:
            # Convert DataFrame to JSON
            json_data = df.to_json(orient='records', date_format='iso')
            data_bytes = json_data.encode('utf-8')
            
            # Compress data
            compressed_data = self.compressor.compress_data(data_bytes, rule.compression_type)
            
            # Generate storage path
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            file_name = f"{rule.table_name}_{timestamp}_chunk_{chunk_number}.json"
            
            if rule.compression_type != CompressionType.NONE:
                file_name += f".{rule.compression_type.value}"
            
            storage_path = f"{operation_id}/{file_name}"
            
            # Store data
            stored_path = await self.storage_manager.store_data(
                compressed_data,
                rule.storage_location,
                rule.storage_config,
                storage_path
            )
            
            # Update operation metrics
            operation = self.active_operations.get(operation_id)
            if operation:
                operation.data_size_bytes += len(data_bytes)
                operation.compressed_size_bytes += len(compressed_data)
                operation.storage_path = stored_path
            
            return stored_path
        
        except Exception as e:
            logger.error(f"Failed to archive data chunk: {e}")
            return None
    
    def _cleanup_operations(self):
        """Clean up completed operations"""
        
        # Keep only last 100 operations in history
        if len(self.operation_history) > 100:
            self.operation_history = self.operation_history[-100:]
    
    async def restore_archived_data(
        self,
        operation_id: str,
        target_table: Optional[str] = None
    ) -> bool:
        """Restore archived data back to database"""
        
        # Find operation in history
        operation = None
        for op in self.operation_history:
            if op.operation_id == operation_id:
                operation = op
                break
        
        if not operation or operation.status != ArchivalStatus.COMPLETED:
            logger.error(f"Operation not found or not completed: {operation_id}")
            return False
        
        try:
            # Find the archival rule
            rule = None
            for policy in self.policies.values():
                for r in policy.rules:
                    if r.rule_id == operation.rule_id:
                        rule = r
                        break
                if rule:
                    break
            
            if not rule:
                logger.error(f"Archival rule not found: {operation.rule_id}")
                return False
            
            # Retrieve and decompress archived data
            compressed_data = await self.storage_manager.retrieve_data(
                operation.storage_path,
                rule.storage_location,
                rule.storage_config
            )
            
            data_bytes = self.compressor.decompress_data(compressed_data, rule.compression_type)
            json_data = data_bytes.decode('utf-8')
            
            # Parse JSON data
            records = json.loads(json_data)
            
            if not records:
                logger.info("No records to restore")
                return True
            
            # Connect to database and restore data
            conn = await asyncpg.connect(self.db_connection_string)
            
            try:
                table_name = target_table or rule.table_name
                
                # Build insert query based on first record structure
                columns = list(records[0].keys())
                placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
                
                insert_query = f"""
                    INSERT INTO {table_name} ({", ".join(columns)})
                    VALUES ({placeholders})
                """
                
                # Insert records
                for record in records:
                    values = [record[col] for col in columns]
                    await conn.execute(insert_query, *values)
                
                logger.info(f"Restored {len(records)} records to {table_name}")
                
                # Update operation status
                operation.status = ArchivalStatus.RESTORED
                
                return True
            
            finally:
                await conn.close()
        
        except Exception as e:
            logger.error(f"Failed to restore archived data: {e}")
            return False
    
    def get_archival_statistics(self) -> Dict[str, Any]:
        """Get archival system statistics"""
        
        total_operations = len(self.operation_history)
        completed_operations = len([op for op in self.operation_history if op.status == ArchivalStatus.COMPLETED])
        failed_operations = len([op for op in self.operation_history if op.status == ArchivalStatus.FAILED])
        
        total_records_archived = sum(op.records_archived for op in self.operation_history)
        total_data_archived = sum(op.data_size_bytes for op in self.operation_history)
        total_compressed_size = sum(op.compressed_size_bytes for op in self.operation_history)
        
        avg_compression_ratio = 0
        if total_compressed_size > 0:
            avg_compression_ratio = total_data_archived / total_compressed_size
        
        return {
            "policies": {
                "total": len(self.policies),
                "active": len([p for p in self.policies.values() if any(r.enabled for r in p.rules)])
            },
            "operations": {
                "total": total_operations,
                "completed": completed_operations,
                "failed": failed_operations,
                "success_rate": completed_operations / total_operations if total_operations > 0 else 0,
                "active": len(self.active_operations)
            },
            "data": {
                "records_archived": total_records_archived,
                "data_size_bytes": total_data_archived,
                "compressed_size_bytes": total_compressed_size,
                "average_compression_ratio": avg_compression_ratio,
                "storage_savings_percent": (1 - (total_compressed_size / total_data_archived)) * 100 if total_data_archived > 0 else 0
            }
        }
    
    def list_policies(self) -> List[Dict[str, Any]]:
        """List all archival policies"""
        
        policies = []
        for policy in self.policies.values():
            policies.append({
                "policy_id": policy.policy_id,
                "name": policy.name,
                "description": policy.description,
                "rules_count": len(policy.rules),
                "active_rules": len([r for r in policy.rules if r.enabled]),
                "schedule": policy.schedule_cron,
                "created_at": policy.created_at.isoformat(),
                "updated_at": policy.updated_at.isoformat()
            })
        
        return policies
    
    def get_operation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get archival operation history"""
        
        recent_operations = sorted(
            self.operation_history,
            key=lambda op: op.started_at or datetime.min,
            reverse=True
        )[:limit]
        
        return [op.to_dict() for op in recent_operations]
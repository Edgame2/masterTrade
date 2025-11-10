"""
Database Optimization API

REST API for database optimization system providing endpoints for
monitoring, optimization, archival management, and performance analytics.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Path as PathParam
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from pydantic import BaseModel, Field
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logging.warning("FastAPI not available for API endpoints")

# Import our optimization components
from .archival_manager import ArchivalManager, ArchivalRule, ArchivalPolicy, CompressionType, StorageLocation
from .query_optimizer import QueryOptimizer, QueryMetrics, IndexCandidate
from .performance_monitor import PerformanceMonitor, DatabaseMetrics, PerformanceAlert, AlertSeverity

logger = logging.getLogger(__name__)

# Pydantic models for API
if FASTAPI_AVAILABLE:
    
    class ArchivalRuleRequest(BaseModel):
        table_name: str
        retention_days: int
        date_column: str = "created_at"
        compression_type: str = "gzip"
        storage_location: str = "local_disk"
        storage_config: Dict[str, Any] = {}
        where_clause: Optional[str] = None
        priority: int = 1
        
    class ArchivalPolicyRequest(BaseModel):
        name: str
        description: str
        rules: List[ArchivalRuleRequest]
        schedule_cron: str = "0 2 * * *"
        notification_emails: List[str] = []
    
    class QueryAnalysisRequest(BaseModel):
        query: str
        
    class PerformanceThresholdUpdate(BaseModel):
        metric_type: str
        warning_threshold: float
        critical_threshold: float
    
    class EmailConfigRequest(BaseModel):
        smtp_host: str
        smtp_port: int = 587
        username: str = ""
        password: str = ""
        use_tls: bool = True
        notification_emails: List[str] = []
    
    class OptimizationRequest(BaseModel):
        force_optimization: bool = False
        max_indexes_to_create: int = 3
        include_tables: List[str] = []
        exclude_tables: List[str] = []


class DatabaseOptimizationAPI:
    """
    REST API for database optimization system
    
    Provides comprehensive endpoints for monitoring, optimization,
    archival management, and performance analytics.
    """
    
    def __init__(
        self,
        db_connection_string: str,
        archival_manager: Optional[ArchivalManager] = None,
        query_optimizer: Optional[QueryOptimizer] = None,
        performance_monitor: Optional[PerformanceMonitor] = None,
        api_key: Optional[str] = None
    ):
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI not available")
        
        self.db_connection_string = db_connection_string
        self.api_key = api_key
        
        # Initialize components if not provided
        self.archival_manager = archival_manager or ArchivalManager(db_connection_string)
        self.query_optimizer = query_optimizer or QueryOptimizer(db_connection_string)
        self.performance_monitor = performance_monitor or PerformanceMonitor(db_connection_string)
        
        # Initialize FastAPI app
        self.app = FastAPI(
            title="Database Optimization API",
            description="Comprehensive database optimization and monitoring system",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc"
        )
        
        # Security
        self.security = HTTPBearer() if api_key else None
        
        # Setup routes
        self._setup_routes()
        
        # Background task tracking
        self.background_tasks: Dict[str, Any] = {}
    
    def _setup_routes(self):
        """Setup API routes"""
        
        # Health check
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        
        # System status
        @self.app.get("/status")
        async def system_status(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            return {
                "archival_manager": {
                    "policies": len(self.archival_manager.policies),
                    "active_operations": len(self.archival_manager.active_operations)
                },
                "query_optimizer": {
                    "cached_queries": len(self.query_optimizer.query_analyzer.query_cache),
                    "running": self.query_optimizer._running
                },
                "performance_monitor": {
                    "running": self.performance_monitor._running,
                    "active_alerts": len(self.performance_monitor.active_alerts),
                    "current_health_score": self.performance_monitor.current_metrics.get_health_score() if self.performance_monitor.current_metrics else None
                }
            }
        
        # Performance Monitoring Endpoints
        @self.app.get("/performance/current")
        async def get_current_performance(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            metrics = self.performance_monitor.get_current_metrics()
            if metrics:
                return metrics.to_dict()
            else:
                raise HTTPException(status_code=404, detail="No current metrics available")
        
        @self.app.get("/performance/history")
        async def get_performance_history(
            hours: int = Query(24, ge=1, le=168),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            metrics = self.performance_monitor.get_metrics_history(hours)
            return [m.to_dict() for m in metrics]
        
        @self.app.get("/performance/summary")
        async def get_performance_summary(
            hours: int = Query(24, ge=1, le=168),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            return self.performance_monitor.get_performance_summary(hours)
        
        @self.app.get("/performance/alerts")
        async def get_performance_alerts(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            return {
                "active": [alert.to_dict() for alert in self.performance_monitor.get_active_alerts()],
                "history": [alert.to_dict() for alert in self.performance_monitor.get_alert_history()]
            }
        
        @self.app.post("/performance/start-monitoring")
        async def start_performance_monitoring(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            await self.performance_monitor.start_monitoring()
            return {"status": "started", "message": "Performance monitoring started"}
        
        @self.app.post("/performance/stop-monitoring")
        async def stop_performance_monitoring(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            await self.performance_monitor.stop_monitoring()
            return {"status": "stopped", "message": "Performance monitoring stopped"}
        
        @self.app.put("/performance/thresholds")
        async def update_performance_thresholds(
            threshold_update: PerformanceThresholdUpdate,
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            try:
                from .performance_monitor import MetricType
                metric_type = MetricType(threshold_update.metric_type)
                
                thresholds = {
                    AlertSeverity.WARNING: threshold_update.warning_threshold,
                    AlertSeverity.CRITICAL: threshold_update.critical_threshold
                }
                
                self.performance_monitor.update_thresholds(metric_type, thresholds)
                
                return {
                    "status": "updated",
                    "metric_type": threshold_update.metric_type,
                    "thresholds": thresholds
                }
            
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid metric type: {e}")
        
        # Query Optimization Endpoints
        @self.app.post("/optimization/analyze-query")
        async def analyze_query(
            request: QueryAnalysisRequest,
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            try:
                analysis = await self.query_optimizer.analyze_query(request.query)
                return analysis
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Query analysis failed: {e}")
        
        @self.app.get("/optimization/slow-queries")
        async def get_slow_queries(
            threshold_ms: float = Query(1000, ge=100),
            limit: int = Query(10, ge=1, le=50),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            slow_queries = self.query_optimizer.query_analyzer.get_slow_queries(threshold_ms, limit)
            return [q.to_dict() for q in slow_queries]
        
        @self.app.get("/optimization/recommendations")
        async def get_optimization_recommendations(
            limit: int = Query(10, ge=1, le=50),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            recommendations = self.query_optimizer.get_query_recommendations(limit)
            return recommendations
        
        @self.app.post("/optimization/run-cycle")
        async def run_optimization_cycle(
            request: OptimizationRequest,
            background_tasks: BackgroundTasks,
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            task_id = f"optimization_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            background_tasks.add_task(
                self._run_optimization_background,
                task_id,
                request.max_indexes_to_create,
                request.include_tables,
                request.exclude_tables
            )
            
            return {
                "status": "started",
                "task_id": task_id,
                "message": "Optimization cycle started in background"
            }
        
        @self.app.get("/optimization/statistics")
        async def get_optimization_statistics(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            return self.query_optimizer.get_optimization_statistics()
        
        @self.app.post("/optimization/start")
        async def start_query_optimizer(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            await self.query_optimizer.start_optimizer()
            return {"status": "started", "message": "Query optimizer started"}
        
        @self.app.post("/optimization/stop")
        async def stop_query_optimizer(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            await self.query_optimizer.stop_optimizer()
            return {"status": "stopped", "message": "Query optimizer stopped"}
        
        # Archival Management Endpoints
        @self.app.get("/archival/policies")
        async def list_archival_policies(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            return self.archival_manager.list_policies()
        
        @self.app.post("/archival/policies")
        async def create_archival_policy(
            policy_request: ArchivalPolicyRequest,
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            try:
                # Convert request to archival rules
                rules = []
                for rule_req in policy_request.rules:
                    rule = ArchivalRule(
                        rule_id=f"{policy_request.name}_{rule_req.table_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                        table_name=rule_req.table_name,
                        retention_days=rule_req.retention_days,
                        date_column=rule_req.date_column,
                        compression_type=CompressionType(rule_req.compression_type),
                        storage_location=StorageLocation(rule_req.storage_location),
                        storage_config=rule_req.storage_config,
                        where_clause=rule_req.where_clause,
                        priority=rule_req.priority
                    )
                    rules.append(rule)
                
                # Create policy
                policy_id = f"policy_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                
                policy = self.archival_manager.create_policy(
                    policy_id=policy_id,
                    name=policy_request.name,
                    description=policy_request.description,
                    rules=rules,
                    schedule_cron=policy_request.schedule_cron
                )
                
                return {
                    "status": "created",
                    "policy_id": policy_id,
                    "policy": policy.to_dict()
                }
            
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid request: {e}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Policy creation failed: {e}")
        
        @self.app.delete("/archival/policies/{policy_id}")
        async def delete_archival_policy(
            policy_id: str = PathParam(...),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            if policy_id in self.archival_manager.policies:
                # Remove policy file
                policy_file = self.archival_manager.policies_dir / f"{policy_id}.json"
                if policy_file.exists():
                    policy_file.unlink()
                
                del self.archival_manager.policies[policy_id]
                
                return {"status": "deleted", "policy_id": policy_id}
            else:
                raise HTTPException(status_code=404, detail="Policy not found")
        
        @self.app.get("/archival/statistics")
        async def get_archival_statistics(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            return self.archival_manager.get_archival_statistics()
        
        @self.app.get("/archival/operations")
        async def get_archival_operations(
            limit: int = Query(50, ge=1, le=200),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            return self.archival_manager.get_operation_history(limit)
        
        @self.app.post("/archival/start")
        async def start_archival_scheduler(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            await self.archival_manager.start_scheduler()
            return {"status": "started", "message": "Archival scheduler started"}
        
        @self.app.post("/archival/stop")
        async def stop_archival_scheduler(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            await self.archival_manager.stop_scheduler()
            return {"status": "stopped", "message": "Archival scheduler stopped"}
        
        @self.app.post("/archival/restore/{operation_id}")
        async def restore_archived_data(
            operation_id: str = PathParam(...),
            target_table: Optional[str] = Query(None),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            success = await self.archival_manager.restore_archived_data(operation_id, target_table)
            
            if success:
                return {
                    "status": "restored",
                    "operation_id": operation_id,
                    "target_table": target_table
                }
            else:
                raise HTTPException(status_code=500, detail="Data restoration failed")
        
        # Background Tasks Endpoints
        @self.app.get("/tasks")
        async def list_background_tasks(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            return {
                "active_tasks": list(self.background_tasks.keys()),
                "tasks": self.background_tasks
            }
        
        @self.app.get("/tasks/{task_id}")
        async def get_background_task(
            task_id: str = PathParam(...),
            credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)
        ):
            if task_id in self.background_tasks:
                return self.background_tasks[task_id]
            else:
                raise HTTPException(status_code=404, detail="Task not found")
        
        # System Control Endpoints
        @self.app.post("/system/start-all")
        async def start_all_services(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            try:
                await self.performance_monitor.start_monitoring()
                await self.query_optimizer.start_optimizer()
                await self.archival_manager.start_scheduler()
                
                return {
                    "status": "started",
                    "message": "All optimization services started",
                    "services": ["performance_monitor", "query_optimizer", "archival_manager"]
                }
            
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to start services: {e}")
        
        @self.app.post("/system/stop-all")
        async def stop_all_services(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            try:
                await self.performance_monitor.stop_monitoring()
                await self.query_optimizer.stop_optimizer()
                await self.archival_manager.stop_scheduler()
                
                return {
                    "status": "stopped",
                    "message": "All optimization services stopped",
                    "services": ["performance_monitor", "query_optimizer", "archival_manager"]
                }
            
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to stop services: {e}")
        
        # Export/Import Configuration
        @self.app.get("/config/export")
        async def export_configuration(credentials: HTTPAuthorizationCredentials = Depends(self._verify_token)):
            config = {
                "archival_policies": [policy.to_dict() for policy in self.archival_manager.policies.values()],
                "performance_thresholds": self.performance_monitor.thresholds,
                "optimizer_config": self.query_optimizer.get_optimization_statistics(),
                "exported_at": datetime.utcnow().isoformat()
            }
            
            return config
        
        # Metrics Export (Prometheus format)
        @self.app.get("/metrics", response_class=JSONResponse)
        async def export_metrics():
            """Export metrics in Prometheus format"""
            
            current_metrics = self.performance_monitor.get_current_metrics()
            
            if not current_metrics:
                return JSONResponse(content={"error": "No metrics available"})
            
            # Convert to Prometheus-style metrics
            prometheus_metrics = []
            
            # Database metrics
            prometheus_metrics.extend([
                f"database_cpu_usage_percent {current_metrics.cpu_usage_percent}",
                f"database_memory_usage_percent {current_metrics.memory_usage_percent}",
                f"database_connection_count {current_metrics.connection_count}",
                f"database_active_queries {current_metrics.active_queries}",
                f"database_buffer_cache_hit_ratio {current_metrics.buffer_cache_hit_ratio}",
                f"database_deadlock_count {current_metrics.deadlock_count}",
                f"database_lock_wait_count {current_metrics.lock_wait_count}",
                f"database_health_score {current_metrics.get_health_score()}"
            ])
            
            # System metrics
            prometheus_metrics.extend([
                f"optimization_active_alerts {len(self.performance_monitor.active_alerts)}",
                f"optimization_cached_queries {len(self.query_optimizer.query_analyzer.query_cache)}",
                f"optimization_archival_policies {len(self.archival_manager.policies)}",
                f"optimization_active_operations {len(self.archival_manager.active_operations)}"
            ])
            
            return JSONResponse(content={"metrics": prometheus_metrics})
    
    def _verify_token(self, credentials: Optional[HTTPAuthorizationCredentials] = None) -> Optional[HTTPAuthorizationCredentials]:
        """Verify API token"""
        
        if not self.api_key:
            return None  # No authentication required
        
        if not credentials:
            raise HTTPException(status_code=401, detail="Authorization required")
        
        if credentials.credentials != self.api_key:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return credentials
    
    async def _run_optimization_background(
        self,
        task_id: str,
        max_indexes: int,
        include_tables: List[str],
        exclude_tables: List[str]
    ):
        """Run optimization cycle in background"""
        
        self.background_tasks[task_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "max_indexes": max_indexes,
            "include_tables": include_tables,
            "exclude_tables": exclude_tables,
            "progress": "Starting optimization cycle..."
        }
        
        try:
            # Update progress
            self.background_tasks[task_id]["progress"] = "Analyzing slow queries..."
            
            # Run optimization cycle
            await self.query_optimizer.run_optimization_cycle()
            
            # Update progress
            self.background_tasks[task_id]["progress"] = "Creating recommended indexes..."
            
            # Create indexes with limits
            created_indexes = await self.query_optimizer.index_manager.create_recommended_indexes(max_indexes)
            
            # Complete task
            self.background_tasks[task_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "created_indexes": created_indexes,
                "progress": f"Optimization completed. {len(created_indexes)} indexes created."
            })
        
        except Exception as e:
            self.background_tasks[task_id].update({
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error": str(e),
                "progress": f"Optimization failed: {e}"
            })
    
    def run_server(self, host: str = "0.0.0.0", port: int = 8000, debug: bool = False):
        """Run the API server"""
        
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI not available")
        
        logger.info(f"Starting Database Optimization API on {host}:{port}")
        
        uvicorn.run(
            self.app,
            host=host,
            port=port,
            debug=debug,
            log_level="info" if not debug else "debug"
        )


# Factory function for easy API creation
def create_optimization_api(
    db_connection_string: str,
    api_key: Optional[str] = None,
    host: str = "0.0.0.0",
    port: int = 8000
) -> DatabaseOptimizationAPI:
    """Create and configure database optimization API"""
    
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not available for API creation")
    
    # Initialize components
    archival_manager = ArchivalManager(db_connection_string)
    query_optimizer = QueryOptimizer(db_connection_string)
    performance_monitor = PerformanceMonitor(db_connection_string)
    
    # Create API
    api = DatabaseOptimizationAPI(
        db_connection_string=db_connection_string,
        archival_manager=archival_manager,
        query_optimizer=query_optimizer,
        performance_monitor=performance_monitor,
        api_key=api_key
    )
    
    return api


# CLI entry point
def main():
    """CLI entry point for running the API server"""
    
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Database Optimization API Server")
    parser.add_argument("--db-url", required=True, help="Database connection URL")
    parser.add_argument("--api-key", help="API authentication key")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Create and run API
    try:
        api = create_optimization_api(
            db_connection_string=args.db_url,
            api_key=args.api_key,
            host=args.host,
            port=args.port
        )
        
        api.run_server(host=args.host, port=args.port, debug=args.debug)
    
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        exit(1)


if __name__ == "__main__":
    main()
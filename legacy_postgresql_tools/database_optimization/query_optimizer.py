"""
Query Optimizer

Intelligent query optimization system with automatic index management,
query analysis, and performance enhancement capabilities.
"""

import logging
import asyncio
import json
import re
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, Counter
import statistics

try:
    import asyncpg
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    logging.warning("PostgreSQL libraries not available")

try:
    import sqlparse
    from sqlparse import sql, tokens
    SQLPARSE_AVAILABLE = True
except ImportError:
    SQLPARSE_AVAILABLE = False
    logging.warning("SQLParse not available for SQL analysis")

logger = logging.getLogger(__name__)


class OptimizationStrategy(Enum):
    """Query optimization strategies"""
    INDEX_CREATION = "index_creation"
    QUERY_REWRITE = "query_rewrite"
    STATISTICS_UPDATE = "statistics_update"
    PARTITION_PRUNING = "partition_pruning"
    JOIN_OPTIMIZATION = "join_optimization"
    SUBQUERY_OPTIMIZATION = "subquery_optimization"


class IndexType(Enum):
    """Database index types"""
    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GIST = "gist"
    SPGIST = "spgist"
    BRIN = "brin"
    PARTIAL = "partial"
    EXPRESSION = "expression"
    UNIQUE = "unique"


class QueryComplexity(Enum):
    """Query complexity levels"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


@dataclass
class QueryMetrics:
    """Query execution metrics"""
    query_hash: str
    execution_time_ms: float
    rows_examined: int
    rows_returned: int
    cpu_time_ms: float
    io_time_ms: float
    memory_usage_kb: int
    buffer_hits: int
    buffer_misses: int
    temp_files_created: int
    temp_file_size_kb: int
    execution_count: int = 1
    last_executed: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def efficiency_score(self) -> float:
        """Calculate query efficiency score (0-100)"""
        if self.rows_examined == 0:
            return 100.0
        
        # Base efficiency on rows_returned/rows_examined ratio
        selectivity = self.rows_returned / self.rows_examined
        
        # Adjust for execution time (faster is better)
        time_factor = max(0.1, 1 / (1 + self.execution_time_ms / 1000))
        
        # Adjust for I/O efficiency
        io_efficiency = 1.0
        if self.buffer_hits + self.buffer_misses > 0:
            io_efficiency = self.buffer_hits / (self.buffer_hits + self.buffer_misses)
        
        efficiency = (selectivity * 0.4 + time_factor * 0.4 + io_efficiency * 0.2) * 100
        return min(100.0, efficiency)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "query_hash": self.query_hash,
            "execution_time_ms": self.execution_time_ms,
            "rows_examined": self.rows_examined,
            "rows_returned": self.rows_returned,
            "cpu_time_ms": self.cpu_time_ms,
            "io_time_ms": self.io_time_ms,
            "memory_usage_kb": self.memory_usage_kb,
            "buffer_hits": self.buffer_hits,
            "buffer_misses": self.buffer_misses,
            "temp_files_created": self.temp_files_created,
            "temp_file_size_kb": self.temp_file_size_kb,
            "execution_count": self.execution_count,
            "efficiency_score": self.efficiency_score,
            "last_executed": self.last_executed.isoformat()
        }


@dataclass
class IndexCandidate:
    """Index creation candidate"""
    table_name: str
    columns: List[str]
    index_type: IndexType = IndexType.BTREE
    where_clause: Optional[str] = None
    estimated_benefit: float = 0.0
    estimated_size_mb: float = 0.0
    creation_cost_ms: float = 0.0
    usage_frequency: int = 0
    priority_score: float = 0.0
    
    @property
    def index_name(self) -> str:
        """Generate index name"""
        columns_str = "_".join(self.columns)
        return f"idx_{self.table_name}_{columns_str}"
    
    def calculate_priority_score(self) -> float:
        """Calculate priority score for index creation"""
        # Higher benefit and frequency = higher priority
        # Lower size and creation cost = higher priority
        
        benefit_score = min(10.0, self.estimated_benefit)
        frequency_score = min(10.0, self.usage_frequency / 100)
        size_penalty = max(0.1, 10.0 / (1 + self.estimated_size_mb / 100))
        cost_penalty = max(0.1, 10.0 / (1 + self.creation_cost_ms / 10000))
        
        self.priority_score = (benefit_score * 0.4 + frequency_score * 0.3 + 
                              size_penalty * 0.15 + cost_penalty * 0.15)
        
        return self.priority_score
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "table_name": self.table_name,
            "columns": self.columns,
            "index_type": self.index_type.value,
            "where_clause": self.where_clause,
            "estimated_benefit": self.estimated_benefit,
            "estimated_size_mb": self.estimated_size_mb,
            "creation_cost_ms": self.creation_cost_ms,
            "usage_frequency": self.usage_frequency,
            "priority_score": self.priority_score,
            "index_name": self.index_name
        }


@dataclass
class QueryPlan:
    """Query execution plan analysis"""
    query_hash: str
    query_text: str
    plan_json: Dict[str, Any]
    total_cost: float
    startup_cost: float
    execution_time_ms: float
    complexity: QueryComplexity = QueryComplexity.SIMPLE
    optimization_opportunities: List[Dict[str, Any]] = field(default_factory=list)
    recommended_indexes: List[IndexCandidate] = field(default_factory=list)
    
    def analyze_plan_nodes(self) -> Dict[str, Any]:
        """Analyze plan nodes for optimization opportunities"""
        
        analysis = {
            "sequential_scans": [],
            "expensive_sorts": [],
            "nested_loops": [],
            "hash_joins": [],
            "index_scans": [],
            "bitmap_scans": []
        }
        
        def analyze_node(node: Dict, depth: int = 0):
            node_type = node.get("Node Type", "")
            
            if node_type == "Seq Scan":
                analysis["sequential_scans"].append({
                    "table": node.get("Relation Name", ""),
                    "cost": node.get("Total Cost", 0),
                    "rows": node.get("Plan Rows", 0),
                    "filter": node.get("Filter", "")
                })
            
            elif node_type == "Sort":
                sort_cost = node.get("Total Cost", 0)
                if sort_cost > 1000:  # Expensive sort threshold
                    analysis["expensive_sorts"].append({
                        "cost": sort_cost,
                        "sort_key": node.get("Sort Key", []),
                        "sort_method": node.get("Sort Method", "")
                    })
            
            elif node_type == "Nested Loop":
                analysis["nested_loops"].append({
                    "cost": node.get("Total Cost", 0),
                    "rows": node.get("Plan Rows", 0),
                    "join_type": node.get("Join Type", "")
                })
            
            elif node_type == "Hash Join":
                analysis["hash_joins"].append({
                    "cost": node.get("Total Cost", 0),
                    "rows": node.get("Plan Rows", 0),
                    "join_type": node.get("Join Type", "")
                })
            
            # Recursively analyze child plans
            for child in node.get("Plans", []):
                analyze_node(child, depth + 1)
        
        if "Plan" in self.plan_json:
            analyze_node(self.plan_json["Plan"])
        
        return analysis
    
    def determine_complexity(self) -> QueryComplexity:
        """Determine query complexity based on plan analysis"""
        
        analysis = self.analyze_plan_nodes()
        
        complexity_score = 0
        
        # Add points for various complexity factors
        complexity_score += len(analysis["sequential_scans"]) * 2
        complexity_score += len(analysis["expensive_sorts"]) * 3
        complexity_score += len(analysis["nested_loops"]) * 2
        complexity_score += len(analysis["hash_joins"]) * 1
        
        # Consider total cost
        if self.total_cost > 10000:
            complexity_score += 3
        elif self.total_cost > 1000:
            complexity_score += 2
        elif self.total_cost > 100:
            complexity_score += 1
        
        # Determine complexity level
        if complexity_score >= 10:
            self.complexity = QueryComplexity.VERY_COMPLEX
        elif complexity_score >= 6:
            self.complexity = QueryComplexity.COMPLEX
        elif complexity_score >= 3:
            self.complexity = QueryComplexity.MODERATE
        else:
            self.complexity = QueryComplexity.SIMPLE
        
        return self.complexity
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "query_hash": self.query_hash,
            "query_text": self.query_text[:500],  # Truncate for storage
            "total_cost": self.total_cost,
            "startup_cost": self.startup_cost,
            "execution_time_ms": self.execution_time_ms,
            "complexity": self.complexity.value,
            "optimization_opportunities": self.optimization_opportunities,
            "recommended_indexes": [idx.to_dict() for idx in self.recommended_indexes],
            "plan_analysis": self.analyze_plan_nodes()
        }


class SQLAnalyzer:
    """SQL query parsing and analysis"""
    
    def __init__(self):
        self.table_patterns = []
        self.column_patterns = []
        
    def parse_query(self, query: str) -> Dict[str, Any]:
        """Parse SQL query and extract metadata"""
        
        if not SQLPARSE_AVAILABLE:
            return self._simple_parse(query)
        
        try:
            parsed = sqlparse.parse(query)[0]
            
            analysis = {
                "query_type": self._get_query_type(parsed),
                "tables": self._extract_tables(parsed),
                "columns": self._extract_columns(parsed),
                "where_conditions": self._extract_where_conditions(parsed),
                "joins": self._extract_joins(parsed),
                "order_by": self._extract_order_by(parsed),
                "group_by": self._extract_group_by(parsed),
                "aggregates": self._extract_aggregates(parsed),
                "subqueries": self._has_subqueries(parsed)
            }
            
            return analysis
        
        except Exception as e:
            logger.warning(f"SQL parsing failed, using simple parse: {e}")
            return self._simple_parse(query)
    
    def _simple_parse(self, query: str) -> Dict[str, Any]:
        """Simple regex-based query parsing fallback"""
        
        query_upper = query.upper()
        
        # Determine query type
        if query_upper.strip().startswith('SELECT'):
            query_type = 'SELECT'
        elif query_upper.strip().startswith('INSERT'):
            query_type = 'INSERT'
        elif query_upper.strip().startswith('UPDATE'):
            query_type = 'UPDATE'
        elif query_upper.strip().startswith('DELETE'):
            query_type = 'DELETE'
        else:
            query_type = 'OTHER'
        
        # Extract table names (basic regex)
        table_pattern = r'\b(?:FROM|JOIN|UPDATE|INSERT\s+INTO)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        tables = re.findall(table_pattern, query, re.IGNORECASE)
        
        return {
            "query_type": query_type,
            "tables": list(set(tables)),
            "columns": [],
            "where_conditions": [],
            "joins": [],
            "order_by": [],
            "group_by": [],
            "aggregates": [],
            "subqueries": "SELECT" in query_upper and query_upper.count("SELECT") > 1
        }
    
    def _get_query_type(self, parsed) -> str:
        """Extract query type from parsed SQL"""
        
        for token in parsed.tokens:
            if token.ttype is tokens.Keyword.DML:
                return token.value.upper()
        
        return "UNKNOWN"
    
    def _extract_tables(self, parsed) -> List[str]:
        """Extract table names from parsed SQL"""
        
        tables = []
        
        def extract_from_token(token):
            if hasattr(token, 'tokens'):
                for subtoken in token.tokens:
                    extract_from_token(subtoken)
            elif token.ttype is None and isinstance(token, sql.Identifier):
                tables.append(str(token))
        
        extract_from_token(parsed)
        return list(set(tables))
    
    def _extract_columns(self, parsed) -> List[str]:
        """Extract column references from parsed SQL"""
        # Simplified implementation
        return []
    
    def _extract_where_conditions(self, parsed) -> List[str]:
        """Extract WHERE conditions from parsed SQL"""
        # Simplified implementation
        return []
    
    def _extract_joins(self, parsed) -> List[Dict[str, str]]:
        """Extract JOIN information from parsed SQL"""
        # Simplified implementation
        return []
    
    def _extract_order_by(self, parsed) -> List[str]:
        """Extract ORDER BY columns from parsed SQL"""
        # Simplified implementation
        return []
    
    def _extract_group_by(self, parsed) -> List[str]:
        """Extract GROUP BY columns from parsed SQL"""
        # Simplified implementation
        return []
    
    def _extract_aggregates(self, parsed) -> List[str]:
        """Extract aggregate functions from parsed SQL"""
        # Simplified implementation
        return []
    
    def _has_subqueries(self, parsed) -> bool:
        """Check if query contains subqueries"""
        # Simplified implementation
        return False
    
    def generate_query_hash(self, query: str) -> str:
        """Generate hash for query (normalized)"""
        
        # Normalize query by removing whitespace and converting to lowercase
        normalized = re.sub(r'\s+', ' ', query.strip().lower())
        
        # Remove parameter values for better grouping
        normalized = re.sub(r"'[^']*'", "'?'", normalized)
        normalized = re.sub(r'\b\d+\b', '?', normalized)
        
        return hashlib.md5(normalized.encode()).hexdigest()


class IndexManager:
    """Database index management and optimization"""
    
    def __init__(self, db_connection_string: str):
        self.db_connection_string = db_connection_string
        self.existing_indexes: Dict[str, List[Dict]] = {}
        self.index_candidates: List[IndexCandidate] = []
        
    async def refresh_index_metadata(self):
        """Refresh metadata about existing indexes"""
        
        if not POSTGRESQL_AVAILABLE:
            return
        
        try:
            conn = await asyncpg.connect(self.db_connection_string)
            
            # Query to get existing indexes
            index_query = """
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    indexdef,
                    pg_size_pretty(pg_total_relation_size(indexrelid::regclass)) as size
                FROM pg_indexes 
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
            """
            
            rows = await conn.fetch(index_query)
            
            # Group indexes by table
            self.existing_indexes.clear()
            for row in rows:
                table_name = row['tablename']
                if table_name not in self.existing_indexes:
                    self.existing_indexes[table_name] = []
                
                self.existing_indexes[table_name].append({
                    'name': row['indexname'],
                    'definition': row['indexdef'],
                    'size': row['size']
                })
            
            await conn.close()
            
            logger.info(f"Refreshed metadata for {len(self.existing_indexes)} tables")
        
        except Exception as e:
            logger.error(f"Failed to refresh index metadata: {e}")
    
    async def analyze_missing_indexes(self, query_metrics: List[QueryMetrics]) -> List[IndexCandidate]:
        """Analyze queries to identify missing index opportunities"""
        
        candidates = []
        
        # Analyze slow queries for index opportunities
        slow_queries = [qm for qm in query_metrics if qm.execution_time_ms > 1000]
        
        for query_metric in slow_queries:
            # This is a simplified analysis - in practice, you'd need
            # to analyze the actual query plans and WHERE clauses
            
            # For demonstration, create some example candidates
            candidate = IndexCandidate(
                table_name="example_table",
                columns=["timestamp", "symbol"],
                index_type=IndexType.BTREE,
                estimated_benefit=query_metric.execution_time_ms / 2,  # Assume 50% improvement
                estimated_size_mb=10.0,
                creation_cost_ms=5000.0,
                usage_frequency=query_metric.execution_count
            )
            
            candidate.calculate_priority_score()
            candidates.append(candidate)
        
        self.index_candidates = sorted(candidates, key=lambda c: c.priority_score, reverse=True)
        return self.index_candidates
    
    async def create_recommended_indexes(self, max_indexes: int = 5) -> List[Dict[str, Any]]:
        """Create recommended indexes based on analysis"""
        
        if not POSTGRESQL_AVAILABLE:
            return []
        
        created_indexes = []
        
        # Sort candidates by priority
        top_candidates = sorted(
            self.index_candidates, 
            key=lambda c: c.priority_score, 
            reverse=True
        )[:max_indexes]
        
        try:
            conn = await asyncpg.connect(self.db_connection_string)
            
            for candidate in top_candidates:
                try:
                    # Check if similar index already exists
                    if self._similar_index_exists(candidate):
                        logger.info(f"Similar index already exists for {candidate.table_name}")
                        continue
                    
                    # Generate CREATE INDEX statement
                    create_sql = self._generate_create_index_sql(candidate)
                    
                    start_time = datetime.utcnow()
                    await conn.execute(create_sql)
                    end_time = datetime.utcnow()
                    
                    actual_creation_time = (end_time - start_time).total_seconds() * 1000
                    
                    created_indexes.append({
                        "index_name": candidate.index_name,
                        "table_name": candidate.table_name,
                        "columns": candidate.columns,
                        "creation_time_ms": actual_creation_time,
                        "estimated_benefit": candidate.estimated_benefit,
                        "sql": create_sql
                    })
                    
                    logger.info(f"Created index: {candidate.index_name}")
                
                except Exception as e:
                    logger.error(f"Failed to create index {candidate.index_name}: {e}")
            
            await conn.close()
        
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
        
        return created_indexes
    
    def _similar_index_exists(self, candidate: IndexCandidate) -> bool:
        """Check if similar index already exists"""
        
        existing = self.existing_indexes.get(candidate.table_name, [])
        
        for index in existing:
            # Simple check - in practice, would need more sophisticated comparison
            if any(col in index['definition'] for col in candidate.columns):
                return True
        
        return False
    
    def _generate_create_index_sql(self, candidate: IndexCandidate) -> str:
        """Generate CREATE INDEX SQL statement"""
        
        columns_str = ", ".join(candidate.columns)
        
        sql = f"CREATE INDEX {candidate.index_name} ON {candidate.table_name}"
        
        if candidate.index_type != IndexType.BTREE:
            sql += f" USING {candidate.index_type.value}"
        
        sql += f" ({columns_str})"
        
        if candidate.where_clause:
            sql += f" WHERE {candidate.where_clause}"
        
        return sql


class QueryAnalyzer:
    """Query performance analysis and optimization"""
    
    def __init__(self, db_connection_string: str):
        self.db_connection_string = db_connection_string
        self.sql_analyzer = SQLAnalyzer()
        self.query_cache: Dict[str, QueryMetrics] = {}
        self.query_plans: Dict[str, QueryPlan] = {}
        
    async def analyze_query_performance(self, query: str) -> Optional[QueryPlan]:
        """Analyze query performance and generate optimization plan"""
        
        if not POSTGRESQL_AVAILABLE:
            return None
        
        query_hash = self.sql_analyzer.generate_query_hash(query)
        
        try:
            conn = await asyncpg.connect(self.db_connection_string)
            
            # Get query execution plan
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
            
            start_time = datetime.utcnow()
            result = await conn.fetchval(explain_query)
            end_time = datetime.utcnow()
            
            execution_time_ms = (end_time - start_time).total_seconds() * 1000
            
            # Parse execution plan
            plan_data = result[0] if isinstance(result, list) else result
            
            query_plan = QueryPlan(
                query_hash=query_hash,
                query_text=query,
                plan_json=plan_data,
                total_cost=plan_data.get("Plan", {}).get("Total Cost", 0),
                startup_cost=plan_data.get("Plan", {}).get("Startup Cost", 0),
                execution_time_ms=execution_time_ms
            )
            
            # Analyze complexity and opportunities
            query_plan.determine_complexity()
            query_plan.optimization_opportunities = self._identify_optimization_opportunities(query_plan)
            
            self.query_plans[query_hash] = query_plan
            
            await conn.close()
            
            return query_plan
        
        except Exception as e:
            logger.error(f"Query analysis failed: {e}")
            return None
    
    def _identify_optimization_opportunities(self, query_plan: QueryPlan) -> List[Dict[str, Any]]:
        """Identify optimization opportunities from query plan"""
        
        opportunities = []
        analysis = query_plan.analyze_plan_nodes()
        
        # Sequential scan opportunities
        for seq_scan in analysis["sequential_scans"]:
            if seq_scan["cost"] > 100:  # Expensive seq scan
                opportunities.append({
                    "type": OptimizationStrategy.INDEX_CREATION.value,
                    "description": f"Create index on {seq_scan['table']} for sequential scan optimization",
                    "table": seq_scan["table"],
                    "estimated_benefit": seq_scan["cost"] * 0.7,  # Assume 70% improvement
                    "priority": "HIGH" if seq_scan["cost"] > 1000 else "MEDIUM"
                })
        
        # Expensive sort opportunities
        for sort in analysis["expensive_sorts"]:
            opportunities.append({
                "type": OptimizationStrategy.INDEX_CREATION.value,
                "description": f"Create index on sort columns: {', '.join(sort['sort_key'])}",
                "sort_keys": sort["sort_key"],
                "estimated_benefit": sort["cost"] * 0.8,
                "priority": "HIGH" if sort["cost"] > 2000 else "MEDIUM"
            })
        
        # Nested loop join opportunities
        for nested_loop in analysis["nested_loops"]:
            if nested_loop["cost"] > 1000:
                opportunities.append({
                    "type": OptimizationStrategy.JOIN_OPTIMIZATION.value,
                    "description": "Consider hash join or merge join instead of nested loop",
                    "estimated_benefit": nested_loop["cost"] * 0.5,
                    "priority": "MEDIUM"
                })
        
        return opportunities
    
    def update_query_metrics(self, query: str, metrics: QueryMetrics):
        """Update query metrics in cache"""
        
        query_hash = metrics.query_hash
        
        if query_hash in self.query_cache:
            # Update existing metrics
            existing = self.query_cache[query_hash]
            existing.execution_count += metrics.execution_count
            existing.last_executed = metrics.last_executed
            
            # Update averages
            total_executions = existing.execution_count
            existing.execution_time_ms = (
                (existing.execution_time_ms * (total_executions - 1) + metrics.execution_time_ms)
                / total_executions
            )
        else:
            self.query_cache[query_hash] = metrics
    
    def get_slow_queries(self, threshold_ms: float = 1000, limit: int = 10) -> List[QueryMetrics]:
        """Get slowest queries above threshold"""
        
        slow_queries = [
            metrics for metrics in self.query_cache.values()
            if metrics.execution_time_ms >= threshold_ms
        ]
        
        return sorted(slow_queries, key=lambda q: q.execution_time_ms, reverse=True)[:limit]
    
    def get_frequent_queries(self, min_count: int = 10, limit: int = 10) -> List[QueryMetrics]:
        """Get most frequently executed queries"""
        
        frequent_queries = [
            metrics for metrics in self.query_cache.values()
            if metrics.execution_count >= min_count
        ]
        
        return sorted(frequent_queries, key=lambda q: q.execution_count, reverse=True)[:limit]


class QueryOptimizer:
    """
    Intelligent query optimization system
    
    Analyzes query performance, manages indexes, and provides
    optimization recommendations for database queries.
    """
    
    def __init__(
        self,
        db_connection_string: str,
        optimization_interval_hours: int = 6,
        slow_query_threshold_ms: float = 1000
    ):
        self.db_connection_string = db_connection_string
        self.optimization_interval_hours = optimization_interval_hours
        self.slow_query_threshold_ms = slow_query_threshold_ms
        
        # Components
        self.query_analyzer = QueryAnalyzer(db_connection_string)
        self.index_manager = IndexManager(db_connection_string)
        self.sql_analyzer = SQLAnalyzer()
        
        # State
        self.optimization_history: List[Dict[str, Any]] = []
        self._running = False
        self._optimizer_task: Optional[asyncio.Task] = None
    
    async def start_optimizer(self):
        """Start the query optimizer"""
        
        if self._running:
            logger.warning("Query optimizer already running")
            return
        
        self._running = True
        self._optimizer_task = asyncio.create_task(self._optimizer_loop())
        
        logger.info("Query optimizer started")
    
    async def stop_optimizer(self):
        """Stop the query optimizer"""
        
        self._running = False
        
        if self._optimizer_task:
            self._optimizer_task.cancel()
            try:
                await self._optimizer_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Query optimizer stopped")
    
    async def _optimizer_loop(self):
        """Main optimizer loop"""
        
        while self._running:
            try:
                await self.run_optimization_cycle()
                
                # Sleep for optimization interval
                await asyncio.sleep(self.optimization_interval_hours * 3600)
            
            except Exception as e:
                logger.error(f"Optimizer loop error: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error
    
    async def run_optimization_cycle(self):
        """Run complete optimization cycle"""
        
        logger.info("Starting optimization cycle")
        
        optimization_start = datetime.utcnow()
        
        try:
            # 1. Refresh index metadata
            await self.index_manager.refresh_index_metadata()
            
            # 2. Analyze slow queries
            slow_queries = self.query_analyzer.get_slow_queries(
                threshold_ms=self.slow_query_threshold_ms
            )
            
            # 3. Generate index recommendations
            query_metrics = list(self.query_analyzer.query_cache.values())
            index_candidates = await self.index_manager.analyze_missing_indexes(query_metrics)
            
            # 4. Create recommended indexes (limited)
            created_indexes = await self.index_manager.create_recommended_indexes(max_indexes=3)
            
            # 5. Record optimization results
            optimization_result = {
                "timestamp": optimization_start.isoformat(),
                "slow_queries_analyzed": len(slow_queries),
                "index_candidates_found": len(index_candidates),
                "indexes_created": len(created_indexes),
                "created_indexes": created_indexes,
                "duration_minutes": (datetime.utcnow() - optimization_start).total_seconds() / 60
            }
            
            self.optimization_history.append(optimization_result)
            
            # Keep only last 100 optimization cycles
            if len(self.optimization_history) > 100:
                self.optimization_history = self.optimization_history[-100:]
            
            logger.info(f"Optimization cycle completed: {len(created_indexes)} indexes created")
        
        except Exception as e:
            logger.error(f"Optimization cycle failed: {e}")
    
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """Analyze individual query and provide recommendations"""
        
        # Parse query structure
        query_structure = self.sql_analyzer.parse_query(query)
        
        # Analyze performance
        query_plan = await self.query_analyzer.analyze_query_performance(query)
        
        # Generate recommendations
        recommendations = []
        
        if query_plan:
            recommendations.extend(query_plan.optimization_opportunities)
        
        return {
            "query_hash": self.sql_analyzer.generate_query_hash(query),
            "query_structure": query_structure,
            "execution_plan": query_plan.to_dict() if query_plan else None,
            "recommendations": recommendations,
            "complexity": query_plan.complexity.value if query_plan else "unknown"
        }
    
    def get_optimization_statistics(self) -> Dict[str, Any]:
        """Get optimizer statistics"""
        
        total_cycles = len(self.optimization_history)
        total_indexes_created = sum(cycle["indexes_created"] for cycle in self.optimization_history)
        
        avg_cycle_time = 0
        if self.optimization_history:
            avg_cycle_time = statistics.mean(
                cycle["duration_minutes"] for cycle in self.optimization_history
            )
        
        return {
            "query_cache": {
                "total_queries": len(self.query_analyzer.query_cache),
                "slow_queries": len(self.query_analyzer.get_slow_queries()),
                "frequent_queries": len(self.query_analyzer.get_frequent_queries())
            },
            "optimization_cycles": {
                "total_cycles": total_cycles,
                "total_indexes_created": total_indexes_created,
                "average_cycle_time_minutes": avg_cycle_time
            },
            "index_management": {
                "tables_monitored": len(self.index_manager.existing_indexes),
                "current_candidates": len(self.index_manager.index_candidates)
            }
        }
    
    def get_query_recommendations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top query optimization recommendations"""
        
        recommendations = []
        
        # Get slow queries
        slow_queries = self.query_analyzer.get_slow_queries(limit=limit)
        
        for query_metrics in slow_queries:
            query_hash = query_metrics.query_hash
            query_plan = self.query_analyzer.query_plans.get(query_hash)
            
            recommendation = {
                "query_hash": query_hash,
                "execution_time_ms": query_metrics.execution_time_ms,
                "execution_count": query_metrics.execution_count,
                "efficiency_score": query_metrics.efficiency_score,
                "optimization_opportunities": query_plan.optimization_opportunities if query_plan else [],
                "priority": "HIGH" if query_metrics.execution_time_ms > 5000 else "MEDIUM"
            }
            
            recommendations.append(recommendation)
        
        return recommendations
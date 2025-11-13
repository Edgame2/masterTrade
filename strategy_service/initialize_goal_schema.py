#!/usr/bin/env python3
"""
Initialize Goal-Oriented Trading Schema

Run this script to create the necessary database tables for:
- Financial goals tracking
- Goal progress monitoring
- Automatic adjustments
- Position sizing recommendations
- Milestones

Goals initialized:
1. 10% monthly return
2. $10K monthly profit
3. $1M portfolio target
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg
import structlog

logger = structlog.get_logger()


async def initialize_goal_schema():
    """Initialize goal-oriented trading database schema."""
    
    # Database connection parameters
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = int(os.getenv("POSTGRES_PORT", "5432"))
    db_name = os.getenv("POSTGRES_DB", "mastertrade")
    db_user = os.getenv("POSTGRES_USER", "mastertrade")
    db_password = os.getenv("POSTGRES_PASSWORD", "mastertrade")
    
    logger.info(
        "Connecting to PostgreSQL",
        host=db_host,
        port=db_port,
        database=db_name
    )
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password
        )
        
        # Read and execute schema SQL
        schema_file = Path(__file__).parent / "goal_oriented_schema.sql"
        
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            return False
        
        logger.info(f"Reading schema from {schema_file}")
        schema_sql = schema_file.read_text()
        
        logger.info("Executing schema creation...")
        await conn.execute(schema_sql)
        
        # Verify tables were created
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN (
                'financial_goals',
                'goal_progress',
                'goal_adjustments',
                'goal_milestones',
                'position_sizing_recommendations'
            )
            ORDER BY table_name
        """)
        
        created_tables = [record["table_name"] for record in tables]
        
        logger.info(
            "Goal-oriented trading schema initialized",
            tables_created=created_tables
        )
        
        # Verify default goals were inserted
        goal_count = await conn.fetchval("SELECT COUNT(*) FROM financial_goals")
        logger.info(f"Default goals created: {goal_count}")
        
        if goal_count >= 3:
            goals = await conn.fetch("""
                SELECT goal_type, target_value, priority, status
                FROM financial_goals
                ORDER BY priority
            """)
            
            print("\n" + "="*60)
            print("DEFAULT GOALS INITIALIZED")
            print("="*60)
            for goal in goals:
                goal_type_display = {
                    'monthly_return_pct': 'Monthly Return',
                    'monthly_profit_usd': 'Monthly Profit',
                    'portfolio_target_usd': 'Portfolio Target'
                }.get(goal['goal_type'], goal['goal_type'])
                
                if goal['goal_type'] == 'monthly_return_pct':
                    target_display = f"{float(goal['target_value']) * 100:.1f}%"
                else:
                    target_display = f"${float(goal['target_value']):,.2f}"
                
                print(f"\nPriority {goal['priority']}: {goal_type_display}")
                print(f"  Target: {target_display}")
                print(f"  Status: {goal['status']}")
            
            print("\n" + "="*60)
            print("SETUP COMPLETE!")
            print("="*60)
            print("\nYou can now:")
            print("1. View goals: GET /api/v1/goals/summary")
            print("2. Track progress: GET /api/v1/goals/{goal_id}/progress")
            print("3. Calculate position sizes: POST /api/v1/position-sizing/calculate")
            print("\nGoal tracking runs automatically every hour.")
            print("="*60 + "\n")
        
        await conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize goal schema: {e}", exc_info=True)
        return False


async def main():
    """Main entry point."""
    success = await initialize_goal_schema()
    
    if success:
        print("\n✓ Goal-oriented trading schema initialized successfully!\n")
        sys.exit(0)
    else:
        print("\n✗ Failed to initialize goal schema. Check logs for details.\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

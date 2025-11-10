-- PostgreSQL base schema for MasterTrade services
-- Enables UUID generation and JSONB utilities
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================================
-- Strategy Service Tables
-- =====================================================================

CREATE TABLE IF NOT EXISTS strategies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    configuration JSONB NOT NULL DEFAULT '{}'::JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    status TEXT NOT NULL DEFAULT 'active',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    allocation NUMERIC(10, 5) NOT NULL DEFAULT 1.0,
    activation_state TEXT NOT NULL DEFAULT 'live',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    deactivated_at TIMESTAMPTZ,
    replaced_at TIMESTAMPTZ,
    replaced_by UUID,
    replaces UUID
);

CREATE INDEX IF NOT EXISTS idx_strategies_active
    ON strategies (is_active) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS strategy_symbols (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
CREATE TABLE IF NOT EXISTS backtest_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    backtest_id TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy_time
    ON backtest_results (strategy_id, created_at DESC);

CREATE TABLE IF NOT EXISTS learning_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    insights JSONB NOT NULL DEFAULT '{}'::JSONB,
    generation_stats JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS idx_learning_insights_timestamp
    ON learning_insights (timestamp DESC);

    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (strategy_id, symbol)
);

CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence NUMERIC(10, 5) NOT NULL,
    price NUMERIC(18, 8) NOT NULL,
    quantity NUMERIC(28, 10),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_strategy_timestamp
    ON signals (strategy_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_timestamp
    ON signals (symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS strategy_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    signals_count INTEGER NOT NULL,
    execution_time NUMERIC(18, 6) NOT NULL,
    error TEXT,
    signals_summary JSONB NOT NULL DEFAULT '[]'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_performance_strategy_timestamp
    ON strategy_performance (strategy_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS crypto_selections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    selection_date DATE NOT NULL,
    selection_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    selected_cryptos JSONB NOT NULL DEFAULT '[]'::JSONB,
    total_selected INTEGER NOT NULL,
    UNIQUE (selection_date)
);

-- =====================================================================
-- Strategy Review / Daily Review Tables
-- =====================================================================

CREATE TABLE IF NOT EXISTS strategy_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID REFERENCES strategies(id) ON DELETE CASCADE,
    reviewer TEXT,
    performance_grade TEXT,
    decision TEXT,
    confidence_score NUMERIC(10, 5),
    scores JSONB NOT NULL DEFAULT '{}'::JSONB,
    summary TEXT,
    recommendations TEXT,
    review_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    review_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_reviews_date
    ON strategy_reviews (review_date DESC);

CREATE TABLE IF NOT EXISTS strategy_review_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_strategy_review_tasks_status
    ON strategy_review_tasks (status);

CREATE TABLE IF NOT EXISTS daily_review_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    review_date DATE NOT NULL UNIQUE,
    grade_distribution JSONB NOT NULL DEFAULT '{}'::JSONB,
    decision_distribution JSONB NOT NULL DEFAULT '{}'::JSONB,
    total_strategies_reviewed INTEGER NOT NULL DEFAULT 0,
    avg_confidence NUMERIC(10, 5),
    top_performers JSONB NOT NULL DEFAULT '[]'::JSONB,
    strategies_needing_attention JSONB NOT NULL DEFAULT '[]'::JSONB,
    market_regime JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_review_summaries_date
    ON daily_review_summaries (review_date DESC);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    notification_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_created_at
    ON notifications (created_at DESC);

-- =====================================================================
-- Strategy Positions / Trades (used by analytics and reviews)
-- =====================================================================

CREATE TABLE IF NOT EXISTS strategy_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC(28, 10) NOT NULL,
    entry_price NUMERIC(18, 8) NOT NULL,
    current_price NUMERIC(18, 8),
    unrealized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_strategy_positions_strategy_status
    ON strategy_positions (strategy_id, status);

CREATE TABLE IF NOT EXISTS strategy_trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    position_id UUID REFERENCES strategy_positions(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC(28, 10) NOT NULL,
    price NUMERIC(18, 8) NOT NULL,
    fees NUMERIC(18, 8) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strategy_trades_strategy_timestamp
    ON strategy_trades (strategy_id, executed_at DESC);

-- =====================================================================
-- Order Executor Tables (aligns with existing implementation)
-- =====================================================================

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    strategy_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    signal_id INTEGER,
    exchange_order_id TEXT,
    client_order_id TEXT NOT NULL,
    order_type TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    price NUMERIC,
    stop_price NUMERIC,
    status TEXT NOT NULL,
    filled_quantity NUMERIC NOT NULL DEFAULT 0,
    avg_fill_price NUMERIC,
    commission NUMERIC NOT NULL DEFAULT 0,
    commission_asset TEXT,
    environment TEXT NOT NULL DEFAULT 'testnet',
    order_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    update_time TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders (status);

CREATE INDEX IF NOT EXISTS idx_orders_symbol_time
    ON orders (symbol, order_time DESC);

CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    exchange_trade_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    commission NUMERIC NOT NULL DEFAULT 0,
    commission_asset TEXT,
    is_maker BOOLEAN NOT NULL DEFAULT FALSE,
    trade_time TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
    ON trades (symbol, trade_time DESC);

CREATE TABLE IF NOT EXISTS portfolio_balances (
    asset TEXT PRIMARY KEY,
    free_balance NUMERIC NOT NULL DEFAULT 0,
    locked_balance NUMERIC NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trading_config (
    config_type TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    type TEXT,
    description TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================================================================
-- Risk Manager Tables
-- =====================================================================

CREATE TABLE IF NOT EXISTS risk_positions (
    id TEXT PRIMARY KEY,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC(28, 10) NOT NULL,
    entry_price NUMERIC(18, 8) NOT NULL,
    current_price NUMERIC(18, 8),
    unrealized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    stop_loss_price NUMERIC(18, 8),
    take_profit_price NUMERIC(18, 8),
    status TEXT NOT NULL,
    position_value_usd NUMERIC(28, 10) NOT NULL DEFAULT 0,
    risk_score NUMERIC(18, 8) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_risk_positions_strategy_status
    ON risk_positions (strategy_id, status);

CREATE TABLE IF NOT EXISTS risk_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (date)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    snapshot JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE IF NOT EXISTS risk_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    limit_type TEXT NOT NULL,
    target TEXT,
    config JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stop_losses (
    id TEXT PRIMARY KEY,
    position_id TEXT REFERENCES risk_positions(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    stop_type TEXT NOT NULL,
    status TEXT NOT NULL,
    entry_price NUMERIC(18, 8) NOT NULL,
    current_price NUMERIC(18, 8) NOT NULL,
    stop_price NUMERIC(18, 8) NOT NULL,
    initial_stop_price NUMERIC(18, 8) NOT NULL,
    quantity NUMERIC(28, 10) NOT NULL,
    trigger_count INTEGER NOT NULL DEFAULT 0,
    config JSONB NOT NULL DEFAULT '{}'::JSONB,
    profit_loss NUMERIC(18, 8) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stop_losses_symbol_status
    ON stop_losses (symbol, status);

CREATE TABLE IF NOT EXISTS risk_alerts (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT,
    message TEXT NOT NULL,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
    symbol TEXT,
    current_value NUMERIC,
    threshold_value NUMERIC,
    recommendation TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    status TEXT NOT NULL DEFAULT 'open',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_status_severity
    ON risk_alerts (status, severity);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_timestamp
    ON risk_alerts (timestamp DESC);

CREATE TABLE IF NOT EXISTS correlation_matrices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    correlations JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (date)
);

CREATE TABLE IF NOT EXISTS var_calculations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    values JSONB NOT NULL DEFAULT '{}'::JSONB,
    method TEXT NOT NULL DEFAULT 'historical_simulation'
);

CREATE TABLE IF NOT EXISTS drawdown_tracking (
    date DATE PRIMARY KEY,
    peak_value NUMERIC(28, 10) NOT NULL,
    current_value NUMERIC(28, 10) NOT NULL,
    current_drawdown NUMERIC(18, 8) NOT NULL DEFAULT 0,
    max_drawdown NUMERIC(18, 8) NOT NULL DEFAULT 0,
    drawdown_duration_days INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_admin_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_admin_actions_created_at
    ON risk_admin_actions (created_at DESC);

CREATE TABLE IF NOT EXISTS risk_adjustment_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    adjustments JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS idx_risk_adjustment_history_time
    ON risk_adjustment_history (timestamp DESC);

CREATE TABLE IF NOT EXISTS risk_configuration_changes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    changes JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_configuration_changes_time
    ON risk_configuration_changes (created_at DESC);

CREATE TABLE IF NOT EXISTS symbol_volatility_cache (
    symbol TEXT PRIMARY KEY,
    period_days INTEGER NOT NULL,
    volatility NUMERIC(18, 8) NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS symbol_liquidity_cache (
    symbol TEXT PRIMARY KEY,
    liquidity_score NUMERIC(18, 8) NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS strategy_activation_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_strategies JSONB NOT NULL DEFAULT '[]'::JSONB,
    deactivated_strategies JSONB NOT NULL DEFAULT '[]'::JSONB,
    max_active_strategies INTEGER NOT NULL,
    activation_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE INDEX IF NOT EXISTS idx_strategy_activation_log_time
    ON strategy_activation_log (timestamp DESC);


CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pair TEXT NOT NULL,
    buy_venue TEXT NOT NULL,
    sell_venue TEXT NOT NULL,
    buy_price NUMERIC(18, 8) NOT NULL,
    sell_price NUMERIC(18, 8) NOT NULL,
    profit_percent NUMERIC(18, 8) NOT NULL,
    estimated_profit_usd NUMERIC(28, 10) NOT NULL,
    trade_amount NUMERIC(28, 10) NOT NULL,
    gas_cost NUMERIC(28, 10) NOT NULL DEFAULT 0,
    arbitrage_type TEXT NOT NULL,
    executed BOOLEAN NOT NULL DEFAULT FALSE,
    execution_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arbitrage_opportunities_profit
    ON arbitrage_opportunities (executed, profit_percent DESC);

CREATE INDEX IF NOT EXISTS idx_arbitrage_opportunities_pair_time
    ON arbitrage_opportunities (pair, timestamp DESC);

CREATE TABLE IF NOT EXISTS arbitrage_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opportunity_id UUID REFERENCES arbitrage_opportunities(id) ON DELETE SET NULL,
    execution_type TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    status TEXT NOT NULL,
    transactions JSONB NOT NULL DEFAULT '[]'::JSONB,
    actual_profit_usd NUMERIC(28, 10),
    gas_used NUMERIC(28, 10),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_arbitrage_executions_status_time
    ON arbitrage_executions (status, start_time DESC);

CREATE TABLE IF NOT EXISTS dex_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pair TEXT NOT NULL,
    dex TEXT NOT NULL,
    chain TEXT NOT NULL,
    price NUMERIC(28, 10) NOT NULL,
    volume NUMERIC(28, 10),
    liquidity NUMERIC(28, 10),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dex_prices_pair_time
    ON dex_prices (pair, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_dex_prices_venue
    ON dex_prices (dex, pair, timestamp DESC);

CREATE TABLE IF NOT EXISTS flash_loan_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    protocol TEXT NOT NULL,
    token TEXT NOT NULL,
    estimated_profit NUMERIC(28, 10) NOT NULL,
    capital_required NUMERIC(28, 10) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flash_loan_opportunities_protocol_time
    ON flash_loan_opportunities (protocol, timestamp DESC);

CREATE TABLE IF NOT EXISTS triangular_arbitrage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange TEXT NOT NULL,
    chain TEXT NOT NULL,
    route JSONB NOT NULL DEFAULT '{}'::JSONB,
    profit_percent NUMERIC(18, 8) NOT NULL,
    executed BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_triangular_arbitrage_exchange_time
    ON triangular_arbitrage (exchange, timestamp DESC);

CREATE TABLE IF NOT EXISTS gas_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chain TEXT NOT NULL,
    standard_gwei NUMERIC(18, 8) NOT NULL,
    fast_gwei NUMERIC(18, 8),
    safe_gwei NUMERIC(18, 8),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gas_prices_chain_time
    ON gas_prices (chain, timestamp DESC);

-- =====================================================================
-- API Gateway Tables (caching, audit, overrides)
-- =====================================================================

CREATE TABLE IF NOT EXISTS dashboard_cache (
    cache_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_audit_action_time
    ON api_audit_log (action, created_at DESC);

CREATE TABLE IF NOT EXISTS manual_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    state JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_manual_overrides_resource
    ON manual_overrides (resource_type, resource_id);

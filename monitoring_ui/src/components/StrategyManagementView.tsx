'use client';

import { useEffect, useState } from 'react';
import {
  FiActivity,
  FiTrendingUp,
  FiTrendingDown,
  FiPause,
  FiPlay,
  FiRefreshCw,
  FiAlertCircle,
  FiCheckCircle,
  FiClock,
  FiTarget,
  FiBarChart2
} from 'react-icons/fi';

/**
 * Strategy performance metrics
 */
interface StrategyPerformance {
  strategy_id: string;
  strategy_name: string;
  sharpe_ratio: number;
  total_return: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
}

/**
 * Activation status response
 */
interface ActivationStatus {
  max_active_strategies: number;
  current_active_count: number;
  current_active_strategies: any[];
  last_check: string;
  next_check_eligible: boolean;
  top_candidates: any[];
  activation_criteria: {
    min_sharpe_ratio: number;
    max_drawdown_threshold: number;
    min_trades: number;
    max_days_inactive: number;
  };
}

/**
 * Dashboard data response
 */
interface DashboardData {
  total_active_strategies: number;
  performance_overview: {
    avg_sharpe_ratio: number;
    avg_return: number;
    strategies_profitable: number;
    strategies_with_positive_sharpe: number;
  };
  top_performers: StrategyPerformance[];
  underperformers: StrategyPerformance[];
  market_regime: string;
  last_update: string;
}

/**
 * Strategy Management View Component
 * 
 * Comprehensive strategy monitoring dashboard showing:
 * - Automatic strategy generation pipeline status
 * - Active strategy count and performance
 * - Top performers and underperformers
 * - Activation candidates from automated backtesting
 * - Pause/Resume strategy controls
 * - Real-time performance metrics
 */
export default function StrategyManagementView() {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [activationStatus, setActivationStatus] = useState<ActivationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState<'active' | 'top' | 'under' | 'candidates'>('active');

  const STRATEGY_API = process.env.NEXT_PUBLIC_STRATEGY_API_URL || 'http://localhost:8006';

  useEffect(() => {
    fetchStrategyData();
    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchStrategyData, 60000);
    return () => clearInterval(interval);
  }, []);

  /**
   * Fetch all strategy data
   */
  const fetchStrategyData = async () => {
    try {
      setError(null);

      const [dashboardRes, activationRes] = await Promise.all([
        fetch(`${STRATEGY_API}/api/v1/strategy/performance/dashboard`),
        fetch(`${STRATEGY_API}/api/v1/strategy/activation/status`)
      ]);

      if (!dashboardRes.ok || !activationRes.ok) {
        throw new Error('Failed to fetch strategy data');
      }

      const dashboard = await dashboardRes.json();
      const activation = await activationRes.json();

      setDashboardData(dashboard);
      setActivationStatus(activation);
      setLastUpdate(new Date());
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch strategy data');
      setLoading(false);
    }
  };

  /**
   * Pause a strategy
   */
  const pauseStrategy = async (strategyId: string) => {
    try {
      const response = await fetch(`${STRATEGY_API}/api/v1/strategy/${strategyId}/pause`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error('Failed to pause strategy');
      }

      // Refresh data
      await fetchStrategyData();
    } catch (err) {
      alert(`Error pausing strategy: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  /**
   * Resume a strategy
   */
  const resumeStrategy = async (strategyId: string) => {
    try {
      const response = await fetch(`${STRATEGY_API}/api/v1/strategy/${strategyId}/resume`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error('Failed to resume strategy');
      }

      // Refresh data
      await fetchStrategyData();
    } catch (err) {
      alert(`Error resuming strategy: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  /**
   * Get market regime color
   */
  const getRegimeColor = (regime: string) => {
    switch (regime.toLowerCase()) {
      case 'bull':
      case 'bullish':
        return 'text-green-400 bg-green-500/20';
      case 'bear':
      case 'bearish':
        return 'text-red-400 bg-red-500/20';
      case 'sideways':
      case 'ranging':
        return 'text-yellow-400 bg-yellow-500/20';
      default:
        return 'text-gray-400 bg-gray-500/20';
    }
  };

  /**
   * Format percentage
   */
  const formatPercent = (value: number): string => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400">Loading strategy data...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6">
        <div className="flex items-center gap-3">
          <FiAlertCircle className="w-6 h-6 text-red-400" />
          <div>
            <h3 className="text-lg font-semibold text-red-400">Failed to Load Strategies</h3>
            <p className="text-sm text-red-300 mt-1">{error}</p>
          </div>
        </div>
        <button
          onClick={fetchStrategyData}
          className="mt-4 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!dashboardData || !activationStatus) {
    return <div className="text-slate-400">No data available</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Strategy Management</h2>
          <p className="text-slate-400 mt-1">
            Monitor automated strategy generation and live performance
          </p>
        </div>
        <div className="flex items-center gap-4">
          {lastUpdate && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <FiClock className="w-4 h-4" />
              <span>{lastUpdate.toLocaleTimeString()}</span>
            </div>
          )}
          <button
            onClick={fetchStrategyData}
            className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            title="Refresh"
          >
            <FiRefreshCw className="w-5 h-5 text-slate-300" />
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Active Strategies */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <FiActivity className="w-8 h-8 text-blue-400" />
            <span className="text-xs text-slate-400">
              {activationStatus.current_active_count} / {activationStatus.max_active_strategies}
            </span>
          </div>
          <div className="text-3xl font-bold text-white">{activationStatus.current_active_count}</div>
          <div className="text-sm text-slate-400 mt-1">Active Strategies</div>
        </div>

        {/* Avg Sharpe Ratio */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <FiBarChart2 className="w-8 h-8 text-purple-400 mb-2" />
          <div className="text-3xl font-bold text-white">
            {dashboardData.performance_overview.avg_sharpe_ratio?.toFixed(2) || '0.00'}
          </div>
          <div className="text-sm text-slate-400 mt-1">Avg Sharpe Ratio</div>
        </div>

        {/* Profitable */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <FiTrendingUp className="w-8 h-8 text-green-400 mb-2" />
          <div className="text-3xl font-bold text-white">
            {dashboardData.performance_overview.strategies_profitable || 0}
          </div>
          <div className="text-sm text-slate-400 mt-1">Profitable Strategies</div>
        </div>

        {/* Market Regime */}
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <FiTarget className="w-8 h-8 text-yellow-400 mb-2" />
          <div className={`text-2xl font-bold px-3 py-1 rounded-lg inline-block ${getRegimeColor(dashboardData.market_regime)}`}>
            {dashboardData.market_regime.toUpperCase()}
          </div>
          <div className="text-sm text-slate-400 mt-1">Market Regime</div>
        </div>
      </div>

      {/* Activation Candidates Info */}
      {activationStatus.top_candidates && activationStatus.top_candidates.length > 0 && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <FiCheckCircle className="w-5 h-5 text-blue-400" />
            <span className="text-blue-300 font-medium">
              {activationStatus.top_candidates.length} strategies ready for activation
            </span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="bg-slate-800 rounded-lg border border-slate-700">
        <div className="border-b border-slate-700">
          <nav className="flex space-x-8 px-6">
            {[
              { key: 'active', label: 'Active', count: activationStatus.current_active_count },
              { key: 'top', label: 'Top Performers', count: dashboardData.top_performers.length },
              { key: 'under', label: 'Underperformers', count: dashboardData.underperformers.length },
              { key: 'candidates', label: 'Candidates', count: activationStatus.top_candidates.length }
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
                className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
                  activeTab === tab.key
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-500'
                }`}
              >
                {tab.label}
                <span className="px-2 py-0.5 rounded-full bg-slate-700 text-xs">
                  {tab.count}
                </span>
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          {/* Active Strategies */}
          {activeTab === 'active' && (
            <div className="space-y-4">
              {activationStatus.current_active_strategies.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <FiActivity className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p>No active strategies</p>
                  <p className="text-sm mt-2">Strategies will be automatically activated based on performance</p>
                </div>
              ) : (
                activationStatus.current_active_strategies.map((strategy: any) => (
                  <StrategyCard
                    key={strategy.strategy_id}
                    strategy={strategy}
                    onPause={() => pauseStrategy(strategy.strategy_id)}
                    onResume={() => resumeStrategy(strategy.strategy_id)}
                  />
                ))
              )}
            </div>
          )}

          {/* Top Performers */}
          {activeTab === 'top' && (
            <div className="space-y-4">
              {dashboardData.top_performers.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <FiTrendingUp className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p>No top performers yet</p>
                </div>
              ) : (
                dashboardData.top_performers.map((strategy, idx) => (
                  <PerformanceCard key={strategy.strategy_id} strategy={strategy} rank={idx + 1} />
                ))
              )}
            </div>
          )}

          {/* Underperformers */}
          {activeTab === 'under' && (
            <div className="space-y-4">
              {dashboardData.underperformers.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <FiTrendingDown className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p>No underperformers</p>
                </div>
              ) : (
                dashboardData.underperformers.map((strategy) => (
                  <PerformanceCard key={strategy.strategy_id} strategy={strategy} isUnderperformer />
                ))
              )}
            </div>
          )}

          {/* Candidates */}
          {activeTab === 'candidates' && (
            <div className="space-y-4">
              {activationStatus.top_candidates.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <FiTarget className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p>No activation candidates</p>
                  <p className="text-sm mt-2">New strategies are generated daily at 3:00 AM UTC</p>
                </div>
              ) : (
                activationStatus.top_candidates.map((candidate: any) => (
                  <CandidateCard key={candidate.strategy_id} candidate={candidate} />
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Activation Criteria Info */}
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <h3 className="text-lg font-semibold text-white mb-4">Automatic Activation Criteria</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-slate-400">Min Sharpe Ratio:</span>
            <span className="ml-2 text-white font-medium">
              {activationStatus.activation_criteria.min_sharpe_ratio}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Max Drawdown:</span>
            <span className="ml-2 text-white font-medium">
              {(activationStatus.activation_criteria.max_drawdown_threshold * 100).toFixed(0)}%
            </span>
          </div>
          <div>
            <span className="text-slate-400">Min Trades:</span>
            <span className="ml-2 text-white font-medium">
              {activationStatus.activation_criteria.min_trades}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Max Inactive Days:</span>
            <span className="ml-2 text-white font-medium">
              {activationStatus.activation_criteria.max_days_inactive}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Strategy Card Component (for active strategies)
 */
function StrategyCard({ strategy, onPause, onResume }: any) {
  return (
    <div className="bg-slate-700/50 rounded-lg p-4 flex items-center justify-between">
      <div>
        <h4 className="font-medium text-white">{strategy.strategy_name || strategy.strategy_id}</h4>
        <p className="text-sm text-slate-400 mt-1">ID: {strategy.strategy_id.substring(0, 8)}...</p>
      </div>
      <div className="flex items-center gap-4">
        <button
          onClick={strategy.status === 'active' ? onPause : onResume}
          className="p-2 bg-slate-600 hover:bg-slate-500 rounded-lg transition-colors"
          title={strategy.status === 'active' ? 'Pause' : 'Resume'}
        >
          {strategy.status === 'active' ? (
            <FiPause className="w-5 h-5 text-yellow-400" />
          ) : (
            <FiPlay className="w-5 h-5 text-green-400" />
          )}
        </button>
      </div>
    </div>
  );
}

/**
 * Performance Card Component
 */
function PerformanceCard({ strategy, rank, isUnderperformer }: any) {
  return (
    <div className="bg-slate-700/50 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {rank && (
            <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 font-bold">
              #{rank}
            </div>
          )}
          <div>
            <h4 className="font-medium text-white">{strategy.strategy_name || 'Unnamed Strategy'}</h4>
            <p className="text-xs text-slate-400 mt-1">ID: {strategy.strategy_id.substring(0, 12)}...</p>
          </div>
        </div>
        {isUnderperformer ? (
          <FiTrendingDown className="w-6 h-6 text-red-400" />
        ) : (
          <FiTrendingUp className="w-6 h-6 text-green-400" />
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <span className="text-slate-400 block">Sharpe</span>
          <span className={`font-bold ${strategy.sharpe_ratio > 0 ? 'text-green-400' : 'text-red-400'}`}>
            {strategy.sharpe_ratio.toFixed(2)}
          </span>
        </div>
        <div>
          <span className="text-slate-400 block">Return</span>
          <span className={`font-bold ${strategy.total_return > 0 ? 'text-green-400' : 'text-red-400'}`}>
            {strategy.total_return >= 0 ? '+' : ''}{strategy.total_return.toFixed(2)}%
          </span>
        </div>
        <div>
          <span className="text-slate-400 block">Drawdown</span>
          <span className="text-red-400 font-bold">
            {strategy.max_drawdown.toFixed(2)}%
          </span>
        </div>
        <div>
          <span className="text-slate-400 block">Win Rate</span>
          <span className="text-white font-bold">
            {(strategy.win_rate * 100).toFixed(1)}%
          </span>
        </div>
        <div>
          <span className="text-slate-400 block">Trades</span>
          <span className="text-white font-bold">
            {strategy.total_trades}
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Candidate Card Component
 */
function CandidateCard({ candidate }: any) {
  return (
    <div className="bg-slate-700/50 rounded-lg p-4 border-l-4 border-blue-500">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-medium text-white">Candidate Strategy</h4>
          <p className="text-xs text-slate-400 mt-1">ID: {candidate.strategy_id?.substring(0, 12) || 'N/A'}...</p>
        </div>
        <span className="px-3 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full">
          Ready for Activation
        </span>
      </div>
    </div>
  );
}

'use client';

import { useEffect, useMemo, useState } from 'react';
import { FiAward, FiActivity, FiBarChart2, FiRefreshCcw, FiTrendingUp } from 'react-icons/fi';
import PerformanceChart from './PerformanceChart';
import LoadingSpinner from './LoadingSpinner';

interface DashboardOverview {
  total_strategies?: number;
  active_strategies?: number;
  recent_trades?: number;
  recent_signals?: number;
  active_orders?: number;
  portfolio_value?: number;
  last_updated?: string;
}

interface StrategyRow {
  id: string;
  name: string;
  performance_score?: number;
  total_pnl?: number;
  win_rate?: number;
  status?: string;
  created_at?: string;
}

const PerformanceMetrics = () => {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [topStrategies, setTopStrategies] = useState<StrategyRow[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const portfolioValue = useMemo(() => {
    if (!overview || overview.portfolio_value === undefined || overview.portfolio_value === null) {
      return 0;
    }
    return typeof overview.portfolio_value === 'number'
      ? overview.portfolio_value
      : Number(overview.portfolio_value) || 0;
  }, [overview]);

  useEffect(() => {
    const loadAll = async () => {
      try {
        setLoading(true);
        setError(null);
        const [overviewResponse, strategiesResponse] = await Promise.all([
          fetch(`${apiBase}/api/dashboard/overview`),
          fetch(`${apiBase}/api/strategies`),
        ]);

        if (!overviewResponse.ok) {
          throw new Error('Unable to load performance overview');
        }

        const overviewPayload = await overviewResponse.json();
        setOverview(overviewPayload);

        if (strategiesResponse.ok) {
          const strategiesPayload = await strategiesResponse.json();
          const strategyArray: StrategyRow[] = Array.isArray(strategiesPayload)
            ? strategiesPayload
            : strategiesPayload.strategies || [];

          const sorted = [...strategyArray]
            .filter((item) => (item.performance_score ?? 0) > 0)
            .sort((a, b) => (b.performance_score ?? 0) - (a.performance_score ?? 0))
            .slice(0, 10);

          setTopStrategies(sorted);
        }
      } catch (err) {
        console.error('Error loading performance metrics', err);
        setError(err instanceof Error ? err.message : 'Failed to load performance metrics');
      } finally {
        setLoading(false);
      }
    };

    loadAll();
    const interval = window.setInterval(loadAll, 30_000);
    return () => window.clearInterval(interval);
  }, [apiBase]);

  const strategyStats = useMemo(() => {
    if (!topStrategies.length) {
      return null;
    }

    const averageWinRate =
      topStrategies.reduce((sum, item) => sum + (item.win_rate ?? 0), 0) / topStrategies.length;
    const averageScore =
      topStrategies.reduce((sum, item) => sum + (item.performance_score ?? 0), 0) / topStrategies.length;

    return {
      averageWinRate,
      averageScore,
    };
  }, [topStrategies]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">Performance Intelligence</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Track aggregate performance signals, top-performing strategies, and portfolio momentum.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
          <FiRefreshCcw className="h-4 w-4" />
          {overview?.last_updated ? new Date(overview.last_updated).toLocaleString() : '—'}
        </div>
      </div>

      {loading ? (
        <div className="flex h-80 items-center justify-center rounded-lg bg-white dark:bg-gray-800">
          <LoadingSpinner />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Active Strategies</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {overview?.active_strategies ?? 0}
                </span>
                <FiActivity className="h-6 w-6 text-sky-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                {overview?.total_strategies ?? 0} total tracked
              </p>
            </div>

            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Recent Signals (24h)</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {overview?.recent_signals ?? 0}
                </span>
                <FiBarChart2 className="h-6 w-6 text-emerald-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Signals generated across all markets
              </p>
            </div>

            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Recent Trades (24h)</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {overview?.recent_trades ?? 0}
                </span>
                <FiAward className="h-6 w-6 text-violet-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Executions processed by the order engine
              </p>
            </div>

            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Portfolio Value (approx)</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  ${portfolioValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
                <FiTrendingUp className="h-6 w-6 text-green-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Estimated based on recent trades
              </p>
            </div>
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <PerformanceChart detailed />
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <div className="mb-4 flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Top Performing Strategies</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Ranked by performance score and win rate over the latest evaluation window.
                </p>
              </div>
              {strategyStats && (
                <div className="flex gap-6 text-sm text-gray-500 dark:text-gray-400">
                  <span>Avg Win Rate: {strategyStats.averageWinRate.toFixed(1)}%</span>
                  <span>Avg Score: {strategyStats.averageScore.toFixed(1)}</span>
                </div>
              )}
            </div>

            {topStrategies.length === 0 ? (
              <div className="py-12 text-center text-gray-500 dark:text-gray-400">
                No performance data available yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead>
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Strategy
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Score
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Win Rate
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Total P&L
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {topStrategies.map((strategy) => (
                      <tr key={strategy.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                        <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                          {strategy.name}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {strategy.performance_score?.toFixed(1) ?? '—'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {strategy.win_rate?.toFixed(1) ?? '—'}%
                        </td>
                        <td className="px-4 py-3 text-sm font-medium text-emerald-500">
                          ${strategy.total_pnl?.toFixed(2) ?? '0.00'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {strategy.status ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default PerformanceMetrics;

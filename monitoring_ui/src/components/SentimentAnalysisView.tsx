'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
  Legend,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from 'recharts';
import { FiAlertCircle, FiRefreshCcw, FiSmile, FiTrendingUp } from 'react-icons/fi';
import LoadingSpinner from './LoadingSpinner';

interface SentimentAggregate {
  source?: string;
  type?: string;
  count?: number;
  avg_polarity?: number;
  latest_timestamp?: string;
}

interface GlobalSentimentResponse {
  global_crypto_sentiment?: Record<string, number>;
  global_market_sentiment?: Record<string, number>;
  timestamp?: string;
}

const SENTIMENT_COLORS = ['#0ea5e9', '#22c55e', '#f97316', '#a855f7', '#ef4444', '#14b8a6'];

const clampPercent = (value: number) => Math.min(100, Math.max(0, value));

const SentimentAnalysisView = () => {
  const apiFallback = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const marketDataBase = process.env.NEXT_PUBLIC_MARKET_DATA_API_URL || apiFallback;
  const [summary, setSummary] = useState<Record<string, SentimentAggregate>>({});
  const [globalSentiment, setGlobalSentiment] = useState<GlobalSentimentResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSentiment = async () => {
      try {
        setLoading(true);
        setError(null);
        const [summaryResponse, globalResponse] = await Promise.all([
          fetch(`${marketDataBase}/api/sentiment/summary`).catch(() => fetch(`${apiFallback}/api/sentiment/summary`)),
          fetch(`${marketDataBase}/api/sentiment/global`).catch(() => fetch(`${apiFallback}/api/sentiment/global`)),
        ]);

        if (summaryResponse && summaryResponse.ok) {
          const summaryPayload = await summaryResponse.json();
          setSummary(summaryPayload ?? {});
        }

        if (globalResponse && globalResponse.ok) {
          const globalPayload = await globalResponse.json();
          setGlobalSentiment(globalPayload);
        }
      } catch (err) {
        console.error('Error fetching sentiment', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch sentiment analytics');
      } finally {
        setLoading(false);
      }
    };

    fetchSentiment();
    const interval = window.setInterval(fetchSentiment, 60_000);
    return () => window.clearInterval(interval);
  }, [apiFallback, marketDataBase]);

  const sentimentByType = useMemo(() => {
    const grouped: Record<string, { type: string; total: number; count: number }> = {};
    Object.values(summary || {}).forEach((item) => {
      const type = item.type ?? 'unknown';
      const polarity = typeof item.avg_polarity === 'number' ? item.avg_polarity : 0;
      if (!grouped[type]) {
        grouped[type] = { type, total: 0, count: 0 };
      }
      grouped[type].total += polarity;
      grouped[type].count += 1;
    });

    return Object.values(grouped).map((entry) => {
      const normalized = entry.count > 0 ? entry.total / entry.count : 0;
      // Convert -1..1 polarity to 0..100 scale
      return {
        type: entry.type,
        avgPolarity: normalized,
        sentimentScore: clampPercent((normalized + 1) * 50),
      };
    });
  }, [summary]);

  const topSources = useMemo(() => {
    const aggregates = Object.values(summary || {});
    return aggregates
      .filter((item) => typeof item.count === 'number' && item.count > 0)
      .sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
      .slice(0, 8);
  }, [summary]);

  const globalCryptoData = useMemo(() => {
    if (!globalSentiment?.global_crypto_sentiment) {
      return [];
    }
    return Object.entries(globalSentiment.global_crypto_sentiment).map(([label, value]) => ({
      label,
      value,
    }));
  }, [globalSentiment]);

  const globalMarketData = useMemo(() => {
    if (!globalSentiment?.global_market_sentiment) {
      return [];
    }
    return Object.entries(globalSentiment.global_market_sentiment).map(([label, value]) => ({
      label,
      value,
    }));
  }, [globalSentiment]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">Sentiment Radar</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Consolidated crypto and macro sentiment signals aggregated from social, market, and on-chain data sources.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <FiRefreshCcw className="h-4 w-4" />
          Auto-refreshing every minute
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
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Average Sentiment by Type</h3>
            {sentimentByType.length === 0 ? (
              <div className="flex h-64 items-center justify-center text-gray-500 dark:text-gray-400">
                No sentiment data captured.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <RadialBarChart
                  cx="50%"
                  cy="50%"
                  innerRadius="20%"
                  outerRadius="100%"
                  data={sentimentByType.map((item) => ({
                    name: item.type,
                    value: item.sentimentScore,
                  }))}
                >
                  <RadialBar
                    background
                    cornerRadius={12}
                    dataKey="value"
                  >
                    {sentimentByType.map((_, index) => (
                      <Cell key={`sentiment-type-${index}`} fill={SENTIMENT_COLORS[index % SENTIMENT_COLORS.length]} />
                    ))}
                  </RadialBar>
                  <Legend iconSize={10} layout="vertical" verticalAlign="middle" align="right" />
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      `${value.toFixed(1)}%`,
                      name,
                    ]}
                  />
                </RadialBarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Global Crypto Sentiment</h3>
              <FiSmile className="h-5 w-5 text-emerald-500" />
            </div>
            {globalCryptoData.length === 0 ? (
              <div className="flex h-64 items-center justify-center text-gray-500 dark:text-gray-400">
                Awaiting sentiment feed.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={globalCryptoData}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={3}
                    label={({ label, percent }) => `${label} ${(percent * 100).toFixed(0)}%`}
                  >
                    {globalCryptoData.map((_, index) => (
                      <Cell key={`crypto-sentiment-${index}`} fill={SENTIMENT_COLORS[index % SENTIMENT_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [`${(value as number).toFixed(2)}`, 'Score']} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Global Market Sentiment</h3>
              <FiTrendingUp className="h-5 w-5 text-sky-500" />
            </div>
            {globalMarketData.length === 0 ? (
              <div className="flex h-64 items-center justify-center text-gray-500 dark:text-gray-400">
                No macro sentiment snapshots.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={globalMarketData}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={3}
                    label={({ label, percent }) => `${label} ${(percent * 100).toFixed(0)}%`}
                  >
                    {globalMarketData.map((_, index) => (
                      <Cell key={`market-sentiment-${index}`} fill={SENTIMENT_COLORS[(index + 2) % SENTIMENT_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [`${(value as number).toFixed(2)}`, 'Score']} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}

      <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Most Active Sentiment Sources</h3>
          <FiAlertCircle className="h-5 w-5 text-amber-500" />
        </div>
        {topSources.length === 0 ? (
          <div className="py-12 text-center text-gray-500 dark:text-gray-400">
            No active sentiment contributions recorded.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Type
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Observations
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Avg Polarity
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Last Update
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {topSources.map((item, index) => (
                  <tr key={`${item.source}-${item.type}-${index}`} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                    <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                      {item.source ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {item.type ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {item.count?.toLocaleString() ?? '0'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {typeof item.avg_polarity === 'number' ? item.avg_polarity.toFixed(3) : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {item.latest_timestamp ? new Date(item.latest_timestamp).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default SentimentAnalysisView;

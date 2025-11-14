'use client';

import { useEffect, useState } from 'react';
import {
  FiTrendingUp,
  FiTrendingDown,
  FiActivity,
  FiDatabase,
  FiDollarSign,
  FiBarChart2,
  FiPieChart,
  FiRefreshCw
} from 'react-icons/fi';
import { BiNetworkChart } from 'react-icons/bi';

interface AlphaContribution {
  source_name: string;
  source_type: 'onchain' | 'social' | 'macro' | 'technical' | 'composite';
  total_alpha: number;
  alpha_percentage: number;
  trades_influenced: number;
  avg_alpha_per_trade: number;
  win_rate: number;
  sharpe_ratio: number;
  signals_generated: number;
  signals_used: number;
  signal_quality_score: number;
  monthly_trend: number[];
  last_30_days: {
    alpha: number;
    trades: number;
    win_rate: number;
  };
}

interface StrategyAttribution {
  strategy_id: string;
  strategy_name: string;
  total_alpha: number;
  data_source_contributions: {
    source_name: string;
    alpha: number;
    percentage: number;
  }[];
  best_performing_source: string;
  worst_performing_source: string;
}

export default function AlphaAttributionView() {
  const [attributions, setAttributions] = useState<AlphaContribution[]>([]);
  const [strategyAttribution, setStrategyAttribution] = useState<StrategyAttribution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<'7d' | '30d' | '90d' | '1y'>('30d');
  const [sortBy, setSortBy] = useState<'alpha' | 'trades' | 'winrate' | 'sharpe'>('alpha');

  const API_URL = process.env.NEXT_PUBLIC_STRATEGY_API_URL || 'http://localhost:8006';

  useEffect(() => {
    fetchAlphaAttribution();
    const interval = setInterval(fetchAlphaAttribution, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [timeframe]);

  const fetchAlphaAttribution = async () => {
    try {
      // TODO: Replace with actual API endpoints once implemented
      const response = await fetch(`${API_URL}/api/v1/analytics/alpha-attribution?timeframe=${timeframe}`);
      
      if (!response.ok) {
        // Mock data for development
        const mockAttributions: AlphaContribution[] = [
          {
            source_name: 'RSI_Technical',
            source_type: 'technical',
            total_alpha: 12.5,
            alpha_percentage: 28.3,
            trades_influenced: 145,
            avg_alpha_per_trade: 0.086,
            win_rate: 64.8,
            sharpe_ratio: 2.34,
            signals_generated: 230,
            signals_used: 145,
            signal_quality_score: 85.2,
            monthly_trend: [8.2, 9.5, 11.3, 12.5],
            last_30_days: {
              alpha: 12.5,
              trades: 48,
              win_rate: 66.7
            }
          },
          {
            source_name: 'Social_Sentiment_Twitter',
            source_type: 'social',
            total_alpha: 9.8,
            alpha_percentage: 22.2,
            trades_influenced: 98,
            avg_alpha_per_trade: 0.100,
            win_rate: 61.2,
            sharpe_ratio: 1.95,
            signals_generated: 156,
            signals_used: 98,
            signal_quality_score: 78.5,
            monthly_trend: [7.1, 8.4, 9.1, 9.8],
            last_30_days: {
              alpha: 9.8,
              trades: 32,
              win_rate: 62.5
            }
          },
          {
            source_name: 'Glassnode_NVT',
            source_type: 'onchain',
            total_alpha: 8.3,
            alpha_percentage: 18.8,
            trades_influenced: 67,
            avg_alpha_per_trade: 0.124,
            win_rate: 67.2,
            sharpe_ratio: 2.18,
            signals_generated: 89,
            signals_used: 67,
            signal_quality_score: 82.4,
            monthly_trend: [6.5, 7.2, 7.9, 8.3],
            last_30_days: {
              alpha: 8.3,
              trades: 22,
              win_rate: 68.2
            }
          },
          {
            source_name: 'MACD_Composite',
            source_type: 'composite',
            total_alpha: 7.1,
            alpha_percentage: 16.1,
            trades_influenced: 112,
            avg_alpha_per_trade: 0.063,
            win_rate: 58.9,
            sharpe_ratio: 1.76,
            signals_generated: 178,
            signals_used: 112,
            signal_quality_score: 74.3,
            monthly_trend: [5.8, 6.3, 6.8, 7.1],
            last_30_days: {
              alpha: 7.1,
              trades: 38,
              win_rate: 60.5
            }
          },
          {
            source_name: 'VIX_Macro',
            source_type: 'macro',
            total_alpha: 6.5,
            alpha_percentage: 14.7,
            trades_influenced: 89,
            avg_alpha_per_trade: 0.073,
            win_rate: 60.7,
            sharpe_ratio: 1.88,
            signals_generated: 134,
            signals_used: 89,
            signal_quality_score: 76.8,
            monthly_trend: [5.2, 5.8, 6.2, 6.5],
            last_30_days: {
              alpha: 6.5,
              trades: 28,
              win_rate: 64.3
            }
          }
        ];

        const mockStrategyAttribution: StrategyAttribution[] = [
          {
            strategy_id: 'strat_001',
            strategy_name: 'Momentum_RSI_Strategy',
            total_alpha: 18.7,
            data_source_contributions: [
              { source_name: 'RSI_Technical', alpha: 8.2, percentage: 43.9 },
              { source_name: 'Social_Sentiment_Twitter', alpha: 5.3, percentage: 28.3 },
              { source_name: 'VIX_Macro', alpha: 3.1, percentage: 16.6 },
              { source_name: 'MACD_Composite', alpha: 2.1, percentage: 11.2 }
            ],
            best_performing_source: 'RSI_Technical',
            worst_performing_source: 'MACD_Composite'
          },
          {
            strategy_id: 'strat_002',
            strategy_name: 'OnChain_Analysis_Strategy',
            total_alpha: 14.2,
            data_source_contributions: [
              { source_name: 'Glassnode_NVT', alpha: 7.8, percentage: 54.9 },
              { source_name: 'Social_Sentiment_Twitter', alpha: 4.1, percentage: 28.9 },
              { source_name: 'RSI_Technical', alpha: 2.3, percentage: 16.2 }
            ],
            best_performing_source: 'Glassnode_NVT',
            worst_performing_source: 'RSI_Technical'
          }
        ];

        setAttributions(mockAttributions);
        setStrategyAttribution(mockStrategyAttribution);
      } else {
        const data = await response.json();
        setAttributions(data.attributions || []);
        setStrategyAttribution(data.strategy_attribution || []);
      }
      setError(null);
    } catch (err) {
      console.error('Error fetching alpha attribution:', err);
      setError('Failed to load alpha attribution data');
    } finally {
      setLoading(false);
    }
  };

  const getSortedAttributions = () => {
    return [...attributions].sort((a, b) => {
      switch (sortBy) {
        case 'alpha':
          return b.total_alpha - a.total_alpha;
        case 'trades':
          return b.trades_influenced - a.trades_influenced;
        case 'winrate':
          return b.win_rate - a.win_rate;
        case 'sharpe':
          return b.sharpe_ratio - a.sharpe_ratio;
        default:
          return 0;
      }
    });
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'onchain':
        return <BiNetworkChart className="text-purple-400" />;
      case 'social':
        return <FiActivity className="text-blue-400" />;
      case 'macro':
        return <FiTrendingUp className="text-green-400" />;
      case 'technical':
        return <FiBarChart2 className="text-orange-400" />;
      case 'composite':
        return <FiPieChart className="text-pink-400" />;
      default:
        return <FiDatabase className="text-gray-400" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'onchain':
        return 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300';
      case 'social':
        return 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300';
      case 'macro':
        return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
      case 'technical':
        return 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300';
      case 'composite':
        return 'bg-pink-100 text-pink-700 dark:bg-pink-900 dark:text-pink-300';
      default:
        return 'bg-gray-100 text-gray-700 dark:bg-gray-900 dark:text-gray-300';
    }
  };

  const totalAlpha = attributions.reduce((sum, attr) => sum + attr.total_alpha, 0);
  const totalTrades = attributions.reduce((sum, attr) => sum + attr.trades_influenced, 0);
  const avgWinRate = attributions.reduce((sum, attr) => sum + attr.win_rate, 0) / (attributions.length || 1);
  const avgSharpe = attributions.reduce((sum, attr) => sum + attr.sharpe_ratio, 0) / (attributions.length || 1);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900">
        <FiRefreshCw className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Alpha Attribution</h2>
          <p className="text-slate-400 text-sm mt-1">
            Performance contribution by data source
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value as any)}
            className="bg-slate-800 text-white border border-slate-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
            <option value="90d">Last 90 Days</option>
            <option value="1y">Last Year</option>
          </select>
          <button
            onClick={fetchAlphaAttribution}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm"
          >
            <FiRefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm">Total Alpha</p>
            <FiDollarSign className="text-green-400" />
          </div>
          <h3 className="text-2xl font-bold text-white">{totalAlpha.toFixed(2)}%</h3>
          <p className="text-green-400 text-sm mt-1">
            <FiTrendingUp className="inline w-3 h-3" /> Above benchmark
          </p>
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm">Total Trades</p>
            <FiActivity className="text-blue-400" />
          </div>
          <h3 className="text-2xl font-bold text-white">{totalTrades}</h3>
          <p className="text-slate-400 text-sm mt-1">Influenced by signals</p>
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm">Avg Win Rate</p>
            <FiBarChart2 className="text-purple-400" />
          </div>
          <h3 className="text-2xl font-bold text-white">{avgWinRate.toFixed(1)}%</h3>
          <p className="text-slate-400 text-sm mt-1">Across all sources</p>
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-slate-400 text-sm">Avg Sharpe</p>
            <FiPieChart className="text-orange-400" />
          </div>
          <h3 className="text-2xl font-bold text-white">{avgSharpe.toFixed(2)}</h3>
          <p className="text-slate-400 text-sm mt-1">Risk-adjusted return</p>
        </div>
      </div>

      {/* Sort Controls */}
      <div className="flex gap-2 flex-wrap">
        <span className="text-slate-400 text-sm self-center">Sort by:</span>
        {[
          { value: 'alpha', label: 'Alpha' },
          { value: 'trades', label: 'Trades' },
          { value: 'winrate', label: 'Win Rate' },
          { value: 'sharpe', label: 'Sharpe Ratio' }
        ].map((option) => (
          <button
            key={option.value}
            onClick={() => setSortBy(option.value as any)}
            className={`px-3 py-1 rounded-lg text-sm transition-colors ${
              sortBy === option.value
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Alpha Attribution Table */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">Data Source Performance</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-700">
              <tr>
                <th className="text-left px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Source
                </th>
                <th className="text-left px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Type
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Alpha
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  % Contribution
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Trades
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Avg Alpha/Trade
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Win Rate
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Sharpe
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-300 uppercase tracking-wider">
                  Signal Quality
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {getSortedAttributions().map((attr, index) => (
                <tr key={attr.source_name} className="hover:bg-slate-750 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      {getTypeIcon(attr.source_type)}
                      <span className="text-white font-medium">{attr.source_name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs rounded-full ${getTypeColor(attr.source_type)}`}>
                      {attr.source_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <span className="text-green-400 font-semibold">
                      {attr.total_alpha.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-white">
                    {attr.alpha_percentage.toFixed(1)}%
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-white">
                    {attr.trades_influenced}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-white">
                    {attr.avg_alpha_per_trade.toFixed(3)}%
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <span className={attr.win_rate >= 60 ? 'text-green-400' : 'text-yellow-400'}>
                      {attr.win_rate.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <span className={attr.sharpe_ratio >= 2.0 ? 'text-green-400' : 'text-white'}>
                      {attr.sharpe_ratio.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-16 bg-slate-700 rounded-full h-2">
                        <div
                          className="bg-blue-500 h-2 rounded-full"
                          style={{ width: `${attr.signal_quality_score}%` }}
                        />
                      </div>
                      <span className="text-white text-sm">{attr.signal_quality_score.toFixed(0)}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Strategy-Level Attribution */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">Strategy-Level Attribution</h3>
          <p className="text-slate-400 text-sm mt-1">Alpha contribution breakdown by strategy</p>
        </div>
        <div className="p-6 space-y-6">
          {strategyAttribution.map((strat) => (
            <div key={strat.strategy_id} className="bg-slate-750 rounded-lg p-4 border border-slate-700">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h4 className="text-white font-semibold">{strat.strategy_name}</h4>
                  <p className="text-slate-400 text-sm">{strat.strategy_id}</p>
                </div>
                <div className="text-right">
                  <div className="text-xl font-bold text-green-400">{strat.total_alpha.toFixed(2)}%</div>
                  <div className="text-xs text-slate-400">Total Alpha</div>
                </div>
              </div>
              <div className="space-y-2">
                {strat.data_source_contributions.map((contrib) => (
                  <div key={contrib.source_name} className="flex items-center gap-2">
                    <div className="flex-1">
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-white">{contrib.source_name}</span>
                        <span className="text-slate-400">{contrib.alpha.toFixed(2)}% ({contrib.percentage.toFixed(1)}%)</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2">
                        <div
                          className="bg-blue-500 h-2 rounded-full"
                          style={{ width: `${contrib.percentage}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-700 flex justify-between text-xs">
                <div>
                  <span className="text-slate-400">Best: </span>
                  <span className="text-green-400 font-medium">{strat.best_performing_source}</span>
                </div>
                <div>
                  <span className="text-slate-400">Worst: </span>
                  <span className="text-red-400 font-medium">{strat.worst_performing_source}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

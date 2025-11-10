'use client';

import { useEffect, useState } from 'react';
import { FiCheckCircle, FiXCircle, FiClock, FiTrendingUp } from 'react-icons/fi';

interface Strategy {
  id: string;
  name: string;
  status: string;
  performance_score?: number;
  total_trades?: number;
  win_rate?: number;
  total_pnl?: number;
  created_at: string;
}

export default function StrategyList() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'ACTIVE' | 'INACTIVE'>('ALL');

  useEffect(() => {
    fetchStrategies();
  }, [filter]);

  const fetchStrategies = async () => {
    try {
      setLoading(true);
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
      const url = filter === 'ALL' ? `${apiUrl}/api/strategies` : `${apiUrl}/api/strategies?status=${filter}`;
      const response = await fetch(url);
      const data = await response.json();
      setStrategies(Array.isArray(data) ? data : data.strategies || []);
    } catch (error) {
      console.error('Error fetching strategies:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return <FiCheckCircle className="text-success" />;
      case 'INACTIVE':
        return <FiXCircle className="text-gray-400" />;
      default:
        return <FiClock className="text-warning" />;
    }
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">
          Trading Strategies
        </h2>
        <div className="flex space-x-2">
          {['ALL', 'ACTIVE', 'INACTIVE'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f as any)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                filter === f
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-700 dark:text-gray-300'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary-600"></div>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Strategy
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Performance
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Win Rate
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Total P&L
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Trades
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {strategies.map((strategy) => (
                <tr key={strategy.id} className="hover:bg-gray-50 dark:hover:bg-slate-700">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <FiTrendingUp className="mr-2 text-primary-600" />
                      <span className="font-medium text-gray-900 dark:text-white">
                        {strategy.name}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      {getStatusIcon(strategy.status)}
                      <span className="ml-2 text-sm">{strategy.status}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className="w-16 bg-gray-200 rounded-full h-2 dark:bg-gray-700">
                        <div
                          className="bg-primary-600 h-2 rounded-full"
                          style={{ width: `${Math.min(strategy.performance_score ?? 0, 100)}%` }}
                        ></div>
                      </div>
                      <span className="ml-2 text-sm">{(strategy.performance_score ?? 0).toFixed(1)}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`text-sm ${(strategy.win_rate ?? 0) >= 50 ? 'text-success' : 'text-danger'}`}>
                      {(strategy.win_rate ?? 0).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`font-medium ${(strategy.total_pnl ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                      ${(strategy.total_pnl ?? 0).toFixed(2)}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {strategy.total_trades ?? 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {strategies.length === 0 && (
            <div className="text-center py-12 text-gray-500">
              No strategies found
            </div>
          )}
        </div>
      )}
    </div>
  );
}

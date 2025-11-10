'use client';

import { useEffect, useState } from 'react';
import { FiDollarSign, FiTrendingUp, FiActivity } from 'react-icons/fi';

interface PortfolioSummary {
  totalPositions: number;
  totalValue: number;
  totalPnL: number;
  totalPnLPercent: number;
}

export default function PortfolioOverview() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary>({
    totalPositions: 0,
    totalValue: 0,
    totalPnL: 0,
    totalPnLPercent: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPortfolio();
    const interval = setInterval(fetchPortfolio, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchPortfolio = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
      const response = await fetch(`${apiUrl}/api/portfolio/balance`);
      const data = await response.json();
      setPortfolio(data.summary || portfolio);
    } catch (error) {
      console.error('Error fetching portfolio:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6 h-64 flex items-center justify-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6 flex items-center">
        <FiActivity className="mr-2 text-primary-600" />
        Portfolio Overview
      </h2>

      <div className="space-y-6">
        <div className="flex items-center justify-between p-4 bg-gradient-to-r from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-lg">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Total Value</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              ${portfolio.totalValue.toFixed(2)}
            </p>
          </div>
          <FiDollarSign className="w-12 h-12 text-blue-500" />
        </div>

        <div className="flex items-center justify-between p-4 bg-gradient-to-r from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-lg">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Total P&L</p>
            <p className={`text-2xl font-bold ${portfolio.totalPnL >= 0 ? 'text-success' : 'text-danger'}`}>
              ${portfolio.totalPnL.toFixed(2)}
            </p>
            <p className={`text-sm ${portfolio.totalPnLPercent >= 0 ? 'text-success' : 'text-danger'}`}>
              {portfolio.totalPnLPercent >= 0 ? '↑' : '↓'} {Math.abs(portfolio.totalPnLPercent).toFixed(2)}%
            </p>
          </div>
          <FiTrendingUp className={`w-12 h-12 ${portfolio.totalPnL >= 0 ? 'text-success' : 'text-danger'}`} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-gray-50 dark:bg-slate-700 rounded-lg">
            <p className="text-sm text-gray-600 dark:text-gray-400">Open Positions</p>
            <p className="text-xl font-bold text-gray-900 dark:text-white">{portfolio.totalPositions}</p>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-slate-700 rounded-lg">
            <p className="text-sm text-gray-600 dark:text-gray-400">Avg P&L</p>
            <p className={`text-xl font-bold ${portfolio.totalPnL >= 0 ? 'text-success' : 'text-danger'}`}>
              ${portfolio.totalPositions > 0 ? (portfolio.totalPnL / portfolio.totalPositions).toFixed(2) : '0.00'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

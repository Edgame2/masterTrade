'use client';

import { useEffect, useState } from 'react';
import { FiTrendingUp, FiTrendingDown } from 'react-icons/fi';

interface Position {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  opened_at: string;
}

export default function LivePositions({ limit }: { limit?: number }) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 5000); // Update every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchPositions = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
      const response = await fetch(`${apiUrl}/api/portfolio/balance`);
      const data = await response.json();
      const allPositions = data.positions || [];
      setPositions(limit ? allPositions.slice(0, limit) : allPositions);
    } catch (error) {
      console.error('Error fetching positions:', error);
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
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">
          Live Positions
        </h2>
        <span className="flex items-center text-sm text-success">
          <span className="w-2 h-2 bg-success rounded-full mr-2 pulse-dot"></span>
          Live
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          No open positions
        </div>
      ) : (
        <div className="space-y-4">
          {positions.map((position) => (
            <div
              key={position.id}
              className="p-4 bg-gray-50 dark:bg-slate-700 rounded-lg hover:shadow-md transition"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-3">
                  <span className="text-lg font-bold text-gray-900 dark:text-white">
                    {position.symbol}
                  </span>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    position.side === 'LONG' 
                      ? 'bg-success/20 text-success' 
                      : 'bg-danger/20 text-danger'
                  }`}>
                    {position.side}
                  </span>
                </div>
                <div className="text-right">
                  <div className={`flex items-center ${
                    position.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'
                  }`}>
                    {position.unrealized_pnl >= 0 ? (
                      <FiTrendingUp className="mr-1" />
                    ) : (
                      <FiTrendingDown className="mr-1" />
                    )}
                    <span className="font-bold">
                      ${Math.abs(position.unrealized_pnl).toFixed(2)}
                    </span>
                  </div>
                  <span className={`text-sm ${
                    position.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'
                  }`}>
                    {position.unrealized_pnl_percent >= 0 ? '+' : ''}
                    {position.unrealized_pnl_percent.toFixed(2)}%
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Entry</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    ${position.entry_price.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Current</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    ${position.current_price.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500 dark:text-gray-400">Quantity</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {position.quantity}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

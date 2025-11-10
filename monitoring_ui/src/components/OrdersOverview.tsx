'use client';

import { useEffect, useState } from 'react';
import { FiAlertTriangle, FiCheckCircle, FiClock, FiHash, FiRefreshCcw, FiTrendingUp } from 'react-icons/fi';
import LoadingSpinner from './LoadingSpinner';

interface OrderRecord {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL' | string;
  order_type?: string;
  status?: string;
  price?: number;
  quantity?: number;
  order_time?: string;
  filled_quantity?: number;
}

const statusColors: Record<string, string> = {
  NEW: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200',
  PARTIALLY_FILLED: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200',
  FILLED: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200',
  CANCELED: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200',
};

const OrdersOverview = () => {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const [activeOrders, setActiveOrders] = useState<OrderRecord[]>([]);
  const [recentOrders, setRecentOrders] = useState<OrderRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadOrders = async () => {
      try {
        setLoading(true);
        setError(null);
        const [activeResponse, recentResponse] = await Promise.all([
          fetch(`${apiBase}/api/orders/active`),
          fetch(`${apiBase}/api/orders/recent?limit=100`),
        ]);

        if (!activeResponse.ok) {
          throw new Error('Unable to load active orders');
        }

        const activePayload = await activeResponse.json();
        setActiveOrders(Array.isArray(activePayload) ? activePayload : []);

        if (recentResponse.ok) {
          const recentPayload = await recentResponse.json();
          const list = Array.isArray(recentPayload) ? recentPayload : recentPayload.orders || [];
          setRecentOrders(list);
        }
      } catch (err) {
        console.error('Error loading orders', err);
        setError(err instanceof Error ? err.message : 'Failed to load orders');
      } finally {
        setLoading(false);
      }
    };

    loadOrders();
    const interval = window.setInterval(loadOrders, 10_000);
    return () => window.clearInterval(interval);
  }, [apiBase]);

  const formatDate = (value?: string) => {
    if (!value) {
      return '—';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  };

  const formatNumber = (value?: number) => {
    if (value === undefined || value === null || Number.isNaN(value)) {
      return '—';
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">Order Flow</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Monitor order execution, status transitions, and reconciliation in real-time.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <FiRefreshCcw className="h-4 w-4" />
          Auto-refreshing every 10 seconds
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center rounded-lg bg-white dark:bg-gray-800">
          <LoadingSpinner />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Active Orders</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {activeOrders.length}
                </span>
                <FiClock className="h-6 w-6 text-sky-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Orders currently working in the market
              </p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Recent Fills</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {recentOrders.filter((order) => order.status === 'FILLED').length}
                </span>
                <FiCheckCircle className="h-6 w-6 text-emerald-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Filled within the last 100 orders
              </p>
            </div>
            <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
              <p className="text-sm text-gray-500 dark:text-gray-400">Alerts</p>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {recentOrders.filter((order) => order.status === 'CANCELED').length}
                </span>
                <FiAlertTriangle className="h-6 w-6 text-amber-500" />
              </div>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Recently canceled or rejected orders
              </p>
            </div>
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Active Orders</h3>
              <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                <FiHash className="h-4 w-4" />
                {activeOrders.length} live
              </div>
            </div>

            {activeOrders.length === 0 ? (
              <div className="py-12 text-center text-gray-500 dark:text-gray-400">
                The order book is currently clear.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead>
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Symbol
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Side
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Price
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Quantity
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Opened At
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {activeOrders.map((order) => (
                      <tr key={order.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                        <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                          {order.symbol}
                        </td>
                        <td className="px-4 py-3 text-sm font-medium">
                          <span
                            className={`rounded-md px-2 py-1 text-xs font-semibold ${
                              order.side === 'BUY'
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                                : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200'
                            }`}
                          >
                            {order.side}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {formatNumber(order.price)}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {formatNumber(order.quantity)}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <span
                            className={`rounded-md px-2 py-1 text-xs font-semibold ${
                              statusColors[order.status ?? ''] || 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                            }`}
                          >
                            {order.status ?? '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {formatDate(order.order_time)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Order History</h3>
              <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                <FiTrendingUp className="h-4 w-4" />
                Latest 100 submissions
              </div>
            </div>

            {recentOrders.length === 0 ? (
              <div className="py-12 text-center text-gray-500 dark:text-gray-400">
                No historical orders available.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead>
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Order ID
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Symbol
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Side
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Price
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Quantity
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Time
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {recentOrders.map((order) => (
                      <tr key={order.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {order.id}
                        </td>
                        <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                          {order.symbol}
                        </td>
                        <td className="px-4 py-3 text-sm font-medium">
                          <span
                            className={`rounded-md px-2 py-1 text-xs font-semibold ${
                              order.side === 'BUY'
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                                : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200'
                            }`}
                          >
                            {order.side}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {formatNumber(order.price)}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {formatNumber(order.quantity)}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <span
                            className={`rounded-md px-2 py-1 text-xs font-semibold ${
                              statusColors[order.status ?? ''] || 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                            }`}
                          >
                            {order.status ?? '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {formatDate(order.order_time)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default OrdersOverview;

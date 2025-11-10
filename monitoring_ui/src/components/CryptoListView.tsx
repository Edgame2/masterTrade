'use client';

import { useEffect, useMemo, useState } from 'react';
import { FiFilter, FiSearch, FiRefreshCw, FiShield } from 'react-icons/fi';
import LoadingSpinner from './LoadingSpinner';

interface SymbolRow {
  id: string;
  symbol: string;
  base_asset?: string;
  quote_asset?: string;
  asset_type?: string;
  exchange?: string;
  tracking?: boolean;
  active_for_trading?: boolean;
  liquidity_score?: number | string;
  volatility_score?: number | string;
  updated_at?: string;
}

const CryptoListView = () => {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const [symbols, setSymbols] = useState<SymbolRow[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>('');
  const [showActiveOnly, setShowActiveOnly] = useState<boolean>(false);
  const [showTradingOnly, setShowTradingOnly] = useState<boolean>(false);

  const formatScore = (value?: number | string) => {
    if (value === undefined || value === null) {
      return '—';
    }
    const numeric = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numeric) ? numeric.toFixed(2) : '—';
  };

  useEffect(() => {
    const loadSymbols = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(`${apiBase}/api/symbols?include_inactive=true`);
        if (!response.ok) {
          throw new Error('Failed to fetch symbol registry');
        }
        const payload = await response.json();
        const list: SymbolRow[] = payload.symbols || payload || [];
        setSymbols(list);
      } catch (err) {
        console.error('Error fetching symbols', err);
        setError(err instanceof Error ? err.message : 'Unable to load symbols');
      } finally {
        setLoading(false);
      }
    };

    loadSymbols();
  }, [apiBase]);

  const filteredSymbols = useMemo(() => {
    return symbols.filter((symbol) => {
      const matchesSearch = search
        ? symbol.symbol.toLowerCase().includes(search.toLowerCase()) ||
          symbol.base_asset?.toLowerCase().includes(search.toLowerCase()) ||
          symbol.quote_asset?.toLowerCase().includes(search.toLowerCase())
        : true;
      const matchesActive = showActiveOnly ? symbol.tracking : true;
      const matchesTrading = showTradingOnly ? symbol.active_for_trading : true;
      return matchesSearch && matchesActive && matchesTrading;
    });
  }, [symbols, search, showActiveOnly, showTradingOnly]);

  const refreshTimestamp = useMemo(() => {
    const hasTimestamps = symbols.some((item) => item.updated_at);
    if (!hasTimestamps) {
      return null;
    }
    const sorted = [...symbols]
      .filter((item) => item.updated_at)
      .sort((a, b) => (new Date(b.updated_at ?? 0).getTime() || 0) - (new Date(a.updated_at ?? 0).getTime() || 0));
    return sorted[0]?.updated_at ? new Date(sorted[0].updated_at!).toLocaleString() : null;
  }, [symbols]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">Crypto Asset Registry</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Complete inventory of tracked cryptocurrency pairs with liquidity, volatility, and trading status.
          </p>
        </div>
        {refreshTimestamp && (
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <FiRefreshCw className="h-4 w-4" />
            Updated {refreshTimestamp}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4 rounded-lg bg-white p-4 shadow dark:bg-gray-800 md:flex-row md:items-center md:justify-between">
        <div className="relative w-full md:w-80">
          <FiSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search symbol, base asset, or quote asset"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-gray-600 dark:text-gray-300">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showActiveOnly}
              onChange={(event) => setShowActiveOnly(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="flex items-center gap-2"><FiFilter className="h-4 w-4" /> Tracking Only</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showTradingOnly}
              onChange={(event) => setShowTradingOnly(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="flex items-center gap-2"><FiShield className="h-4 w-4" /> Live Trading</span>
          </label>
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
        <div className="overflow-x-auto rounded-lg bg-white shadow dark:bg-gray-800">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Symbol
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Base / Quote
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Exchange
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Tracking
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Trading
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Liquidity Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Volatility Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Updated
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {filteredSymbols.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-gray-500 dark:text-gray-400">
                    No symbols match the current filters.
                  </td>
                </tr>
              ) : (
                filteredSymbols.map((symbol) => (
                  <tr key={symbol.id ?? symbol.symbol} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
                    <td className="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-white">
                      {symbol.symbol}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {symbol.base_asset ?? '—'} / {symbol.quote_asset ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {symbol.exchange ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span
                        className={`rounded-md px-2 py-1 text-xs font-semibold ${
                          symbol.tracking
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                        }`}
                      >
                        {symbol.tracking ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span
                        className={`rounded-md px-2 py-1 text-xs font-semibold ${
                          symbol.active_for_trading
                            ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200'
                            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                        }`}
                      >
                        {symbol.active_for_trading ? 'Live' : 'Paper'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {formatScore(symbol.liquidity_score)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {formatScore(symbol.volatility_score)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                      {symbol.updated_at ? new Date(symbol.updated_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CryptoListView;

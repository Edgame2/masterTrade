'use client';

import { useCallback, useEffect, useState } from 'react';
import { FiActivity, FiCheck, FiClock, FiDatabase, FiRefreshCw, FiTrendingUp, FiX } from 'react-icons/fi';
import LoadingSpinner from './LoadingSpinner';

interface SymbolData {
  id: string;
  symbol: string;
  base_asset: string;
  quote_asset: string;
  asset_type?: string;
  exchange?: string;
  tracking: boolean;
  active_for_trading: boolean;
  created_at?: string;
  updated_at?: string;
  notes?: string;
  liquidity_score?: number | string;
  volatility_score?: number | string;
}

interface SymbolDetail extends SymbolData {
  average_spread_bps?: number;
  average_volume_24h?: number;
  volatility_24h?: number;
  data_sources?: string[];
  indicators_enabled?: string[];
}

interface HistoricalStats {
  symbol: string;
  intervals: {
    [key: string]: {
      record_count: number;
      earliest_data: string | null;
      latest_data: string | null;
      has_data: boolean;
    };
  };
}

const formatNumber = (value?: number | string | null): string => {
  if (value === undefined || value === null) {
    return '—';
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return '—';
  }
  return numeric >= 1000
    ? numeric.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : numeric.toLocaleString(undefined, { maximumFractionDigits: 4 });
};

const formatDate = (dateString?: string | null): string => {
  if (!dateString) {
    return '—';
  }
  const date = new Date(dateString);
  return Number.isNaN(date.getTime()) ? dateString : `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
};

const CryptoPairDetail = () => {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const [symbols, setSymbols] = useState<SymbolData[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [symbolDetail, setSymbolDetail] = useState<SymbolDetail | null>(null);
  const [historicalStats, setHistoricalStats] = useState<HistoricalStats | null>(null);
  const [loadingSymbols, setLoadingSymbols] = useState<boolean>(true);
  const [loadingStats, setLoadingStats] = useState<boolean>(false);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [includeInactive, setIncludeInactive] = useState<boolean>(false);

  const fetchSymbols = useCallback(async () => {
    try {
      setLoadingSymbols(true);
      const response = await fetch(`${apiBase}/api/symbols?include_inactive=${includeInactive}`);
      if (!response.ok) {
        throw new Error('Failed to fetch symbols');
      }
      const payload = await response.json();
      const list: SymbolData[] = payload.symbols || payload || [];
      setSymbols(list);
      if (!selectedSymbol && list.length > 0) {
        setSelectedSymbol(list[0].symbol);
      }
      setError(null);
    } catch (err) {
      console.error('Error fetching symbols', err);
      setError(err instanceof Error ? err.message : 'Failed to load symbols');
    } finally {
      setLoadingSymbols(false);
    }
  }, [apiBase, includeInactive, selectedSymbol]);

  useEffect(() => {
    fetchSymbols();
  }, [fetchSymbols]);

  useEffect(() => {
    if (!selectedSymbol) {
      setSymbolDetail(null);
      setHistoricalStats(null);
      return;
    }

    const loadDetailAndStats = async () => {
      try {
        setLoadingDetail(true);
        const detailResponse = await fetch(`${apiBase}/api/symbols/${selectedSymbol}`);
        if (detailResponse.ok) {
          const detailPayload = await detailResponse.json();
          setSymbolDetail(detailPayload);
        } else if (detailResponse.status !== 404) {
          throw new Error('Failed to load symbol detail');
        }
      } catch (err) {
        console.error('Error loading symbol detail', err);
        setSymbolDetail(null);
      } finally {
        setLoadingDetail(false);
      }
    };

    const loadHistoricalStats = async () => {
      try {
        setLoadingStats(true);
        const response = await fetch(`${apiBase}/api/symbols/${selectedSymbol}/historical-data`);
        if (!response.ok) {
          throw new Error('Failed to fetch historical stats');
        }
        const payload = await response.json();
        setHistoricalStats(payload);
      } catch (err) {
        console.error('Error fetching historical stats', err);
        setHistoricalStats(null);
      } finally {
        setLoadingStats(false);
      }
    };

    loadDetailAndStats();
    loadHistoricalStats();
  }, [apiBase, selectedSymbol]);

  const toggleTracking = async (symbol: string) => {
    try {
      const response = await fetch(`${apiBase}/api/symbols/${symbol}/toggle-tracking`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Failed to toggle tracking');
      }
      // Refresh list and details
      const updatedList = symbols.map((item) =>
        item.symbol === symbol ? { ...item, tracking: !item.tracking } : item
      );
      setSymbols(updatedList);
      if (symbolDetail && symbolDetail.symbol === symbol) {
        setSymbolDetail({ ...symbolDetail, tracking: !symbolDetail.tracking });
      }
    } catch (err) {
      console.error('Error toggling tracking', err);
    }
  };

  if (loadingSymbols) {
    return (
      <div className="flex h-80 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">Crypto Pair Detail</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Inspect tracking status, metadata, and historical coverage for each trading pair.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            Show inactive
          </label>
          <button
            onClick={() => setSelectedSymbol(null)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            Clear Selection
          </button>
          <button
            onClick={() => fetchSymbols()}
            className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-sm text-gray-600 shadow hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <FiRefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Tracked Symbols</h3>
            <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
              {symbols.map((symbol) => (
                <button
                  key={symbol.id}
                  onClick={() => setSelectedSymbol(symbol.symbol)}
                  className={`w-full rounded-lg border p-4 text-left transition ${
                    selectedSymbol === symbol.symbol
                      ? 'border-blue-500 bg-blue-50 dark:border-blue-400/60 dark:bg-blue-900/20'
                      : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-700/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-lg font-semibold text-gray-900 dark:text-white">
                        {symbol.symbol}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {symbol.base_asset}/{symbol.quote_asset} {symbol.exchange ? `• ${symbol.exchange}` : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-md px-2 py-1 text-xs font-semibold ${
                          symbol.tracking
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                        }`}
                      >
                        {symbol.tracking ? 'Tracking' : 'Inactive'}
                      </span>
                      {symbol.active_for_trading && (
                        <span className="rounded-md bg-blue-100 px-2 py-1 text-xs font-semibold text-blue-700 dark:bg-blue-900/40 dark:text-blue-200">
                          Live
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Symbol Insight</h3>
            {loadingDetail ? (
              <div className="flex h-40 items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : !selectedSymbol ? (
              <div className="flex h-40 items-center justify-center text-gray-500 dark:text-gray-400">
                Select a symbol to view details.
              </div>
            ) : !symbolDetail ? (
              <div className="flex h-40 items-center justify-center text-gray-500 dark:text-gray-400">
                No detail available for {selectedSymbol}.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Base Asset</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {symbolDetail.base_asset}
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Quote Asset</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {symbolDetail.quote_asset}
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Exchange</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {symbolDetail.exchange ?? '—'}
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Asset Type</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {symbolDetail.asset_type ?? '—'}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="flex items-center gap-3 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
                    <FiActivity className="h-5 w-5 text-sky-500" />
                    <div>
                      <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Tracking</p>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {symbolDetail.tracking ? 'Enabled' : 'Disabled'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
                    <FiTrendingUp className="h-5 w-5 text-emerald-500" />
                    <div>
                      <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Trading Mode</p>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">
                        {symbolDetail.active_for_trading ? 'Live Trading' : 'Paper Trading'}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Liquidity Score</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {formatNumber(symbolDetail.liquidity_score ?? symbolDetail.average_volume_24h)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Volatility Score</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {formatNumber(symbolDetail.volatility_score ?? symbolDetail.volatility_24h)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900/40">
                    <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Spread (bps)</p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {formatNumber(symbolDetail.average_spread_bps)}
                    </p>
                  </div>
                </div>

                {symbolDetail.notes && (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300">
                    {symbolDetail.notes}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>Created {formatDate(symbolDetail.created_at)}</span>
                  <span>•</span>
                  <span>Updated {formatDate(symbolDetail.updated_at)}</span>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => toggleTracking(symbolDetail.symbol)}
                    className={`rounded-md px-4 py-2 text-sm font-semibold ${
                      symbolDetail.tracking
                        ? 'bg-rose-600 text-white hover:bg-rose-700'
                        : 'bg-emerald-600 text-white hover:bg-emerald-700'
                    }`}
                  >
                    {symbolDetail.tracking ? 'Disable Tracking' : 'Enable Tracking'}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Historical Coverage</h3>
              <FiDatabase className="h-5 w-5 text-indigo-500" />
            </div>
            {loadingStats ? (
              <div className="flex h-40 items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : !historicalStats ? (
              <div className="flex h-40 items-center justify-center text-gray-500 dark:text-gray-400">
                No historical data statistics available.
              </div>
            ) : (
              <div className="space-y-3">
                {Object.entries(historicalStats.intervals).map(([interval, stats]) => (
                  <div key={interval} className="rounded-lg border border-gray-200 p-4 dark:border-gray-700">
                    <div className="flex items-center justify-between">
                      <h4 className="text-base font-semibold text-gray-900 dark:text-white">
                        {interval.toUpperCase()} interval
                      </h4>
                      <span
                        className={`flex items-center gap-2 rounded-md px-2 py-1 text-xs font-semibold ${
                          stats.has_data
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                        }`}
                      >
                        {stats.has_data ? (
                          <>
                            <FiCheck className="h-3 w-3" /> Available
                          </>
                        ) : (
                          <>
                            <FiX className="h-3 w-3" /> Missing
                          </>
                        )}
                      </span>
                    </div>
                    {stats.has_data && (
                      <div className="mt-3 grid grid-cols-1 gap-2 text-sm text-gray-600 dark:text-gray-300 sm:grid-cols-3">
                        <div>
                          <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Records</p>
                          <p className="font-semibold text-gray-900 dark:text-white">
                            {stats.record_count.toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Earliest</p>
                          <p className="font-semibold text-gray-900 dark:text-white">
                            {formatDate(stats.earliest_data)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs uppercase text-gray-500 dark:text-gray-400">Latest</p>
                          <p className="font-semibold text-gray-900 dark:text-white">
                            {formatDate(stats.latest_data)}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CryptoPairDetail;

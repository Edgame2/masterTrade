'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { FiActivity, FiCalendar, FiTrendingDown, FiTrendingUp } from 'react-icons/fi';
import LoadingSpinner from './LoadingSpinner';

interface SymbolRecord {
  id: string;
  symbol: string;
  base_asset?: string;
  quote_asset?: string;
  tracking?: boolean;
  active_for_trading?: boolean;
}

interface MarketDataPoint {
  symbol: string;
  timestamp: string;
  open_price?: string | number;
  high_price?: string | number;
  low_price?: string | number;
  close_price?: string | number;
  volume?: string | number;
  interval?: string;
}

interface PriceStats {
  latest: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  averageVolume: number;
  interval?: string;
}

const DEFAULT_SYMBOL = 'BTCUSDC';
const DEFAULT_LIMIT = 240;

const toNumber = (value?: string | number | null): number => {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const formatUSD = (value: number): string => {
  return value >= 1
    ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
    : `$${value.toFixed(6)}`;
};

const formatPercent = (value: number): string => {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
};

const HistoricalDataDashboard = () => {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const [symbols, setSymbols] = useState<SymbolRecord[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [limit, setLimit] = useState<number>(DEFAULT_LIMIT);
  const [marketData, setMarketData] = useState<MarketDataPoint[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSymbols = async () => {
      try {
        const response = await fetch(`${apiBase}/api/symbols?include_inactive=true`);
        if (!response.ok) {
          throw new Error('Failed to load symbols');
        }
        const payload = await response.json();
        const symbolList: SymbolRecord[] = payload.symbols || payload || [];
        setSymbols(symbolList);
        if (!symbolList.some((item) => item.symbol === selectedSymbol) && symbolList.length > 0) {
          setSelectedSymbol(symbolList[0].symbol);
        }
      } catch (err) {
        console.error('Error loading symbols', err);
        setError(err instanceof Error ? err.message : 'Unable to fetch symbols');
      }
    };

    loadSymbols();
  }, [apiBase, selectedSymbol]);

  useEffect(() => {
    const controller = new AbortController();
    const loadMarketData = async () => {
      if (!selectedSymbol) {
        setMarketData([]);
        return;
      }
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(
          `${apiBase}/api/market-data/${encodeURIComponent(selectedSymbol)}?limit=${limit}`,
          { signal: controller.signal }
        );
        if (!response.ok) {
          throw new Error('Failed to load historical data');
        }
        const payload = await response.json();
        const data: MarketDataPoint[] = Array.isArray(payload) ? payload : payload.data || [];
        setMarketData(data.reverse());
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          console.error('Error loading market data', err);
          setError(err instanceof Error ? err.message : 'Unable to fetch historical data');
        }
      } finally {
        setLoading(false);
      }
    };

    loadMarketData();
    return () => controller.abort();
  }, [apiBase, limit, selectedSymbol]);

  const parsedData = useMemo(() => {
    return marketData.map((point) => ({
      timestamp: point.timestamp,
      close: toNumber((point as { close?: string | number }).close ?? point.close_price ?? point.high_price),
      high: toNumber(point.high_price),
      low: toNumber(point.low_price),
      volume: toNumber(point.volume),
      interval: point.interval,
    }));
  }, [marketData]);

  const priceStats: PriceStats | null = useMemo(() => {
    if (parsedData.length === 0) {
      return null;
    }

    const closes = parsedData.map((item) => item.close);
    const volumes = parsedData.map((item) => item.volume);
    const latest = closes[closes.length - 1];
    const first = closes[0];
    const high = Math.max(...closes);
    const low = Math.min(...closes);
    const change = latest - first;
    const changePercent = first === 0 ? 0 : (change / first) * 100;
    const averageVolume = volumes.reduce((sum, value) => sum + value, 0) / volumes.length;

    return {
      latest,
      change,
      changePercent,
      high,
      low,
      averageVolume,
      interval: parsedData[parsedData.length - 1]?.interval,
    };
  }, [parsedData]);

  const handleLimitChange = (newLimit: number) => {
    setLimit(newLimit);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">Historical Data</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Inspect price history, volatility, and liquidity for tracked symbols.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex flex-col text-sm font-medium text-gray-700 dark:text-gray-200">
            Symbol
            <select
              className="mt-1 rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900"
              value={selectedSymbol}
              onChange={(event) => setSelectedSymbol(event.target.value)}
            >
              {symbols.map((item) => (
                <option key={item.id ?? item.symbol} value={item.symbol}>
                  {item.symbol}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-sm font-medium text-gray-700 dark:text-gray-200">
            Data Points
            <select
              className="mt-1 rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900"
              value={limit}
              onChange={(event) => handleLimitChange(Number(event.target.value))}
            >
              {[120, 240, 360, 720].map((value) => (
                <option key={value} value={value}>
                  Last {value}
                </option>
              ))}
            </select>
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
      ) : parsedData.length === 0 ? (
        <div className="flex h-80 items-center justify-center rounded-lg bg-white text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          No historical data available for {selectedSymbol}.
        </div>
      ) : (
        <>
          {priceStats && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
                <p className="text-sm text-gray-500 dark:text-gray-400">Last Price</p>
                <div className="mt-2 flex items-center justify-between">
                  <div className="text-2xl font-semibold text-gray-900 dark:text-white">
                    {formatUSD(priceStats.latest)}
                  </div>
                  {priceStats.change >= 0 ? (
                    <FiTrendingUp className="h-6 w-6 text-emerald-500" />
                  ) : (
                    <FiTrendingDown className="h-6 w-6 text-rose-500" />
                  )}
                </div>
                <p
                  className={`mt-2 text-sm font-medium ${
                    priceStats.change >= 0 ? 'text-emerald-600' : 'text-rose-600'
                  }`}
                >
                  {formatUSD(priceStats.change)} ({formatPercent(priceStats.changePercent)})
                </p>
              </div>

              <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
                <p className="text-sm text-gray-500 dark:text-gray-400">Range</p>
                <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
                  {formatUSD(priceStats.low)} - {formatUSD(priceStats.high)}
                </div>
                <p className="mt-2 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <FiCalendar className="h-4 w-4" />
                  Last {limit} data points
                  {priceStats.interval ? ` (${priceStats.interval} bars)` : ''}
                </p>
              </div>

              <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
                <p className="text-sm text-gray-500 dark:text-gray-400">Average Volume</p>
                <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
                  {priceStats.averageVolume.toLocaleString(undefined, {
                    maximumFractionDigits: 0,
                  })}
                </div>
                <p className="mt-2 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <FiActivity className="h-4 w-4" />
                  Estimated per interval
                </p>
              </div>

              <div className="rounded-lg bg-white p-4 shadow dark:bg-gray-800">
                <p className="text-sm text-gray-500 dark:text-gray-400">Data Coverage</p>
                <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
                  {parsedData.length}
                </div>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  Records fetched for {selectedSymbol}
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            <div className="xl:col-span-2 rounded-lg bg-white p-6 shadow dark:bg-gray-800">
              <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
                Price History
              </h3>
              <ResponsiveContainer width="100%" height={360}>
                <AreaChart data={parsedData}>
                  <defs>
                    <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                  <XAxis dataKey="timestamp" tick={{ fill: '#9CA3AF' }} minTickGap={32} />
                  <YAxis tick={{ fill: '#9CA3AF' }} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1f2937',
                      borderRadius: '0.75rem',
                      border: 'none',
                      color: '#f3f4f6',
                    }}
                  />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="close"
                    name="Close"
                    stroke="#0ea5e9"
                    strokeWidth={2}
                    fill="url(#priceGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
              <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
                Volume Profile
              </h3>
              <ResponsiveContainer width="100%" height={360}>
                <BarChart data={parsedData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.15} />
                  <XAxis
                    dataKey="timestamp"
                    hide
                  />
                  <YAxis tick={{ fill: '#9CA3AF' }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1f2937',
                      borderRadius: '0.75rem',
                      border: 'none',
                      color: '#f3f4f6',
                    }}
                    formatter={(value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    labelStyle={{ color: '#f3f4f6' }}
                  />
                  <Bar dataKey="volume" name="Volume" fill="#6366f1" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default HistoricalDataDashboard;

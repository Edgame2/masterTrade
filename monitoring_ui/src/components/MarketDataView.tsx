'use client';

import { useEffect, useState } from 'react';
import { 
  FiDatabase, 
  FiActivity, 
  FiClock,
  FiTrendingUp,
  FiRefreshCw,
  FiCheckCircle,
  FiAlertCircle
} from 'react-icons/fi';

interface MarketDataSummary {
  symbol: string;
  intervals: {
    [interval: string]: {
      earliest: string;
      latest: string;
      records: number;
      data_age_hours: number;
    };
  };
}

interface CollectorStatus {
  name: string;
  enabled: boolean;
  connected: boolean;
  type: string;
}

export default function MarketDataView() {
  const [data, setData] = useState<MarketDataSummary[]>([]);
  const [collectors, setCollectors] = useState<CollectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

  useEffect(() => {
    fetchMarketData();
    fetchCollectors();
    // Refresh every 60 seconds
    const interval = setInterval(() => {
      fetchMarketData();
      fetchCollectors();
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchMarketData = async () => {
    try {
      const response = await fetch(`${API_URL}/api/market-data/summary`);
      if (!response.ok) {
        throw new Error('Failed to fetch market data summary');
      }
      const result = await response.json();
      
      // Transform the data
      const summaryMap = new Map<string, MarketDataSummary>();
      
      result.summary?.forEach((item: any) => {
        const symbol = item.symbol;
        const interval = item.interval;
        
        if (!summaryMap.has(symbol)) {
          summaryMap.set(symbol, { symbol, intervals: {} });
        }
        
        const summary = summaryMap.get(symbol)!;
        const latest = new Date(item.last_timestamp);
        const now = new Date();
        const ageHours = (now.getTime() - latest.getTime()) / (1000 * 60 * 60);
        
        summary.intervals[interval] = {
          earliest: item.first_timestamp,
          latest: item.last_timestamp,
          records: item.record_count,
          data_age_hours: ageHours
        };
      });
      
      setData(Array.from(summaryMap.values()).sort((a, b) => a.symbol.localeCompare(b.symbol)));
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      console.error('Error fetching market data:', err);
      setError('Failed to load market data');
    } finally {
      setLoading(false);
    }
  };

  const fetchCollectors = async () => {
    try {
      const response = await fetch(`${API_URL}/api/collectors`);
      if (response.ok) {
        const result = await response.json();
        const collectorList = Object.values(result.collectors || {}) as CollectorStatus[];
        setCollectors(collectorList);
      }
    } catch (err) {
      console.error('Error fetching collectors:', err);
    }
  };

  const getDataAgeColor = (ageHours: number) => {
    if (ageHours < 24) return 'text-green-600 dark:text-green-400';
    if (ageHours < 72) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatAgeHours = (hours: number) => {
    if (hours < 1) return `${Math.round(hours * 60)}m ago`;
    if (hours < 24) return `${Math.round(hours)}h ago`;
    return `${Math.round(hours / 24)}d ago`;
  };

  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
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
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white">Market Data</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Real-time market data coverage and collection status
          </p>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={() => {
              fetchMarketData();
              fetchCollectors();
            }}
            className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            <FiRefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Collectors Status */}
      {collectors.length > 0 && (
        <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
          <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <FiActivity className="h-5 w-5" />
            Data Collectors
          </h3>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {collectors.map((collector) => (
              <div
                key={collector.name}
                className="flex items-center justify-between rounded-lg border border-gray-200 p-4 dark:border-gray-700"
              >
                <div>
                  <p className="font-semibold text-gray-900 dark:text-white capitalize">
                    {collector.name.replace(/_/g, ' ')}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{collector.type}</p>
                </div>
                <div className="flex items-center gap-2">
                  {collector.enabled && collector.connected ? (
                    <FiCheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <FiAlertCircle className="h-5 w-5 text-yellow-500" />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Market Data Summary */}
      <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <FiDatabase className="h-5 w-5" />
          Symbol Coverage ({data.length} symbols)
        </h3>
        
        <div className="space-y-4">
          {data.map((summary) => (
            <div
              key={summary.symbol}
              className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
            >
              <div className="mb-3 flex items-center justify-between">
                <h4 className="text-lg font-bold text-gray-900 dark:text-white">
                  {summary.symbol}
                </h4>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {Object.keys(summary.intervals).length} intervals
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                {Object.entries(summary.intervals)
                  .sort((a, b) => {
                    const order = ['1m', '5m', '15m', '1h', '4h', '1d'];
                    return order.indexOf(a[0]) - order.indexOf(b[0]);
                  })
                  .map(([interval, info]) => (
                    <div
                      key={interval}
                      className="rounded-md bg-gray-50 p-3 dark:bg-gray-900"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                          {interval}
                        </span>
                        <FiClock className={`h-3 w-3 ${getDataAgeColor(info.data_age_hours)}`} />
                      </div>
                      <p className="text-sm font-bold text-gray-900 dark:text-white">
                        {info.records.toLocaleString()}
                      </p>
                      <p className={`text-xs ${getDataAgeColor(info.data_age_hours)}`}>
                        {formatAgeHours(info.data_age_hours)}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Since {new Date(info.earliest).toLocaleDateString()}
                      </p>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
        
        {data.length === 0 && (
          <div className="text-center py-12">
            <FiDatabase className="mx-auto h-12 w-12 text-gray-400" />
            <p className="mt-4 text-gray-600 dark:text-gray-400">No market data available</p>
          </div>
        )}
      </div>
    </div>
  );
}

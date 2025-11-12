'use client';

import { useEffect, useState } from 'react';
import {
  FiActivity,
  FiCheckCircle,
  FiAlertCircle,
  FiXCircle,
  FiClock,
  FiRefreshCw,
  FiDatabase,
  FiServer,
  FiTrendingUp
} from 'react-icons/fi';

/**
 * Service health interface
 */
interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'down';
  uptime: number;
  lastCheck: string;
  url: string;
  responseTime?: number;
}

/**
 * Data source freshness summary
 */
interface DataFreshness {
  total: number;
  fresh: number;  // < 5 min
  stale: number;  // 5-15 min
  expired: number; // > 15 min
}

/**
 * System Health View Component
 * 
 * Displays overall system health including:
 * - Microservice status (market_data, strategy, risk_manager, etc.)
 * - Data source freshness summary
 * - Active alerts count
 * - Recent errors
 * - System uptime metrics
 */
export default function SystemHealthView() {
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [dataFreshness, setDataFreshness] = useState<DataFreshness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  // API URLs
  const MARKET_DATA_API = process.env.NEXT_PUBLIC_MARKET_DATA_API_URL || 'http://localhost:8000';
  const RISK_MANAGER_API = process.env.NEXT_PUBLIC_RISK_MANAGER_API_URL || 'http://localhost:8003';

  useEffect(() => {
    fetchSystemHealth();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchSystemHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  /**
   * Fetch system health from all services
   */
  const fetchSystemHealth = async () => {
    try {
      setError(null);
      
      // Check all services in parallel
      const [marketDataHealth, riskManagerHealth, dataSourcesHealth] = await Promise.allSettled([
        checkService('Market Data Service', `${MARKET_DATA_API}/health`),
        checkService('Risk Manager', `${RISK_MANAGER_API}/health`),
        fetchDataSourcesFreshness()
      ]);

      // Process results
      const servicesList: ServiceHealth[] = [];
      
      if (marketDataHealth.status === 'fulfilled') {
        servicesList.push(marketDataHealth.value);
      } else {
        servicesList.push({
          name: 'Market Data Service',
          status: 'down',
          uptime: 0,
          lastCheck: new Date().toISOString(),
          url: MARKET_DATA_API
        });
      }

      if (riskManagerHealth.status === 'fulfilled') {
        servicesList.push(riskManagerHealth.value);
      } else {
        servicesList.push({
          name: 'Risk Manager',
          status: 'down',
          uptime: 0,
          lastCheck: new Date().toISOString(),
          url: RISK_MANAGER_API
        });
      }

      setServices(servicesList);

      if (dataSourcesHealth.status === 'fulfilled') {
        setDataFreshness(dataSourcesHealth.value);
      }

      setLastUpdate(new Date());
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch system health');
      setLoading(false);
    }
  };

  /**
   * Check individual service health
   */
  const checkService = async (name: string, url: string): Promise<ServiceHealth> => {
    const startTime = Date.now();
    
    try {
      const response = await fetch(url, { method: 'GET' });
      const responseTime = Date.now() - startTime;
      
      const data = await response.json();
      
      return {
        name,
        status: response.ok ? 'healthy' : 'degraded',
        uptime: data.uptime || 0,
        lastCheck: new Date().toISOString(),
        url,
        responseTime
      };
    } catch (error) {
      return {
        name,
        status: 'down',
        uptime: 0,
        lastCheck: new Date().toISOString(),
        url,
        responseTime: Date.now() - startTime
      };
    }
  };

  /**
   * Fetch data sources freshness summary
   */
  const fetchDataSourcesFreshness = async (): Promise<DataFreshness> => {
    try {
      const response = await fetch(`${MARKET_DATA_API}/collectors`);
      const data = await response.json();
      
      if (!data.success || !data.collectors) {
        throw new Error('Invalid response from collectors endpoint');
      }

      const collectors = Object.values(data.collectors) as any[];
      const now = Date.now();
      
      let fresh = 0;
      let stale = 0;
      let expired = 0;

      collectors.forEach((collector: any) => {
        if (collector.rate_limiter?.last_request_time) {
          const lastUpdate = new Date(collector.rate_limiter.last_request_time).getTime();
          const minutesOld = (now - lastUpdate) / 1000 / 60;
          
          if (minutesOld < 5) fresh++;
          else if (minutesOld < 15) stale++;
          else expired++;
        } else {
          expired++; // No recent activity
        }
      });

      return {
        total: collectors.length,
        fresh,
        stale,
        expired
      };
    } catch (error) {
      return {
        total: 0,
        fresh: 0,
        stale: 0,
        expired: 0
      };
    }
  };

  /**
   * Get status icon component
   */
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <FiCheckCircle className="w-6 h-6 text-green-400" />;
      case 'degraded':
        return <FiAlertCircle className="w-6 h-6 text-yellow-400" />;
      case 'down':
        return <FiXCircle className="w-6 h-6 text-red-400" />;
      default:
        return <FiActivity className="w-6 h-6 text-gray-400" />;
    }
  };

  /**
   * Get status color class
   */
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'text-green-400 bg-green-500/20 border-green-500/30';
      case 'degraded':
        return 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30';
      case 'down':
        return 'text-red-400 bg-red-500/20 border-red-500/30';
      default:
        return 'text-gray-400 bg-gray-500/20 border-gray-500/30';
    }
  };

  /**
   * Format uptime display
   */
  const formatUptime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400">Loading system health...</p>
        </div>
      </div>
    );
  }

  // Calculate overall system status
  const allHealthy = services.every(s => s.status === 'healthy');
  const anyDown = services.some(s => s.status === 'down');
  const overallStatus = anyDown ? 'degraded' : allHealthy ? 'healthy' : 'degraded';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">System Health</h2>
          <p className="text-slate-400 mt-1">
            Real-time monitoring of all services and data sources
          </p>
        </div>
        <div className="flex items-center gap-4">
          {lastUpdate && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <FiClock className="w-4 h-4" />
              <span>{lastUpdate.toLocaleTimeString()}</span>
            </div>
          )}
          <button
            onClick={fetchSystemHealth}
            className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            title="Refresh"
          >
            <FiRefreshCw className="w-5 h-5 text-slate-300" />
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <FiAlertCircle className="w-5 h-5 text-red-400" />
            <span className="text-red-400">{error}</span>
          </div>
        </div>
      )}

      {/* Overall Status Card */}
      <div className={`rounded-lg p-6 border ${getStatusColor(overallStatus)}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {getStatusIcon(overallStatus)}
            <div>
              <h3 className="text-xl font-bold text-white">
                System Status: {overallStatus === 'healthy' ? 'All Systems Operational' : 'Service Disruption Detected'}
              </h3>
              <p className="text-sm text-slate-300 mt-1">
                {services.filter(s => s.status === 'healthy').length} of {services.length} services healthy
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Services Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {services.map((service) => (
          <div
            key={service.name}
            className="bg-slate-800 rounded-lg p-6 border border-slate-700"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <FiServer className="w-6 h-6 text-blue-400" />
                <div>
                  <h3 className="text-lg font-semibold text-white">{service.name}</h3>
                  <p className="text-xs text-slate-400 mt-1">{service.url}</p>
                </div>
              </div>
              {getStatusIcon(service.status)}
            </div>

            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Status:</span>
                <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(service.status)}`}>
                  {service.status.toUpperCase()}
                </span>
              </div>
              
              {service.responseTime !== undefined && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Response Time:</span>
                  <span className={`text-white font-medium ${
                    service.responseTime < 100 ? 'text-green-400' :
                    service.responseTime < 500 ? 'text-yellow-400' :
                    'text-red-400'
                  }`}>
                    {service.responseTime}ms
                  </span>
                </div>
              )}
              
              {service.uptime > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Uptime:</span>
                  <span className="text-white font-medium">
                    {formatUptime(service.uptime)}
                  </span>
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Last Check:</span>
                <span className="text-white font-medium">
                  {new Date(service.lastCheck).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Data Freshness Summary */}
      {dataFreshness && (
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
          <div className="flex items-center gap-3 mb-4">
            <FiDatabase className="w-6 h-6 text-purple-400" />
            <h3 className="text-lg font-semibold text-white">Data Source Freshness</h3>
          </div>

          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-white">{dataFreshness.total}</div>
              <div className="text-sm text-slate-400 mt-1">Total Sources</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-400">{dataFreshness.fresh}</div>
              <div className="text-sm text-slate-400 mt-1">Fresh (&lt;5min)</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-yellow-400">{dataFreshness.stale}</div>
              <div className="text-sm text-slate-400 mt-1">Stale (5-15min)</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-red-400">{dataFreshness.expired}</div>
              <div className="text-sm text-slate-400 mt-1">Expired (&gt;15min)</div>
            </div>
          </div>

          {/* Freshness bar */}
          <div className="mt-4 w-full bg-slate-700 rounded-full h-3 overflow-hidden flex">
            <div
              className="bg-green-500 h-full"
              style={{ width: `${(dataFreshness.fresh / dataFreshness.total) * 100}%` }}
            />
            <div
              className="bg-yellow-500 h-full"
              style={{ width: `${(dataFreshness.stale / dataFreshness.total) * 100}%` }}
            />
            <div
              className="bg-red-500 h-full"
              style={{ width: `${(dataFreshness.expired / dataFreshness.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <div className="flex gap-3">
          <FiTrendingUp className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-300">
            <p className="font-medium mb-2">System Monitoring:</p>
            <ul className="space-y-1 text-xs text-blue-200">
              <li>• Health checks run every 30 seconds automatically</li>
              <li>• Data freshness indicates when collectors last fetched data</li>
              <li>• Response times under 100ms are optimal, over 500ms may indicate issues</li>
              <li>• Click refresh to manually update all metrics</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

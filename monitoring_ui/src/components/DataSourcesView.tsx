'use client';

import { useEffect, useState } from 'react';
import { 
  FiDatabase, 
  FiActivity, 
  FiAlertCircle, 
  FiCheckCircle,
  FiXCircle,
  FiSettings,
  FiDollarSign,
  FiClock,
  FiTrendingUp,
  FiRefreshCw
} from 'react-icons/fi';
import { BiNetworkChart } from 'react-icons/bi';
import DataSourceConfigModal from './DataSourceConfigModal';
import { FreshnessBadge } from './FreshnessIndicator';

interface DataSource {
  name: string;
  type: string;
  enabled: boolean;
  status: string;
  health: string;
  last_update: string | null;
  error_rate: number;
  requests_today: number;
  monthly_cost: number | null;
  success_rate: number;
  rate_limiter?: {
    current_rate: number;
    backoff_multiplier: number;
    total_requests: number;
    total_throttles: number;
    total_backoffs: number;
  };
  circuit_breaker?: {
    state: string;
    failure_count: number;
    failure_threshold: number;
    health_score: number;
  };
  configured_rate_limit?: number;
}

export default function DataSourcesView() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<DataSource | null>(null);
  const [showConfigModal, setShowConfigModal] = useState(false);

  const API_URL = process.env.NEXT_PUBLIC_MARKET_DATA_API_URL || 'http://localhost:8000';

  useEffect(() => {
    fetchDataSources();
    // Poll for updates every 30 seconds
    const interval = setInterval(fetchDataSources, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchDataSources = async () => {
    try {
      const response = await fetch(`${API_URL}/collectors`);
      if (!response.ok) {
        throw new Error('Failed to fetch data sources');
      }
      const data = await response.json();
      // Transform the collectors data to match our interface
      const transformedSources = data.collectors?.map((collector: any) => ({
        name: collector.name,
        type: collector.type || 'unknown',
        enabled: collector.enabled,
        status: collector.status,
        health: collector.health,
        last_update: collector.last_collection_time,
        error_rate: collector.metrics?.error_rate || 0,
        requests_today: collector.metrics?.requests_today || 0,
        monthly_cost: collector.cost,
        success_rate: collector.metrics?.success_rate || 0
      })) || [];
      setSources(transformedSources);
      setError(null);
    } catch (err) {
      console.error('Error fetching data sources:', err);
      setError('Failed to load data sources');
    } finally {
      setLoading(false);
    }
  };

  const toggleDataSource = async (sourceName: string, currentState: boolean) => {
    try {
      const action = currentState ? 'disable' : 'enable';
      const response = await fetch(`${API_URL}/collectors/${sourceName}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (response.ok) {
        fetchDataSources(); // Refresh the list
      } else {
        console.error(`Failed to ${action} collector`);
      }
    } catch (err) {
      console.error('Error toggling data source:', err);
    }
  };

  const getStatusIcon = (status: string, health: string) => {
    if (status === 'disabled') return <FiXCircle className="text-gray-400" />;
    if (health === 'healthy') return <FiCheckCircle className="text-green-500" />;
    if (health === 'degraded') return <FiAlertCircle className="text-yellow-500" />;
    return <FiXCircle className="text-red-500" />;
  };

  const getStatusColor = (status: string, health: string) => {
    if (status === 'disabled') return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400';
    if (health === 'healthy') return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
    if (health === 'degraded') return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300';
    return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300';
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'onchain':
        return <BiNetworkChart className="text-purple-500" />;
      case 'social':
        return <FiActivity className="text-blue-500" />;
      case 'macro':
        return <FiTrendingUp className="text-green-500" />;
      case 'institutional':
        return <FiDatabase className="text-orange-500" />;
      default:
        return <FiDatabase className="text-gray-500" />;
    }
  };

  const getFreshnessColor = (lastUpdate: string | null) => {
    if (!lastUpdate) return 'text-gray-400';
    const now = new Date().getTime();
    const updateTime = new Date(lastUpdate).getTime();
    const minutesAgo = (now - updateTime) / 1000 / 60;
    
    if (minutesAgo < 5) return 'text-green-500';
    if (minutesAgo < 15) return 'text-yellow-500';
    return 'text-red-500';
  };

  const formatLastUpdate = (lastUpdate: string | null) => {
    if (!lastUpdate) return 'Never';
    const now = new Date().getTime();
    const updateTime = new Date(lastUpdate).getTime();
    const minutesAgo = Math.floor((now - updateTime) / 1000 / 60);
    
    if (minutesAgo < 1) return 'Just now';
    if (minutesAgo < 60) return `${minutesAgo}m ago`;
    const hoursAgo = Math.floor(minutesAgo / 60);
    if (hoursAgo < 24) return `${hoursAgo}h ago`;
    const daysAgo = Math.floor(hoursAgo / 24);
    return `${daysAgo}d ago`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <FiRefreshCw className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <div className="flex items-center">
          <FiAlertCircle className="w-5 h-5 text-red-500 mr-2" />
          <p className="text-red-700 dark:text-red-300">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Data Sources</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Monitor and manage all data collection sources
          </p>
        </div>
        <button
          onClick={fetchDataSources}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition"
        >
          <FiRefreshCw className="w-4 h-4" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Total Sources</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{sources.length}</p>
            </div>
            <FiDatabase className="w-8 h-8 text-primary-600" />
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Active</p>
              <p className="text-2xl font-bold text-green-600">
                {sources.filter(s => s.enabled && s.health === 'healthy').length}
              </p>
            </div>
            <FiCheckCircle className="w-8 h-8 text-green-500" />
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Degraded</p>
              <p className="text-2xl font-bold text-yellow-600">
                {sources.filter(s => s.health === 'degraded').length}
              </p>
            </div>
            <FiAlertCircle className="w-8 h-8 text-yellow-500" />
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Monthly Cost</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                ${sources.reduce((sum, s) => sum + (s.monthly_cost || 0), 0).toFixed(0)}
              </p>
            </div>
            <FiDollarSign className="w-8 h-8 text-green-600" />
          </div>
        </div>
      </div>

      {/* Data Sources Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sources.map((source) => (
          <div
            key={source.name}
            className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center space-x-3">
                <div className="text-2xl">
                  {getTypeIcon(source.type)}
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    {source.name}
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                    {source.type}
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                {getStatusIcon(source.status, source.health)}
              </div>
            </div>

            {/* Status Badge */}
            <div className="mb-4 flex items-center justify-between">
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(source.status, source.health)}`}>
                {source.status === 'disabled' ? 'Disabled' : source.health}
              </span>
              {source.last_update && (
                <FreshnessBadge timestamp={source.last_update} />
              )}
            </div>

            {/* Metrics */}
            <div className="space-y-3 mb-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">Success Rate</span>
                <span className="font-medium text-gray-900 dark:text-white">
                  {(source.success_rate * 100).toFixed(1)}%
                </span>
              </div>

              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">Requests Today</span>
                <span className="font-medium text-gray-900 dark:text-white">
                  {source.requests_today}
                </span>
              </div>

              {source.monthly_cost && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-400">Monthly Cost</span>
                  <span className="font-medium text-gray-900 dark:text-white">
                    ${source.monthly_cost}
                  </span>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center space-x-2 pt-4 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => toggleDataSource(source.name, source.enabled)}
                className={`flex-1 px-4 py-2 rounded-lg font-medium transition ${
                  source.enabled
                    ? 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900 dark:text-red-300'
                    : 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-300'
                }`}
              >
                {source.enabled ? 'Disable' : 'Enable'}
              </button>
              <button
                onClick={() => {
                  setSelectedSource(source);
                  setShowConfigModal(true);
                }}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 transition"
              >
                <FiSettings className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Empty State */}
      {sources.length === 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-12 text-center">
          <FiDatabase className="w-16 h-16 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            No Data Sources Found
          </h3>
          <p className="text-gray-600 dark:text-gray-400">
            Data sources will appear here once they are configured in the market data service.
          </p>
        </div>
      )}

      {/* Configuration Modal */}
      <DataSourceConfigModal
        isOpen={showConfigModal}
        source={selectedSource}
        onClose={() => {
          setShowConfigModal(false);
          setSelectedSource(null);
        }}
        onSave={() => {
          // Refresh data after successful save
          fetchDataSources();
        }}
      />
    </div>
  );
}

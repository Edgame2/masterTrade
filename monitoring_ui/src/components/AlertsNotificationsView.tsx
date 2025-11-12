'use client';

import { useState, useEffect } from 'react';
import { 
  FiBell, 
  FiAlertCircle, 
  FiAlertTriangle, 
  FiCheck, 
  FiX,
  FiFilter,
  FiPlus,
  FiMail,
  FiMessageSquare,
  FiRefreshCw
} from 'react-icons/fi';

const ALERT_API_URL = process.env.NEXT_PUBLIC_ALERT_API_URL || 'http://localhost:8007';

interface Alert {
  alert_id: string;
  alert_type: string;
  priority: string;
  title: string;
  message: string;
  status: string;
  created_at: string;
  triggered_at?: string;
  sent_at?: string;
  acknowledged_at?: string;
  trigger_count: number;
  channels: string[];
  symbol?: string;
  strategy_id?: string;
}

interface AlertStats {
  total_alerts: number;
  active_alerts: number;
  triggered_alerts: number;
  acknowledged_alerts: number;
  resolved_alerts: number;
  by_priority: { [key: string]: number };
  by_type: { [key: string]: number };
}

export default function AlertsNotificationsView() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  
  // UI state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [activeTab, setActiveTab] = useState<'active' | 'history' | 'config'>('active');
  
  // Alert creation form state
  const [alertType, setAlertType] = useState<'price' | 'performance' | 'risk' | 'health'>('price');
  const [formData, setFormData] = useState({
    symbol: 'BTCUSDT',
    operator: '>',
    threshold: '',
    priority: 'medium',
    channels: ['email'],
    // Performance alert fields
    strategy_id: '',
    metric: 'win_rate',
    streak_type: 'winning',
    streak_length: '3',
    // Risk alert fields
    risk_metric: 'drawdown',
    position_id: '',
    // Health alert fields
    service_name: 'market_data_service',
    health_metric: 'uptime',
    consecutive_failures: '3',
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const fetchData = async () => {
    try {
      setError(null);
      
      // Fetch alerts and stats in parallel
      const [alertsRes, statsRes] = await Promise.allSettled([
        fetch(`${ALERT_API_URL}/api/alerts/list?limit=100`),
        fetch(`${ALERT_API_URL}/api/alerts/stats/summary`)
      ]);
      
      if (alertsRes.status === 'fulfilled' && alertsRes.value.ok) {
        const alertsData = await alertsRes.value.json();
        setAlerts(Array.isArray(alertsData) ? alertsData : []);
      }
      
      if (statsRes.status === 'fulfilled' && statsRes.value.ok) {
        const statsData = await statsRes.value.json();
        setStats(statsData);
      }
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const acknowledgeAlert = async (alertId: string) => {
    try {
      const response = await fetch(`${ALERT_API_URL}/api/alerts/acknowledge/${alertId}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        fetchData(); // Refresh data
      }
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  const resolveAlert = async (alertId: string) => {
    try {
      const response = await fetch(`${ALERT_API_URL}/api/alerts/resolve/${alertId}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        fetchData(); // Refresh data
      }
    } catch (err) {
      console.error('Failed to resolve alert:', err);
    }
  };

  const createAlert = async () => {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(false);
    
    try {
      let endpoint = '';
      let body: any = {
        channels: formData.channels,
        priority: formData.priority,
      };
      
      // Build request based on alert type
      switch (alertType) {
        case 'price':
          endpoint = '/api/alerts/price';
          body = {
            ...body,
            symbol: formData.symbol,
            operator: formData.operator,
            threshold: parseFloat(formData.threshold),
          };
          break;
          
        case 'performance':
          endpoint = '/api/alerts/performance';
          body = {
            ...body,
            strategy_id: formData.strategy_id,
            metric: formData.metric,
            operator: formData.operator,
            threshold: parseFloat(formData.threshold),
          };
          if (formData.metric === 'streak') {
            body.streak_type = formData.streak_type;
            body.streak_length = parseInt(formData.streak_length);
          }
          break;
          
        case 'risk':
          endpoint = '/api/alerts/risk';
          body = {
            ...body,
            risk_metric: formData.risk_metric,
            operator: formData.operator,
            threshold: parseFloat(formData.threshold),
          };
          if (formData.symbol) body.symbol = formData.symbol;
          if (formData.position_id) body.position_id = formData.position_id;
          break;
          
        case 'health':
          endpoint = '/api/alerts/health';
          body = {
            ...body,
            service_name: formData.service_name,
            health_metric: formData.health_metric,
            operator: formData.operator,
            threshold: parseFloat(formData.threshold),
            consecutive_failures: parseInt(formData.consecutive_failures),
          };
          break;
      }
      
      const response = await fetch(`${ALERT_API_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create alert');
      }
      
      setSubmitSuccess(true);
      setTimeout(() => {
        setShowCreateForm(false);
        setSubmitSuccess(false);
        fetchData(); // Refresh alert list
      }, 1500);
      
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create alert');
    } finally {
      setSubmitting(false);
    }
  };

  // Filter alerts
  const filteredAlerts = alerts.filter(alert => {
    if (statusFilter !== 'all' && alert.status !== statusFilter) return false;
    if (priorityFilter !== 'all' && alert.priority !== priorityFilter) return false;
    if (typeFilter !== 'all' && alert.alert_type !== typeFilter) return false;
    return true;
  });

  const getPriorityColor = (priority: string) => {
    switch (priority.toLowerCase()) {
      case 'critical': return 'text-red-600 bg-red-50';
      case 'high': return 'text-orange-600 bg-orange-50';
      case 'medium': return 'text-yellow-600 bg-yellow-50';
      case 'low': return 'text-blue-600 bg-blue-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const getPriorityIcon = (priority: string) => {
    switch (priority.toLowerCase()) {
      case 'critical':
      case 'high':
        return <FiAlertTriangle className="text-red-500" />;
      case 'medium':
        return <FiAlertCircle className="text-yellow-500" />;
      default:
        return <FiBell className="text-blue-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const colors: { [key: string]: string } = {
      active: 'bg-green-100 text-green-800',
      triggered: 'bg-red-100 text-red-800',
      acknowledged: 'bg-yellow-100 text-yellow-800',
      resolved: 'bg-gray-100 text-gray-800',
      suppressed: 'bg-purple-100 text-purple-800'
    };
    
    return (
      <span className={`px-2 py-1 text-xs font-medium rounded-full ${colors[status] || colors.active}`}>
        {status.toUpperCase()}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <FiRefreshCw className="animate-spin text-primary-500" size={32} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Stats */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            Alerts & Notifications
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Monitor and manage system alerts
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          <FiPlus size={20} />
          Create Alert
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow-md">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Total Alerts</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {stats.total_alerts}
                </p>
              </div>
              <FiBell className="text-gray-400" size={32} />
            </div>
          </div>

          <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow-md">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Active</p>
                <p className="text-2xl font-bold text-green-600">
                  {stats.active_alerts}
                </p>
              </div>
              <FiAlertCircle className="text-green-500" size={32} />
            </div>
          </div>

          <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow-md">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Triggered</p>
                <p className="text-2xl font-bold text-red-600">
                  {stats.triggered_alerts}
                </p>
              </div>
              <FiAlertTriangle className="text-red-500" size={32} />
            </div>
          </div>

          <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow-md">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Resolved</p>
                <p className="text-2xl font-bold text-gray-600">
                  {stats.resolved_alerts}
                </p>
              </div>
              <FiCheck className="text-gray-400" size={32} />
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow-md">
        <div className="flex items-center gap-2 mb-4">
          <FiFilter className="text-gray-500" />
          <span className="font-medium text-gray-700 dark:text-gray-300">Filters</span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active</option>
              <option value="triggered">Triggered</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="suppressed">Suppressed</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Priority
            </label>
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
            >
              <option value="all">All Priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Type
            </label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
            >
              <option value="all">All Types</option>
              <option value="price">Price</option>
              <option value="performance">Performance</option>
              <option value="risk">Risk</option>
              <option value="system">System Health</option>
              <option value="milestone">Milestone</option>
            </select>
          </div>
        </div>
      </div>

      {/* Alerts List */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Alerts ({filteredAlerts.length})
          </h3>
        </div>

        {error && (
          <div className="p-4 m-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

        <div className="divide-y divide-gray-200 dark:divide-gray-700">
          {filteredAlerts.length === 0 ? (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">
              No alerts found matching the selected filters
            </div>
          ) : (
            filteredAlerts.map((alert) => (
              <div key={alert.alert_id} className="p-4 hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1">
                    <div className="mt-1">
                      {getPriorityIcon(alert.priority)}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold text-gray-900 dark:text-white">
                          {alert.title}
                        </h4>
                        {getStatusBadge(alert.status)}
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getPriorityColor(alert.priority)}`}>
                          {alert.priority.toUpperCase()}
                        </span>
                      </div>
                      
                      <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                        {alert.message}
                      </p>
                      
                      <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                        <span>Type: {alert.alert_type}</span>
                        {alert.symbol && <span>Symbol: {alert.symbol}</span>}
                        <span>Triggers: {alert.trigger_count}</span>
                        <span>Created: {new Date(alert.created_at).toLocaleString()}</span>
                      </div>
                      
                      {alert.channels.length > 0 && (
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-xs text-gray-500">Channels:</span>
                          {alert.channels.map((channel) => (
                            <span
                              key={channel}
                              className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 text-xs rounded"
                            >
                              {channel === 'email' && <FiMail size={12} />}
                              {channel === 'telegram' && <FiMessageSquare size={12} />}
                              {channel}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    {alert.status === 'triggered' && (
                      <button
                        onClick={() => acknowledgeAlert(alert.alert_id)}
                        className="px-3 py-1 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600 transition-colors"
                        title="Acknowledge"
                      >
                        <FiCheck size={16} />
                      </button>
                    )}
                    {(alert.status === 'triggered' || alert.status === 'acknowledged') && (
                      <button
                        onClick={() => resolveAlert(alert.alert_id)}
                        className="px-3 py-1 text-sm bg-green-500 text-white rounded hover:bg-green-600 transition-colors"
                        title="Resolve"
                      >
                        <FiX size={16} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Placeholder for Create Alert Form */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl max-w-2xl w-full p-6 my-8">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                Create New Alert
              </h3>
              <button
                onClick={() => {
                  setShowCreateForm(false);
                  setSubmitError(null);
                  setSubmitSuccess(false);
                }}
                className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              >
                <FiX size={24} />
              </button>
            </div>
            
            {/* Alert Type Selection */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Alert Type
              </label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {(['price', 'performance', 'risk', 'health'] as const).map((type) => (
                  <button
                    key={type}
                    onClick={() => setAlertType(type)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                      alertType === type
                        ? 'bg-primary-500 text-white'
                        : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-slate-600'
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>
            
            <div className="space-y-4 max-h-96 overflow-y-auto pr-2">
              {/* Price Alert Fields */}
              {alertType === 'price' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Symbol
                    </label>
                    <input
                      type="text"
                      value={formData.symbol}
                      onChange={(e) => setFormData({ ...formData, symbol: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      placeholder="BTCUSDT"
                    />
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Operator
                      </label>
                      <select
                        value={formData.operator}
                        onChange={(e) => setFormData({ ...formData, operator: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      >
                        <option value=">">Greater than (&gt;)</option>
                        <option value="<">Less than (&lt;)</option>
                        <option value=">=">Greater or equal (≥)</option>
                        <option value="<=">Less or equal (≤)</option>
                        <option value="crosses_above">Crosses Above</option>
                        <option value="crosses_below">Crosses Below</option>
                      </select>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Threshold Price
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={formData.threshold}
                        onChange={(e) => setFormData({ ...formData, threshold: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                        placeholder="50000"
                      />
                    </div>
                  </div>
                </>
              )}
              
              {/* Performance Alert Fields */}
              {alertType === 'performance' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Strategy ID
                    </label>
                    <input
                      type="text"
                      value={formData.strategy_id}
                      onChange={(e) => setFormData({ ...formData, strategy_id: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      placeholder="strategy_12345"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Metric
                    </label>
                    <select
                      value={formData.metric}
                      onChange={(e) => setFormData({ ...formData, metric: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                    >
                      <option value="win_rate">Win Rate</option>
                      <option value="pnl">P&L</option>
                      <option value="drawdown">Drawdown</option>
                      <option value="sharpe_ratio">Sharpe Ratio</option>
                      <option value="streak">Streak</option>
                    </select>
                  </div>
                  
                  {formData.metric === 'streak' && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Streak Type
                        </label>
                        <select
                          value={formData.streak_type}
                          onChange={(e) => setFormData({ ...formData, streak_type: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                        >
                          <option value="winning">Winning</option>
                          <option value="losing">Losing</option>
                        </select>
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Streak Length
                        </label>
                        <input
                          type="number"
                          value={formData.streak_length}
                          onChange={(e) => setFormData({ ...formData, streak_length: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                        />
                      </div>
                    </div>
                  )}
                  
                  {formData.metric !== 'streak' && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Operator
                        </label>
                        <select
                          value={formData.operator}
                          onChange={(e) => setFormData({ ...formData, operator: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                        >
                          <option value=">">Greater than (&gt;)</option>
                          <option value="<">Less than (&lt;)</option>
                          <option value=">=">Greater or equal (≥)</option>
                          <option value="<=">Less or equal (≤)</option>
                        </select>
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Threshold
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          value={formData.threshold}
                          onChange={(e) => setFormData({ ...formData, threshold: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                          placeholder="0.5"
                        />
                      </div>
                    </div>
                  )}
                </>
              )}
              
              {/* Risk Alert Fields */}
              {alertType === 'risk' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Risk Metric
                    </label>
                    <select
                      value={formData.risk_metric}
                      onChange={(e) => setFormData({ ...formData, risk_metric: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                    >
                      <option value="drawdown">Drawdown</option>
                      <option value="position_size">Position Size</option>
                      <option value="leverage">Leverage</option>
                      <option value="margin">Margin</option>
                      <option value="exposure">Exposure</option>
                    </select>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Operator
                      </label>
                      <select
                        value={formData.operator}
                        onChange={(e) => setFormData({ ...formData, operator: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      >
                        <option value=">">Greater than (&gt;)</option>
                        <option value="<">Less than (&lt;)</option>
                        <option value=">=">Greater or equal (≥)</option>
                        <option value="<=">Less or equal (≤)</option>
                      </select>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Threshold
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={formData.threshold}
                        onChange={(e) => setFormData({ ...formData, threshold: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                        placeholder="0.1"
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Symbol (Optional)
                    </label>
                    <input
                      type="text"
                      value={formData.symbol}
                      onChange={(e) => setFormData({ ...formData, symbol: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      placeholder="BTCUSDT"
                    />
                  </div>
                </>
              )}
              
              {/* Health Alert Fields */}
              {alertType === 'health' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Service Name
                    </label>
                    <select
                      value={formData.service_name}
                      onChange={(e) => setFormData({ ...formData, service_name: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                    >
                      <option value="market_data_service">Market Data Service</option>
                      <option value="strategy_service">Strategy Service</option>
                      <option value="order_executor">Order Executor</option>
                      <option value="risk_manager">Risk Manager</option>
                      <option value="alert_system">Alert System</option>
                      <option value="api_gateway">API Gateway</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Health Metric
                    </label>
                    <select
                      value={formData.health_metric}
                      onChange={(e) => setFormData({ ...formData, health_metric: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                    >
                      <option value="uptime">Uptime</option>
                      <option value="error_rate">Error Rate</option>
                      <option value="latency">Latency</option>
                      <option value="cpu">CPU Usage</option>
                      <option value="memory">Memory Usage</option>
                    </select>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Operator
                      </label>
                      <select
                        value={formData.operator}
                        onChange={(e) => setFormData({ ...formData, operator: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      >
                        <option value=">">Greater than (&gt;)</option>
                        <option value="<">Less than (&lt;)</option>
                        <option value=">=">Greater or equal (≥)</option>
                        <option value="<=">Less or equal (≤)</option>
                      </select>
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Threshold
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={formData.threshold}
                        onChange={(e) => setFormData({ ...formData, threshold: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                        placeholder="90"
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Consecutive Failures
                    </label>
                    <input
                      type="number"
                      value={formData.consecutive_failures}
                      onChange={(e) => setFormData({ ...formData, consecutive_failures: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                    />
                  </div>
                </>
              )}
              
              {/* Common Fields */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Priority
                </label>
                <select
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Notification Channels
                </label>
                <div className="space-y-2">
                  {['email', 'telegram', 'discord', 'sms'].map((channel) => (
                    <label key={channel} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={formData.channels.includes(channel)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setFormData({ ...formData, channels: [...formData.channels, channel] });
                          } else {
                            setFormData({ ...formData, channels: formData.channels.filter(c => c !== channel) });
                          }
                        }}
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300 capitalize">{channel}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
            
            {/* Error/Success Messages */}
            {submitError && (
              <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-sm text-red-600 dark:text-red-400">{submitError}</p>
              </div>
            )}
            
            {submitSuccess && (
              <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                <p className="text-sm text-green-600 dark:text-green-400">Alert created successfully!</p>
              </div>
            )}
            
            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => {
                  setShowCreateForm(false);
                  setSubmitError(null);
                  setSubmitSuccess(false);
                }}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                onClick={createAlert}
                disabled={submitting || !formData.threshold || formData.channels.length === 0}
                className="px-4 py-2 text-sm font-medium text-white bg-primary-500 hover:bg-primary-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {submitting && <FiRefreshCw className="animate-spin" size={16} />}
                {submitting ? 'Creating...' : 'Create Alert'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

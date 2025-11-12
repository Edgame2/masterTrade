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
  FiRefreshCw,
  FiSettings,
  FiCheckCircle,
  FiClock,
  FiAlertOctagon,
  FiSlash,
  FiEye
} from 'react-icons/fi';

const ALERT_API_URL = process.env.NEXT_PUBLIC_ALERT_API_URL || 'http://localhost:8007';
const API_GATEWAY_URL = process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8090';

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
  resolved_at?: string;
  trigger_count: number;
  channels: string[];
  symbol?: string;
  strategy_id?: string;
  position_id?: string;
  data?: any;
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

interface NotificationChannel {
  channel_type: string;
  enabled: boolean;
  config: any;
}

export default function AlertsPage() {
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
    // Common fields
    priority: 'medium',
    channels: ['email'],
    throttle_minutes: '5',
    max_triggers: '10',
    
    // Price alert fields
    symbol: 'BTCUSDT',
    operator: '>',
    threshold: '',
    
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
  
  // Notification channels config
  const [channels, setChannels] = useState<NotificationChannel[]>([
    { channel_type: 'email', enabled: true, config: {} },
    { channel_type: 'telegram', enabled: false, config: {} },
    { channel_type: 'discord', enabled: false, config: {} },
    { channel_type: 'sms', enabled: false, config: {} },
    { channel_type: 'webhook', enabled: false, config: {} },
  ]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [statusFilter, priorityFilter, typeFilter]);

  const fetchData = async () => {
    try {
      setError(null);
      
      // Build query params
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (priorityFilter !== 'all') params.append('priority', priorityFilter);
      if (typeFilter !== 'all') params.append('type', typeFilter);
      params.append('limit', '100');
      
      // Fetch alerts and stats
      const [alertsRes, statsRes] = await Promise.allSettled([
        fetch(`${ALERT_API_URL}/api/alerts/list?${params.toString()}`),
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
      
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
      setLoading(false);
    }
  };

  const handleCreateAlert = async () => {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(false);
    
    try {
      let endpoint = '';
      let body: any = {
        priority: formData.priority,
        channels: formData.channels,
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
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create alert');
      }
      
      setSubmitSuccess(true);
      setTimeout(() => {
        setShowCreateForm(false);
        setSubmitSuccess(false);
        fetchData();
      }, 1500);
      
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create alert');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      const response = await fetch(`${ALERT_API_URL}/api/alerts/${alertId}/acknowledge`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        throw new Error('Failed to acknowledge alert');
      }
      
      fetchData();
    } catch (err) {
      console.error('Error acknowledging alert:', err);
    }
  };

  const handleResolveAlert = async (alertId: string) => {
    try {
      const response = await fetch(`${ALERT_API_URL}/api/alerts/${alertId}/resolve`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        throw new Error('Failed to resolve alert');
      }
      
      fetchData();
    } catch (err) {
      console.error('Error resolving alert:', err);
    }
  };

  const handleSnoozeAlert = async (alertId: string, minutes: number) => {
    try {
      const response = await fetch(`${ALERT_API_URL}/api/alerts/${alertId}/snooze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ duration_minutes: minutes }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to snooze alert');
      }
      
      fetchData();
    } catch (err) {
      console.error('Error snoozing alert:', err);
    }
  };

  const handleDeleteAlert = async (alertId: string) => {
    if (!confirm('Are you sure you want to delete this alert?')) {
      return;
    }
    
    try {
      const response = await fetch(`${ALERT_API_URL}/api/alerts/${alertId}`, {
        method: 'DELETE',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete alert');
      }
      
      fetchData();
    } catch (err) {
      console.error('Error deleting alert:', err);
    }
  };

  const getPriorityColor = (priority: string) => {
    const colors: { [key: string]: string } = {
      critical: 'text-red-600 bg-red-100 dark:bg-red-900/30',
      high: 'text-orange-600 bg-orange-100 dark:bg-orange-900/30',
      medium: 'text-yellow-600 bg-yellow-100 dark:bg-yellow-900/30',
      low: 'text-blue-600 bg-blue-100 dark:bg-blue-900/30',
      info: 'text-gray-600 bg-gray-100 dark:bg-gray-700',
    };
    return colors[priority.toLowerCase()] || colors.info;
  };

  const getStatusColor = (status: string) => {
    const colors: { [key: string]: string } = {
      pending: 'text-gray-600 bg-gray-100 dark:bg-gray-700',
      triggered: 'text-red-600 bg-red-100 dark:bg-red-900/30',
      sent: 'text-blue-600 bg-blue-100 dark:bg-blue-900/30',
      acknowledged: 'text-yellow-600 bg-yellow-100 dark:bg-yellow-900/30',
      resolved: 'text-green-600 bg-green-100 dark:bg-green-900/30',
      expired: 'text-gray-500 bg-gray-100 dark:bg-gray-700',
      suppressed: 'text-purple-600 bg-purple-100 dark:bg-purple-900/30',
    };
    return colors[status.toLowerCase()] || colors.pending;
  };

  const filteredAlerts = alerts.filter(alert => {
    if (activeTab === 'active') {
      return ['pending', 'triggered', 'sent'].includes(alert.status);
    } else if (activeTab === 'history') {
      return ['acknowledged', 'resolved', 'expired'].includes(alert.status);
    }
    return true;
  });

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
              <FiBell className="text-blue-500" />
              Alert Configuration & Management
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mt-2">
              Configure alerts, manage notifications, and view alert history
            </p>
          </div>
          
          <div className="flex gap-3">
            <button
              onClick={fetchData}
              className="px-4 py-2 bg-gray-200 dark:bg-slate-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-slate-600 flex items-center gap-2"
            >
              <FiRefreshCw className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            
            <button
              onClick={() => setShowCreateForm(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
            >
              <FiPlus />
              Create Alert
            </button>
          </div>
        </div>

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Total Alerts</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total_alerts}</p>
                </div>
                <FiBell className="text-gray-400 text-3xl" />
              </div>
            </div>
            
            <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Active</p>
                  <p className="text-2xl font-bold text-blue-600">{stats.active_alerts}</p>
                </div>
                <FiAlertCircle className="text-blue-400 text-3xl" />
              </div>
            </div>
            
            <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Triggered</p>
                  <p className="text-2xl font-bold text-red-600">{stats.triggered_alerts}</p>
                </div>
                <FiAlertTriangle className="text-red-400 text-3xl" />
              </div>
            </div>
            
            <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Acknowledged</p>
                  <p className="text-2xl font-bold text-yellow-600">{stats.acknowledged_alerts}</p>
                </div>
                <FiCheckCircle className="text-yellow-400 text-3xl" />
              </div>
            </div>
            
            <div className="bg-white dark:bg-slate-800 p-4 rounded-lg shadow">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Resolved</p>
                  <p className="text-2xl font-bold text-green-600">{stats.resolved_alerts}</p>
                </div>
                <FiCheck className="text-green-400 text-3xl" />
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex gap-8 px-6">
              <button
                onClick={() => setActiveTab('active')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'active'
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                Active Alerts
              </button>
              <button
                onClick={() => setActiveTab('history')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'history'
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                Alert History
              </button>
              <button
                onClick={() => setActiveTab('config')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'config'
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                Configuration
              </button>
            </nav>
          </div>

          {/* Filters */}
          {(activeTab === 'active' || activeTab === 'history') && (
            <div className="p-4 bg-gray-50 dark:bg-slate-700/50 border-b border-gray-200 dark:border-gray-700">
              <div className="flex flex-wrap gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <FiFilter className="inline mr-1" />
                    Status
                  </label>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                  >
                    <option value="all">All</option>
                    <option value="pending">Pending</option>
                    <option value="triggered">Triggered</option>
                    <option value="sent">Sent</option>
                    <option value="acknowledged">Acknowledged</option>
                    <option value="resolved">Resolved</option>
                    <option value="expired">Expired</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Priority
                  </label>
                  <select
                    value={priorityFilter}
                    onChange={(e) => setPriorityFilter(e.target.value)}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                  >
                    <option value="all">All</option>
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                    <option value="info">Info</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Type
                  </label>
                  <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                  >
                    <option value="all">All</option>
                    <option value="price">Price</option>
                    <option value="performance">Performance</option>
                    <option value="risk">Risk</option>
                    <option value="health">Health</option>
                    <option value="milestone">Milestone</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Content */}
          <div className="p-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <FiRefreshCw className="animate-spin text-4xl text-blue-500" />
              </div>
            ) : error ? (
              <div className="text-center py-12">
                <FiAlertCircle className="mx-auto text-5xl text-red-500 mb-4" />
                <p className="text-red-600 dark:text-red-400">{error}</p>
              </div>
            ) : activeTab === 'config' ? (
              /* Configuration Tab */
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <FiSettings />
                    Notification Channels
                  </h3>
                  
                  <div className="space-y-4">
                    {channels.map((channel) => (
                      <div
                        key={channel.channel_type}
                        className="flex items-center justify-between p-4 bg-gray-50 dark:bg-slate-700/50 rounded-lg border border-gray-200 dark:border-gray-600"
                      >
                        <div className="flex items-center gap-3">
                          {channel.channel_type === 'email' && <FiMail className="text-2xl text-blue-500" />}
                          {channel.channel_type === 'telegram' && <FiMessageSquare className="text-2xl text-blue-500" />}
                          {channel.channel_type === 'discord' && <FiMessageSquare className="text-2xl text-indigo-500" />}
                          {channel.channel_type === 'sms' && <FiMessageSquare className="text-2xl text-green-500" />}
                          {channel.channel_type === 'webhook' && <FiSettings className="text-2xl text-purple-500" />}
                          
                          <div>
                            <p className="font-medium text-gray-900 dark:text-white capitalize">
                              {channel.channel_type}
                            </p>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                              {channel.enabled ? 'Active' : 'Disabled'}
                            </p>
                          </div>
                        </div>
                        
                        <button
                          onClick={() => {
                            const updated = channels.map(c =>
                              c.channel_type === channel.channel_type
                                ? { ...c, enabled: !c.enabled }
                                : c
                            );
                            setChannels(updated);
                          }}
                          className={`px-4 py-2 rounded-lg font-medium ${
                            channel.enabled
                              ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-slate-600 dark:text-gray-300'
                          }`}
                        >
                          {channel.enabled ? 'Enabled' : 'Disabled'}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
                    Escalation Rules
                  </h3>
                  
                  <div className="space-y-3">
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                      <div className="flex items-start gap-3">
                        <FiAlertOctagon className="text-red-600 text-xl mt-0.5" />
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">Critical Alerts</p>
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            Escalate to SMS and phone call after 5 minutes if not acknowledged
                          </p>
                        </div>
                      </div>
                    </div>
                    
                    <div className="p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
                      <div className="flex items-start gap-3">
                        <FiAlertTriangle className="text-orange-600 text-xl mt-0.5" />
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">High Priority Alerts</p>
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            Send to backup email after 15 minutes if not acknowledged
                          </p>
                        </div>
                      </div>
                    </div>
                    
                    <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
                      <div className="flex items-start gap-3">
                        <FiClock className="text-yellow-600 text-xl mt-0.5" />
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">Medium/Low Priority</p>
                          <p className="text-sm text-gray-600 dark:text-gray-400">
                            Auto-acknowledge after 24 hours if no action taken
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div>
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
                    Alert Thresholds
                  </h3>
                  
                  <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700 dark:text-gray-300">Max alerts per minute</span>
                        <span className="font-mono text-gray-900 dark:text-white">100</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700 dark:text-gray-300">Alert retention (days)</span>
                        <span className="font-mono text-gray-900 dark:text-white">30</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700 dark:text-gray-300">Duplicate suppression (minutes)</span>
                        <span className="font-mono text-gray-900 dark:text-white">5</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-700 dark:text-gray-300">Throttle period (minutes)</span>
                        <span className="font-mono text-gray-900 dark:text-white">5</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : filteredAlerts.length === 0 ? (
              <div className="text-center py-12">
                <FiBell className="mx-auto text-5xl text-gray-400 mb-4" />
                <p className="text-gray-600 dark:text-gray-400">No alerts found</p>
              </div>
            ) : (
              /* Alerts List */
              <div className="space-y-4">
                {filteredAlerts.map((alert) => (
                  <div
                    key={alert.alert_id}
                    className="p-4 bg-gray-50 dark:bg-slate-700/50 rounded-lg border border-gray-200 dark:border-gray-600"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${getPriorityColor(alert.priority)}`}>
                            {alert.priority.toUpperCase()}
                          </span>
                          <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(alert.status)}`}>
                            {alert.status.toUpperCase()}
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {alert.alert_type.toUpperCase()}
                          </span>
                        </div>
                        
                        <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                          {alert.title}
                        </h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                          {alert.message}
                        </p>
                        
                        <div className="flex flex-wrap gap-4 text-xs text-gray-500 dark:text-gray-400">
                          {alert.symbol && (
                            <span>Symbol: {alert.symbol}</span>
                          )}
                          {alert.strategy_id && (
                            <span>Strategy: {alert.strategy_id}</span>
                          )}
                          <span>Triggered: {alert.trigger_count}x</span>
                          <span>Created: {new Date(alert.created_at).toLocaleString()}</span>
                          {alert.triggered_at && (
                            <span>Last Trigger: {new Date(alert.triggered_at).toLocaleString()}</span>
                          )}
                        </div>
                        
                        <div className="flex flex-wrap gap-2 mt-2">
                          {alert.channels.map((channel) => (
                            <span
                              key={channel}
                              className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs"
                            >
                              {channel}
                            </span>
                          ))}
                        </div>
                      </div>
                      
                      <div className="flex flex-col gap-2">
                        {alert.status === 'triggered' || alert.status === 'sent' ? (
                          <>
                            <button
                              onClick={() => handleAcknowledgeAlert(alert.alert_id)}
                              className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 text-sm flex items-center gap-1"
                              title="Acknowledge"
                            >
                              <FiCheckCircle />
                              Acknowledge
                            </button>
                            
                            <button
                              onClick={() => handleResolveAlert(alert.alert_id)}
                              className="px-3 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400 text-sm flex items-center gap-1"
                              title="Resolve"
                            >
                              <FiCheck />
                              Resolve
                            </button>
                            
                            <button
                              onClick={() => handleSnoozeAlert(alert.alert_id, 60)}
                              className="px-3 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400 text-sm flex items-center gap-1"
                              title="Snooze for 1 hour"
                            >
                              <FiClock />
                              Snooze 1h
                            </button>
                          </>
                        ) : alert.status === 'acknowledged' ? (
                          <button
                            onClick={() => handleResolveAlert(alert.alert_id)}
                            className="px-3 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400 text-sm flex items-center gap-1"
                            title="Resolve"
                          >
                            <FiCheck />
                            Resolve
                          </button>
                        ) : null}
                        
                        <button
                          onClick={() => handleDeleteAlert(alert.alert_id)}
                          className="px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 text-sm flex items-center gap-1"
                          title="Delete"
                        >
                          <FiX />
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Alert Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Create New Alert
                </h2>
                <button
                  onClick={() => {
                    setShowCreateForm(false);
                    setSubmitError(null);
                    setSubmitSuccess(false);
                  }}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <FiX className="text-2xl" />
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Alert Type Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Alert Type
                </label>
                <div className="grid grid-cols-4 gap-3">
                  {(['price', 'performance', 'risk', 'health'] as const).map((type) => (
                    <button
                      key={type}
                      onClick={() => setAlertType(type)}
                      className={`p-3 rounded-lg border-2 text-center capitalize ${
                        alertType === type
                          ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                          : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              {/* Dynamic Form Fields Based on Alert Type */}
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
                      placeholder="e.g., BTCUSDT"
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
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
                        placeholder="e.g., 50000"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  </div>
                </>
              )}

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
                      placeholder="e.g., strategy-123"
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
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
                      <option value="pnl">Profit/Loss</option>
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
                        <option value=">">Greater than</option>
                        <option value="<">Less than</option>
                        <option value=">=">Greater or equal</option>
                        <option value="<=">Less or equal</option>
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
                      />
                    </div>
                  </div>
                </>
              )}

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
                        Symbol (Optional)
                      </label>
                      <input
                        type="text"
                        value={formData.symbol}
                        onChange={(e) => setFormData({ ...formData, symbol: e.target.value })}
                        placeholder="e.g., BTCUSDT"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Position ID (Optional)
                      </label>
                      <input
                        type="text"
                        value={formData.position_id}
                        onChange={(e) => setFormData({ ...formData, position_id: e.target.value })}
                        placeholder="e.g., pos-123"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      />
                    </div>
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
                        <option value=">">Greater than</option>
                        <option value="<">Less than</option>
                        <option value=">=">Greater or equal</option>
                        <option value="<=">Less or equal</option>
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
                      />
                    </div>
                  </div>
                </>
              )}

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

                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Operator
                      </label>
                      <select
                        value={formData.operator}
                        onChange={(e) => setFormData({ ...formData, operator: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white"
                      >
                        <option value=">">Greater than</option>
                        <option value="<">Less than</option>
                        <option value=">=">Greater or equal</option>
                        <option value="<=">Less or equal</option>
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
                      />
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
                  <option value="info">Info</option>
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
                  {['email', 'telegram', 'discord', 'sms', 'webhook'].map((channel) => (
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
                        className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500"
                      />
                      <span className="text-gray-700 dark:text-gray-300 capitalize">{channel}</span>
                    </label>
                  ))}
                </div>
              </div>

              {submitError && (
                <div className="p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg">
                  <p className="text-red-700 dark:text-red-400">{submitError}</p>
                </div>
              )}

              {submitSuccess && (
                <div className="p-4 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg">
                  <p className="text-green-700 dark:text-green-400 flex items-center gap-2">
                    <FiCheck />
                    Alert created successfully!
                  </p>
                </div>
              )}
            </div>

            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowCreateForm(false);
                  setSubmitError(null);
                  setSubmitSuccess(false);
                }}
                className="px-4 py-2 bg-gray-200 dark:bg-slate-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-slate-600"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateAlert}
                disabled={submitting || submitSuccess}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {submitting ? (
                  <>
                    <FiRefreshCw className="animate-spin" />
                    Creating...
                  </>
                ) : submitSuccess ? (
                  <>
                    <FiCheck />
                    Created!
                  </>
                ) : (
                  <>
                    <FiPlus />
                    Create Alert
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

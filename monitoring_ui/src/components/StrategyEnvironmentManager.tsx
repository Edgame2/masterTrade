'use client';

import React, { useState, useEffect } from 'react';
import { FiSettings, FiCheckCircle, FiXCircle, FiAlertTriangle, FiLoader } from 'react-icons/fi';

interface StrategyEnvironmentConfig {
  strategy_id: number;
  environment: 'testnet' | 'production';
  max_position_size?: number;
  max_daily_trades?: number;
  risk_multiplier: number;
  enabled: boolean;
  updated_at?: string;
}

interface ExchangeStatus {
  testnet: {
    connected: boolean;
    balance?: Record<string, number>;
    last_updated?: string;
  };
  production: {
    connected: boolean;
    balance?: Record<string, number>;
    last_updated?: string;
  };
}

const StrategyEnvironmentManager: React.FC = () => {
  const [configs, setConfigs] = useState<StrategyEnvironmentConfig[]>([]);
  const [exchangeStatus, setExchangeStatus] = useState<ExchangeStatus | null>(null);
  const [activeTab, setActiveTab] = useState<'configurations' | 'exchange-status'>('configurations');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Form state for new/edit strategy configuration
  const [editingStrategy, setEditingStrategy] = useState<number | null>(null);
  const [formData, setFormData] = useState<Partial<StrategyEnvironmentConfig>>({
    environment: 'testnet',
    risk_multiplier: 1.0,
    enabled: true,
  });

  const API_BASE = process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8080';

  useEffect(() => {
    fetchConfigurations();
    fetchExchangeStatus();
    
    // Poll exchange status every 30 seconds
    const interval = setInterval(fetchExchangeStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchConfigurations = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/strategy-environments`);
      if (response.ok) {
        const data = await response.json();
        setConfigs(data);
      } else {
        setError('Failed to fetch strategy configurations');
      }
    } catch (err) {
      setError('Network error fetching configurations');
    } finally {
      setLoading(false);
    }
  };

  const fetchExchangeStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/exchange-environments/status`);
      if (response.ok) {
        const data = await response.json();
        setExchangeStatus(data);
      }
    } catch (err) {
      console.error('Failed to fetch exchange status:', err);
    }
  };

  const handleSaveConfiguration = async (strategyId: number) => {
    setSaving(strategyId);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/strategy-environments/${strategyId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (response.ok) {
        await fetchConfigurations();
        setEditingStrategy(null);
        setFormData({
          environment: 'testnet',
          risk_multiplier: 1.0,
          enabled: true,
        });
      } else {
        setError('Failed to save configuration');
      }
    } catch (err) {
      setError('Network error saving configuration');
    } finally {
      setSaving(null);
    }
  };

  const handleEditStrategy = (config: StrategyEnvironmentConfig) => {
    setEditingStrategy(config.strategy_id);
    setFormData(config);
  };

  const getEnvironmentBadge = (environment: string) => {
    const baseClasses = "px-2 py-1 rounded-full text-xs font-medium";
    const colorClasses = environment === 'production' 
      ? 'bg-red-100 text-red-800' 
      : 'bg-blue-100 text-blue-800';
    
    return (
      <span className={`${baseClasses} ${colorClasses}`}>
        {environment.toUpperCase()}
      </span>
    );
  };

  const getConnectionStatus = (environment: 'testnet' | 'production') => {
    if (!exchangeStatus) return null;
    
    const status = exchangeStatus[environment];
    return status.connected ? (
      <div className="flex items-center gap-2 text-green-600">
        <FiCheckCircle size={16} />
        Connected
      </div>
    ) : (
      <div className="flex items-center gap-2 text-red-600">
        <FiXCircle size={16} />
        Disconnected
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <FiLoader className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex items-center">
            <FiAlertTriangle className="h-4 w-4 text-red-400 mr-2" />
            <span className="text-red-800">{error}</span>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('configurations')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'configurations'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Strategy Configurations
          </button>
          <button
            onClick={() => setActiveTab('exchange-status')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'exchange-status'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Exchange Status
          </button>
        </nav>
      </div>

      {/* Configurations Tab */}
      {activeTab === 'configurations' && (
        <div className="space-y-6">
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-medium text-gray-900 flex items-center gap-2">
                <FiSettings size={20} />
                Strategy Environment Configuration
              </h3>
            </div>
            <div className="p-6 space-y-6">
              {/* Configuration Form */}
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6">
                <h4 className="text-lg font-medium mb-4">
                  {editingStrategy ? `Edit Strategy ${editingStrategy}` : 'Add New Strategy Configuration'}
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Strategy ID
                    </label>
                    <input
                      type="number"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      value={formData.strategy_id || ''}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
                        setFormData({...formData, strategy_id: parseInt(e.target.value)})
                      }
                      disabled={editingStrategy !== null}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Environment
                    </label>
                    <select
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      value={formData.environment}
                      onChange={(e: React.ChangeEvent<HTMLSelectElement>) => 
                        setFormData({...formData, environment: e.target.value as 'testnet' | 'production'})
                      }
                    >
                      <option value="testnet">Testnet</option>
                      <option value="production">Production</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Max Position Size
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      value={formData.max_position_size || ''}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
                        setFormData({...formData, max_position_size: parseFloat(e.target.value)})
                      }
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Max Daily Trades
                    </label>
                    <input
                      type="number"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      value={formData.max_daily_trades || ''}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
                        setFormData({...formData, max_daily_trades: parseInt(e.target.value)})
                      }
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Risk Multiplier
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      value={formData.risk_multiplier || 1.0}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
                        setFormData({...formData, risk_multiplier: parseFloat(e.target.value)})
                      }
                    />
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="enabled"
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                      checked={formData.enabled || false}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
                        setFormData({...formData, enabled: e.target.checked})
                      }
                    />
                    <label htmlFor="enabled" className="ml-2 block text-sm text-gray-900">
                      Enabled
                    </label>
                  </div>
                </div>
                <div className="flex gap-2 mt-6">
                  <button
                    onClick={() => handleSaveConfiguration(formData.strategy_id!)}
                    disabled={!formData.strategy_id || saving === formData.strategy_id}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 flex items-center"
                  >
                    {saving === formData.strategy_id && <FiLoader className="mr-2 h-4 w-4 animate-spin" />}
                    {editingStrategy ? 'Update' : 'Add'} Configuration
                  </button>
                  {editingStrategy && (
                    <button
                      onClick={() => {
                        setEditingStrategy(null);
                        setFormData({environment: 'testnet', risk_multiplier: 1.0, enabled: true});
                      }}
                      className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              {/* Existing Configurations */}
              <div className="space-y-4">
                {configs.map((config) => (
                  <div key={config.strategy_id} className="bg-gray-50 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-2">
                        <div className="flex items-center gap-3">
                          <h4 className="font-semibold text-gray-900">Strategy {config.strategy_id}</h4>
                          {getEnvironmentBadge(config.environment)}
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            config.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                          }`}>
                            {config.enabled ? 'Active' : 'Inactive'}
                          </span>
                        </div>
                        <div className="text-sm text-gray-600 space-y-1">
                          <div>Max Position: {config.max_position_size || 'Unlimited'}</div>
                          <div>Max Daily Trades: {config.max_daily_trades || 'Unlimited'}</div>
                          <div>Risk Multiplier: {config.risk_multiplier}</div>
                          {config.updated_at && (
                            <div>Updated: {new Date(config.updated_at).toLocaleString()}</div>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => handleEditStrategy(config)}
                        className="px-3 py-1 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Exchange Status Tab */}
      {activeTab === 'exchange-status' && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">Exchange Connection Status</h3>
          </div>
          <div className="p-6">
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-lg font-medium text-gray-900">Testnet</h4>
                  {getConnectionStatus('testnet')}
                </div>
                {exchangeStatus?.testnet?.balance && (
                  <div>
                    <h5 className="font-medium mb-2 text-gray-700">Balance:</h5>
                    <div className="space-y-1 text-sm">
                      {Object.entries(exchangeStatus.testnet.balance).map(([asset, amount]) => (
                        <div key={asset} className="flex justify-between">
                          <span className="text-gray-600">{asset}:</span>
                          <span className="font-medium">{amount}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-lg font-medium text-gray-900">Production</h4>
                  {getConnectionStatus('production')}
                </div>
                {exchangeStatus?.production?.balance && (
                  <div>
                    <h5 className="font-medium mb-2 text-gray-700">Balance:</h5>
                    <div className="space-y-1 text-sm">
                      {Object.entries(exchangeStatus.production.balance).map(([asset, amount]) => (
                        <div key={asset} className="flex justify-between">
                          <span className="text-gray-600">{asset}:</span>
                          <span className="font-medium">{amount}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StrategyEnvironmentManager;
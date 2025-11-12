'use client';

import React, { useState, useEffect } from 'react';
import { 
  FiX, FiSave, FiAlertCircle, FiCheckCircle, FiInfo,
  FiSettings, FiZap, FiClock, FiTrendingUp
} from 'react-icons/fi';

/**
 * Data source interface matching the parent component
 */
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

/**
 * Modal props
 */
interface DataSourceConfigModalProps {
  isOpen: boolean;
  source: DataSource | null;
  onClose: () => void;
  onSave: () => void;
}

/**
 * Rate limit configuration form state
 */
interface RateLimitConfig {
  max_requests_per_second: number;
  backoff_multiplier: number;
  max_backoff: number;
}

/**
 * Data Source Configuration Modal Component
 * 
 * Provides UI for configuring data source settings including:
 * - Rate limiting (requests per second, backoff multiplier, max backoff)
 * - API key status display (read-only)
 * - Collector statistics and health metrics
 * 
 * API Integration:
 * - PUT /collectors/{name}/rate-limit - Update rate limit configuration
 */
export default function DataSourceConfigModal({ 
  isOpen, 
  source, 
  onClose, 
  onSave 
}: DataSourceConfigModalProps) {
  const [config, setConfig] = useState<RateLimitConfig>({
    max_requests_per_second: 1.0,
    backoff_multiplier: 2.0,
    max_backoff: 16.0
  });
  
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Initialize config from source when modal opens
  useEffect(() => {
    if (source && isOpen) {
      setConfig({
        max_requests_per_second: source.rate_limiter?.current_rate || source.configured_rate_limit || 1.0,
        backoff_multiplier: source.rate_limiter?.backoff_multiplier || 2.0,
        max_backoff: 16.0 // Default, not exposed in source yet
      });
      setError(null);
      setSuccess(false);
      setValidationErrors({});
    }
  }, [source, isOpen]);

  // Don't render if not open or no source
  if (!isOpen || !source) {
    return null;
  }

  /**
   * Validate form inputs
   */
  const validateConfig = (): boolean => {
    const errors: Record<string, string> = {};

    if (config.max_requests_per_second <= 0) {
      errors.max_requests_per_second = 'Must be greater than 0';
    }
    if (config.max_requests_per_second > 100) {
      errors.max_requests_per_second = 'Recommended maximum is 100 req/s';
    }

    if (config.backoff_multiplier < 1.0) {
      errors.backoff_multiplier = 'Must be >= 1.0';
    }
    if (config.backoff_multiplier > 10) {
      errors.backoff_multiplier = 'Recommended maximum is 10';
    }

    if (config.max_backoff < 1.0) {
      errors.max_backoff = 'Must be >= 1.0';
    }
    if (config.max_backoff > 3600) {
      errors.max_backoff = 'Recommended maximum is 3600 seconds (1 hour)';
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  /**
   * Handle form submission
   */
  const handleSave = async () => {
    if (!validateConfig()) {
      return;
    }

    setIsSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_MARKET_DATA_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/collectors/${source.name}/rate-limit`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Failed to update configuration');
      }

      setSuccess(true);
      
      // Call parent onSave callback to refresh data
      setTimeout(() => {
        onSave();
        onClose();
      }, 1500);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration');
    } finally {
      setIsSaving(false);
    }
  };

  /**
   * Handle input changes with validation
   */
  const handleInputChange = (field: keyof RateLimitConfig, value: string) => {
    const numValue = parseFloat(value);
    if (isNaN(numValue)) return;

    setConfig(prev => ({ ...prev, [field]: numValue }));
    
    // Clear validation error for this field
    if (validationErrors[field]) {
      setValidationErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  /**
   * Get collector type label
   */
  const getTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
      'onchain': 'On-Chain',
      'social': 'Social Media',
      'market_data': 'Market Data',
      'sentiment': 'Sentiment'
    };
    return labels[type] || type;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-slate-800 rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <FiSettings className="w-6 h-6 text-blue-400" />
            <div>
              <h2 className="text-xl font-bold text-white">
                Configure {source.name}
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                {getTypeLabel(source.type)} Data Source
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
            disabled={isSaving}
          >
            <FiX className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Success/Error Messages */}
          {success && (
            <div className="flex items-center gap-2 p-4 bg-green-500/20 border border-green-500/30 rounded-lg">
              <FiCheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-400">Configuration saved successfully!</span>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 p-4 bg-red-500/20 border border-red-500/30 rounded-lg">
              <FiAlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-red-400">{error}</span>
            </div>
          )}

          {/* Current Statistics */}
          <div className="bg-slate-700/50 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <FiInfo className="w-4 h-4" />
              Current Statistics
            </h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-slate-400">Status:</span>
                <span className={`ml-2 font-medium ${
                  source.status === 'healthy' ? 'text-green-400' :
                  source.status === 'degraded' ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {source.status}
                </span>
              </div>
              <div>
                <span className="text-slate-400">Success Rate:</span>
                <span className="ml-2 font-medium text-white">
                  {source.success_rate.toFixed(1)}%
                </span>
              </div>
              {source.rate_limiter && (
                <>
                  <div>
                    <span className="text-slate-400">Total Requests:</span>
                    <span className="ml-2 font-medium text-white">
                      {source.rate_limiter.total_requests.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400">Throttles:</span>
                    <span className="ml-2 font-medium text-yellow-400">
                      {source.rate_limiter.total_throttles.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400">Backoffs:</span>
                    <span className="ml-2 font-medium text-orange-400">
                      {source.rate_limiter.total_backoffs.toLocaleString()}
                    </span>
                  </div>
                </>
              )}
              {source.circuit_breaker && (
                <div>
                  <span className="text-slate-400">Circuit Breaker:</span>
                  <span className={`ml-2 font-medium ${
                    source.circuit_breaker.state === 'closed' ? 'text-green-400' :
                    source.circuit_breaker.state === 'half_open' ? 'text-yellow-400' :
                    'text-red-400'
                  }`}>
                    {source.circuit_breaker.state}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Rate Limit Configuration */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
              <FiZap className="w-4 h-4" />
              Rate Limit Configuration
            </h3>

            {/* Max Requests Per Second */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Max Requests Per Second
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                value={config.max_requests_per_second}
                onChange={(e) => handleInputChange('max_requests_per_second', e.target.value)}
                className={`w-full px-4 py-2 bg-slate-700 border rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  validationErrors.max_requests_per_second 
                    ? 'border-red-500' 
                    : 'border-slate-600'
                }`}
                disabled={isSaving}
              />
              {validationErrors.max_requests_per_second && (
                <p className="mt-1 text-sm text-red-400">
                  {validationErrors.max_requests_per_second}
                </p>
              )}
              <p className="mt-1 text-xs text-slate-400">
                Maximum API requests per second. Lower values reduce API costs and avoid rate limits.
              </p>
            </div>

            {/* Backoff Multiplier */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                <FiTrendingUp className="inline w-4 h-4 mr-1" />
                Backoff Multiplier
              </label>
              <input
                type="number"
                step="0.1"
                min="1.0"
                max="10"
                value={config.backoff_multiplier}
                onChange={(e) => handleInputChange('backoff_multiplier', e.target.value)}
                className={`w-full px-4 py-2 bg-slate-700 border rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  validationErrors.backoff_multiplier 
                    ? 'border-red-500' 
                    : 'border-slate-600'
                }`}
                disabled={isSaving}
              />
              {validationErrors.backoff_multiplier && (
                <p className="mt-1 text-sm text-red-400">
                  {validationErrors.backoff_multiplier}
                </p>
              )}
              <p className="mt-1 text-xs text-slate-400">
                Exponential backoff multiplier when rate limited. Higher values = longer waits between retries.
              </p>
            </div>

            {/* Max Backoff */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                <FiClock className="inline w-4 h-4 mr-1" />
                Max Backoff (seconds)
              </label>
              <input
                type="number"
                step="1"
                min="1"
                max="3600"
                value={config.max_backoff}
                onChange={(e) => handleInputChange('max_backoff', e.target.value)}
                className={`w-full px-4 py-2 bg-slate-700 border rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  validationErrors.max_backoff 
                    ? 'border-red-500' 
                    : 'border-slate-600'
                }`}
                disabled={isSaving}
              />
              {validationErrors.max_backoff && (
                <p className="mt-1 text-sm text-red-400">
                  {validationErrors.max_backoff}
                </p>
              )}
              <p className="mt-1 text-xs text-slate-400">
                Maximum wait time between retry attempts. Prevents excessive delays.
              </p>
            </div>
          </div>

          {/* Info Box */}
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
            <div className="flex gap-2">
              <FiInfo className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-300">
                <p className="font-medium mb-1">Configuration Tips:</p>
                <ul className="space-y-1 text-xs text-blue-200">
                  <li>• Lower rate limits reduce API costs but may delay data collection</li>
                  <li>• Backoff multiplier of 2.0 is recommended for most APIs</li>
                  <li>• Max backoff prevents indefinite waiting on persistent failures</li>
                  <li>• Changes take effect immediately for new requests</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-300 hover:text-white transition-colors"
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <FiSave className="w-4 h-4" />
                Save Configuration
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { FiAlertCircle, FiCheckCircle, FiSave, FiSettings, FiSliders, FiTarget } from 'react-icons/fi';
import LoadingSpinner from './LoadingSpinner';

interface RiskLimitsResponse {
  position_limits?: {
    max_single_position_percent?: number;
  };
  portfolio_limits?: {
    max_portfolio_risk_percent?: number;
    max_leverage_ratio?: number;
    max_drawdown_percent?: number;
    max_var_percent?: number;
  };
}

interface StrategyGenerationConfig {
  population_size: number;
  generations: number;
  mutation_rate: number;
  crossover_rate: number;
}

const DEFAULT_GENERATION_CONFIG: StrategyGenerationConfig = {
  population_size: 200,
  generations: 50,
  mutation_rate: 0.1,
  crossover_rate: 0.8,
};

const SystemSettingsPanel = () => {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
  const riskApiBase = process.env.NEXT_PUBLIC_RISK_API_URL || apiBase;
  const strategyApiBase = process.env.NEXT_PUBLIC_STRATEGY_API_URL || apiBase;

  const [initializing, setInitializing] = useState<boolean>(true);
  const [loadingSection, setLoadingSection] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusVariant, setStatusVariant] = useState<'success' | 'error' | 'info'>('info');

  const [tradeLimits, setTradeLimits] = useState({
    maxSinglePositionPercent: '',
    maxPortfolioVarPercent: '',
    maxDrawdownPercent: '',
    maxLeverageRatio: '',
  });
  const [dailyLossCap, setDailyLossCap] = useState<string>('');
  const [activeStrategyLimit, setActiveStrategyLimit] = useState<string>('');
  const [generationConfig, setGenerationConfig] = useState<StrategyGenerationConfig>(DEFAULT_GENERATION_CONFIG);

  const showStatus = (message: string, variant: 'success' | 'error' | 'info' = 'info') => {
    setStatusMessage(message);
    setStatusVariant(variant);
    window.setTimeout(() => setStatusMessage(null), 8000);
  };

  const parseNumber = (value: string) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : undefined;
  };

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const [riskResponse, strategyActiveResponse, generationResponse] = await Promise.all([
          fetch(`${riskApiBase}/config/risk-limits`).catch(() => null),
          fetch(`${strategyApiBase}/api/v1/strategy/activation/max-active`).catch(() => null),
          fetch(`${strategyApiBase}/api/v1/strategy/generation/config`).catch(() => null),
        ]);

        if (riskResponse && riskResponse.ok) {
          const riskPayload: RiskLimitsResponse = await riskResponse.json();
          setTradeLimits({
            maxSinglePositionPercent: riskPayload.position_limits?.max_single_position_percent?.toString() ?? '',
            maxPortfolioVarPercent: riskPayload.portfolio_limits?.max_var_percent?.toString() ?? '',
            maxDrawdownPercent: riskPayload.portfolio_limits?.max_drawdown_percent?.toString() ?? '',
            maxLeverageRatio: riskPayload.portfolio_limits?.max_leverage_ratio?.toString() ?? '',
          });
          setDailyLossCap(riskPayload.portfolio_limits?.max_drawdown_percent?.toString() ?? '');
        }

        if (strategyActiveResponse && strategyActiveResponse.ok) {
          const activationPayload = await strategyActiveResponse.json();
          const limit = activationPayload?.max_active_strategies ?? activationPayload?.new_value;
          if (limit !== undefined) {
            setActiveStrategyLimit(String(limit));
          }
        }

        if (generationResponse && generationResponse.ok) {
          const generationPayload = await generationResponse.json();
          setGenerationConfig({
            population_size: Number(generationPayload.population_size ?? DEFAULT_GENERATION_CONFIG.population_size),
            generations: Number(generationPayload.generations ?? DEFAULT_GENERATION_CONFIG.generations),
            mutation_rate: Number(generationPayload.mutation_rate ?? DEFAULT_GENERATION_CONFIG.mutation_rate),
            crossover_rate: Number(generationPayload.crossover_rate ?? DEFAULT_GENERATION_CONFIG.crossover_rate),
          });
        } else {
          const stored = window.localStorage.getItem('mastertrade_generation_config');
          if (stored) {
            try {
              const parsed = JSON.parse(stored);
              setGenerationConfig({
                population_size: Number(parsed.population_size ?? DEFAULT_GENERATION_CONFIG.population_size),
                generations: Number(parsed.generations ?? DEFAULT_GENERATION_CONFIG.generations),
                mutation_rate: Number(parsed.mutation_rate ?? DEFAULT_GENERATION_CONFIG.mutation_rate),
                crossover_rate: Number(parsed.crossover_rate ?? DEFAULT_GENERATION_CONFIG.crossover_rate),
              });
            } catch (err) {
              console.warn('Failed to parse cached generation config', err);
            }
          }
        }
      } catch (err) {
        console.error('Error loading system settings', err);
        showStatus('Unable to load settings from services. Check connectivity.', 'error');
      } finally {
        setInitializing(false);
      }
    };

    loadSettings();
  }, [riskApiBase, strategyApiBase]);

  const handleSaveTradeLimits = async (event: FormEvent) => {
    event.preventDefault();
    setLoadingSection('trade');
    try {
      const payload = {
        max_single_position: parseNumber(tradeLimits.maxSinglePositionPercent),
        max_var_percent: parseNumber(tradeLimits.maxPortfolioVarPercent),
        max_drawdown_percent: parseNumber(tradeLimits.maxDrawdownPercent),
        max_leverage: parseNumber(tradeLimits.maxLeverageRatio),
      };

      const response = await fetch(`${riskApiBase}/config/risk-limits`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error('Risk manager rejected the update');
      }

      showStatus('Risk limits updated successfully.', 'success');
    } catch (err) {
      console.error('Error saving risk limits', err);
      showStatus('Failed to update risk limits. Verify the risk service is reachable.', 'error');
    } finally {
      setLoadingSection(null);
    }
  };

  const handleSaveDailyLossCap = async (event: FormEvent) => {
    event.preventDefault();
    setLoadingSection('loss');
    try {
      const payload = {
        max_drawdown_percent: parseNumber(dailyLossCap),
      };
      const response = await fetch(`${riskApiBase}/config/risk-limits`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error('Risk manager rejected the update');
      }
      showStatus('Daily loss cap updated.', 'success');
    } catch (err) {
      console.error('Error saving daily loss cap', err);
      showStatus('Unable to update the daily loss cap.', 'error');
    } finally {
      setLoadingSection(null);
    }
  };

  const handleSaveStrategyLimit = async (event: FormEvent) => {
    event.preventDefault();
    setLoadingSection('active-strategy');
    try {
      const value = parseNumber(activeStrategyLimit);
      if (!value || value < 1) {
        throw new Error('Max active strategies must be >= 1');
      }
      const response = await fetch(
        `${strategyApiBase}/api/v1/strategy/activation/max-active?max_active=${encodeURIComponent(value)}`,
        {
          method: 'PUT',
        }
      );
      if (!response.ok) {
        throw new Error('Strategy service rejected the update');
      }
      showStatus('Active strategy limit saved.', 'success');
    } catch (err) {
      console.error('Error saving strategy limit', err);
      showStatus('Failed to update max active strategies.', 'error');
    } finally {
      setLoadingSection(null);
    }
  };

  const handleSaveGenerationConfig = async (event: FormEvent) => {
    event.preventDefault();
    setLoadingSection('generation');
    try {
      const response = await fetch(`${strategyApiBase}/api/v1/strategy/generation/config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          population_size: generationConfig.population_size,
          generations: generationConfig.generations,
          mutation_rate: generationConfig.mutation_rate,
          crossover_rate: generationConfig.crossover_rate,
        }),
      });

      if (!response.ok) {
        if (response.status === 404) {
          // Persist locally if the strategy API does not expose configuration persistence yet.
          window.localStorage.setItem('mastertrade_generation_config', JSON.stringify(generationConfig));
          showStatus('Strategy generation parameters cached locally (service endpoint unavailable).', 'info');
        } else {
          throw new Error('Strategy service rejected the update');
        }
      } else {
        showStatus('Strategy generation parameters updated.', 'success');
      }
    } catch (err) {
      console.error('Error saving generation config', err);
      showStatus('Failed to persist generation parameters.', 'error');
    } finally {
      setLoadingSection(null);
    }
  };

  const isSaving = useMemo(() => loadingSection !== null, [loadingSection]);

  if (initializing) {
    return (
      <div className="flex h-80 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold">System Controls</h2>
          <p className="text-gray-600 dark:text-gray-400">
            Adjust live risk limits, activation thresholds, and automated strategy generation parameters.
          </p>
        </div>
        {statusMessage && (
          <div
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm ${
              statusVariant === 'success'
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200'
                : statusVariant === 'error'
                ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200'
                : 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200'
            }`}
          >
            {statusVariant === 'success' ? (
              <FiCheckCircle className="h-4 w-4" />
            ) : statusVariant === 'error' ? (
              <FiAlertCircle className="h-4 w-4" />
            ) : (
              <FiSettings className="h-4 w-4" />
            )}
            <span>{statusMessage}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <form onSubmit={handleSaveTradeLimits} className="space-y-4 rounded-lg bg-white p-6 shadow dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Trade Limits</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Configure exposure caps across positions and portfolio risk.
              </p>
            </div>
            <FiSliders className="h-5 w-5 text-sky-500" />
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Max Single Position %
              <input
                type="number"
                step="0.1"
                min="0"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={tradeLimits.maxSinglePositionPercent}
                onChange={(event) =>
                  setTradeLimits((prev) => ({ ...prev, maxSinglePositionPercent: event.target.value }))
                }
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Max Portfolio VaR %
              <input
                type="number"
                step="0.1"
                min="0"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={tradeLimits.maxPortfolioVarPercent}
                onChange={(event) =>
                  setTradeLimits((prev) => ({ ...prev, maxPortfolioVarPercent: event.target.value }))
                }
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Max Drawdown %
              <input
                type="number"
                step="0.1"
                min="0"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={tradeLimits.maxDrawdownPercent}
                onChange={(event) =>
                  setTradeLimits((prev) => ({ ...prev, maxDrawdownPercent: event.target.value }))
                }
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Max Leverage Ratio
              <input
                type="number"
                step="0.1"
                min="0"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={tradeLimits.maxLeverageRatio}
                onChange={(event) =>
                  setTradeLimits((prev) => ({ ...prev, maxLeverageRatio: event.target.value }))
                }
              />
            </label>
          </div>
          <button
            type="submit"
            className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSaving && loadingSection === 'trade'}
          >
            <FiSave className="h-4 w-4" /> Save Limits
          </button>
        </form>

        <form onSubmit={handleSaveDailyLossCap} className="space-y-4 rounded-lg bg-white p-6 shadow dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Daily Loss Cap</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Hard stop threshold for total daily losses (mapped to risk drawdown control).
              </p>
            </div>
            <FiTarget className="h-5 w-5 text-rose-500" />
          </div>
          <label className="text-sm text-gray-600 dark:text-gray-300">
            Daily Loss Cap %
            <input
              type="number"
              step="0.1"
              min="0"
              className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              value={dailyLossCap}
              onChange={(event) => setDailyLossCap(event.target.value)}
            />
          </label>
          <button
            type="submit"
            className="flex items-center gap-2 rounded-md bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSaving && loadingSection === 'loss'}
          >
            <FiSave className="h-4 w-4" /> Save Loss Cap
          </button>
        </form>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <form onSubmit={handleSaveStrategyLimit} className="space-y-4 rounded-lg bg-white p-6 shadow dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Active Strategy Limit</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Control how many strategies are allowed to run live concurrently.
              </p>
            </div>
            <FiSettings className="h-5 w-5 text-indigo-500" />
          </div>
          <label className="text-sm text-gray-600 dark:text-gray-300">
            Max Active Strategies
            <input
              type="number"
              min="1"
              className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
              value={activeStrategyLimit}
              onChange={(event) => setActiveStrategyLimit(event.target.value)}
            />
          </label>
          <button
            type="submit"
            className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSaving && loadingSection === 'active-strategy'}
          >
            <FiSave className="h-4 w-4" /> Save Strategy Limit
          </button>
        </form>

        <form onSubmit={handleSaveGenerationConfig} className="space-y-4 rounded-lg bg-white p-6 shadow dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Strategy Generation Parameters</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Tune the genetic programming and reinforcement learning pipeline driving strategy discovery.
              </p>
            </div>
            <FiSettings className="h-5 w-5 text-emerald-500" />
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Population Size
              <input
                type="number"
                min="50"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={generationConfig.population_size}
                onChange={(event) =>
                  setGenerationConfig((prev) => ({ ...prev, population_size: Number(event.target.value) }))
                }
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Generations
              <input
                type="number"
                min="10"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={generationConfig.generations}
                onChange={(event) =>
                  setGenerationConfig((prev) => ({ ...prev, generations: Number(event.target.value) }))
                }
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Mutation Rate
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={generationConfig.mutation_rate}
                onChange={(event) =>
                  setGenerationConfig((prev) => ({ ...prev, mutation_rate: Number(event.target.value) }))
                }
              />
            </label>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Crossover Rate
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                className="mt-1 w-full rounded-md border border-gray-300 bg-white p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                value={generationConfig.crossover_rate}
                onChange={(event) =>
                  setGenerationConfig((prev) => ({ ...prev, crossover_rate: Number(event.target.value) }))
                }
              />
            </label>
          </div>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <button
              type="submit"
              className="flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isSaving && loadingSection === 'generation'}
            >
              <FiSave className="h-4 w-4" /> Save Generation Parameters
            </button>
            <button
              type="button"
              onClick={() => setGenerationConfig(DEFAULT_GENERATION_CONFIG)}
              className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-300 dark:hover:text-gray-100"
            >
              Reset to defaults
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default SystemSettingsPanel;

'use client';

import { useState, useEffect } from 'react';
import { FiPlay, FiRefreshCw, FiCheckCircle, FiXCircle, FiClock, FiTrendingUp, FiAlertTriangle } from 'react-icons/fi';
import { io, Socket } from 'socket.io-client';

interface BacktestResult {
  strategy_id: string;
  strategy_name: string;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_return: number;
  cagr: number;
  profit_factor: number;
  total_trades: number;
  avg_monthly_return: number;
  monthly_returns: number[];
  passed_criteria: boolean;
  backtest_duration_days: number;
  created_at: string;
}

interface GenerationProgress {
  job_id: string;
  status: 'pending' | 'generating' | 'backtesting' | 'completed' | 'failed' | 'cancelled';
  total_strategies: number;
  strategies_generated: number;
  strategies_backtested: number;
  strategies_passed: number;
  strategies_failed: number;
  current_strategy?: string;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  estimated_completion?: string;
}

interface GenerationResults {
  job_id: string;
  status: string;
  total_strategies: number;
  strategies_passed: number;
  strategies_failed: number;
  backtest_summaries: BacktestResult[];
  started_at: string;
  completed_at?: string;
}

export default function StrategyGenerator() {
  const [numStrategies, setNumStrategies] = useState<number>(10);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<GenerationProgress | null>(null);
  const [results, setResults] = useState<GenerationResults | null>(null);
  const [socket, setSocket] = useState<Socket | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

  // Setup Socket.IO connection
  useEffect(() => {
    const socketUrl = process.env.NEXT_PUBLIC_WS_URL || 'http://localhost:8080';
    const newSocket = io(socketUrl, {
      transports: ['websocket', 'polling'],
    });

    newSocket.on('connect', () => {
      console.log('Socket.IO connected for strategy generation');
    });

    newSocket.on('generation_progress', (data: GenerationProgress) => {
      console.log('Progress update:', data);
      if (data.job_id === currentJobId) {
        setProgress(data);
        
        // If completed, fetch full results
        if (data.status === 'completed') {
          fetchResults(data.job_id);
        }
      }
    });

    newSocket.on('disconnect', () => {
      console.log('Socket.IO disconnected');
    });

    setSocket(newSocket);

    return () => {
      newSocket.disconnect();
    };
  }, [currentJobId]);

  const startGeneration = async () => {
    if (numStrategies < 1 || numStrategies > 1000) {
      setError('Number of strategies must be between 1 and 1000');
      return;
    }

    setIsGenerating(true);
    setError(null);
    setProgress(null);
    setResults(null);

    try {
      const response = await fetch(`${apiUrl}/api/strategies/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          num_strategies: numStrategies,
          config: {},
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to start generation: ${response.statusText}`);
      }

      const data = await response.json();
      setCurrentJobId(data.job_id);
      
      // Start polling for progress
      pollProgress(data.job_id);
    } catch (err: any) {
      setError(err.message);
      setIsGenerating(false);
    }
  };

  const pollProgress = async (jobId: string) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`${apiUrl}/api/strategies/jobs/${jobId}/progress`);
        
        if (response.ok) {
          const progressData: GenerationProgress = await response.json();
          setProgress(progressData);

          if (progressData.status === 'completed' || progressData.status === 'failed' || progressData.status === 'cancelled') {
            clearInterval(pollInterval);
            setIsGenerating(false);
            
            if (progressData.status === 'completed') {
              fetchResults(jobId);
            }
          }
        }
      } catch (err) {
        console.error('Error polling progress:', err);
      }
    }, 2000); // Poll every 2 seconds

    // Stop polling after 30 minutes
    setTimeout(() => clearInterval(pollInterval), 30 * 60 * 1000);
  };

  const fetchResults = async (jobId: string) => {
    try {
      const response = await fetch(`${apiUrl}/api/strategies/jobs/${jobId}/results`);
      
      if (response.ok) {
        const resultsData: GenerationResults = await response.json();
        setResults(resultsData);
      }
    } catch (err) {
      console.error('Error fetching results:', err);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <FiClock className="w-5 h-5 text-gray-500 animate-pulse" />;
      case 'generating':
        return <FiRefreshCw className="w-5 h-5 text-blue-500 animate-spin" />;
      case 'backtesting':
        return <FiRefreshCw className="w-5 h-5 text-purple-500 animate-spin" />;
      case 'completed':
        return <FiCheckCircle className="w-5 h-5 text-green-500" />;
      case 'failed':
        return <FiXCircle className="w-5 h-5 text-red-500" />;
      case 'cancelled':
        return <FiXCircle className="w-5 h-5 text-gray-500" />;
      default:
        return null;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return 'bg-gray-100 text-gray-800';
      case 'generating':
        return 'bg-blue-100 text-blue-800';
      case 'backtesting':
        return 'bg-purple-100 text-purple-800';
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'cancelled':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDuration = (startedAt?: string, completedAt?: string) => {
    if (!startedAt) return 'N/A';
    
    const start = new Date(startedAt);
    const end = completedAt ? new Date(completedAt) : new Date();
    const durationMs = end.getTime() - start.getTime();
    
    const minutes = Math.floor(durationMs / 60000);
    const seconds = Math.floor((durationMs % 60000) / 1000);
    
    return `${minutes}m ${seconds}s`;
  };

  return (
    <div className="space-y-6">
      {/* Generation Form */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center">
              <FiTrendingUp className="mr-3 text-primary-600" />
              Strategy Generator
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Generate and backtest new trading strategies automatically
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label htmlFor="numStrategies" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Number of Strategies
            </label>
            <input
              type="number"
              id="numStrategies"
              min="1"
              max="1000"
              value={numStrategies}
              onChange={(e) => setNumStrategies(parseInt(e.target.value) || 1)}
              disabled={isGenerating}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent dark:bg-slate-700 dark:text-white disabled:opacity-50"
              placeholder="Enter number (1-1000)"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Each strategy will be automatically generated and backtested with 90 days of historical data
            </p>
          </div>

          {error && (
            <div className="flex items-center p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <FiAlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 mr-3" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          <button
            onClick={startGeneration}
            disabled={isGenerating}
            className="w-full flex items-center justify-center space-x-2 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isGenerating ? (
              <>
                <FiRefreshCw className="animate-spin" />
                <span>Generating...</span>
              </>
            ) : (
              <>
                <FiPlay />
                <span>Start Generation</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Progress Display */}
      {progress && (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center">
              {getStatusIcon(progress.status)}
              <span className="ml-2">Generation Progress</span>
            </h3>
            <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(progress.status)}`}>
              {progress.status.toUpperCase()}
            </span>
          </div>

          {/* Progress Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-50 dark:bg-slate-700 rounded-lg p-4">
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Total</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{progress.total_strategies}</p>
            </div>
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
              <p className="text-xs text-blue-600 dark:text-blue-400 mb-1">Generated</p>
              <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{progress.strategies_generated}</p>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-xs text-purple-600 dark:text-purple-400 mb-1">Backtested</p>
              <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">{progress.strategies_backtested}</p>
            </div>
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
              <p className="text-xs text-green-600 dark:text-green-400 mb-1">Passed</p>
              <p className="text-2xl font-bold text-green-600 dark:text-green-400">{progress.strategies_passed}</p>
            </div>
          </div>

          {/* Progress Bars */}
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-gray-400">Generation Progress</span>
                <span className="text-gray-900 dark:text-white font-medium">
                  {progress.strategies_generated} / {progress.total_strategies}
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${(progress.strategies_generated / progress.total_strategies) * 100}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 dark:text-gray-400">Backtesting Progress</span>
                <span className="text-gray-900 dark:text-white font-medium">
                  {progress.strategies_backtested} / {progress.total_strategies}
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  className="bg-purple-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${(progress.strategies_backtested / progress.total_strategies) * 100}%` }}
                />
              </div>
            </div>
          </div>

          {progress.current_strategy && (
            <div className="mt-4 p-3 bg-gray-50 dark:bg-slate-700 rounded-lg">
              <p className="text-xs text-gray-600 dark:text-gray-400">Currently Processing</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white">{progress.current_strategy}</p>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
            <span>Duration: {formatDuration(progress.started_at, progress.completed_at)}</span>
            {progress.started_at && (
              <span>Started: {new Date(progress.started_at).toLocaleTimeString()}</span>
            )}
          </div>
        </div>
      )}

      {/* Results Display */}
      {results && results.backtest_summaries && results.backtest_summaries.length > 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Backtest Results</h3>
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="text-green-600 dark:text-green-400 font-medium">{results.strategies_passed}</span>
              {' passed, '}
              <span className="text-red-600 dark:text-red-400 font-medium">{results.strategies_failed}</span>
              {' failed'}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-slate-700">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Strategy</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Win Rate</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Sharpe</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">CAGR</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Drawdown</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Trades</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {results.backtest_summaries.map((result) => (
                  <tr key={result.strategy_id} className="hover:bg-gray-50 dark:hover:bg-slate-700/50">
                    <td className="px-4 py-3">
                      {result.passed_criteria ? (
                        <FiCheckCircle className="w-4 h-4 text-green-500" />
                      ) : (
                        <FiXCircle className="w-4 h-4 text-red-500" />
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                      {result.strategy_name}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={result.win_rate >= 0.45 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                        {(result.win_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={result.sharpe_ratio >= 1.0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                        {result.sharpe_ratio.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={result.cagr >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                        {(result.cagr * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={result.max_drawdown >= -0.25 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                        {(result.max_drawdown * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                      {result.total_trades}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {results.backtest_summaries.length > 5 && (
            <div className="mt-4 text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Showing top results. Total: {results.backtest_summaries.length} strategies
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

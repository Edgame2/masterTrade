'use client';

import { useEffect, useState } from 'react';
import {
  FiTrendingUp,
  FiDollarSign,
  FiTarget,
  FiRefreshCw,
  FiAlertCircle,
  FiCheckCircle,
  FiClock,
  FiActivity
} from 'react-icons/fi';

/**
 * Financial goal interface matching risk_manager API response
 */
interface FinancialGoal {
  goal_type: 'monthly_return' | 'monthly_income' | 'portfolio_value';
  target_value: number;
  current_value: number;
  progress_percent: number;
  status: 'on_track' | 'at_risk' | 'behind' | 'achieved';
  updated_at: string;
}

/**
 * Goals API response
 */
interface GoalsStatusResponse {
  success: boolean;
  goals: FinancialGoal[];
  timestamp: string;
}

/**
 * Alert interface for goal-related alerts
 */
interface GoalAlert {
  alert_id: string;
  alert_type: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  title: string;
  message: string;
  status: 'pending' | 'acknowledged' | 'resolved';
  created_at: string;
  data: {
    goal_type?: string;
    status?: string;
    actual_value?: number;
    target_value?: number;
    progress_percent?: number;
  } | null;
}

/**
 * Goal Progress View Component
 * 
 * Displays financial goal tracking:
 * - 10% monthly return target
 * - €4,000 monthly income target
 * - €1,000,000 portfolio value target
 * 
 * Features:
 * - Real-time progress bars
 * - Status indicators (on track, at risk, behind, achieved)
 * - Current vs target values
 * - Days remaining calculations
 * - Required daily return projections
 */
export default function GoalProgressView() {
  const [goals, setGoals] = useState<FinancialGoal[]>([]);
  const [alerts, setAlerts] = useState<GoalAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const RISK_MANAGER_API = process.env.NEXT_PUBLIC_RISK_MANAGER_API_URL || 'http://localhost:8003';
  const ALERT_API = process.env.NEXT_PUBLIC_ALERT_API_URL || 'http://localhost:8007';

  useEffect(() => {
    fetchGoalsStatus();
    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchGoalsStatus, 60000);
    return () => clearInterval(interval);
  }, []);

  /**
   * Fetch goals status from risk_manager API and related alerts from alert_system
   */
  const fetchGoalsStatus = async () => {
    try {
      setError(null);
      
      // Fetch goals
      const goalsResponse = await fetch(`${RISK_MANAGER_API}/goals/status`);
      
      if (!goalsResponse.ok) {
        throw new Error(`HTTP ${goalsResponse.status}: ${goalsResponse.statusText}`);
      }

      const goalsData: GoalsStatusResponse = await goalsResponse.json();
      
      if (!goalsData.success) {
        throw new Error('API returned success: false');
      }

      setGoals(goalsData.goals);

      // Fetch goal-related alerts (milestone type)
      try {
        const alertsResponse = await fetch(`${ALERT_API}/api/alerts/list?limit=50`);
        if (alertsResponse.ok) {
          const alertsData: GoalAlert[] = await alertsResponse.json();
          // Filter for milestone alerts (goal-related) that are pending
          const goalAlerts = alertsData.filter(
            alert => alert.alert_type === 'milestone' && alert.status === 'pending'
          );
          setAlerts(goalAlerts);
        }
      } catch (alertError) {
        console.warn('Failed to fetch alerts:', alertError);
        // Don't fail the whole component if alerts fail
      }

      setLastUpdate(new Date());
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch goals');
      setLoading(false);
    }
  };

  /**
   * Get goal display configuration
   */
  const getGoalConfig = (goalType: string) => {
    switch (goalType) {
      case 'monthly_return':
        return {
          title: 'Monthly Return Target',
          icon: FiTrendingUp,
          color: 'blue',
          unit: '%',
          format: (val: number) => val.toFixed(2),
          description: 'Achieve 10% monthly return on portfolio'
        };
      case 'monthly_income':
        return {
          title: 'Monthly Income Target',
          icon: FiDollarSign,
          color: 'green',
          unit: '€',
          format: (val: number) => val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
          description: 'Generate €4,000 monthly trading income'
        };
      case 'portfolio_value':
        return {
          title: 'Portfolio Value Target',
          icon: FiTarget,
          color: 'purple',
          unit: '€',
          format: (val: number) => val.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }),
          description: 'Reach €1,000,000 total portfolio value'
        };
      default:
        return {
          title: goalType,
          icon: FiActivity,
          color: 'gray',
          unit: '',
          format: (val: number) => val.toString(),
          description: ''
        };
    }
  };

  /**
   * Get status badge styling
   */
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'achieved':
        return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'on_track':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'at_risk':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'behind':
        return 'bg-red-500/20 text-red-400 border-red-500/30';
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  /**
   * Get progress bar color based on progress percentage
   */
  const getProgressColor = (percent: number) => {
    if (percent >= 90) return 'bg-green-500';
    if (percent >= 70) return 'bg-blue-500';
    if (percent >= 50) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  /**
   * Calculate days remaining in current month
   */
  const getDaysRemainingInMonth = () => {
    const now = new Date();
    const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    const daysLeft = lastDay.getDate() - now.getDate();
    return daysLeft;
  };

  /**
   * Calculate required daily return to meet monthly target
   */
  const getRequiredDailyReturn = (goal: FinancialGoal) => {
    if (goal.goal_type !== 'monthly_return') return null;
    
    const daysRemaining = getDaysRemainingInMonth();
    if (daysRemaining <= 0) return null;
    
    const remainingTarget = goal.target_value - goal.current_value;
    const requiredDaily = remainingTarget / daysRemaining;
    
    return requiredDaily;
  };

  /**
   * Get alerts for a specific goal
   */
  const getGoalAlerts = (goalType: string): GoalAlert[] => {
    return alerts.filter(alert => {
      // Check if alert data contains matching goal_type
      if (alert.data && alert.data.goal_type === goalType) {
        return true;
      }
      // Also check if title contains the goal type
      const titleLower = alert.title.toLowerCase();
      if (goalType === 'monthly_return' && titleLower.includes('monthly return')) return true;
      if (goalType === 'monthly_income' && titleLower.includes('monthly income')) return true;
      if (goalType === 'portfolio_value' && titleLower.includes('portfolio value')) return true;
      return false;
    });
  };

  /**
   * Get alert priority color
   */
  const getAlertPriorityColor = (priority: string) => {
    switch (priority) {
      case 'CRITICAL':
        return 'text-red-400 bg-red-500/20 border-red-500/30';
      case 'HIGH':
        return 'text-orange-400 bg-orange-500/20 border-orange-500/30';
      case 'MEDIUM':
        return 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30';
      case 'LOW':
        return 'text-blue-400 bg-blue-500/20 border-blue-500/30';
      default:
        return 'text-gray-400 bg-gray-500/20 border-gray-500/30';
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400">Loading goal progress...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6">
        <div className="flex items-center gap-3">
          <FiAlertCircle className="w-6 h-6 text-red-400" />
          <div>
            <h3 className="text-lg font-semibold text-red-400">Failed to Load Goals</h3>
            <p className="text-sm text-red-300 mt-1">{error}</p>
          </div>
        </div>
        <button
          onClick={fetchGoalsStatus}
          className="mt-4 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Financial Goals</h2>
          <p className="text-slate-400 mt-1">
            Track progress toward trading objectives
          </p>
        </div>
        <div className="flex items-center gap-4">
          {lastUpdate && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <FiClock className="w-4 h-4" />
              <span>
                Updated {lastUpdate.toLocaleTimeString()}
              </span>
            </div>
          )}
          <button
            onClick={fetchGoalsStatus}
            className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            title="Refresh"
          >
            <FiRefreshCw className="w-5 h-5 text-slate-300" />
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {goals.map((goal) => {
          const config = getGoalConfig(goal.goal_type);
          const Icon = config.icon;
          const requiredDaily = getRequiredDailyReturn(goal);
          const goalAlerts = getGoalAlerts(goal.goal_type);

          return (
            <div
              key={goal.goal_type}
              className="bg-slate-800 rounded-lg p-6 border border-slate-700 hover:border-slate-600 transition-colors"
            >
              {/* Goal Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`p-3 rounded-lg bg-${config.color}-500/20`}>
                    <Icon className={`w-6 h-6 text-${config.color}-400`} />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white">
                      {config.title}
                    </h3>
                    <p className="text-xs text-slate-400 mt-1">
                      {config.description}
                    </p>
                  </div>
                </div>
              </div>

              {/* Status Badge */}
              <div className="flex items-center gap-2 mb-4">
                <span className={`px-3 py-1 rounded-full text-xs font-medium border ${getStatusColor(goal.status)}`}>
                  {goal.status === 'achieved' && <FiCheckCircle className="inline w-3 h-3 mr-1" />}
                  {goal.status.replace('_', ' ').toUpperCase()}
                </span>
                {goalAlerts.length > 0 && (
                  <span className="px-2 py-1 rounded-full text-xs font-medium bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                    {goalAlerts.length} Alert{goalAlerts.length > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {/* Active Alerts */}
              {goalAlerts.length > 0 && (
                <div className="mb-4 space-y-2">
                  {goalAlerts.slice(0, 2).map((alert) => (
                    <div
                      key={alert.alert_id}
                      className={`p-3 rounded-lg border text-xs ${getAlertPriorityColor(alert.priority)}`}
                    >
                      <div className="flex items-start gap-2">
                        <FiAlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium">{alert.title}</div>
                          <div className="text-xs opacity-80 mt-1 line-clamp-2">
                            {alert.message}
                          </div>
                          <div className="text-xs opacity-60 mt-1">
                            {new Date(alert.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                  {goalAlerts.length > 2 && (
                    <div className="text-xs text-slate-400 text-center">
                      +{goalAlerts.length - 2} more alert{goalAlerts.length - 2 > 1 ? 's' : ''}
                    </div>
                  )}
                </div>
              )}

              {/* Progress Bar */}
              <div className="mb-4">
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className="text-slate-400">Progress</span>
                  <span className="text-white font-semibold">
                    {goal.progress_percent.toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-full ${getProgressColor(goal.progress_percent)} transition-all duration-500`}
                    style={{ width: `${Math.min(goal.progress_percent, 100)}%` }}
                  />
                </div>
              </div>

              {/* Current vs Target */}
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Current:</span>
                  <span className="text-white font-medium">
                    {config.unit === '€' && config.unit}
                    {config.format(goal.current_value)}
                    {config.unit !== '€' && config.unit}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Target:</span>
                  <span className="text-white font-medium">
                    {config.unit === '€' && config.unit}
                    {config.format(goal.target_value)}
                    {config.unit !== '€' && config.unit}
                  </span>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-slate-700">
                  <span className="text-slate-400">Remaining:</span>
                  <span className="text-blue-400 font-medium">
                    {config.unit === '€' && config.unit}
                    {config.format(goal.target_value - goal.current_value)}
                    {config.unit !== '€' && config.unit}
                  </span>
                </div>
              </div>

              {/* Additional Info for Monthly Return Goal */}
              {goal.goal_type === 'monthly_return' && requiredDaily !== null && (
                <div className="mt-4 pt-4 border-t border-slate-700">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-400">Days left this month:</span>
                    <span className="text-white font-medium">{getDaysRemainingInMonth()}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm mt-2">
                    <span className="text-slate-400">Required daily return:</span>
                    <span className={`font-medium ${requiredDaily > 1 ? 'text-red-400' : 'text-green-400'}`}>
                      {requiredDaily.toFixed(2)}%
                    </span>
                  </div>
                </div>
              )}

              {/* Last Updated */}
              <div className="mt-4 pt-4 border-t border-slate-700">
                <p className="text-xs text-slate-500">
                  Last updated: {new Date(goal.updated_at).toLocaleString()}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Empty State */}
      {goals.length === 0 && (
        <div className="bg-slate-800 rounded-lg p-12 text-center">
          <FiTarget className="w-16 h-16 mx-auto text-slate-600 mb-4" />
          <h3 className="text-xl font-semibold text-slate-400 mb-2">No Goals Configured</h3>
          <p className="text-slate-500">
            Financial goals will appear here once they are configured in the risk manager.
          </p>
        </div>
      )}

      {/* Info Box */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <div className="flex gap-3">
          <FiActivity className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-300">
            <p className="font-medium mb-2">About Financial Goals:</p>
            <ul className="space-y-1 text-xs text-blue-200">
              <li>• <strong>Monthly Return</strong>: Track monthly portfolio returns against 10% target</li>
              <li>• <strong>Monthly Income</strong>: Monitor realized profits toward €4,000/month goal</li>
              <li>• <strong>Portfolio Value</strong>: Progress toward €1,000,000 total portfolio value</li>
              <li>• Goals update automatically based on trading activity and portfolio performance</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

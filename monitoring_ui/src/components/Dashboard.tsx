'use client';

import { useEffect, useState } from 'react';
import { signOut, useSession } from 'next-auth/react';
import { FiLogOut, FiActivity, FiTrendingUp, FiDollarSign, FiAlertCircle } from 'react-icons/fi';
import Sidebar from './Sidebar';
import StrategyList from './StrategyList';
import PortfolioOverview from './PortfolioOverview';
import PerformanceChart from './PerformanceChart';
import LivePositions from './LivePositions';
import CryptoManager from './CryptoManager';
import StrategyGenerator from './StrategyGenerator';
import DataSourcesView from './DataSourcesView';
import GoalProgressView from './GoalProgressView';
import SystemHealthView from './SystemHealthView';
import StrategyManagementView from './StrategyManagementView';
import AlertsNotificationsView from './AlertsNotificationsView';
import UserManagementView from './UserManagementView';
import AlphaAttributionView from './AlphaAttributionView';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function Dashboard() {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState<'overview' | 'strategies' | 'generator' | 'positions' | 'performance' | 'crypto' | 'datasources' | 'goals' | 'alpha' | 'strategy-mgmt' | 'alerts' | 'users'>('overview');
  const [stats, setStats] = useState({
    totalPnL: 0,
    totalValue: 0,
    activeStrategies: 0,
    openPositions: 0,
  });

  // WebSocket connection for real-time updates
  const { connected, data: wsData } = useWebSocket(process.env.NEXT_PUBLIC_WS_URL || '');

  useEffect(() => {
    // Fetch initial dashboard stats
    fetchDashboardStats();
  }, []);

  useEffect(() => {
    // Update stats from WebSocket data
    if (wsData) {
      updateStatsFromWS(wsData);
    }
  }, [wsData]);

  const fetchDashboardStats = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
      const [portfolioRes, strategiesRes] = await Promise.all([
        fetch(`${apiUrl}/api/portfolio/balance`),
        fetch(`${apiUrl}/api/strategies`),
      ]);

      const portfolioData = await portfolioRes.json();
      const strategiesData = await strategiesRes.json();

      setStats({
        totalPnL: portfolioData.summary?.totalPnL || 0,
        totalValue: portfolioData.summary?.totalValue || 0,
        activeStrategies: strategiesData?.length || 0,
        openPositions: portfolioData.summary?.totalPositions || 0,
      });
    } catch (error) {
      console.error('Error fetching dashboard stats:', error);
    }
  };

  const updateStatsFromWS = (data: any) => {
    if (data.type === 'portfolio_update') {
      setStats(prev => ({
        ...prev,
        totalPnL: data.totalPnL,
        totalValue: data.totalValue,
        openPositions: data.openPositions,
      }));
    }
  };

  const StatCard = ({ title, value, icon: Icon, trend, color }: any) => (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-5 hover:border-slate-600 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm text-slate-400 mb-1">{title}</p>
          <h3 className={`text-2xl font-bold ${color}`}>{value}</h3>
          {trend && (
            <p className={`text-sm mt-1 ${trend > 0 ? 'text-green-400' : 'text-red-400'}`}>
              {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
            </p>
          )}
        </div>
        <div className={`p-3 rounded-lg ${color} bg-opacity-10 bg-current`}>
          <Icon className={`w-6 h-6 ${color}`} />
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-900 overflow-hidden">
      {/* Sidebar Navigation */}
      <Sidebar activeTab={activeTab} onTabChange={(tab) => setActiveTab(tab as any)} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-slate-800 shadow-lg border-b border-slate-700">
          <div className="px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <h1 className="text-xl font-bold text-white">
                  {activeTab.charAt(0).toUpperCase() + activeTab.slice(1).replace('-', ' ')}
                </h1>
                {connected && (
                  <span className="flex items-center text-sm text-green-400">
                    <span className="w-2 h-2 bg-green-400 rounded-full mr-2 animate-pulse"></span>
                    Live
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-4">
                <span className="text-sm text-slate-400">
                  {session?.user?.email}
                </span>
                <button
                  onClick={() => signOut()}
                  className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                >
                  <FiLogOut />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* Stats Grid */}
        <div className="bg-slate-900 px-6 py-6 border-b border-slate-800">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Total P&L"
              value={`$${stats.totalPnL.toFixed(2)}`}
              icon={FiDollarSign}
              trend={2.5}
              color="text-green-400"
            />
            <StatCard
              title="Portfolio Value"
              value={`$${stats.totalValue.toFixed(2)}`}
              icon={FiTrendingUp}
              color="text-blue-400"
            />
            <StatCard
              title="Active Strategies"
              value={stats.activeStrategies}
              icon={FiActivity}
              color="text-purple-400"
            />
            <StatCard
              title="Open Positions"
              value={stats.openPositions}
              icon={FiAlertCircle}
              color="text-yellow-400"
            />
          </div>
        </div>

        {/* Main Content - Scrollable */}
        <main className="flex-1 overflow-y-auto bg-slate-900 px-6 py-6">
          <div className="max-w-7xl mx-auto">
            {activeTab === 'overview' && (
              <div className="space-y-6">
                <SystemHealthView />
                <PerformanceChart />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <PortfolioOverview />
                  <LivePositions limit={5} />
                </div>
              </div>
            )}
            {activeTab === 'strategies' && <StrategyList />}
            {activeTab === 'generator' && <StrategyGenerator />}
            {activeTab === 'positions' && <LivePositions />}
            {activeTab === 'performance' && <PerformanceChart detailed />}
            {activeTab === 'crypto' && <CryptoManager />}
            {activeTab === 'datasources' && <DataSourcesView />}
            {activeTab === 'goals' && <GoalProgressView />}
            {activeTab === 'alpha' && <AlphaAttributionView />}
            {activeTab === 'strategy-mgmt' && <StrategyManagementView />}
            {activeTab === 'alerts' && <AlertsNotificationsView />}
            {activeTab === 'users' && <UserManagementView />}
          </div>
        </main>
      </div>
    </div>
  );
}

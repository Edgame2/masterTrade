'use client';

import { useEffect, useState } from 'react';
import { signOut, useSession } from 'next-auth/react';
import { FiLogOut, FiActivity, FiTrendingUp, FiDollarSign, FiAlertCircle } from 'react-icons/fi';
import StrategyList from './StrategyList';
import PortfolioOverview from './PortfolioOverview';
import PerformanceChart from './PerformanceChart';
import LivePositions from './LivePositions';
import CryptoManager from './CryptoManager';
import StrategyGenerator from './StrategyGenerator';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function Dashboard() {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState<'overview' | 'strategies' | 'generator' | 'positions' | 'performance' | 'crypto'>('overview');
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
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md p-6 card-hover">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{title}</p>
          <h3 className={`text-2xl font-bold ${color}`}>{value}</h3>
          {trend && (
            <p className={`text-sm mt-1 ${trend > 0 ? 'text-success' : 'text-danger'}`}>
              {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
            </p>
          )}
        </div>
        <div className={`p-3 rounded-full ${color} bg-opacity-10`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <header className="bg-white dark:bg-slate-800 shadow-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <FiTrendingUp className="w-8 h-8 text-primary-600" />
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                MasterTrade
              </h1>
              {connected && (
                <span className="flex items-center text-sm text-success">
                  <span className="w-2 h-2 bg-success rounded-full mr-2 pulse-dot"></span>
                  Live
                </span>
              )}
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {session?.user?.email}
              </span>
              <button
                onClick={() => signOut()}
                className="flex items-center space-x-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition"
              >
                <FiLogOut />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Total P&L"
            value={`$${stats.totalPnL.toFixed(2)}`}
            icon={FiDollarSign}
            trend={2.5}
            color="text-success"
          />
          <StatCard
            title="Portfolio Value"
            value={`$${stats.totalValue.toFixed(2)}`}
            icon={FiTrendingUp}
            color="text-primary-600"
          />
          <StatCard
            title="Active Strategies"
            value={stats.activeStrategies}
            icon={FiActivity}
            color="text-blue-600"
          />
          <StatCard
            title="Open Positions"
            value={stats.openPositions}
            icon={FiAlertCircle}
            color="text-warning"
          />
        </div>

        {/* Tabs */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md mb-6">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex space-x-8 px-6">
              {['overview', 'strategies', 'generator', 'positions', 'performance', 'crypto'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab as any)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm capitalize ${
                    activeTab === tab
                      ? 'border-primary-500 text-primary-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Tab Content */}
        <div className="animate-slideIn">
          {activeTab === 'overview' && (
            <div className="space-y-6">
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
        </div>
      </main>
    </div>
  );
}

'use client';

import { 
  FiHome, 
  FiActivity, 
  FiZap, 
  FiLayers, 
  FiTrendingUp, 
  FiDollarSign,
  FiDatabase,
  FiTarget,
  FiSettings,
  FiBell,
  FiUsers,
  FiChevronLeft,
  FiChevronRight,
  FiPieChart,
  FiBarChart2
} from 'react-icons/fi';
import { useState } from 'react';

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
  badge?: number;
}

export default function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  const navItems: NavItem[] = [
    { id: 'overview', label: 'Overview', icon: FiHome },
    { id: 'strategies', label: 'Strategies', icon: FiActivity },
    { id: 'strategy-mgmt', label: 'Strategy Management', icon: FiSettings },
    { id: 'generator', label: 'Generator', icon: FiZap },
    { id: 'positions', label: 'Positions', icon: FiLayers },
    { id: 'performance', label: 'Performance', icon: FiTrendingUp },
    { id: 'crypto', label: 'Crypto Manager', icon: FiDollarSign },
    { id: 'datasources', label: 'Data Sources', icon: FiDatabase },
    { id: 'marketdata', label: 'Market Data', icon: FiBarChart2 },
    { id: 'goals', label: 'Financial Goals', icon: FiTarget },
    { id: 'alpha', label: 'Alpha Attribution', icon: FiPieChart },
    { id: 'alerts', label: 'Alerts & Notifications', icon: FiBell },
    { id: 'users', label: 'User Management', icon: FiUsers },
  ];

  return (
    <aside 
      className={`${
        collapsed ? 'w-16' : 'w-64'
      } bg-slate-800 border-r border-slate-700 transition-all duration-300 flex flex-col h-screen sticky top-0`}
    >
      {/* Sidebar Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        {!collapsed && (
          <div className="flex items-center space-x-2">
            <FiTrendingUp className="w-6 h-6 text-blue-400" />
            <h2 className="text-lg font-bold text-white">MasterTrade</h2>
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <FiChevronRight className="w-5 h-5" />
          ) : (
            <FiChevronLeft className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 overflow-y-auto py-4">
        <ul className="space-y-1 px-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            
            return (
              <li key={item.id}>
                <button
                  onClick={() => onTabChange(item.id)}
                  className={`
                    w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg
                    transition-all duration-200 group
                    ${isActive 
                      ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' 
                      : 'text-slate-400 hover:bg-slate-700 hover:text-white'
                    }
                  `}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon className={`w-5 h-5 flex-shrink-0 ${isActive ? 'text-white' : 'group-hover:text-white'}`} />
                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left text-sm font-medium">
                        {item.label}
                      </span>
                      {item.badge && (
                        <span className="bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                  {collapsed && item.badge && (
                    <span className="absolute left-full ml-2 bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
                      {item.badge}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Sidebar Footer */}
      {!collapsed && (
        <div className="p-4 border-t border-slate-700">
          <div className="text-xs text-slate-500">
            <div className="mb-1">Version 1.0.0</div>
            <div>© 2025 MasterTrade</div>
          </div>
        </div>
      )}
    </aside>
  );
}

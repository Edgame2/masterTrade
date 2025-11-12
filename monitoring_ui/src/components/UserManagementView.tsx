"use client";

import React, { useState, useEffect } from 'react';
import {
  FiUsers,
  FiUserPlus,
  FiEdit2,
  FiTrash2,
  FiShield,
  FiClock,
  FiCheckCircle,
  FiXCircle,
  FiAlertCircle,
  FiRefreshCw,
  FiEye,
  FiKey
} from 'react-icons/fi';

// Types
interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'operator' | 'quant' | 'viewer';
  status: 'active' | 'inactive' | 'suspended';
  last_seen: string | null;
  created_at: string;
  updated_at: string;
  preferences: Record<string, any>;
}

interface UserActivity {
  id: string;
  user_id: string;
  action: string;
  details: Record<string, any>;
  timestamp: string;
  ip_address: string | null;
}

interface CreateUserForm {
  email: string;
  name: string;
  role: User['role'];
  password: string;
}

interface UpdateUserForm {
  name?: string;
  role?: User['role'];
  status?: User['status'];
}

const API_URL = process.env.NEXT_PUBLIC_API_GATEWAY_URL || 'http://localhost:8090';

export default function UserManagementView() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [userActivities, setUserActivities] = useState<UserActivity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showActivitiesModal, setShowActivitiesModal] = useState(false);
  const [filter, setFilter] = useState<{
    role: string;
    status: string;
  }>({
    role: '',
    status: ''
  });

  // Form state
  const [createForm, setCreateForm] = useState<CreateUserForm>({
    email: '',
    name: '',
    role: 'viewer',
    password: ''
  });
  const [updateForm, setUpdateForm] = useState<UpdateUserForm>({});
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    fetchUsers();
    const interval = setInterval(fetchUsers, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [filter]);

  const fetchUsers = async () => {
    setIsRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (filter.role) params.append('role', filter.role);
      if (filter.status) params.append('status', filter.status);
      params.append('limit', '100');

      const response = await fetch(`${API_URL}/api/v1/users?${params}`);
      if (!response.ok) throw new Error('Failed to fetch users');
      
      const data = await response.json();
      setUsers(data.users || []);
    } catch (error) {
      console.error('Error fetching users:', error);
      setErrorMessage('Failed to load users');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  const fetchUserActivities = async (userId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/v1/users/${userId}/activities?limit=50`);
      if (!response.ok) throw new Error('Failed to fetch activities');
      
      const data = await response.json();
      setUserActivities(data.activities || []);
    } catch (error) {
      console.error('Error fetching activities:', error);
      setErrorMessage('Failed to load user activities');
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    try {
      const response = await fetch(`${API_URL}/api/v1/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(createForm)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create user');
      }

      setSuccessMessage('User created successfully');
      setShowCreateModal(false);
      setCreateForm({ email: '', name: '', role: 'viewer', password: '' });
      fetchUsers();
      
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error: any) {
      setErrorMessage(error.message);
    }
  };

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    setErrorMessage('');
    setSuccessMessage('');

    try {
      const response = await fetch(`${API_URL}/api/v1/users/${selectedUser.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateForm)
      });

      if (!response.ok) throw new Error('Failed to update user');

      setSuccessMessage('User updated successfully');
      setShowEditModal(false);
      setSelectedUser(null);
      setUpdateForm({});
      fetchUsers();
      
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error: any) {
      setErrorMessage(error.message);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    if (!confirm('Are you sure you want to delete this user?')) return;

    setErrorMessage('');
    setSuccessMessage('');

    try {
      const response = await fetch(`${API_URL}/api/v1/users/${userId}`, {
        method: 'DELETE'
      });

      if (!response.ok) throw new Error('Failed to delete user');

      setSuccessMessage('User deleted successfully');
      fetchUsers();
      
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error: any) {
      setErrorMessage(error.message);
    }
  };

  const openEditModal = (user: User) => {
    setSelectedUser(user);
    setUpdateForm({
      name: user.name,
      role: user.role,
      status: user.status
    });
    setShowEditModal(true);
  };

  const openActivitiesModal = (user: User) => {
    setSelectedUser(user);
    fetchUserActivities(user.id);
    setShowActivitiesModal(true);
  };

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case 'admin': return 'bg-red-500/20 text-red-400';
      case 'operator': return 'bg-blue-500/20 text-blue-400';
      case 'quant': return 'bg-purple-500/20 text-purple-400';
      case 'viewer': return 'bg-gray-500/20 text-gray-400';
      default: return 'bg-gray-500/20 text-gray-400';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'active': return <FiCheckCircle className="text-green-500" />;
      case 'inactive': return <FiXCircle className="text-gray-500" />;
      case 'suspended': return <FiAlertCircle className="text-orange-500" />;
      default: return <FiXCircle className="text-gray-500" />;
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <FiUsers className="text-3xl text-blue-400" />
          <div>
            <h2 className="text-2xl font-bold text-white">User Management</h2>
            <p className="text-slate-400 text-sm">Manage users, roles, and permissions</p>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={fetchUsers}
            disabled={isRefreshing}
            className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            <FiRefreshCw className={isRefreshing ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
          >
            <FiUserPlus />
            <span>Add User</span>
          </button>
        </div>
      </div>

      {/* Messages */}
      {errorMessage && (
        <div className="bg-red-500/10 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg flex items-center space-x-2">
          <FiAlertCircle />
          <span>{errorMessage}</span>
        </div>
      )}

      {successMessage && (
        <div className="bg-green-500/10 border border-green-500/50 text-green-400 px-4 py-3 rounded-lg flex items-center space-x-2">
          <FiCheckCircle />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Filters */}
      <div className="bg-slate-800 rounded-lg p-4">
        <div className="flex items-center space-x-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Role</label>
            <select
              value={filter.role}
              onChange={(e) => setFilter({ ...filter, role: e.target.value })}
              className="px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Roles</option>
              <option value="admin">Admin</option>
              <option value="operator">Operator</option>
              <option value="quant">Quant</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Status</label>
            <select
              value={filter.status}
              onChange={(e) => setFilter({ ...filter, status: e.target.value })}
              className="px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>

          <div className="flex-1 text-right text-sm text-slate-400 self-end pb-2">
            {users.length} user{users.length !== 1 ? 's' : ''}
          </div>
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-slate-800 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-900 border-b border-slate-700">
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                User
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Role
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Last Seen
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700">
            {users.map((user) => (
              <tr key={user.id} className="hover:bg-slate-700/50 transition-colors">
                <td className="px-6 py-4">
                  <div>
                    <div className="text-sm font-medium text-white">{user.name}</div>
                    <div className="text-sm text-slate-400">{user.email}</div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getRoleBadgeColor(user.role)}`}>
                    <FiShield className="mr-1" />
                    {user.role}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(user.status)}
                    <span className="text-sm text-slate-300 capitalize">{user.status}</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center space-x-2 text-sm text-slate-400">
                    <FiClock />
                    <span>{formatDate(user.last_seen)}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-400">
                  {new Date(user.created_at).toLocaleDateString()}
                </td>
                <td className="px-6 py-4 text-right">
                  <div className="flex items-center justify-end space-x-2">
                    <button
                      onClick={() => openActivitiesModal(user)}
                      className="p-2 hover:bg-slate-600 rounded-lg transition-colors text-blue-400"
                      title="View Activities"
                    >
                      <FiEye />
                    </button>
                    <button
                      onClick={() => openEditModal(user)}
                      className="p-2 hover:bg-slate-600 rounded-lg transition-colors text-yellow-400"
                      title="Edit User"
                    >
                      <FiEdit2 />
                    </button>
                    <button
                      onClick={() => handleDeleteUser(user.id)}
                      className="p-2 hover:bg-slate-600 rounded-lg transition-colors text-red-400"
                      title="Delete User"
                    >
                      <FiTrash2 />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {users.length === 0 && (
          <div className="text-center py-12 text-slate-400">
            <FiUsers className="text-5xl mx-auto mb-4 opacity-50" />
            <p>No users found</p>
          </div>
        )}
      </div>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-white mb-4">Create New User</h3>
            
            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={createForm.email}
                  onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Name</label>
                <input
                  type="text"
                  required
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Role</label>
                <select
                  value={createForm.role}
                  onChange={(e) => setCreateForm({ ...createForm, role: e.target.value as User['role'] })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                >
                  <option value="viewer">Viewer</option>
                  <option value="quant">Quant</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={createForm.password}
                  onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                  placeholder="At least 8 characters"
                />
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                >
                  Create User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {showEditModal && selectedUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-white mb-4">Edit User</h3>
            
            <form onSubmit={handleUpdateUser} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Email</label>
                <input
                  type="email"
                  disabled
                  value={selectedUser.email}
                  className="w-full px-3 py-2 bg-slate-700/50 text-slate-400 rounded-lg border border-slate-600 cursor-not-allowed"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Name</label>
                <input
                  type="text"
                  value={updateForm.name || ''}
                  onChange={(e) => setUpdateForm({ ...updateForm, name: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Role</label>
                <select
                  value={updateForm.role || selectedUser.role}
                  onChange={(e) => setUpdateForm({ ...updateForm, role: e.target.value as User['role'] })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                >
                  <option value="viewer">Viewer</option>
                  <option value="quant">Quant</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">Status</label>
                <select
                  value={updateForm.status || selectedUser.status}
                  onChange={(e) => setUpdateForm({ ...updateForm, status: e.target.value as User['status'] })}
                  className="w-full px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:outline-none focus:border-blue-500"
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="suspended">Suspended</option>
                </select>
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowEditModal(false);
                    setSelectedUser(null);
                    setUpdateForm({});
                  }}
                  className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
                >
                  Update User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Activities Modal */}
      {showActivitiesModal && selectedUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-white">User Activities</h3>
              <button
                onClick={() => {
                  setShowActivitiesModal(false);
                  setSelectedUser(null);
                  setUserActivities([]);
                }}
                className="text-slate-400 hover:text-white"
              >
                <FiXCircle className="text-xl" />
              </button>
            </div>

            <div className="mb-4 pb-4 border-b border-slate-700">
              <p className="text-slate-300">{selectedUser.name}</p>
              <p className="text-sm text-slate-400">{selectedUser.email}</p>
            </div>

            {userActivities.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <FiClock className="text-4xl mx-auto mb-2 opacity-50" />
                <p>No activities recorded</p>
              </div>
            ) : (
              <div className="space-y-3">
                {userActivities.map((activity) => (
                  <div key={activity.id} className="bg-slate-700/50 rounded-lg p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="text-white font-medium">{activity.action}</p>
                        {activity.details && Object.keys(activity.details).length > 0 && (
                          <div className="mt-2 text-sm text-slate-400">
                            {JSON.stringify(activity.details, null, 2)}
                          </div>
                        )}
                      </div>
                      <div className="text-right ml-4">
                        <p className="text-xs text-slate-400">
                          {new Date(activity.timestamp).toLocaleString()}
                        </p>
                        {activity.ip_address && (
                          <p className="text-xs text-slate-500 mt-1">{activity.ip_address}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

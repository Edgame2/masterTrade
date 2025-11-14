'use client';

import { signIn } from 'next-auth/react';
import { FiMail } from 'react-icons/fi';
import { FcGoogle } from 'react-icons/fc';
import { useState } from 'react';

export default function SignIn() {
  const [devUsername, setDevUsername] = useState('admin');
  const showDevMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';

  const handleDevLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    await signIn('dev-credentials', { 
      username: devUsername,
      callbackUrl: '/' 
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-8 max-w-md w-full">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            MasterTrade
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Advanced AI Trading Bot Monitor
          </p>
        </div>

        <div className="space-y-4">
          {showDevMode && (
            <form onSubmit={handleDevLogin} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Dev Username
                </label>
                <input
                  type="text"
                  value={devUsername}
                  onChange={(e) => setDevUsername(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Enter any username"
                />
              </div>
              <button
                type="submit"
                className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition shadow-sm font-medium"
              >
                Sign in (Dev Mode)
              </button>
            </form>
          )}

          <button
            onClick={() => signIn('google', { callbackUrl: '/' })}
            className="w-full flex items-center justify-center space-x-3 px-6 py-3 bg-white border-2 border-gray-300 rounded-lg hover:bg-gray-50 transition shadow-sm"
          >
            <FcGoogle className="w-6 h-6" />
            <span className="font-medium text-gray-700">Sign in with Google</span>
          </button>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-300"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-gray-500">Secure Authentication</span>
            </div>
          </div>
        </div>

        <div className="mt-8 text-center text-sm text-gray-500">
          <p>Protected by Google OAuth 2.0</p>
          <p className="mt-2">Only authorized users can access</p>
        </div>
      </div>
    </div>
  );
}


'use client';

import { FiClock, FiCheckCircle, FiAlertCircle, FiAlertTriangle } from 'react-icons/fi';

interface FreshnessIndicatorProps {
  timestamp: string | Date;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
  inline?: boolean;
}

/**
 * FreshnessIndicator Component
 * 
 * Visual indicator for data freshness/staleness
 * Color coding:
 * - Green: < 5 min old (fresh)
 * - Yellow: 5-15 min old (aging)
 * - Red: > 15 min old (stale)
 * 
 * Usage:
 * ```tsx
 * <FreshnessIndicator timestamp={lastUpdate} showLabel />
 * ```
 */
export default function FreshnessIndicator({ 
  timestamp, 
  showLabel = false, 
  size = 'md',
  inline = false 
}: FreshnessIndicatorProps) {
  
  /**
   * Calculate age in minutes
   */
  const getAgeInMinutes = (): number => {
    const now = new Date();
    const updateTime = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const diffMs = now.getTime() - updateTime.getTime();
    return Math.floor(diffMs / 60000); // Convert to minutes
  };

  /**
   * Get freshness status based on age
   */
  const getFreshnessStatus = () => {
    const ageMinutes = getAgeInMinutes();
    
    if (ageMinutes < 5) {
      return {
        status: 'fresh',
        color: 'text-green-400',
        bgColor: 'bg-green-500/20',
        borderColor: 'border-green-500/30',
        icon: FiCheckCircle,
        label: 'Fresh',
        pulseClass: 'animate-pulse'
      };
    } else if (ageMinutes < 15) {
      return {
        status: 'aging',
        color: 'text-yellow-400',
        bgColor: 'bg-yellow-500/20',
        borderColor: 'border-yellow-500/30',
        icon: FiAlertTriangle,
        label: 'Aging',
        pulseClass: ''
      };
    } else {
      return {
        status: 'stale',
        color: 'text-red-400',
        bgColor: 'bg-red-500/20',
        borderColor: 'border-red-500/30',
        icon: FiAlertCircle,
        label: 'Stale',
        pulseClass: 'animate-pulse'
      };
    }
  };

  /**
   * Format age as human-readable string
   */
  const getAgeString = (): string => {
    const ageMinutes = getAgeInMinutes();
    
    if (ageMinutes < 1) return 'just now';
    if (ageMinutes === 1) return '1 min ago';
    if (ageMinutes < 60) return `${ageMinutes} mins ago`;
    
    const ageHours = Math.floor(ageMinutes / 60);
    if (ageHours === 1) return '1 hour ago';
    if (ageHours < 24) return `${ageHours} hours ago`;
    
    const ageDays = Math.floor(ageHours / 24);
    if (ageDays === 1) return '1 day ago';
    return `${ageDays} days ago`;
  };

  const freshness = getFreshnessStatus();
  const Icon = freshness.icon;
  const ageString = getAgeString();

  // Size classes
  const sizeClasses = {
    sm: {
      dot: 'w-2 h-2',
      icon: 'w-3 h-3',
      text: 'text-xs',
      padding: 'px-2 py-1'
    },
    md: {
      dot: 'w-2.5 h-2.5',
      icon: 'w-4 h-4',
      text: 'text-sm',
      padding: 'px-3 py-1.5'
    },
    lg: {
      dot: 'w-3 h-3',
      icon: 'w-5 h-5',
      text: 'text-base',
      padding: 'px-4 py-2'
    }
  };

  const classes = sizeClasses[size];

  // Inline compact version (just icon + age)
  if (inline) {
    return (
      <div className="flex items-center gap-1.5" title={`Last updated: ${ageString}`}>
        <Icon className={`${classes.icon} ${freshness.color}`} />
        <span className={`${classes.text} ${freshness.color}`}>
          {ageString}
        </span>
      </div>
    );
  }

  // Full badge version
  if (showLabel) {
    return (
      <div className={`inline-flex items-center gap-2 ${classes.padding} rounded-full border ${freshness.bgColor} ${freshness.borderColor}`}>
        <span className={`${classes.dot} ${freshness.bgColor.replace('/20', '')} rounded-full ${freshness.pulseClass}`} />
        <span className={`${classes.text} font-medium ${freshness.color}`}>
          {freshness.label}
        </span>
        <span className={`${classes.text} ${freshness.color} opacity-75`}>
          • {ageString}
        </span>
      </div>
    );
  }

  // Icon + dot only (minimal)
  return (
    <div className="flex items-center gap-1.5" title={`${freshness.label} - ${ageString}`}>
      <span className={`${classes.dot} ${freshness.bgColor.replace('/20', '')} rounded-full ${freshness.pulseClass}`} />
      <FiClock className={`${classes.icon} ${freshness.color}`} />
    </div>
  );
}

/**
 * Compact freshness badge for cards and lists
 */
export function FreshnessBadge({ timestamp }: { timestamp: string | Date }) {
  return (
    <FreshnessIndicator 
      timestamp={timestamp} 
      showLabel 
      size="sm"
    />
  );
}

/**
 * Inline freshness indicator for headers
 */
export function InlineFreshness({ timestamp }: { timestamp: string | Date }) {
  return (
    <FreshnessIndicator 
      timestamp={timestamp} 
      inline 
      size="sm"
    />
  );
}

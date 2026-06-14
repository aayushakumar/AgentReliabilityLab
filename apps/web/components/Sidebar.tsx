'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart2,
  GitBranch,
  Shield,
  Trophy,
  Play,
  Users,
  Activity,
} from 'lucide-react';
import { clsx } from 'clsx';

const NAV = [
  { href: '/',             label: 'Overview',    icon: Activity },
  { href: '/runs',         label: 'Runs',        icon: Play },
  { href: '/leaderboard',  label: 'Leaderboard', icon: Trophy },
  { href: '/policy',       label: 'Policy',      icon: Shield },
  { href: '/hitl',         label: 'HITL',        icon: Users },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-brand-500 flex items-center justify-center text-white text-xs font-bold">
            ARL
          </div>
          <span className="font-semibold text-sm text-gray-100 leading-tight">
            AgentReliabilityLab
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/' && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                active
                  ? 'bg-brand-600 text-white'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800',
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-gray-800 text-xs text-gray-600">
        v0.1.0 · open-source
      </div>
    </aside>
  );
}

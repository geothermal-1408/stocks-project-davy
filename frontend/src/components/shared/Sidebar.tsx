import { BarChart2, Activity, AlertTriangle, Settings } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/', icon: BarChart2, label: 'Prediction' },
  { to: '/dashboard', icon: Activity, label: 'Dashboard' },
  { to: '/poison', icon: AlertTriangle, label: 'Poison Log' },
  { to: '/admin', icon: Settings, label: 'Admin' },
];

export default function Sidebar() {
  return (
    <nav className="fixed left-0 top-0 h-screen w-[60px] bg-bg-card border-r border-border flex flex-col items-center z-50">
      {/* Logo mark */}
      <div className="w-full h-12 flex items-center justify-center border-b border-border">
        <div className="w-6 h-6 relative">
          <div className="absolute inset-0 border border-accent-mint" style={{ clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)' }} />
        </div>
      </div>

      {/* Nav items */}
      <div className="flex-1 flex flex-col items-center pt-4 gap-2">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `relative w-full flex items-center justify-center h-11 transition-all duration-200 group
              ${isActive
                ? 'text-accent-mint'
                : 'text-text-muted hover:text-text-primary'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <div className="absolute left-0 top-0 h-full w-[2px] bg-accent-mint" />
                )}
                <Icon
                  size={20}
                  className={`transition-all duration-200 ${isActive ? 'fill-accent-mint/20' : ''}`}
                />
                {/* Tooltip */}
                <div className="absolute left-[60px] px-2 py-1 bg-bg-panel border border-border text-xs font-mono text-text-primary opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50">
                  {label}
                </div>
              </>
            )}
          </NavLink>
        ))}
      </div>

      {/* Bottom: Cycle badge */}
      <div className="pb-4 flex flex-col items-center gap-2">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 bg-accent-mint animate-pulse" />
        </div>
        <div className="text-[9px] font-mono text-text-muted tracking-wider leading-tight text-center">
          <span className="text-text-primary">C7</span>
        </div>
      </div>
    </nav>
  );
}

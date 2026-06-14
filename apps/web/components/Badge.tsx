import { clsx } from 'clsx';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'error' | 'warning' | 'info' | 'neutral';
  size?: 'sm' | 'md';
}

const variantClass: Record<string, string> = {
  default:  'bg-gray-700 text-gray-200',
  success:  'bg-emerald-900 text-emerald-300',
  error:    'bg-red-900 text-red-300',
  warning:  'bg-amber-900 text-amber-300',
  info:     'bg-blue-900 text-blue-300',
  neutral:  'bg-gray-800 text-gray-400',
};

export function Badge({ children, variant = 'default', size = 'sm' }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        variantClass[variant],
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, BadgeProps['variant']> = {
    completed:    'success',
    failed:       'error',
    running:      'info',
    pending:      'warning',
    hitl_waiting: 'warning',
    passed:       'success',
    blocked:      'error',
    allowed:      'success',
    hitl:         'warning',
  };
  return <Badge variant={map[status] ?? 'neutral'}>{status}</Badge>;
}

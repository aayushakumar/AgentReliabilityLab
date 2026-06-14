import { clsx } from 'clsx';

interface CardProps {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div className={clsx('bg-gray-900 border border-gray-800 rounded-xl', className)}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: CardProps) {
  return (
    <div className={clsx('px-5 py-4 border-b border-gray-800', className)}>
      {children}
    </div>
  );
}

export function CardTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold text-gray-100">{children}</h3>;
}

export function CardBody({ children, className }: CardProps) {
  return <div className={clsx('p-5', className)}>{children}</div>;
}

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

export function StatCard({ label, value, sub, color = 'text-brand-500' }: StatCardProps) {
  return (
    <Card className="flex flex-col gap-1 p-5">
      <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={clsx('text-3xl font-bold', color)}>{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </Card>
  );
}

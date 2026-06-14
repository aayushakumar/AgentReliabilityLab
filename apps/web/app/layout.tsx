import type { Metadata } from 'next';
import './globals.css';
import { Sidebar } from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'AgentReliabilityLab',
  description: 'Evaluation & observability platform for AI agents',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </body>
    </html>
  );
}

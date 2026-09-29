import type { Metadata } from 'next';
import './style.css';

export const metadata: Metadata = {
  title: 'Learning Studio',
  description: 'Context-aware adaptive learning platform',
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}

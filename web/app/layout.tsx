import type { Metadata } from 'next';
import { IBM_Plex_Mono, Syne } from 'next/font/google';
import IdentityCapture from './components/IdentityCapture';
import './globals.css';

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-mono',
  display: 'swap',
});

const syne = Syne({
  subsets: ['latin'],
  weight: ['700', '800'],
  variable: '--font-syne',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'The +EV Cave',
  description: 'MLB Batter Model — HR, Hits, Total Bases & Strikeouts props, edge-first',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${ibmPlexMono.variable} ${syne.variable} font-mono`}>
        <IdentityCapture />
        {children}
      </body>
    </html>
  );
}

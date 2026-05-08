import type { Metadata } from 'next'
import './globals.css'
import Navbar from '@/components/Navbar'

export const metadata: Metadata = {
  title: 'CryptoStream Analytics',
  description: 'Real-time crypto trade analytics powered by Kafka, Spark, and ADLS',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main className="min-h-screen pt-14">{children}</main>
      </body>
    </html>
  )
}

'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, BarChart2, GitCompare, Cpu } from 'lucide-react'

const links = [
  { href: '/', label: 'DASHBOARD', icon: Activity },
  { href: '/analytics', label: 'ANALYTICS', icon: BarChart2 },
  { href: '/compare', label: 'COMPARE', icon: GitCompare },
  { href: '/pipeline', label: 'PIPELINE', icon: Cpu },
]

export default function Navbar() {
  const path = usePathname()
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#1a1a2e] bg-[#050508]/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-[#00ff88] animate-pulse" />
          <span className="font-display font-800 text-lg tracking-widest text-[#e0e0f0]">
            CRYPTO<span className="text-[#00ff88]">STREAM</span>
          </span>
          <span className="text-[10px] text-[#444466] ml-2 tracking-widest">ANALYTICS</span>
        </div>
        <div className="flex items-center gap-1">
          {links.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}
              className={`flex items-center gap-2 px-4 py-2 text-[11px] tracking-widest transition-all duration-200
                ${path === href
                  ? 'text-[#00ff88] border-b border-[#00ff88]'
                  : 'text-[#444466] hover:text-[#888899]'
                }`}>
              <Icon size={12} />
              {label}
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-[#444466]">
          <span className="blink text-[#00ff88]">●</span>
          <span>LIVE</span>
        </div>
      </div>
    </nav>
  )
}

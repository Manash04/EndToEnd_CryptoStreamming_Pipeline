'use client'
import { useState, useEffect } from 'react'
import { getSummary, formatPrice, formatNumber, signalColor, SYMBOLS, SYMBOL_COLORS } from '@/lib/api'
import LiveTicker from '@/components/LiveTicker'
import { TrendingUp, TrendingDown, Activity, BarChart3, DollarSign, Zap } from 'lucide-react'

function SymbolCard({ sym }: { sym: string }) {
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const color = SYMBOL_COLORS[sym]

  useEffect(() => {
    getSummary(sym).then(setSummary).catch(() => {}).finally(() => setLoading(false))
  }, [sym])

  if (loading) return (
    <div className="card p-5 animate-pulse">
      <div className="text-[11px] tracking-widest mb-2" style={{ color }}>{sym}USDT</div>
      <div className="h-8 bg-[#1a1a2e] rounded mb-3 w-3/4" />
      <div className="h-3 bg-[#1a1a2e] rounded mb-2 w-1/2" />
      <div className="h-3 bg-[#1a1a2e] rounded w-2/3" />
    </div>
  )

  if (!summary) return (
    <div className="card p-5">
      <div className="text-[11px] tracking-widest mb-1" style={{ color }}>{sym}USDT</div>
      <div className="text-[#444466] text-xs mt-2">No data available</div>
      <div className="text-[#333355] text-[10px] mt-1">Run Airflow DAG to populate</div>
    </div>
  )

  const priceChange = (summary.price_close || 0) - (summary.price_open || 0)
  const pctChange = summary.price_open ? (priceChange / summary.price_open) * 100 : 0
  const isUp = priceChange >= 0
  const signalCls = signalColor(summary.strongest_signal)

  return (
    <div className="card p-5 hover:border-[#2a2a4e] transition-colors duration-200">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: color }} />
          <span className="text-[11px] tracking-widest text-[#888899]">{sym}USDT</span>
        </div>
        <span className={`text-[10px] tracking-widest px-2 py-1 rounded-sm ${signalCls} border border-current/20`}>
          {summary.strongest_signal?.replace('_', ' ')}
        </span>
      </div>

      <div className="mb-4">
        <div className="text-[10px] text-[#444466] mb-1">DAILY VWAP</div>
        <div className="text-2xl font-bold tracking-tight" style={{ color }}>
          ${formatPrice(summary.daily_vwap)}
        </div>
        <div className={`text-[11px] mt-1 flex items-center gap-1 ${isUp ? 'text-[#00ff88]' : 'text-[#ff3366]'}`}>
          {isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
          {isUp ? '+' : ''}{pctChange.toFixed(2)}% today
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-[11px]">
        <div>
          <div className="text-[#444466] mb-0.5">VOLUME</div>
          <div className="text-[#e0e0f0]">{formatNumber(summary.total_volume)}</div>
        </div>
        <div>
          <div className="text-[#444466] mb-0.5">TRADES</div>
          <div className="text-[#e0e0f0]">{formatNumber(summary.total_trades, 0)}</div>
        </div>
        <div>
          <div className="text-[#444466] mb-0.5">HIGH</div>
          <div className="text-[#00ff88]">${formatPrice(summary.price_high)}</div>
        </div>
        <div>
          <div className="text-[#444466] mb-0.5">LOW</div>
          <div className="text-[#ff3366]">${formatPrice(summary.price_low)}</div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-[#1a1a2e]">
        <div className="flex justify-between text-[10px] text-[#444466] mb-1">
          <span>BUY</span><span>SELL</span>
        </div>
        <div className="h-1.5 bg-[#1a1a2e] rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${(summary.avg_imbalance || 0.5) * 100}%`,
              background: `linear-gradient(90deg, #00ff88, ${color})`
            }} />
        </div>
        <div className="flex justify-between text-[10px] mt-1">
          <span className="text-[#00ff88]">{((summary.avg_imbalance || 0) * 100).toFixed(1)}%</span>
          <span className="text-[#ff3366]">{(100 - (summary.avg_imbalance || 0) * 100).toFixed(1)}%</span>
        </div>
      </div>
    </div>
  )
}

function StatsBar() {
  const [stats, setStats] = useState({ trades: 0, value: 0 })

  useEffect(() => {
    Promise.all(SYMBOLS.map(s => getSummary(s).catch(() => null))).then(results => {
      const totals = results.reduce((acc, s) => ({
        trades: acc.trades + (s?.total_trades || 0),
        value: acc.value + (s?.total_value_usdt || 0),
      }), { trades: 0, value: 0 })
      setStats(totals)
    })
  }, [])

  return (
    <div className="grid grid-cols-4 gap-3 mb-6">
      {[
        { label: 'TOTAL TRADES TODAY', value: formatNumber(stats.trades, 0), icon: Activity, color: '#00ff88' },
        { label: 'TOTAL VALUE (USD)', value: `$${formatNumber(stats.value)}`, icon: DollarSign, color: '#ffd700' },
        { label: 'SYMBOLS TRACKED', value: '4', icon: BarChart3, color: '#0088ff' },
        { label: 'PIPELINE STATUS', value: 'ACTIVE', icon: Zap, color: '#00ff88' },
      ].map(({ label, value, icon: Icon, color }) => (
        <div key={label} className="card px-4 py-3 flex items-center gap-3">
          <Icon size={16} style={{ color }} />
          <div>
            <div className="text-[10px] text-[#444466] tracking-widest">{label}</div>
            <div className="text-sm font-bold" style={{ color }}>{value}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="mb-8">
        <div className="text-[10px] text-[#444466] tracking-widest mb-2">
          REAL-TIME ANALYTICS // BINANCE STREAM
        </div>
        <h1 className="font-display text-4xl font-800 tracking-tight">
          MARKET <span className="text-[#00ff88] glow-green">OVERVIEW</span>
        </h1>
        <p className="text-[#444466] text-sm mt-2 max-w-lg">
          Live price data from Binance WebSocket. Daily analytics processed by Apache Spark and stored in Azure Data Lake.
        </p>
      </div>

      <div className="mb-6">
        <div className="text-[10px] text-[#444466] tracking-widest mb-3 flex items-center gap-2">
          <span className="blink text-[#00ff88]">●</span>
          LIVE PRICES
        </div>
        <LiveTicker />
      </div>

      <StatsBar />

      <div className="mb-3">
        <div className="text-[10px] text-[#444466] tracking-widest mb-3">
          DAILY ANALYTICS // LATEST SESSION
        </div>
        <div className="grid grid-cols-4 gap-3">
          {SYMBOLS.map(sym => <SymbolCard key={sym} sym={sym} />)}
        </div>
      </div>

      <div className="mt-8 pt-6 border-t border-[#1a1a2e] text-[10px] text-[#444466] flex justify-between">
        <span>DATA SOURCE: BINANCE WEBSOCKET → KAFKA → SPARK → ADLS</span>
        <span>ANALYTICS: VWAP · BUY/SELL IMBALANCE · OHLC</span>
      </div>
    </div>
  )
}
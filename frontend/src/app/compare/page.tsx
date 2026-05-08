'use client'
import { useState, useEffect } from 'react'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'
import { getSummary, formatPrice, formatNumber, signalColor, SYMBOLS, SYMBOL_COLORS } from '@/lib/api'

export default function Compare() {
  const [data, setData] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all(SYMBOLS.map(s => getSummary(s).then(d => [s, d]).catch(() => [s, null])))
      .then(results => {
        const obj: Record<string, any> = {}
        results.forEach(([s, d]) => { obj[s as string] = d })
        setData(obj)
      })
      .finally(() => setLoading(false))
  }, [])

  const metrics = [
    { key: 'total_trades', label: 'TRADES', format: (v: number) => formatNumber(v, 0) },
    { key: 'total_volume', label: 'VOLUME', format: (v: number) => formatNumber(v) },
    { key: 'total_value_usdt', label: 'VALUE (USD)', format: (v: number) => `$${formatNumber(v)}` },
    { key: 'avg_imbalance', label: 'BUY RATIO', format: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: 'daily_vwap', label: 'VWAP', format: (v: number) => `$${formatPrice(v)}` },
  ]

  // Normalize for radar (0-100)
  function normalize(sym: string, key: string): number {
    const vals = SYMBOLS.map(s => data[s]?.[key] || 0)
    const max = Math.max(...vals)
    if (!max) return 0
    return ((data[sym]?.[key] || 0) / max) * 100
  }

  const radarData = ['Trades', 'Volume', 'Value', 'Buy Pressure', 'Imbalance'].map((name, i) => {
    const keys = ['total_trades', 'total_volume', 'total_value_usdt', 'avg_imbalance', 'avg_imbalance']
    const entry: any = { name }
    SYMBOLS.forEach(s => { entry[s] = normalize(s, keys[i]) })
    return entry
  })

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="mb-8">
        <div className="text-[10px] text-[#444466] tracking-widest mb-2">COMPARE // ALL SYMBOLS</div>
        <h1 className="font-display text-4xl font-800 tracking-tight">
          SYMBOL <span className="text-[#0088ff] glow-blue">COMPARISON</span>
        </h1>
        <p className="text-[#444466] text-sm mt-2">Side-by-side comparison of all 4 crypto pairs — latest available data.</p>
      </div>

      {loading ? (
        <div className="text-[#444466] text-sm">Loading comparison data...</div>
      ) : (
        <div className="space-y-6">
          {/* Metrics grid */}
          <div className="card p-6">
            <div className="text-[11px] tracking-widest text-[#444466] mb-4">METRICS COMPARISON</div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-[#1a1a2e]">
                    <th className="text-left py-3 pr-6 text-[#444466] tracking-widest font-normal">METRIC</th>
                    {SYMBOLS.map(s => (
                      <th key={s} className="text-left py-3 pr-6 tracking-widest font-normal"
                        style={{ color: SYMBOL_COLORS[s] }}>{s}USDT</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {metrics.map(({ key, label, format }) => {
                    const vals = SYMBOLS.map(s => data[s]?.[key] || 0)
                    const max = Math.max(...vals)
                    return (
                      <tr key={key} className="border-b border-[#1a1a2e]/50">
                        <td className="py-3 pr-6 text-[#444466] tracking-widest">{label}</td>
                        {SYMBOLS.map(s => {
                          const v = data[s]?.[key] || 0
                          const isMax = v === max && max > 0
                          return (
                            <td key={s} className="py-3 pr-6">
                              <div className={isMax ? 'font-bold' : ''} style={{ color: isMax ? SYMBOL_COLORS[s] : '#888899' }}>
                                {data[s] ? format(v) : '—'}
                              </div>
                              {data[s] && (
                                <div className="mt-1 h-0.5 bg-[#1a1a2e] rounded">
                                  <div className="h-full rounded transition-all"
                                    style={{ width: `${max ? (v / max) * 100 : 0}%`, background: SYMBOL_COLORS[s] }} />
                                </div>
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                  <tr className="border-b border-[#1a1a2e]/50">
                    <td className="py-3 pr-6 text-[#444466] tracking-widest">SIGNAL</td>
                    {SYMBOLS.map(s => (
                      <td key={s} className={`py-3 pr-6 text-[10px] tracking-widest ${signalColor(data[s]?.strongest_signal || '')}`}>
                        {data[s] ? data[s].strongest_signal?.replace('_', ' ') : '—'}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* Radar chart */}
            <div className="card p-6">
              <div className="text-[11px] tracking-widest text-[#444466] mb-4">PERFORMANCE RADAR</div>
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#1a1a2e" />
                  <PolarAngleAxis dataKey="name" tick={{ fill: '#444466', fontSize: 10 }} />
                  {SYMBOLS.map(s => (
                    <Radar key={s} name={s} dataKey={s} stroke={SYMBOL_COLORS[s]}
                      fill={SYMBOL_COLORS[s]} fillOpacity={0.1} strokeWidth={1.5} />
                  ))}
                  <Tooltip contentStyle={{ background: '#0d0d14', border: '1px solid #1a1a2e', fontSize: 11 }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Signal summary */}
            <div className="card p-6">
              <div className="text-[11px] tracking-widest text-[#444466] mb-4">MARKET SIGNALS</div>
              <div className="space-y-4">
                {SYMBOLS.map(s => {
                  const d = data[s]
                  if (!d) return null
                  const imb = d.avg_imbalance || 0
                  return (
                    <div key={s} className="flex items-center gap-4">
                      <div className="w-12 text-[11px] tracking-widest" style={{ color: SYMBOL_COLORS[s] }}>{s}</div>
                      <div className="flex-1">
                        <div className="flex justify-between text-[10px] text-[#444466] mb-1">
                          <span>BUY {(imb * 100).toFixed(1)}%</span>
                          <span>SELL {((1 - imb) * 100).toFixed(1)}%</span>
                        </div>
                        <div className="h-2 bg-[#1a1a2e] rounded-full overflow-hidden">
                          <div className="h-full rounded-full" style={{
                            width: `${imb * 100}%`,
                            background: `linear-gradient(90deg, #00ff88, ${SYMBOL_COLORS[s]})`
                          }} />
                        </div>
                      </div>
                      <div className={`text-[10px] w-24 text-right tracking-widest ${signalColor(d.strongest_signal)}`}>
                        {d.strongest_signal?.replace('_', ' ')}
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="mt-6 pt-4 border-t border-[#1a1a2e]">
                <div className="text-[10px] text-[#444466] mb-3 tracking-widest">VWAP RANKING</div>
                {SYMBOLS
                  .filter(s => data[s])
                  .sort((a, b) => (data[b]?.daily_vwap || 0) - (data[a]?.daily_vwap || 0))
                  .map((s, i) => (
                    <div key={s} className="flex items-center justify-between py-1.5 text-[11px]">
                      <span className="text-[#444466]">#{i + 1}</span>
                      <span style={{ color: SYMBOL_COLORS[s] }}>{s}USDT</span>
                      <span className="text-[#888899]">${formatPrice(data[s]?.daily_vwap)}</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

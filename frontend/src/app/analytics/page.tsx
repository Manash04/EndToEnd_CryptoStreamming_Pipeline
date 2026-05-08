'use client'
import { useState, useEffect } from 'react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { getTrend, getHourly, formatPrice, formatNumber, pressureColor, SYMBOLS, SYMBOL_COLORS } from '@/lib/api'

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card px-3 py-2 text-[11px]">
      <div className="text-[#444466] mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.name} style={{ color: p.color }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(2) : p.value}
        </div>
      ))}
    </div>
  )
}

export default function Analytics() {
  const [selected, setSelected] = useState('BTC')
  const [trend, setTrend] = useState<any[]>([])
  const [hourly, setHourly] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    const yesterdayStr = yesterday.toISOString().split('T')[0]

    Promise.all([
      getTrend(selected, 7).then(d => setTrend(d.trend || [])),
      getHourly(selected, yesterdayStr).then(setHourly),
    ]).finally(() => setLoading(false))
  }, [selected])

  const color = SYMBOL_COLORS[selected]

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="mb-8">
        <div className="text-[10px] text-[#444466] tracking-widest mb-2">ANALYTICS // HISTORICAL DATA</div>
        <h1 className="font-display text-4xl font-800 tracking-tight">
          DEEP <span className="glow-green" style={{ color }}>ANALYTICS</span>
        </h1>
      </div>

      {/* Symbol selector */}
      <div className="flex gap-2 mb-8">
        {SYMBOLS.map(sym => (
          <button key={sym} onClick={() => setSelected(sym)}
            className={`px-6 py-2 text-[11px] tracking-widest border transition-all duration-200 rounded-sm
              ${selected === sym
                ? 'border-current text-current'
                : 'border-[#1a1a2e] text-[#444466] hover:text-[#888899]'
              }`}
            style={selected === sym ? { color: SYMBOL_COLORS[sym], borderColor: SYMBOL_COLORS[sym] } : {}}>
            {sym}USDT
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-[#444466] text-sm">Loading analytics...</div>
      ) : (
        <div className="space-y-6">
          {/* VWAP trend */}
          <div className="card p-6">
            <div className="text-[11px] tracking-widest text-[#444466] mb-4">
              7-DAY VWAP TREND — {selected}USDT
            </div>
            {trend.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={trend.map(d => ({
                  date: d.trade_date?.slice(5),
                  vwap: d.daily_vwap,
                  high: d.price_high,
                  low: d.price_low,
                }))}>
                  <defs>
                    <linearGradient id="vwapGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fill: '#444466', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#444466', fontSize: 10 }} axisLine={false} tickLine={false}
                    tickFormatter={v => `$${formatNumber(v)}`} domain={['auto', 'auto']} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="vwap" stroke={color} fill="url(#vwapGrad)"
                    strokeWidth={2} name="VWAP" dot={{ fill: color, r: 3 }} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-[#444466] text-sm h-[220px] flex items-center justify-center">
                No trend data available yet
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* Hourly volume */}
            <div className="card p-6">
              <div className="text-[11px] tracking-widest text-[#444466] mb-4">
                HOURLY TRADE VOLUME — YESTERDAY
              </div>
              {hourly.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={hourly.map(h => ({
                    hour: `${h.hour}:00`,
                    volume: h.volume,
                    pressure: h.pressure,
                  }))}>
                    <XAxis dataKey="hour" tick={{ fill: '#444466', fontSize: 9 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#444466', fontSize: 9 }} axisLine={false} tickLine={false}
                      tickFormatter={v => formatNumber(v)} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="volume" name="Volume" radius={[2, 2, 0, 0]}>
                      {hourly.map((h, i) => (
                        <Cell key={i} fill={pressureColor(h.pressure)} opacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-[#444466] text-sm h-[200px] flex items-center justify-center">
                  No hourly data yet yesterday
                </div>
              )}
            </div>

            {/* Hourly imbalance */}
            <div className="card p-6">
              <div className="text-[11px] tracking-widest text-[#444466] mb-4">
                BUY/SELL IMBALANCE — YESTERDAY
              </div>
              {hourly.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={hourly.map(h => ({
                    hour: `${h.hour}:00`,
                    buy: (h.imbalance_ratio * 100).toFixed(1),
                    sell: ((1 - h.imbalance_ratio) * 100).toFixed(1),
                  }))}>
                    <XAxis dataKey="hour" tick={{ fill: '#444466', fontSize: 9 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#444466', fontSize: 9 }} axisLine={false} tickLine={false}
                      tickFormatter={v => `${v}%`} domain={[0, 100]} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="buy" name="Buy%" stackId="a" fill="#00ff88" opacity={0.8} />
                    <Bar dataKey="sell" name="Sell%" stackId="a" fill="#ff3366" opacity={0.8} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-[#444466] text-sm h-[200px] flex items-center justify-center">
                  No hourly data yet yesterday
                </div>
              )}
            </div>
          </div>

          {/* Daily stats table */}
          {trend.length > 0 && (
            <div className="card p-6">
              <div className="text-[11px] tracking-widest text-[#444466] mb-4">DAILY BREAKDOWN</div>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[#444466] border-b border-[#1a1a2e]">
                    {['DATE', 'VWAP', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME', 'TRADES', 'SIGNAL'].map(h => (
                      <th key={h} className="text-left py-2 pr-4 tracking-widest font-normal">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...trend].reverse().map(d => (
                    <tr key={d.trade_date} className="border-b border-[#1a1a2e]/50 hover:bg-[#1a1a2e]/30">
                      <td className="py-2 pr-4 text-[#888899]">{d.trade_date}</td>
                      <td className="py-2 pr-4" style={{ color }}>${formatPrice(d.daily_vwap)}</td>
                      <td className="py-2 pr-4 text-[#888899]">${formatPrice(d.price_open)}</td>
                      <td className="py-2 pr-4 text-[#00ff88]">${formatPrice(d.price_high)}</td>
                      <td className="py-2 pr-4 text-[#ff3366]">${formatPrice(d.price_low)}</td>
                      <td className="py-2 pr-4 text-[#888899]">${formatPrice(d.price_close)}</td>
                      <td className="py-2 pr-4 text-[#888899]">{formatNumber(d.total_volume)}</td>
                      <td className="py-2 pr-4 text-[#888899]">{formatNumber(d.total_trades, 0)}</td>
                      <td className={`py-2 text-[10px] ${d.strongest_signal === 'BUY_PRESSURE' ? 'text-[#00ff88]' : d.strongest_signal === 'SELL_PRESSURE' ? 'text-[#ff3366]' : 'text-[#444466]'}`}>
                        {d.strongest_signal?.replace('_', ' ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

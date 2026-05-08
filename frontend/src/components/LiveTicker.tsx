'use client'
import { useEffect, useState, useRef } from 'react'

interface TickerData {
  symbol: string
  price: number
  change: number
  prevPrice: number
}

const SYMBOLS = ['btcusdt', 'ethusdt', 'solusdt', 'bnbusdt']
const DISPLAY = { btcusdt: 'BTC', ethusdt: 'ETH', solusdt: 'SOL', bnbusdt: 'BNB' }

export default function LiveTicker() {
  const [tickers, setTickers] = useState<Record<string, TickerData>>({})
  const [flash, setFlash] = useState<Record<string, 'up' | 'down' | null>>({})
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const streams = SYMBOLS.map(s => `${s}@miniTicker`).join('/')
    const ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      const { data } = JSON.parse(e.data)
      if (!data) return
      const sym = data.s.toLowerCase()
      const newPrice = parseFloat(data.c)
      const openPrice = parseFloat(data.o)
      const change = ((newPrice - openPrice) / openPrice) * 100

      setTickers(prev => {
        const prevPrice = prev[sym]?.price || newPrice
        const direction = newPrice > prevPrice ? 'up' : newPrice < prevPrice ? 'down' : null
        if (direction) {
          setFlash(f => ({ ...f, [sym]: direction }))
          setTimeout(() => setFlash(f => ({ ...f, [sym]: null })), 400)
        }
        return { ...prev, [sym]: { symbol: sym, price: newPrice, change, prevPrice } }
      })
    }

    return () => ws.close()
  }, [])

  return (
    <div className="grid grid-cols-4 gap-3">
      {SYMBOLS.map(sym => {
        const t = tickers[sym]
        const flashColor = flash[sym] === 'up' ? 'bg-[#00ff88]/10' : flash[sym] === 'down' ? 'bg-[#ff3366]/10' : ''
        const changeColor = !t ? '' : t.change >= 0 ? 'text-[#00ff88]' : 'text-[#ff3366]'
        return (
          <div key={sym}
            className={`card p-4 transition-colors duration-300 ${flashColor}`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] tracking-widest text-[#444466]">
                {DISPLAY[sym as keyof typeof DISPLAY]}/USDT
              </span>
              <div className={`text-[10px] px-2 py-0.5 rounded-sm ${!t ? 'bg-[#1a1a2e] text-[#444466]' : t.change >= 0 ? 'bg-[#00ff88]/10 text-[#00ff88]' : 'bg-[#ff3366]/10 text-[#ff3366]'}`}>
                {t ? `${t.change >= 0 ? '+' : ''}${t.change.toFixed(2)}%` : '---'}
              </div>
            </div>
            <div className={`text-2xl font-bold tracking-tight ${t?.change >= 0 ? 'glow-green' : 'glow-red'}`}>
              {t ? `$${t.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '---'}
            </div>
            <div className="text-[10px] text-[#444466] mt-1">LIVE PRICE</div>
          </div>
        )
      })}
    </div>
  )
}

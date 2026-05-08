const API_BASE = '/api/crypto'

export interface Symbol {
  symbol: string
  earliest_date: string
  latest_date: string
  days_available: number
}

export interface DailySummary {
  trade_date: string
  symbol: string
  daily_vwap: number
  total_volume: number
  total_trades: number
  total_value_usdt: number
  price_open: number
  price_close: number
  price_high: number
  price_low: number
  peak_buy_hour: number
  peak_sell_hour: number
  avg_imbalance: number
  strongest_signal: string
}

export interface HourlyData {
  trade_date: string
  symbol: string
  hour: number
  vwap: number
  volume: number
  trade_count: number
  imbalance_ratio: number
  pressure: string
}

export interface TrendData {
  symbol: string
  days: number
  trend: DailySummary[]
}

export async function getSymbols(): Promise<{ symbols: Symbol[] }> {
  const res = await fetch(`${API_BASE}/symbols`, { next: { revalidate: 300 } })
  if (!res.ok) throw new Error('Failed to fetch symbols')
  return res.json()
}

export async function getSummary(symbol: string): Promise<DailySummary> {
  const res = await fetch(`${API_BASE}/summary/${symbol}`, { next: { revalidate: 60 } })
  if (!res.ok) throw new Error(`Failed to fetch summary for ${symbol}`)
  return res.json()
}

export async function getTrend(symbol: string, days = 7): Promise<TrendData> {
  const res = await fetch(`${API_BASE}/trend/${symbol}?days=${days}`, { next: { revalidate: 300 } })
  if (!res.ok) throw new Error(`Failed to fetch trend for ${symbol}`)
  return res.json()
}

export async function getHourly(symbol: string, date: string): Promise<HourlyData[]> {
  const res = await fetch(`${API_BASE}/hourly/${symbol}/${date}`, { next: { revalidate: 60 } })
  if (!res.ok) return []
  return res.json()
}

export async function getCompare(symbols: string, date?: string): Promise<any> {
  const params = new URLSearchParams({ symbols })
  if (date) params.append('trade_date', date)
  const res = await fetch(`${API_BASE}/compare?${params}`, { next: { revalidate: 60 } })
  if (!res.ok) throw new Error('Failed to fetch comparison')
  return res.json()
}

export function formatNumber(n: number, decimals = 2): string {
  if (!n) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(2)}K`
  return n.toFixed(decimals)
}

export function formatPrice(n: number): string {
  if (!n) return '0.00'
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

export function signalColor(signal: string): string {
  if (signal === 'BUY_PRESSURE') return 'text-[#00ff88]'
  if (signal === 'SELL_PRESSURE') return 'text-[#ff3366]'
  return 'text-[#888899]'
}

export function pressureColor(pressure: string): string {
  if (pressure === 'BUY_PRESSURE') return '#00ff88'
  if (pressure === 'SELL_PRESSURE') return '#ff3366'
  return '#888899'
}

export const SYMBOLS = ['BTC', 'ETH', 'SOL', 'BNB']
export const SYMBOL_COLORS: Record<string, string> = {
  BTC: '#ffd700',
  ETH: '#0088ff',
  SOL: '#9945ff',
  BNB: '#f3ba2f',
}

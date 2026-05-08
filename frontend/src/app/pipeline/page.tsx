import { Database, Zap, Cloud, GitBranch, Server, BarChart2, Globe, Clock } from 'lucide-react'

const stack = [
  { name: 'Binance WebSocket', desc: 'Real-time trade stream for BTC, ETH, SOL, BNB', color: '#ffd700', icon: Globe },
  { name: 'Apache Kafka', desc: '4 topics · 3 partitions each · 24hr retention', color: '#00ff88', icon: GitBranch },
  { name: 'Spark Structured Streaming', desc: 'VWAP · buy/sell imbalance · watermarked windows', color: '#0088ff', icon: Zap },
  { name: 'Azure Data Lake Gen2', desc: 'Parquet files · symbol/date partitioning', color: '#0088ff', icon: Cloud },
  { name: 'Apache Airflow', desc: 'Daily batch job at 15:00 UTC · 3-task DAG', color: '#ff3366', icon: Clock },
  { name: 'PostgreSQL', desc: 'daily_analytics · hourly_analytics · pipeline_metrics', color: '#888899', icon: Database },
  { name: 'FastAPI', desc: '5 REST endpoints · Pydantic models · CORS enabled', color: '#00ff88', icon: Server },
  { name: 'Grafana', desc: 'Pipeline monitoring · consumer lag · heartbeat', color: '#ff8c00', icon: BarChart2 },
]

const flow = [
  { step: '01', title: 'INGEST', desc: 'Python producer connects to Binance combined stream WebSocket and publishes normalized trade events to Kafka topics keyed by symbol.' },
  { step: '02', title: 'STREAM', desc: 'Spark Structured Streaming reads from all 4 Kafka topics simultaneously. Computes 1-minute tumbling window VWAP and buy/sell imbalance ratio with 10-second watermark.' },
  { step: '03', title: 'STORE', desc: 'Processed data written to Azure Data Lake Gen2 as Parquet files, partitioned by symbol and date. Checkpoints stored in ADLS for fault tolerance.' },
  { step: '04', title: 'MONITOR', desc: 'Metrics collector polls Spark REST API and Kafka consumer group offsets every 60 seconds. Writes pipeline health metrics to PostgreSQL for Grafana.' },
  { step: '05', title: 'BATCH', desc: 'Airflow DAG triggers daily at 15:00 UTC. PySpark batch job reads previous day Parquet from ADLS, computes daily OHLC + hourly breakdowns, writes to PostgreSQL.' },
  { step: '06', title: 'SERVE', desc: 'FastAPI reads from PostgreSQL and exposes REST endpoints. This Next.js frontend calls the API and renders analytics with live Binance WebSocket prices.' },
]

export default function Pipeline() {
  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="mb-10">
        <div className="text-[10px] text-[#444466] tracking-widest mb-2">PIPELINE // ARCHITECTURE</div>
        <h1 className="font-display text-4xl font-800 tracking-tight">
          HOW IT <span className="text-[#9945ff]" style={{ textShadow: '0 0 20px rgba(153,69,255,0.6)' }}>WORKS</span>
        </h1>
        <p className="text-[#444466] text-sm mt-2 max-w-2xl">
          An end-to-end real-time streaming data pipeline built with industry-standard tools.
          From raw WebSocket tick data to actionable analytics in under 60 seconds.
        </p>
      </div>

      {/* Flow steps */}
      <div className="grid grid-cols-3 gap-4 mb-10">
        {flow.map(({ step, title, desc }) => (
          <div key={step} className="card p-5 hover:border-[#2a2a4e] transition-colors">
            <div className="text-[#444466] text-4xl font-bold mb-3 font-display">{step}</div>
            <div className="text-[11px] tracking-widest text-[#00ff88] mb-2">{title}</div>
            <div className="text-[#888899] text-[12px] leading-relaxed">{desc}</div>
          </div>
        ))}
      </div>

      {/* Tech stack */}
      <div className="card p-6 mb-6">
        <div className="text-[11px] tracking-widest text-[#444466] mb-6">TECHNOLOGY STACK</div>
        <div className="grid grid-cols-4 gap-4">
          {stack.map(({ name, desc, color, icon: Icon }) => (
            <div key={name} className="border border-[#1a1a2e] p-4 rounded-sm hover:border-[#2a2a4e] transition-colors">
              <Icon size={16} className="mb-2" style={{ color }} />
              <div className="text-[11px] font-bold mb-1" style={{ color }}>{name}</div>
              <div className="text-[10px] text-[#444466] leading-relaxed">{desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Data schema */}
      <div className="grid grid-cols-2 gap-4">
        <div className="card p-5">
          <div className="text-[11px] tracking-widest text-[#444466] mb-4">KAFKA MESSAGE SCHEMA</div>
          <pre className="text-[11px] text-[#888899] leading-relaxed">{`{
  "event_type":            "trade",
  "symbol":                "BTCUSDT",
  "price":                 77864.68,
  "quantity":              0.00412,
  "trade_value_usdt":      320.80,
  "trade_time_ms":         1714024800000,
  "is_buyer_market_maker": false,
  "ingested_at":           "2026-04-24T09:00:00"
}`}</pre>
        </div>
        <div className="card p-5">
          <div className="text-[11px] tracking-widest text-[#444466] mb-4">API RESPONSE SCHEMA</div>
          <pre className="text-[11px] text-[#888899] leading-relaxed">{`{
  "trade_date":      "2026-04-24",
  "symbol":          "BTCUSDT",
  "daily_vwap":      77696.93,
  "total_trades":    234423,
  "price_high":      78057.65,
  "price_low":       77402.01,
  "avg_imbalance":   0.4749,
  "strongest_signal": "NEUTRAL"
}`}</pre>
        </div>
      </div>

      <div className="mt-8 pt-6 border-t border-[#1a1a2e] text-[10px] text-[#444466] flex justify-between">
        <span>BUILT WITH: PYTHON · JAVA · TYPESCRIPT</span>
        <span>INFRASTRUCTURE: DOCKER · AZURE · KAFKA · SPARK</span>
      </div>
    </div>
  )
}

import React from "react"
import { useEffect, useRef, useState } from "react"
import { Chart, registerables } from "chart.js"

Chart.register(...registerables)

const API_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "http://localhost:8000"

function ChartView({ chart }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current || !chart?.config) return undefined
    chartRef.current?.destroy()
    chartRef.current = new Chart(canvasRef.current, chart.config)
    return () => chartRef.current?.destroy()
  }, [chart])

  if (!chart?.config) return <p className="muted">No chart available.</p>
  return <div className="chart-wrap"><canvas ref={canvasRef} /></div>
}

function App() {
  const [question, setQuestion] = useState("")
  const [analysis, setAnalysis] = useState(null)
  const [dashboard, setDashboard] = useState([])
  const [loading, setLoading] = useState(false)
  const [dashboardLoading, setDashboardLoading] = useState(true)
  const [error, setError] = useState("")
  const [refreshing, setRefreshing] = useState("")
  const [refreshMessages, setRefreshMessages] = useState({})
  const [removing, setRemoving] = useState("")
  const [pendingRemove, setPendingRemove] = useState(null)

  async function loadDashboard() {
    setDashboardLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/dashboard`)
      const body = await response.json()
      if (!response.ok || !body.success) throw new Error(body.error?.message || "Could not load dashboard.")
      setDashboard(body.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setDashboardLoading(false)
    }
  }

  useEffect(() => { loadDashboard() }, [])

  async function analyze(event) {
    event.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError("")
    setAnalysis(null)
    try {
      const response = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      })
      const body = await response.json()
      if (!response.ok || body.success === false && body.error) throw new Error(body.error?.message || "Analysis failed.")
      setAnalysis(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function pinAnalysis() {
    if (!analysis?.chart && !analysis?.chart_options?.[0]) return
    setError("")
    try {
      const selectedAnalysis = analysis.chart ? analysis : { ...analysis, chart: analysis.chart_options[0] }
      const response = await fetch(`${API_URL}/api/dashboard/pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ analysis: selectedAnalysis }),
      })
      const body = await response.json()
      if (!response.ok || !body.success) throw new Error(body.error?.message || "Could not pin chart.")
      await loadDashboard()
    } catch (err) {
      setError(err.message)
    }
  }

  async function refresh(item) {
    setRefreshing(item.id)
    setError("")
    try {
      const response = await fetch(`${API_URL}/api/dashboard/${item.id}/refresh`, { method: "POST" })
      const body = await response.json()
      if (!response.ok || !body.success) throw new Error(body.error?.message || "Refresh failed.")
      setRefreshMessages((current) => ({ ...current, [item.id]: body.change?.summary || "Refreshed." }))
      await loadDashboard()
    } catch (err) {
      setRefreshMessages((current) => ({ ...current, [item.id]: err.message }))
    } finally {
      setRefreshing("")
    }
  }

  async function remove(item) {
    setRemoving(item.id)
    setError("")
    try {
      const response = await fetch(`${API_URL}/api/dashboard/${item.id}`, { method: "DELETE" })
      const body = await response.json()
      if (!response.ok || !body.success) throw new Error(body.error?.message || "Could not remove pinned analysis.")
      setPendingRemove(null)
      await loadDashboard()
    } catch (err) {
      setError(err.message)
    } finally {
      setRemoving("")
    }
  }

  const displayedChart = analysis?.chart || analysis?.chart_options?.[0]
  const suggestions = ["Show monthly revenue trend in 2017", "Top product categories by revenue", "Review score distribution"]

  return (
    <main className="page">
      <header className="header">
        <a className="brand" href="/" aria-label="CerebralZip Analytics home">
          <span className="brand-mark" aria-hidden="true">CZ</span>
          <span><strong>CerebralZip</strong><small>Analytics workspace</small></span>
        </a>
        <div className="header-status"><span className="status-dot" /> Data assistant online</div>
      </header>

      <section className="query-panel">
        <div className="eyebrow">CerebralZip Analytics</div>
        <h1>Ask a question<br /><span>about your data.</span></h1>
        <p className="query-intro">Explore your e-commerce data in plain language.</p>
        <form onSubmit={analyze} className="query-form">
          <div className="input-wrap">
            <span className="input-icon" aria-hidden="true">?</span>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="e.g. Show monthly revenue trend in 2017"
              aria-label="Ask an analytics question"
            />
          </div>
          <button className="primary-button" type="submit" disabled={loading}>{loading ? "Analyzing..." : "Analyze"}<span aria-hidden="true">-&gt;</span></button>
        </form>
        <div className="suggestions" aria-label="Suggested questions">
          <span>Try asking</span>
          {suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => setQuestion(suggestion)}>{suggestion}</button>)}
        </div>
        {error && <p className="error" role="alert"><strong>Something went wrong</strong>{error}</p>}
      </section>

      <section className="panel result-section">
        <div className="section-heading">
          <div><h2>Analysis</h2></div>
          {analysis && !analysis.error && <span className="result-badge">Ready</span>}
        </div>
        {!analysis && !loading && <div className="state empty-state"><span className="state-icon" aria-hidden="true">+</span><strong>No analysis yet</strong><span>Ask a question above to see a chart and insight.</span></div>}
        {loading && <div className="state loading-state"><span className="loader" aria-hidden="true" /><strong>Finding your answer...</strong><span>We are preparing the right analysis and chart.</span></div>}
        {analysis?.chart === null && <div className="state"><strong>No chartable results</strong><span>{analysis.message || "No results available."}</span></div>}
        {analysis?.error && <p className="error inline-error" role="alert">{analysis.error.message}</p>}
        {displayedChart && (
          <>
            <div className="chart-card"><ChartView chart={displayedChart} /></div>
            <dl className="details">
              <div><dt>Chart type</dt><dd><span className="type-pill">{displayedChart.type}</span></dd></div>
              <div><dt>Why this view</dt><dd>{displayedChart.justification}</dd></div>
            </dl>
            {analysis.insight && <div className="insight"><span className="insight-icon" aria-hidden="true">i</span><p><strong>Key insight</strong>{analysis.insight}</p></div>}
            <button className="secondary-button" onClick={pinAnalysis} type="button"><span aria-hidden="true">+</span> Pin chart</button>
          </>
        )}
      </section>

      <section className="panel">
        <div className="section-heading"><div><h2>Pinned analyses <span className="count-badge">{dashboard.length}</span></h2></div><button className="ghost-button" type="button" onClick={loadDashboard}><span aria-hidden="true">↻</span> Reload</button></div>
        {dashboardLoading && <div className="dashboard-loading"><span /><span /><span /></div>}
        {!dashboardLoading && dashboard.length === 0 && <div className="state dashboard-empty"><span className="state-icon" aria-hidden="true">+</span><strong>No pinned charts yet</strong><span>Pin useful analyses to build your personal dashboard.</span></div>}
        <div className="dashboard-list">
          {dashboard.map((item) => (
            <article className="dashboard-item" key={item.id}>
              <div className="dashboard-item-heading"><div><h3>{item.question}</h3></div><span className="type-pill">{item.chart?.type || "chart"}</span></div>
              <div className="chart-card compact-chart"><ChartView chart={item.chart} /></div>
              {item.insight && <div className="insight compact-insight"><span className="insight-icon" aria-hidden="true">i</span><p>{item.insight}</p></div>}
              <div className="dashboard-actions">
                <button className="secondary-button" type="button" onClick={() => refresh(item)} disabled={refreshing === item.id || removing === item.id}>
                  {refreshing === item.id ? "Refreshing..." : "Refresh"}
                </button>
                <button className="remove-button" type="button" onClick={() => setPendingRemove(item)} disabled={refreshing === item.id || removing === item.id}>Remove</button>
              </div>
              {refreshMessages[item.id] && <p className="refresh-message" role="status"><span aria-hidden="true">&#10003;</span>{refreshMessages[item.id]}</p>}
            </article>
          ))}
        </div>
      </section>
      {pendingRemove && (
        <div className="dialog-backdrop" role="presentation">
          <div className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="remove-title">
            <h2 id="remove-title">Remove this pinned analysis?</h2>
            <p>{pendingRemove.question}</p>
            <div className="dialog-actions">
              <button className="ghost-button" type="button" onClick={() => setPendingRemove(null)} disabled={removing === pendingRemove.id}>Cancel</button>
              <button className="remove-confirm-button" type="button" onClick={() => remove(pendingRemove)} disabled={removing === pendingRemove.id}>{removing === pendingRemove.id ? "Removing..." : "Remove"}</button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}

export default App

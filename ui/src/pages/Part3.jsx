import { useEffect, useState } from 'react'

// ── Helper components ─────────────────────────────────────────────────────────

function VerdictBadge({ verdict }) {
  return (
    <span className={`badge rounded-pill verdict-${verdict}`}>
      {verdict === 'good' ? '✓ GOOD' : '✗ BAD'}
    </span>
  )
}

function ScoreBar({ score }) {
  const pct = Math.min(100, Math.max(0, score))
  return (
    <div className="d-flex align-items-center gap-2">
      <div className="score-bar-wrap">
        <div className={`score-bar ${score >= 62 ? 'good' : 'bad'}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="fw-bold">{score}</span>
    </div>
  )
}

function DimBar({ label, value, max, isWeakest }) {
  const pct = Math.round((value / max) * 100)
  const cls = pct >= 70 ? 'high' : pct >= 40 ? 'mid' : 'low'
  return (
    <div className="mb-2">
      <div className="d-flex justify-content-between mb-1">
        <span style={{ fontSize: '0.78rem', color: isWeakest ? '#e03131' : '#495057', fontWeight: isWeakest ? 700 : 400 }}>
          {label} {isWeakest && <span style={{ fontSize: '0.65rem', background: '#ffe3e3', color: '#c92a2a', padding: '1px 5px', borderRadius: 8, marginLeft: 4 }}>WEAKEST</span>}
        </span>
        <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>{value}/{max}</span>
      </div>
      <div className="dim-bar-wrap" style={{ height: 10 }}>
        <div className={`dim-bar ${cls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Pipeline command block ────────────────────────────────────────────────────

function CommandBlock({ cmd }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <div className="position-relative">
      <pre style={{
        background: '#1e1e2e', color: '#cdd6f4', borderRadius: 8,
        padding: '12px 16px', fontSize: '0.82rem', margin: 0, overflowX: 'auto'
      }}>{cmd}</pre>
      <button
        onClick={copy}
        style={{
          position: 'absolute', top: 8, right: 8,
          background: copied ? '#2f9e44' : '#3b5bdb', color: '#fff',
          border: 'none', borderRadius: 6, padding: '2px 10px',
          fontSize: '0.7rem', cursor: 'pointer'
        }}
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
    </div>
  )
}

// ── Main Part3 component ──────────────────────────────────────────────────────

export default function Part3() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [runList, setRunList] = useState([])

  useEffect(() => {
    fetch('/api/pipeline/latest')
      .then(r => { if (!r.ok) throw new Error('no data'); return r.json() })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))

    fetch('/api/pipeline/list')
      .then(r => r.json())
      .then(setRunList)
      .catch(() => {})
  }, [])

  const meta = data?.meta || {}
  const agg = data?.aggregate || {}
  const results = data?.results || []
  const comparison = data?.comparison || null
  const suggestions = data?.suggestions || null
  const dimAvgs = agg.dim_averages || {}
  const weakest = agg.weakest_dimension

  const DIM_LABELS = {
    language_handling: 'Language Handling',
    protocol_adherence: 'Protocol Adherence',
    discovery_quality: 'Discovery Quality',
    empathy_tone: 'Empathy & Tone',
  }
  const DIM_MAX = {
    language_handling: 15,
    protocol_adherence: 15,
    discovery_quality: 10,
    empathy_tone: 10,
  }

  return (
    <div className="container">

      {/* Page header */}
      <div className="mb-4">
        <h4 className="fw-bold mb-0">Part 3 — The Architect</h4>
        <p className="text-muted small mb-0">
          Reusable prompt iteration pipeline · Simulate any prompt against any transcripts · Compare in one command
        </p>
      </div>

      {/* Pipeline commands */}
      <div className="card border-0 shadow-sm mb-4">
        <div className="card-header bg-white py-3">
          <span className="fw-semibold">Pipeline Commands</span>
        </div>
        <div className="card-body">
          <div className="mb-3">
            <div className="small text-muted mb-1 fw-semibold">Basic run — simulate + score all transcripts</div>
            <CommandBlock cmd="python run_pipeline.py --prompt system-prompt.md --transcripts transcripts/" />
          </div>
          <div className="mb-3">
            <div className="small text-muted mb-1 fw-semibold">Compare two prompts — A/B test in one command</div>
            <CommandBlock cmd={"python run_pipeline.py \\\n  --prompt system-prompt-fixed.md \\\n  --baseline system-prompt.md \\\n  --transcripts transcripts/"} />
          </div>
          <div>
            <div className="small text-muted mb-1 fw-semibold">With auto-suggestions (bonus)</div>
            <CommandBlock cmd="python run_pipeline.py --prompt system-prompt.md --transcripts transcripts/ --suggest" />
          </div>
        </div>
      </div>

      {/* No data state */}
      {!loading && error && (
        <div className="alert alert-warning mb-4">
          <strong>No pipeline results yet.</strong> Run{' '}
          <code>python run_pipeline.py --prompt system-prompt.md --transcripts transcripts/</code> first.
        </div>
      )}

      {loading && (
        <div className="loading-wrap">
          <div className="spinner-border text-secondary" />
          <p className="mt-3">Loading pipeline results...</p>
        </div>
      )}

      {data && (
        <>
          {/* Run info banner */}
          <div className="d-flex flex-wrap gap-2 mb-4">
            <span className="badge bg-light text-dark border">
              Prompt: {meta.prompt_file?.split('/').pop() || meta.prompt_file}
            </span>
            <span className="badge bg-light text-dark border">Model: {meta.model}</span>
            <span className="badge bg-light text-dark border">Max turns/call: {meta.max_turns_per_call}</span>
            <span className="badge bg-light text-dark border">Cost: ${meta.total_cost_usd}</span>
            <span className="badge bg-light text-dark border">{new Date(meta.timestamp).toLocaleString()}</span>
          </div>

          {/* Stat cards */}
          <div className="row g-3 mb-4">
            <div className="col-6 col-md-3">
              <div className="card stat-card p-3">
                <div className="stat-value">{agg.mean_score}</div>
                <div className="stat-label">Mean Score / 100</div>
              </div>
            </div>
            <div className="col-6 col-md-3">
              <div className="card stat-card p-3" style={{ background: '#d3f9d8' }}>
                <div className="stat-value text-success">{agg.good_count}</div>
                <div className="stat-label">Good ({agg.good_pct}%)</div>
              </div>
            </div>
            <div className="col-6 col-md-3">
              <div className="card stat-card p-3" style={{ background: '#ffe3e3' }}>
                <div className="stat-value text-danger">{agg.bad_count}</div>
                <div className="stat-label">Bad ({100 - agg.good_pct}%)</div>
              </div>
            </div>
            <div className="col-6 col-md-3">
              <div className="card stat-card p-3">
                <div className="stat-value text-muted">{meta.total_calls}</div>
                <div className="stat-label">Calls Simulated</div>
              </div>
            </div>
          </div>

          {/* Dimension averages */}
          <div className="row g-3 mb-4">
            <div className="col-md-5">
              <div className="card border-0 shadow-sm p-3 h-100">
                <div className="fw-semibold small mb-3">LLM Dimension Averages</div>
                {Object.entries(DIM_LABELS).map(([key, label]) => (
                  <DimBar
                    key={key}
                    label={label}
                    value={dimAvgs[key] || 0}
                    max={DIM_MAX[key]}
                    isWeakest={key === weakest}
                  />
                ))}
              </div>
            </div>

            {/* Comparison panel */}
            {comparison && (
              <div className="col-md-7">
                <div className="card border-0 shadow-sm p-3 h-100">
                  <div className="fw-semibold small mb-3">Prompt Comparison</div>
                  <div className="d-flex gap-3 mb-3">
                    <div className="text-center flex-fill p-3 rounded" style={{ background: '#fff5f5' }}>
                      <div className="text-muted small mb-1">Baseline</div>
                      <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#e03131' }}>
                        {comparison.baseline_mean}
                      </div>
                      <div className="text-muted small">{comparison.baseline_prompt}</div>
                    </div>
                    <div className="d-flex align-items-center">
                      <span style={{ fontSize: '1.5rem', color: '#adb5bd' }}>→</span>
                    </div>
                    <div className="text-center flex-fill p-3 rounded" style={{ background: '#f4fdf4' }}>
                      <div className="text-muted small mb-1">Current</div>
                      <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#2f9e44' }}>
                        {comparison.current_mean}
                      </div>
                      <div className="text-muted small">{comparison.current_prompt}</div>
                    </div>
                  </div>
                  <div className="text-center mb-3">
                    <span style={{
                      fontSize: '1.1rem', fontWeight: 700,
                      color: comparison.delta_mean > 0 ? '#2f9e44' : comparison.delta_mean < 0 ? '#e03131' : '#868e96'
                    }}>
                      {comparison.delta_mean > 0 ? '+' : ''}{comparison.delta_mean} pts — {comparison.verdict}
                    </span>
                  </div>
                  {comparison.per_call_deltas?.length > 0 && (
                    <div style={{ maxHeight: 160, overflowY: 'auto' }}>
                      <table className="table table-sm mb-0" style={{ fontSize: '0.8rem' }}>
                        <thead>
                          <tr>
                            <th>Call</th>
                            <th>Before</th>
                            <th>After</th>
                            <th>Delta</th>
                            <th>Change</th>
                          </tr>
                        </thead>
                        <tbody>
                          {comparison.per_call_deltas.map(p => (
                            <tr key={p.call_id}>
                              <td style={{ fontFamily: 'monospace' }}>{p.call_id}</td>
                              <td>{p.baseline_score}</td>
                              <td>{p.current_score}</td>
                              <td style={{ color: p.delta > 0 ? '#2f9e44' : p.delta < 0 ? '#e03131' : '#868e96', fontWeight: 600 }}>
                                {p.delta > 0 ? '+' : ''}{p.delta}
                              </td>
                              <td>
                                {p.flipped && <span style={{ fontSize: '0.65rem', background: '#d3f9d8', color: '#2b8a3e', padding: '1px 6px', borderRadius: 8, fontWeight: 700 }}>bad→good</span>}
                                {p.worsened && <span style={{ fontSize: '0.65rem', background: '#ffe3e3', color: '#c92a2a', padding: '1px 6px', borderRadius: 8, fontWeight: 700 }}>good→bad</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Per-call results table */}
          <div className="card border-0 shadow-sm mb-4">
            <div className="card-header bg-white border-bottom py-3">
              <span className="fw-semibold">Simulated Call Scores</span>
              <span className="text-muted small ms-2">Scored with same rubric as Part 1</span>
            </div>
            <div className="table-responsive">
              <table className="table calls-table mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Call</th>
                    <th>Customer</th>
                    <th>Simulated Disposition</th>
                    <th>Original</th>
                    <th>Score</th>
                    <th>Rule / LLM</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {[...results].sort((a, b) => b.score - a.score).map(r => (
                    <tr key={r.call_id} style={{ cursor: 'default' }}>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: '#495057' }}>{r.call_id}</td>
                      <td>{r.customer_name}</td>
                      <td><span className="badge bg-secondary">{r.disposition}</span></td>
                      <td><span className="badge bg-light text-muted border">{r.original_disposition}</span></td>
                      <td><ScoreBar score={r.score} /></td>
                      <td className="text-muted small">{r.rule_score} / {r.llm_score}</td>
                      <td><VerdictBadge verdict={r.verdict} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Auto-suggestions */}
          {suggestions && (
            <div className="card border-0 shadow-sm mb-4">
              <div className="card-header bg-white py-3">
                <span className="fw-semibold">Auto-Generated Prompt Improvement Suggestions</span>
                <span className="badge bg-primary ms-2 small">Bonus</span>
              </div>
              <div className="card-body">
                <pre style={{
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  fontSize: '0.84rem', color: '#343a40', margin: 0
                }}>
                  {suggestions}
                </pre>
              </div>
            </div>
          )}

          {/* Run history */}
          {runList.length > 1 && (
            <div className="card border-0 shadow-sm mb-4">
              <div className="card-header bg-white py-3">
                <span className="fw-semibold">Run History</span>
                <span className="text-muted small ms-2">{runList.length} pipeline runs</span>
              </div>
              <div className="table-responsive">
                <table className="table table-sm mb-0" style={{ fontSize: '0.82rem' }}>
                  <thead className="table-light">
                    <tr>
                      <th>Timestamp</th>
                      <th>Prompt</th>
                      <th>Mean Score</th>
                      <th>Good %</th>
                      <th>Compare?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runList.map((r, i) => (
                      <tr key={i}>
                        <td className="text-muted">{new Date(r.timestamp).toLocaleString()}</td>
                        <td style={{ fontFamily: 'monospace' }}>{r.prompt_file?.split('/').pop()}</td>
                        <td><strong>{r.mean_score}</strong></td>
                        <td>{r.good_pct}%</td>
                        <td>
                          {r.has_comparison
                            ? <span style={{ color: '#2f9e44', fontSize: '0.72rem', fontWeight: 700 }}>vs baseline</span>
                            : <span className="text-muted">—</span>
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

    </div>
  )
}

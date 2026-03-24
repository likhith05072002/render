import { useEffect, useState } from 'react'

// ── Static flaw definitions (no API needed) ──────────────────────────────────
const FLAWS = [
  {
    id: 'FIX 1',
    title: 'switch_language() never triggered',
    desc: 'Defined in Available Functions but absent from every phase prompt. Agent had no rule to call it.',
    calls: ['call_02', 'call_03', 'call_07'],
    color: '#ffe3e3',
    textColor: '#c92a2a',
  },
  {
    id: 'FIX 2',
    title: 'No UTR escalation dead-end',
    desc: '"Collect details then end_call" — but no stop condition when UTR is already provided and cannot be verified.',
    calls: ['call_03'],
    color: '#fff3bf',
    textColor: '#e67700',
  },
  {
    id: 'FIX 3',
    title: 'No inbound callback protocol',
    desc: 'Opening assumed cold outbound only. Inbound/warm-lead calls were treated as cold calls from scratch.',
    calls: ['call_09'],
    color: '#e9ecef',
    textColor: '#495057',
  },
  {
    id: 'FIX 4',
    title: 'end_call() only mandated in Phase 4',
    desc: 'All other exit paths (language barrier, dispute, silence, connectivity) left end_call() implicit.',
    calls: ['call_02', 'call_04', 'call_07'],
    color: '#d0ebff',
    textColor: '#1864ab',
  },
  {
    id: 'FIX 5',
    title: 'Circular exchange rule undefined',
    desc: '"5-6 circular exchanges" had no minimum threshold and confused "confused borrower" with "circular borrower".',
    calls: ['call_10'],
    color: '#e3fafc',
    textColor: '#0c8599',
  },
]

// ── Helper components ─────────────────────────────────────────────────────────

function VerdictBadge({ verdict }) {
  return (
    <span className={`badge rounded-pill verdict-${verdict}`}>
      {verdict === 'good' ? '✓ GOOD' : '✗ BAD'}
    </span>
  )
}

function ScoreDelta({ delta }) {
  const color = delta > 0 ? '#2f9e44' : delta < 0 ? '#e03131' : '#868e96'
  const sign = delta > 0 ? '+' : ''
  return (
    <span style={{ color, fontWeight: 700, fontSize: '1.1rem' }}>
      {sign}{delta} pts
    </span>
  )
}

function DimBar({ label, value, max }) {
  const pct = Math.round((value / max) * 100)
  const cls = pct >= 70 ? 'high' : pct >= 40 ? 'mid' : 'low'
  return (
    <div className="mb-2">
      <div className="d-flex justify-content-between mb-1">
        <span style={{ fontSize: '0.78rem', color: '#495057' }}>{label}</span>
        <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>{value}/{max}</span>
      </div>
      <div className="dim-bar-wrap">
        <div className={`dim-bar ${cls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function FixTag({ fix, applied }) {
  const bg = applied ? '#d3f9d8' : '#ffe3e3'
  const color = applied ? '#2b8a3e' : '#c92a2a'
  return (
    <span style={{
      background: bg, color, fontSize: '0.68rem', fontWeight: 700,
      padding: '2px 8px', borderRadius: 10, marginRight: 4, whiteSpace: 'nowrap'
    }}>
      {applied ? '✓' : '✗'} {fix}
    </span>
  )
}

function SimulationDetail({ sim }) {
  const [showTranscript, setShowTranscript] = useState(false)
  const { before, after, fix_impact, improvements, failure_reason, simulated_transcript, simulated_fn_calls } = sim

  return (
    <div className="mt-3 border-top pt-3">

      {/* Before / After score bars */}
      <div className="row g-3 mb-3">
        <div className="col-6">
          <div className="card border-0 p-3" style={{ background: '#fff5f5' }}>
            <div className="small text-muted fw-semibold mb-2">BEFORE (original)</div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#e03131' }}>{before.score}</div>
            <VerdictBadge verdict={before.verdict} />
            <div className="mt-2">
              <span className="badge bg-secondary">{before.disposition}</span>
            </div>
            <div className="text-muted small mt-1">{before.rule_score} rule + {before.llm_score} LLM</div>
          </div>
        </div>
        <div className="col-6">
          <div className="card border-0 p-3" style={{ background: '#f4fdf4' }}>
            <div className="small text-muted fw-semibold mb-2">AFTER (fixed prompt)</div>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#2f9e44' }}>{after.score}</div>
            <VerdictBadge verdict={after.verdict} />
            <div className="mt-2">
              <span className="badge bg-secondary">{after.disposition}</span>
            </div>
            <div className="text-muted small mt-1">{after.rule_score} rule + {after.llm_score} LLM</div>
          </div>
        </div>
      </div>

      {/* LLM judge breakdown */}
      <div className="mb-3">
        <div className="fw-semibold small mb-2" style={{ color: '#495057' }}>LLM Judge Breakdown (after)</div>
        <DimBar label="Language handling" value={after.llm_breakdown.language_handling} max={15} />
        <DimBar label="Protocol adherence" value={after.llm_breakdown.protocol_adherence} max={15} />
        <DimBar label="Discovery quality" value={after.llm_breakdown.discovery_quality} max={10} />
        <DimBar label="Empathy & tone" value={after.llm_breakdown.empathy_tone} max={10} />
        {after.reasoning && (
          <div className="small text-muted mt-2 fst-italic">
            Judge: {after.reasoning}
          </div>
        )}
      </div>

      {/* Fix impact causality */}
      {fix_impact && fix_impact.length > 0 && (
        <div className="mb-3">
          <div className="fw-semibold small mb-2" style={{ color: '#495057' }}>Fix Causality</div>
          {fix_impact.map((fi, i) => (
            <div key={i} className="d-flex align-items-start gap-2 mb-2 p-2 rounded"
              style={{ background: fi.applied ? '#f4fdf4' : '#fff5f5', border: `1px solid ${fi.applied ? '#b2f2bb' : '#ffc9c9'}` }}>
              <FixTag fix={fi.fix} applied={fi.applied} />
              <div>
                <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{fi.effect}</div>
                <div style={{ fontSize: '0.72rem', color: '#868e96' }}>{fi.definition}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Improvements list */}
      {improvements && improvements.length > 0 && (
        <div className="mb-3">
          <div className="fw-semibold small mb-2" style={{ color: '#495057' }}>Key Improvements</div>
          {improvements.map((imp, i) => (
            <div key={i} className="mb-2 p-2 rounded" style={{ background: '#f8f9fa', border: '1px solid #e9ecef' }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#495057', marginBottom: 2 }}>{imp.flaw}</div>
              <div style={{ fontSize: '0.8rem' }}>
                <span style={{ color: '#c92a2a' }}>Before: </span>{imp.before}
              </div>
              <div style={{ fontSize: '0.8rem' }}>
                <span style={{ color: '#2b8a3e' }}>After: </span>{imp.after}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#1971c2', marginTop: 2 }}>Impact: {imp.impact}</div>
            </div>
          ))}
        </div>
      )}

      {/* Failure transparency */}
      {failure_reason && (
        <div className="alert alert-warning py-2 mb-3" style={{ fontSize: '0.82rem' }}>
          <strong>Partial fix:</strong> {failure_reason}
        </div>
      )}

      {/* Simulated transcript toggle */}
      <button
        className="btn btn-sm btn-outline-secondary mb-2"
        onClick={() => setShowTranscript(v => !v)}
      >
        {showTranscript ? 'Hide' : 'Show'} simulated transcript
        {simulated_fn_calls?.length > 0 && (
          <span className="badge bg-primary ms-2">{simulated_fn_calls.length} fn calls</span>
        )}
      </button>

      {showTranscript && (
        <div className="transcript-wrap border rounded" style={{ maxHeight: 380 }}>
          {simulated_transcript?.map((turn, i) => (
            <div key={i}
              className={`turn-row ${turn.speaker === 'agent' ? 'agent-row' : 'customer-row'}`}
              style={turn.function_calls?.length ? { borderLeft: '3px solid #2f9e44' } : {}}>
              <div className="turn-num">{turn.turn}</div>
              <div className="turn-body">
                <span className={`turn-speaker ${turn.speaker}`}>
                  {turn.speaker.toUpperCase()}
                </span>
                {turn.function_calls?.map(fn => (
                  <span key={fn} style={{
                    fontSize: '0.62rem', background: '#d3f9d8', color: '#2b8a3e',
                    padding: '1px 6px', borderRadius: 8, marginLeft: 6, fontWeight: 700
                  }}>
                    {fn}()
                  </span>
                ))}
                <div className="turn-text">{turn.text || <em style={{ color: '#adb5bd' }}>—</em>}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ComparisonCard({ sim }) {
  const [expanded, setExpanded] = useState(false)
  const delta = sim.after.score - sim.before.score
  const fixesApplied = sim.fix_impact?.filter(f => f.applied) || []
  const fixesFailed = sim.fix_impact?.filter(f => !f.applied) || []

  return (
    <div className="card border-0 shadow-sm mb-3">
      <div
        className="card-header bg-white d-flex justify-content-between align-items-center py-3"
        style={{ cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
      >
        <div>
          <span className="fw-bold me-2" style={{ fontFamily: 'monospace' }}>{sim.call_id}</span>
          <span className="text-muted small">{sim.customer_name}</span>
        </div>
        <div className="d-flex align-items-center gap-3">
          <div className="text-center d-none d-md-block">
            <div className="small text-muted">Before</div>
            <VerdictBadge verdict={sim.before.verdict} />
            <div className="fw-bold small mt-1">{sim.before.score}/100</div>
          </div>
          <div style={{ fontSize: '1.2rem', color: '#adb5bd' }}>→</div>
          <div className="text-center d-none d-md-block">
            <div className="small text-muted">After</div>
            <VerdictBadge verdict={sim.after.verdict} />
            <div className="fw-bold small mt-1">{sim.after.score}/100</div>
          </div>
          <ScoreDelta delta={delta} />
          <div className="d-flex flex-wrap gap-1">
            {fixesApplied.map(f => <FixTag key={f.fix} fix={f.fix} applied={true} />)}
            {fixesFailed.map(f => <FixTag key={f.fix} fix={f.fix} applied={false} />)}
          </div>
          <span style={{ color: '#adb5bd', fontWeight: 600 }}>{expanded ? '▲' : '▼'}</span>
        </div>
      </div>
      {expanded && (
        <div className="card-body">
          <SimulationDetail sim={sim} />
        </div>
      )}
    </div>
  )
}

// ── Main Part2 component ──────────────────────────────────────────────────────

export default function Part2() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/surgeon/results')
      .then(r => {
        if (!r.ok) throw new Error('No results yet')
        return r.json()
      })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const simulations = data?.simulations || []
  const meta = data?.meta || {}
  const comparisons = data?.comparisons || []
  const improved = comparisons.filter(c => c.score_delta > 0).length
  const verdictFlipped = comparisons.filter(c =>
    c.before_verdict === 'bad' && c.after_verdict === 'good'
  ).length

  return (
    <div className="container">

      {/* Page header */}
      <div className="mb-4">
        <h4 className="fw-bold mb-0">Part 2 — The Surgeon</h4>
        <p className="text-muted small mb-0">
          5 prompt flaws identified · 3 bad calls re-simulated · Same scoring system as Part 1
        </p>
      </div>

      {/* Stat cards */}
      {data && (
        <div className="row g-3 mb-4">
          <div className="col-6 col-md-3">
            <div className="card stat-card p-3">
              <div className="stat-value">5</div>
              <div className="stat-label">Flaws Identified</div>
            </div>
          </div>
          <div className="col-6 col-md-3">
            <div className="card stat-card p-3" style={{ background: '#e7f5ff' }}>
              <div className="stat-value text-primary">{simulations.length}</div>
              <div className="stat-label">Calls Simulated</div>
            </div>
          </div>
          <div className="col-6 col-md-3">
            <div className="card stat-card p-3" style={{ background: '#d3f9d8' }}>
              <div className="stat-value text-success">{verdictFlipped}</div>
              <div className="stat-label">Verdicts Flipped</div>
            </div>
          </div>
          <div className="col-6 col-md-3">
            <div className="card stat-card p-3">
              <div className="stat-value text-muted">${meta.total_cost_usd ?? '—'}</div>
              <div className="stat-label">Simulation Cost</div>
            </div>
          </div>
        </div>
      )}

      {/* Section: 5 Flaws */}
      <div className="mb-4">
        <h6 className="fw-bold mb-3">Identified Flaws in system-prompt.md</h6>
        <div className="row g-2">
          {FLAWS.map(f => (
            <div key={f.id} className="col-12 col-md-6 col-lg-4">
              <div className="card border-0 shadow-sm p-3 h-100">
                <div className="d-flex align-items-start gap-2 mb-1">
                  <span className="badge" style={{ background: f.textColor }}>{f.id}</span>
                  <span className="fw-semibold small">{f.title}</span>
                </div>
                <p className="text-muted small mb-2" style={{ lineHeight: 1.5 }}>{f.desc}</p>
                <div className="d-flex flex-wrap gap-1">
                  {f.calls.map(c => (
                    <span key={c} style={{
                      fontSize: '0.65rem', background: f.color, color: f.textColor,
                      padding: '1px 7px', borderRadius: 10, fontWeight: 600
                    }}>
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Section: Before/After Simulations */}
      <div>
        <h6 className="fw-bold mb-1">Before / After Simulation Results</h6>
        <p className="text-muted small mb-3">
          Same customer turns replayed exactly. Only the system prompt changed.
          Before scores taken from Part 1 results.json. After scores computed with same rubric.
        </p>

        {loading && (
          <div className="loading-wrap">
            <div className="spinner-border text-secondary" />
            <p className="mt-3">Loading simulation results...</p>
          </div>
        )}

        {error && (
          <div className="alert alert-warning">
            <strong>Simulations not run yet.</strong> Run{' '}
            <code>python surgeon/simulate.py</code> first.
          </div>
        )}

        {!loading && !error && simulations.length === 0 && (
          <div className="alert alert-warning">
            No simulations found. Run <code>python surgeon/simulate.py</code> first.
          </div>
        )}

        {simulations.map(sim => (
          <ComparisonCard key={sim.call_id} sim={sim} />
        ))}

        {meta.model && (
          <div className="d-flex flex-wrap gap-2 mt-3">
            <span className="badge bg-light text-dark border">Model: {meta.model}</span>
            <span className="badge bg-light text-dark border">Temp: {meta.temperature}</span>
            <span className="badge bg-light text-dark border">Max turns/call: {meta.max_customer_turns_per_call}</span>
            <span className="badge bg-light text-dark border">Cost: ${meta.total_cost_usd}</span>
          </div>
        )}
      </div>

    </div>
  )
}

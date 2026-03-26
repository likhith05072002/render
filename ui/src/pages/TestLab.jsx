import { useMemo, useState } from 'react'

const transcriptExample = `{
  "call_id": "call_99",
  "customer": { "name": "Jane Doe", "dpd": 120 },
  "disposition": "CALLBACK",
  "phases_visited": ["opening", "discovery", "closing"],
  "function_calls": [
    { "turn": 8, "function": "schedule_callback", "params": { "reason": "needs_time" } }
  ],
  "transcript": [
    { "speaker": "agent", "text": "Hello, this is Alex..." },
    { "speaker": "customer", "text": "Can you call me later?" }
  ]
}`

function VerdictBadge({ verdict }) {
  return (
    <span className={`badge rounded-pill verdict-${verdict}`}>
      {verdict === 'good' ? 'GOOD' : 'BAD'}
    </span>
  )
}

function ScoreBar({ score }) {
  const pct = Math.max(0, Math.min(100, score || 0))
  return (
    <div className="d-flex align-items-center gap-2">
      <div className="score-bar-wrap">
        <div className={`score-bar ${score >= 62 ? 'good' : 'bad'}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="fw-bold">{score ?? 0}</span>
    </div>
  )
}

function DimBar({ label, value, max }) {
  const pct = Math.round(((value || 0) / max) * 100)
  const cls = pct >= 70 ? 'high' : pct >= 40 ? 'mid' : 'low'
  return (
    <div className="mb-2">
      <div className="d-flex justify-content-between mb-1">
        <span style={{ fontSize: '0.78rem', color: '#495057' }}>{label}</span>
        <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>{value || 0}/{max}</span>
      </div>
      <div className="dim-bar-wrap">
        <div className={`dim-bar ${cls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function FileDrop({ label, hint, accept, multiple = false, files, onChange }) {
  return (
    <label className="test-dropzone">
      <input
        type="file"
        accept={accept}
        multiple={multiple}
        className="test-file-input"
        onChange={(e) => onChange(Array.from(e.target.files || []))}
      />
      <div className="test-dropzone-title">{label}</div>
      <div className="test-dropzone-hint">{hint}</div>
      {files?.length > 0 && (
        <div className="test-file-list">
          {files.map((file) => (
            <span key={`${file.name}-${file.size}`} className="test-file-chip">
              {file.name}
            </span>
          ))}
        </div>
      )}
    </label>
  )
}

function StatCard({ value, label, tone }) {
  const styles = {
    good: { background: '#d3f9d8', color: '#2b8a3e' },
    bad: { background: '#ffe3e3', color: '#c92a2a' },
    info: { background: '#e7f5ff', color: '#1864ab' },
    neutral: {},
  }

  return (
    <div className="col-6 col-md-3">
      <div className="card stat-card p-3" style={styles[tone] || {}}>
        <div className="stat-value" style={{ color: styles[tone]?.color }}>{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

function ErrorBanner({ error }) {
  if (!error) return null
  return <div className="alert alert-danger mt-3 mb-0">{error}</div>
}

function Panel({ title, subtitle, children, defaultOpen = false }) {
  return (
    <details className="test-panel card border-0 shadow-sm mb-4" open={defaultOpen}>
      <summary className="test-panel-summary">
        <div>
          <div className="fw-bold">{title}</div>
          <div className="text-muted small">{subtitle}</div>
        </div>
        <span className="test-panel-badge">Expand</span>
      </summary>
      <div className="card-body">{children}</div>
    </details>
  )
}

function ScoreBreakdownDetail({ r }) {
  const bd = r.score_breakdown || {}
  const tierA = [
    { label: 'Phase Progression', value: bd.phase_progression ?? 0, max: 20 },
    { label: 'end_call Present', value: bd.end_call_present ?? 0, max: 10 },
    { label: 'No Repetition', value: bd.no_repetition ?? 0, max: 10 },
    { label: 'Disposition Quality', value: bd.disposition_quality ?? 0, max: 10 },
    { label: 'Short Call Penalty', value: bd.short_call_penalty ?? 0, max: 0 },
  ]
  const tierB = [
    { label: 'Language Handling', value: bd.language_handling ?? 0, max: 15 },
    { label: 'Protocol Adherence', value: bd.protocol_adherence ?? bd.escalation_resolution ?? 0, max: 15 },
    { label: 'Discovery Quality', value: bd.discovery_quality ?? bd.discovery_depth ?? 0, max: 10 },
    { label: 'Empathy & Tone', value: bd.empathy_tone ?? 0, max: 10 },
  ]

  return (
    <tr>
      <td colSpan={6} style={{ background: '#f8f9fa', padding: '1rem 1.5rem' }}>
        <div className="row g-3">

          {/* Tier A */}
          <div className="col-md-4">
            <div className="fw-semibold small mb-2" style={{ color: '#1864ab' }}>
              Tier A — Rule-Based ({r.rule_score}/50)
            </div>
            {tierA.map(({ label, value, max }) => (
              <div key={label} className="d-flex justify-content-between small py-1 border-bottom">
                <span style={{ color: '#495057' }}>{label}</span>
                <span className="fw-bold" style={{ color: value < 0 ? '#c92a2a' : '#2b8a3e' }}>
                  {value > 0 ? '+' : ''}{value}{max > 0 ? `/${max}` : ''}
                </span>
              </div>
            ))}
          </div>

          {/* Tier B */}
          <div className="col-md-4">
            <div className="fw-semibold small mb-2" style={{ color: '#862e9c' }}>
              Tier B — LLM Judge ({r.llm_score}/50)
            </div>
            {tierB.map(({ label, value, max }) => (
              <div key={label} className="mb-2">
                <div className="d-flex justify-content-between mb-1">
                  <span style={{ fontSize: '0.75rem', color: '#495057' }}>{label}</span>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{value}/{max}</span>
                </div>
                <div className="dim-bar-wrap">
                  <div
                    className={`dim-bar ${Math.round((value / max) * 100) >= 70 ? 'high' : Math.round((value / max) * 100) >= 40 ? 'mid' : 'low'}`}
                    style={{ width: `${Math.round((value / max) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Reasoning + Worst Messages */}
          <div className="col-md-4">
            {r.reasoning && (
              <div className="mb-3">
                <div className="fw-semibold small mb-1" style={{ color: '#495057' }}>LLM Reasoning</div>
                <div style={{ fontSize: '0.75rem', color: '#666', lineHeight: 1.5 }}>{r.reasoning}</div>
              </div>
            )}
            {r.worst_messages?.length > 0 && (
              <div>
                <div className="fw-semibold small mb-1" style={{ color: '#c92a2a' }}>
                  Worst Messages ({r.worst_messages.length})
                </div>
                {r.worst_messages.map((wm, i) => (
                  <div key={i} className="mb-2 p-2 rounded" style={{ background: '#fff3f3', fontSize: '0.72rem' }}>
                    <div className="fw-bold" style={{ color: '#c92a2a' }}>
                      Turn {wm.turn} · <span style={{ textTransform: 'uppercase' }}>{wm.issue_type?.replace(/_/g, ' ')}</span>
                    </div>
                    <div style={{ color: '#495057', margin: '2px 0' }}>"{wm.text?.slice(0, 100)}{wm.text?.length > 100 ? '…' : ''}"</div>
                    <div style={{ color: '#868e96' }}>{wm.reason}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </td>
    </tr>
  )
}

function DetectiveResults({ data }) {
  const [expanded, setExpanded] = useState(null)
  if (!data) return null
  const results = data.results || []
  const evaluation = data.evaluation
  const aggregate = data.aggregate || {}

  return (
    <div className="mt-4">
      <div className="row g-3 mb-4">
        <StatCard value={results.length} label="Calls Scored" tone="neutral" />
        <StatCard value={aggregate.good_count || 0} label="Predicted Good" tone="good" />
        <StatCard value={aggregate.bad_count || 0} label="Predicted Bad" tone="bad" />
        <StatCard value={evaluation?.accuracy_pct != null ? `${evaluation.accuracy_pct}%` : '$' + (data.meta?.cost_usd ?? 0)} label={evaluation ? 'Accuracy' : 'API Cost'} tone="info" />
      </div>

      {evaluation && !evaluation.error && (
        <div className="alert alert-info border-0">
          <strong>Accuracy:</strong> {evaluation.correct}/{evaluation.total} correct
          {evaluation.mismatches?.length > 0 && (
            <span className="text-muted"> | Mismatches: {evaluation.mismatches.map(m => m.call_id).join(', ')}</span>
          )}
        </div>
      )}

      {(data.errors || []).length > 0 && (
        <div className="alert alert-warning border-0">
          {(data.errors || []).join(' | ')}
        </div>
      )}

      <div className="card border-0 shadow-sm">
        <div className="card-header bg-white py-3 fw-semibold">
          Scored Calls <span className="text-muted fw-normal small ms-2">— click any row to see full breakdown</span>
        </div>
        <div className="table-responsive">
          <table className="table calls-table mb-0">
            <thead className="table-light">
              <tr>
                <th>Call</th>
                <th>Customer</th>
                <th>Disposition</th>
                <th>Score</th>
                <th>Rule / LLM</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {[...results].sort((a, b) => (b.score || 0) - (a.score || 0)).map((r) => (
                <>
                  <tr
                    key={r.call_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setExpanded(expanded === r.call_id ? null : r.call_id)}
                  >
                    <td className="call-id-cell">{r.call_id} {expanded === r.call_id ? '▲' : '▼'}</td>
                    <td>{r.customer_name}</td>
                    <td><span className="badge bg-secondary">{r.disposition}</span></td>
                    <td><ScoreBar score={r.score} /></td>
                    <td className="text-muted small">{r.rule_score} / {r.llm_score}</td>
                    <td><VerdictBadge verdict={r.verdict} /></td>
                  </tr>
                  {expanded === r.call_id && <ScoreBreakdownDetail key={r.call_id + '_detail'} r={r} />}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function SurgeonResults({ data }) {
  const [surgeonExpanded, setSurgeonExpanded] = useState(null)
  if (!data) return null
  const aggregate = data.aggregate || {}
  const comparison = data.comparison
  const results = data.results || []

  return (
    <div className="mt-4">
      <div className="row g-3 mb-4">
        <StatCard value={results.length} label="Calls Simulated" tone="neutral" />
        <StatCard value={aggregate.mean_score || 0} label="Mean Score" tone="info" />
        <StatCard value={aggregate.good_count || 0} label="Good Verdicts" tone="good" />
        <StatCard value={`$${data.meta?.cost_usd ?? 0}`} label="API Cost" tone="neutral" />
      </div>

      {comparison && (
        <div className="card border-0 shadow-sm mb-4">
          <div className="card-header bg-white py-3 fw-semibold">Prompt Comparison</div>
          <div className="card-body">
            <div className="d-flex flex-wrap gap-3 align-items-center">
              <span className="badge bg-light text-dark border">Current: {comparison.current_prompt}</span>
              <span className="badge bg-light text-dark border">Baseline: {comparison.baseline_prompt}</span>
              <span className={`badge ${comparison.delta_mean >= 0 ? 'bg-success' : 'bg-danger'}`}>
                {comparison.delta_mean >= 0 ? '+' : ''}{comparison.delta_mean} pts
              </span>
              <span className="badge bg-primary">{comparison.verdict}</span>
            </div>
          </div>
        </div>
      )}

      <div className="card border-0 shadow-sm">
        <div className="card-header bg-white py-3 fw-semibold">
          Simulation Results <span className="text-muted fw-normal small ms-2">— click any row to see full breakdown</span>
        </div>
        <div className="table-responsive">
          <table className="table calls-table mb-0">
            <thead className="table-light">
              <tr>
                <th>Call</th>
                <th>Customer</th>
                <th>Disposition</th>
                <th>Score</th>
                <th>Rule / LLM</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {[...results].sort((a, b) => (b.score || 0) - (a.score || 0)).map((r) => (
                <>
                  <tr
                    key={r.call_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSurgeonExpanded(surgeonExpanded === r.call_id ? null : r.call_id)}
                  >
                    <td className="call-id-cell">{r.call_id} {surgeonExpanded === r.call_id ? '▲' : '▼'}</td>
                    <td>{r.customer_name || '-'}</td>
                    <td><span className="badge bg-secondary">{r.disposition || 'UNKNOWN'}</span></td>
                    <td><ScoreBar score={r.score} /></td>
                    <td className="text-muted small">{r.rule_score || 0} / {r.llm_score || 0}</td>
                    <td><VerdictBadge verdict={r.verdict || 'bad'} /></td>
                  </tr>
                  {surgeonExpanded === r.call_id && <ScoreBreakdownDetail key={r.call_id + '_detail'} r={r} />}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function PipelineResults({ data }) {
  const [pipelineExpanded, setPipelineExpanded] = useState(null)
  if (!data) return null
  const aggregate = data.aggregate || {}
  const results = data.results || []
  const comparison = data.comparison
  const suggestions = data.suggestions
  const dimAvgs = aggregate.dim_averages || {}

  return (
    <div className="mt-4">
      <div className="row g-3 mb-4">
        <StatCard value={aggregate.mean_score || 0} label="Mean Score" tone="info" />
        <StatCard value={aggregate.good_count || 0} label="Good Verdicts" tone="good" />
        <StatCard value={aggregate.bad_count || 0} label="Bad Verdicts" tone="bad" />
        <StatCard value={`$${data.meta?.cost_usd ?? 0}`} label="API Cost" tone="neutral" />
      </div>

      <div className="row g-3 mb-4">
        <div className="col-md-5">
          <div className="card border-0 shadow-sm p-3 h-100">
            <div className="fw-semibold small mb-3">Dimension Averages</div>
            <DimBar label="Language Handling" value={dimAvgs.language_handling || 0} max={15} />
            <DimBar label="Protocol Adherence" value={dimAvgs.protocol_adherence || 0} max={15} />
            <DimBar label="Discovery Quality" value={dimAvgs.discovery_quality || 0} max={10} />
            <DimBar label="Empathy & Tone" value={dimAvgs.empathy_tone || 0} max={10} />
          </div>
        </div>

        {comparison && (
          <div className="col-md-7">
            <div className="card border-0 shadow-sm p-3 h-100">
              <div className="fw-semibold small mb-3">A/B Comparison</div>
              <div className="d-flex flex-wrap gap-2 mb-3">
                <span className="badge bg-light text-dark border">Current: {comparison.current_prompt}</span>
                <span className="badge bg-light text-dark border">Baseline: {comparison.baseline_prompt}</span>
              </div>
              <div className="test-compare-score">
                {comparison.delta_mean >= 0 ? '+' : ''}{comparison.delta_mean} pts - {comparison.verdict}
              </div>
              <div className="small text-muted mt-2">
                Mean score: {comparison.current_mean} vs {comparison.baseline_mean}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card border-0 shadow-sm mb-4">
        <div className="card-header bg-white py-3 fw-semibold">
          Pipeline Results <span className="text-muted fw-normal small ms-2">— click any row to see full breakdown</span>
        </div>
        <div className="table-responsive">
          <table className="table calls-table mb-0">
            <thead className="table-light">
              <tr>
                <th>Call</th>
                <th>Customer</th>
                <th>Disposition</th>
                <th>Original</th>
                <th>Score</th>
                <th>Rule / LLM</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {[...results].sort((a, b) => (b.score || 0) - (a.score || 0)).map((r) => (
                <>
                  <tr
                    key={r.call_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setPipelineExpanded(pipelineExpanded === r.call_id ? null : r.call_id)}
                  >
                    <td className="call-id-cell">{r.call_id} {pipelineExpanded === r.call_id ? '▲' : '▼'}</td>
                    <td>{r.customer_name || '-'}</td>
                    <td><span className="badge bg-secondary">{r.disposition || 'UNKNOWN'}</span></td>
                    <td><span className="badge bg-light text-dark border">{r.original_disposition || '-'}</span></td>
                    <td><ScoreBar score={r.score} /></td>
                    <td className="text-muted small">{r.rule_score || 0} / {r.llm_score || 0}</td>
                    <td><VerdictBadge verdict={r.verdict || 'bad'} /></td>
                  </tr>
                  {pipelineExpanded === r.call_id && <ScoreBreakdownDetail key={r.call_id + '_detail'} r={r} />}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {suggestions && (
        <div className="card border-0 shadow-sm">
          <div className="card-header bg-white py-3 fw-semibold">Auto Suggestions</div>
          <div className="card-body">
            <pre className="test-suggestions">{suggestions}</pre>
          </div>
        </div>
      )}
    </div>
  )
}

function useFileNames(files) {
  return useMemo(() => files.map(file => file.name), [files])
}

export default function TestLab() {
  const [detectiveFiles, setDetectiveFiles] = useState([])
  const [detectiveVerdicts, setDetectiveVerdicts] = useState([])
  const [detectiveLoading, setDetectiveLoading] = useState(false)
  const [detectiveError, setDetectiveError] = useState('')
  const [detectiveResult, setDetectiveResult] = useState(null)

  const [surgeonPrompt, setSurgeonPrompt] = useState([])
  const [surgeonFiles, setSurgeonFiles] = useState([])
  const [surgeonLoading, setSurgeonLoading] = useState(false)
  const [surgeonError, setSurgeonError] = useState('')
  const [surgeonResult, setSurgeonResult] = useState(null)

  const [pipelinePrompt, setPipelinePrompt] = useState([])
  const [pipelineBaseline, setPipelineBaseline] = useState([])
  const [pipelineFiles, setPipelineFiles] = useState([])
  const [pipelineLoading, setPipelineLoading] = useState(false)
  const [pipelineError, setPipelineError] = useState('')
  const [pipelineResult, setPipelineResult] = useState(null)

  const detectiveNames = useFileNames(detectiveFiles)
  const surgeonNames = useFileNames(surgeonFiles)
  const pipelineNames = useFileNames(pipelineFiles)

  async function postForm(url, formData) {
    const response = await fetch(url, { method: 'POST', body: formData })
    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.error || 'Request failed')
    }
    return data
  }

  async function runDetective() {
    setDetectiveLoading(true)
    setDetectiveError('')
    setDetectiveResult(null)
    try {
      const form = new FormData()
      detectiveFiles.forEach(file => form.append('transcripts[]', file))
      if (detectiveVerdicts[0]) form.append('verdicts', detectiveVerdicts[0])
      setDetectiveResult(await postForm('/api/test/detective', form))
    } catch (err) {
      setDetectiveError(err.message)
    } finally {
      setDetectiveLoading(false)
    }
  }

  async function runSurgeon() {
    setSurgeonLoading(true)
    setSurgeonError('')
    setSurgeonResult(null)
    try {
      const form = new FormData()
      surgeonFiles.forEach(file => form.append('transcripts[]', file))
      if (surgeonPrompt[0]) form.append('prompt', surgeonPrompt[0])
      setSurgeonResult(await postForm('/api/test/surgeon', form))
    } catch (err) {
      setSurgeonError(err.message)
    } finally {
      setSurgeonLoading(false)
    }
  }

  async function runPipeline() {
    setPipelineLoading(true)
    setPipelineError('')
    setPipelineResult(null)
    try {
      const form = new FormData()
      pipelineFiles.forEach(file => form.append('transcripts[]', file))
      if (pipelinePrompt[0]) form.append('prompt', pipelinePrompt[0])
      if (pipelineBaseline[0]) form.append('baseline', pipelineBaseline[0])
      setPipelineResult(await postForm('/api/test/pipeline', form))
    } catch (err) {
      setPipelineError(err.message)
    } finally {
      setPipelineLoading(false)
    }
  }

  function clearDetective() {
    setDetectiveFiles([])
    setDetectiveVerdicts([])
    setDetectiveError('')
    setDetectiveResult(null)
  }

  function clearSurgeon() {
    setSurgeonPrompt([])
    setSurgeonFiles([])
    setSurgeonError('')
    setSurgeonResult(null)
  }

  function clearPipeline() {
    setPipelinePrompt([])
    setPipelineBaseline([])
    setPipelineFiles([])
    setPipelineError('')
    setPipelineResult(null)
  }

  return (
    <div className="container">
      <div className="mb-4">
        <h4 className="fw-bold mb-0">Test Lab - Upload Your Own Data</h4>
        <p className="text-muted small mb-0">
          Use the same scoring engine on your own transcripts and prompts. No CLI required.
        </p>
      </div>

      <Panel
        title="Test A - The Detective"
        subtitle="Upload transcripts and optionally a verdict file to score calls and measure accuracy."
        defaultOpen
      >
        <div className="row g-3">
          <div className="col-md-8">
            <FileDrop
              label="Transcripts"
              hint="Click or drag JSON transcript files here. Up to 20 files."
              accept=".json,application/json"
              multiple
              files={detectiveFiles}
              onChange={setDetectiveFiles}
            />
          </div>
          <div className="col-md-4">
            <FileDrop
              label="verdicts.json (optional)"
              hint="Upload a verdict file to compute accuracy."
              accept=".json,application/json"
              files={detectiveVerdicts}
              onChange={(files) => setDetectiveVerdicts(files.slice(0, 1))}
            />
          </div>
        </div>

        <details className="mt-3">
          <summary className="small fw-semibold text-primary">Expected transcript format</summary>
          <pre className="test-example">{transcriptExample}</pre>
        </details>

        <div className="d-flex gap-2 mt-3">
          <button className="btn btn-primary" disabled={!detectiveFiles.length || detectiveLoading} onClick={runDetective}>
            {detectiveLoading ? `Scoring ${detectiveFiles.length} call(s)...` : 'Run Scorer'}
          </button>
          <button className="btn btn-outline-secondary" onClick={clearDetective}>Clear</button>
        </div>

        {detectiveLoading && <div className="test-loading">Processing uploaded transcripts...</div>}
        <ErrorBanner error={detectiveError} />
        <DetectiveResults data={detectiveResult} />
      </Panel>

      <Panel
        title="Test B - The Surgeon"
        subtitle="Upload a prompt and transcripts to simulate fresh calls and compare the result against the fixed prompt."
      >
        <div className="row g-3">
          <div className="col-md-4">
            <FileDrop
              label="Prompt (optional)"
              hint="If omitted, the original system-prompt.md is used."
              accept=".md,.txt,.json,text/plain"
              files={surgeonPrompt}
              onChange={(files) => setSurgeonPrompt(files.slice(0, 1))}
            />
          </div>
          <div className="col-md-8">
            <FileDrop
              label="Transcripts"
              hint="Upload 1 to 10 call JSON files."
              accept=".json,application/json"
              multiple
              files={surgeonFiles}
              onChange={setSurgeonFiles}
            />
          </div>
        </div>

        <div className="alert alert-light border mt-3 mb-0">
          Your prompt will be tested against the uploaded transcripts and compared with <code>system-prompt-fixed.md</code>.
        </div>

        <div className="d-flex gap-2 mt-3">
          <button className="btn btn-primary" disabled={!surgeonFiles.length || surgeonLoading} onClick={runSurgeon}>
            {surgeonLoading ? `Simulating ${surgeonFiles.length} call(s)...` : 'Run Simulation'}
          </button>
          <button className="btn btn-outline-secondary" onClick={clearSurgeon}>Clear</button>
        </div>

        {surgeonLoading && <div className="test-loading">Running simulation and comparison...</div>}
        <ErrorBanner error={surgeonError} />
        <SurgeonResults data={surgeonResult} />
      </Panel>

      <Panel
        title="Test C - The Pipeline"
        subtitle="Upload a prompt, optional baseline, and transcripts to run the full simulate-score-compare pipeline."
      >
        <div className="row g-3">
          <div className="col-md-4">
            <FileDrop
              label="Prompt (required)"
              hint="Upload the prompt you want to evaluate."
              accept=".md,.txt,.json,text/plain"
              files={pipelinePrompt}
              onChange={(files) => setPipelinePrompt(files.slice(0, 1))}
            />
          </div>
          <div className="col-md-4">
            <FileDrop
              label="Baseline (optional)"
              hint="Upload a baseline prompt for A/B comparison."
              accept=".md,.txt,.json,text/plain"
              files={pipelineBaseline}
              onChange={(files) => setPipelineBaseline(files.slice(0, 1))}
            />
          </div>
          <div className="col-md-4">
            <FileDrop
              label="Transcripts"
              hint="Upload 1 to 10 JSON transcript files."
              accept=".json,application/json"
              multiple
              files={pipelineFiles}
              onChange={setPipelineFiles}
            />
          </div>
        </div>

        <div className="d-flex gap-2 mt-3">
          <button className="btn btn-primary" disabled={!pipelinePrompt.length || !pipelineFiles.length || pipelineLoading} onClick={runPipeline}>
            {pipelineLoading ? `Running pipeline on ${pipelineFiles.length} call(s)...` : 'Run Pipeline'}
          </button>
          <button className="btn btn-outline-secondary" onClick={clearPipeline}>Clear</button>
        </div>

        {pipelineLoading && <div className="test-loading">Simulating, scoring, comparing, and generating suggestions...</div>}
        <ErrorBanner error={pipelineError} />
        <PipelineResults data={pipelineResult} />
      </Panel>

      <div className="small text-muted">
        Selected files: Detective {detectiveNames.length}, Surgeon {surgeonNames.length}, Pipeline {pipelineNames.length}. Server-side budget guard is capped at $0.50 per test run.
      </div>
    </div>
  )
}

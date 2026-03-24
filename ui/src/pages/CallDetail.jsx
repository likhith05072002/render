import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

const ISSUE_LABELS = {
  prompt_violation: 'Prompt Violation',
  tone: 'Tone',
  repetition: 'Repetition',
  missed_resolution: 'Missed Resolution',
  poor_discovery: 'Poor Discovery',
}

const DIMENSIONS = [
  { key: 'phase_progression',    label: 'Phase Progression',      max: 20, tier: 'A' },
  { key: 'end_call_present',     label: 'end_call Present',        max: 10, tier: 'A' },
  { key: 'no_repetition',        label: 'No Repetition',           max: 10, tier: 'A' },
  { key: 'disposition_quality',  label: 'Disposition Quality',     max: 10, tier: 'A' },
  { key: 'language_handling',    label: 'Language Handling',       max: 15, tier: 'B' },
  { key: 'escalation_resolution',label: 'Escalation / Resolution', max: 15, tier: 'B' },
  { key: 'discovery_depth',      label: 'Discovery Depth',         max: 10, tier: 'B' },
  { key: 'empathy_tone',         label: 'Empathy & Tone',          max: 10, tier: 'B' },
]

function dimBarClass(score, max) {
  const pct = score / max
  if (pct >= 0.7) return 'high'
  if (pct >= 0.4) return 'mid'
  return 'low'
}

export default function CallDetail() {
  const { callId } = useParams()
  const navigate = useNavigate()
  const [result, setResult] = useState(null)
  const [transcript, setTranscript] = useState(null)
  const [showTranscript, setShowTranscript] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('/api/results').then(r => r.json()),
      fetch(`/api/transcript/${callId}`).then(r => r.json()),
    ]).then(([resultsData, transcriptData]) => {
      const found = (resultsData.results || []).find(r => r.call_id === callId)
      setResult(found || null)
      setTranscript(transcriptData)
    }).finally(() => setLoading(false))
  }, [callId])

  if (loading) return <div className="loading-wrap"><div className="spinner-border text-secondary" /></div>
  if (!result)  return <div className="container mt-4"><div className="alert alert-danger">Call not found.</div></div>

  const bd = result.score_breakdown || {}
  const isGood = result.verdict === 'good'
  const worstTurns = new Set((result.worst_messages || []).map(w => w.turn))

  return (
    <div className="container">

      {/* Back */}
      <button className="btn btn-sm btn-outline-secondary mb-3" onClick={() => navigate('/part1')}>
        ← Back to Part 1
      </button>

      {/* Header */}
      <div className="row align-items-center mb-4">
        <div className="col">
          <h4 className="fw-bold mb-1">
            {result.call_id}
            <span className="text-muted fw-normal fs-6 ms-2">{result.customer_name}</span>
          </h4>
          <div className="d-flex gap-2 align-items-center flex-wrap">
            <span className="badge bg-secondary">{result.disposition}</span>
            <span className={`badge rounded-pill verdict-${result.verdict}`}>
              {isGood ? '✓ GOOD' : '✗ BAD'}
            </span>
            {transcript && (
              <span className="text-muted small">
                {transcript.total_turns} turns · {transcript.duration_seconds}s · {(transcript.phases_visited || []).join(' → ')}
              </span>
            )}
          </div>
        </div>
        <div className="col-auto text-end">
          <div className={`detail-score-big ${isGood ? 'score-good-text' : 'score-bad-text'}`}>
            {result.score}
            <span className="fs-5 text-muted fw-normal">/100</span>
          </div>
          <div className="text-muted small mt-1">
            Rule <strong>{result.rule_score}</strong> · LLM <strong>{result.llm_score}</strong> · Confidence <strong>{Math.round((result.confidence || 0) * 100)}%</strong>
          </div>
        </div>
      </div>

      {/* Score breakdown + reasoning */}
      <div className="row g-3 mb-4">
        <div className="col-md-7">
          <div className="card border-0 shadow-sm h-100">
            <div className="card-header bg-white fw-semibold border-bottom py-3">Score Breakdown</div>
            <div className="card-body">
              {DIMENSIONS.map(d => {
                const score = bd[d.key] ?? 0
                const pct = Math.round((score / d.max) * 100)
                return (
                  <div key={d.key} className="mb-3">
                    <div className="d-flex justify-content-between align-items-center mb-1">
                      <span className="small d-flex align-items-center gap-2">
                        <span className={`tier-badge-${d.tier.toLowerCase()}`}>Tier {d.tier}</span>
                        {d.label}
                      </span>
                      <span className="fw-bold small">{score}/{d.max}</span>
                    </div>
                    <div className="d-flex align-items-center gap-2">
                      <div className="dim-bar-wrap">
                        <div
                          className={`dim-bar ${dimBarClass(score, d.max)}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-muted small">{pct}%</span>
                    </div>
                  </div>
                )
              })}
              {bd.short_call_penalty != null && bd.short_call_penalty !== 0 && (
                <div className="mt-2 small text-danger fw-semibold">
                  Short-call penalty: {bd.short_call_penalty} pts
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="col-md-5">
          <div className="card border-0 shadow-sm h-100">
            <div className="card-header bg-white fw-semibold border-bottom py-3">LLM Reasoning</div>
            <div className="card-body">
              <p className="small text-muted lh-lg">{result.reasoning || 'No reasoning available.'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Worst messages */}
      {result.worst_messages?.length > 0 && (
        <div className="card border-0 shadow-sm mb-4">
          <div className="card-header bg-white fw-semibold border-bottom py-3">
            ⚠ Worst Agent Messages
          </div>
          <div className="table-responsive">
            <table className="table mb-0" style={{ fontSize: '0.875rem' }}>
              <thead className="table-light">
                <tr>
                  <th style={{ width: 60 }}>Turn</th>
                  <th style={{ width: 150 }}>Issue Type</th>
                  <th>Message</th>
                  <th>Why It Failed</th>
                </tr>
              </thead>
              <tbody>
                {result.worst_messages.map((wm, i) => (
                  <tr key={i}>
                    <td className="text-muted">{wm.turn}</td>
                    <td>
                      <span className={`issue-badge issue-${wm.issue_type}`}>
                        {ISSUE_LABELS[wm.issue_type] || wm.issue_type}
                      </span>
                    </td>
                    <td className="worst-text-cell">{wm.text}</td>
                    <td className="small text-muted">{wm.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Full transcript */}
      <div className="card border-0 shadow-sm">
        <div
          className="card-header bg-white border-bottom py-3 d-flex justify-content-between align-items-center"
          style={{ cursor: 'pointer' }}
          onClick={() => setShowTranscript(v => !v)}
        >
          <span className="fw-semibold">Full Transcript ({transcript?.total_turns || 0} turns)</span>
          <span className="text-muted small">{showTranscript ? '▲ Hide' : '▼ Show'}</span>
        </div>
        {showTranscript && transcript && (
          <div className="transcript-wrap">
            {transcript.transcript?.map((turn, i) => {
              const turnNum = i + 1
              const isWorst = worstTurns.has(turnNum)
              return (
                <div
                  key={i}
                  className={`turn-row ${turn.speaker}-row ${isWorst ? 'worst-row' : ''}`}
                >
                  <div className="turn-num">#{turnNum}</div>
                  <div className="turn-body">
                    <div>
                      <span className={`turn-speaker ${turn.speaker}`}>{turn.speaker.toUpperCase()}</span>
                      {isWorst && <span className="worst-flag">⚠ flagged</span>}
                    </div>
                    <div className="turn-text">{turn.text}</div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}

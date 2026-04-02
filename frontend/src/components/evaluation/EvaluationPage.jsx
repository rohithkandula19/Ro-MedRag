import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../../services/api'

function MetricBar({ label, value, color }) {
  const pct = Math.round(value * 100)
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color, fontFamily: 'var(--font-mono)' }}>{value.toFixed(2)}</span>
      </div>
      <div style={{ height: 6, background: 'var(--bg-deep)', borderRadius: 3, overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1] }}
          style={{ height: '100%', background: color, borderRadius: 3 }}
        />
      </div>
    </div>
  )
}

function ResultCard({ result, index }) {
  const [expanded, setExpanded] = useState(false)
  const passed = result.faithfulness > 0.6 && result.answer_relevancy > 0.6 &&
                 result.context_precision > 0.4 && result.citation_accuracy > 0.7

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08 }}
      onClick={() => setExpanded(e => !e)}
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${passed ? 'rgba(0,255,157,0.15)' : 'rgba(255,107,53,0.15)'}`,
        borderLeft: `3px solid ${passed ? '#00ff9d' : '#ff6b35'}`,
        borderRadius: '0 12px 12px 0',
        padding: '14px 18px',
        marginBottom: 8,
        cursor: 'pointer',
        transition: 'all 0.2s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{
          width: 24, height: 24, borderRadius: '50%',
          background: passed ? 'rgba(0,255,157,0.1)' : 'rgba(255,107,53,0.1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, color: passed ? '#00ff9d' : '#ff6b35',
          flexShrink: 0,
        }}>
          {passed ? '✓' : '✗'}
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
            {result.query}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
            {result.chunks_retrieved} chunks · {result.latency_ms}ms · {result.tokens_used} tokens
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {[
            { label: 'F', value: result.faithfulness },
            { label: 'R', value: result.answer_relevancy },
            { label: 'P', value: result.context_precision },
            { label: 'C', value: result.citation_accuracy },
          ].map(m => (
            <div key={m.label} style={{
              width: 32, height: 32, borderRadius: 6,
              background: m.value > 0.7 ? 'rgba(0,255,157,0.08)' : m.value > 0.4 ? 'rgba(255,199,117,0.08)' : 'rgba(255,107,53,0.08)',
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ fontSize: 8, color: 'var(--text-muted)' }}>{m.label}</span>
              <span style={{ fontSize: 10, fontWeight: 600, color: m.value > 0.7 ? '#00ff9d' : m.value > 0.4 ? '#fac775' : '#ff6b35', fontFamily: 'var(--font-mono)' }}>
                {m.value.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              marginTop: 12, paddingTop: 12,
              borderTop: '1px solid var(--border-subtle)',
              fontSize: 12, color: 'var(--text-secondary)',
              lineHeight: 1.6, fontFamily: 'var(--font-mono)',
            }}>
              {result.answer}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export default function EvaluationPage() {
  const [results, setResults] = useState(null)

  const runEval = useMutation({
    mutationFn: () => api.post('/eval/run', {}).then(r => r.data),
    onSuccess: (data) => setResults(data),
  })

  const runSingle = useMutation({
    mutationFn: (query) => api.post('/eval/single', { query }).then(r => r.data),
    onSuccess: (data) => {
      setResults(prev => prev ? {
        ...prev,
        results: [...(prev.results || []), {
          query: data.query,
          answer: data.answer,
          ...data.metrics,
          ...data.performance,
          insufficient_evidence: data.insufficient_evidence,
        }]
      } : {
        metrics: data.metrics,
        results: [{
          query: data.query,
          answer: data.answer,
          ...data.metrics,
          ...data.performance,
          insufficient_evidence: data.insufficient_evidence,
        }]
      })
    }
  })

  const [singleQuery, setSingleQuery] = useState('')

  return (
    <div style={{ padding: '32px', maxWidth: 1000, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 32, fontWeight: 800,
          background: 'linear-gradient(135deg, var(--text-primary), #00d4ff)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          marginBottom: 6,
        }}>
          RAG Evaluation
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
          Measure retrieval quality, answer faithfulness, and citation accuracy
        </p>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <button
          className="btn-primary"
          onClick={() => runEval.mutate()}
          disabled={runEval.isPending}
          style={{ padding: '12px 24px', fontSize: 14 }}
        >
          {runEval.isPending ? '⟳ Running full suite...' : '▶ Run Full Evaluation'}
        </button>
      </div>

      {/* Single query eval */}
      <div style={{
        display: 'flex', gap: 12, marginBottom: 32,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 12, padding: '12px 16px',
      }}>
        <input
          value={singleQuery}
          onChange={e => setSingleQuery(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && singleQuery.trim()) {
              runSingle.mutate(singleQuery.trim())
              setSingleQuery('')
            }
          }}
          placeholder="Test a single query..."
          className="input-field"
          style={{ flex: 1 }}
        />
        <button
          className="btn-primary"
          onClick={() => {
            if (singleQuery.trim()) {
              runSingle.mutate(singleQuery.trim())
              setSingleQuery('')
            }
          }}
          disabled={runSingle.isPending || !singleQuery.trim()}
          style={{ padding: '10px 18px', fontSize: 13 }}
        >
          {runSingle.isPending ? '⟳' : 'Evaluate'}
        </button>
      </div>

      {/* Loading state */}
      {runEval.isPending && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            textAlign: 'center', padding: 60,
            color: 'var(--text-muted)', fontSize: 14,
          }}
        >
          <div style={{
            width: 40, height: 40, margin: '0 auto 16px',
            border: '3px solid var(--border-subtle)',
            borderTopColor: '#00d4ff',
            borderRadius: '50%',
            animation: 'spin-slow 0.8s linear infinite',
          }} />
          Running 5 test queries against the RAG pipeline...
          <br />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>This may take 1-2 minutes</span>
        </motion.div>
      )}

      {/* Results */}
      {results && !runEval.isPending && (
        <>
          {/* Summary metrics */}
          {results.metrics && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 12, marginBottom: 24,
            }}>
              <div style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 12, padding: 20,
              }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8, letterSpacing: '0.05em' }}>
                  PASS RATE
                </div>
                <div style={{
                  fontSize: 32, fontWeight: 800,
                  color: (results.pass_rate || 0) > 0.7 ? '#00ff9d' : '#ff6b35',
                  fontFamily: 'var(--font-display)',
                }}>
                  {Math.round((results.pass_rate || 0) * 100)}%
                </div>
              </div>
              <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8, letterSpacing: '0.05em' }}>
                  QUERIES
                </div>
                <div style={{ fontSize: 32, fontWeight: 800, color: '#00d4ff', fontFamily: 'var(--font-display)' }}>
                  {results.total_queries || results.results?.length || 0}
                </div>
              </div>
              <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8, letterSpacing: '0.05em' }}>
                  AVG LATENCY
                </div>
                <div style={{ fontSize: 32, fontWeight: 800, color: '#7b61ff', fontFamily: 'var(--font-display)' }}>
                  {results.performance?.avg_latency_ms ? `${(results.performance.avg_latency_ms / 1000).toFixed(1)}s` : '-'}
                </div>
              </div>
              <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8, letterSpacing: '0.05em' }}>
                  TOTAL TOKENS
                </div>
                <div style={{ fontSize: 32, fontWeight: 800, color: '#00ff9d', fontFamily: 'var(--font-display)' }}>
                  {(results.performance?.total_tokens || 0).toLocaleString()}
                </div>
              </div>
            </div>
          )}

          {/* Metric bars */}
          {results.metrics && (
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 16, padding: 24, marginBottom: 24,
            }}>
              <h3 style={{
                fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700,
                color: 'var(--text-primary)', marginBottom: 20,
              }}>
                Aggregate Metrics
              </h3>
              <MetricBar label="Faithfulness" value={results.metrics.avg_faithfulness || results.metrics.faithfulness || 0} color="#00d4ff" />
              <MetricBar label="Answer Relevancy" value={results.metrics.avg_answer_relevancy || results.metrics.answer_relevancy || 0} color="#7b61ff" />
              <MetricBar label="Context Precision" value={results.metrics.avg_context_precision || results.metrics.context_precision || 0} color="#fac775" />
              <MetricBar label="Citation Accuracy" value={results.metrics.avg_citation_accuracy || results.metrics.citation_accuracy || 0} color="#00ff9d" />
            </div>
          )}

          {/* Individual results */}
          {results.results?.length > 0 && (
            <div>
              <h3 style={{
                fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700,
                color: 'var(--text-primary)', marginBottom: 16,
              }}>
                Query Results ({results.results.length})
              </h3>
              {results.results.map((r, i) => (
                <ResultCard key={i} result={r} index={i} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

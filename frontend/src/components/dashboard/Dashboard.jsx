import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Suspense, lazy } from 'react'
import { documentsAPI, chatAPI } from '../../services/api'
import { useAuthStore } from '../../store/authStore'

const Scene3D = lazy(() => import('../3d/Scene3D'))

const FADE_UP = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { delay, duration: 0.5, ease: [0.4, 0, 0.2, 1] },
})

function StatCard({ label, value, icon, color, onClick }) {
  return (
    <motion.div
      {...FADE_UP(0.1)}
      whileHover={{ scale: 1.02, y: -2 }}
      onClick={onClick}
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid var(--border-subtle)`,
        borderRadius: 16,
        padding: '24px',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
        overflow: 'hidden',
        transition: 'border-color 0.2s',
      }}
      onHoverStart={e => e.target.style && (e.target.style.borderColor = 'var(--border-active)')}
    >
      <div style={{
        position: 'absolute', top: 0, right: 0,
        width: 100, height: 100,
        background: `radial-gradient(circle at center, ${color}20, transparent 70%)`,
        borderRadius: '0 0 0 100%',
      }} />
      <div style={{ fontSize: 28, marginBottom: 12 }}>{icon}</div>
      <div style={{
        fontFamily: 'var(--font-display)',
        fontSize: 36, fontWeight: 800,
        color: color, lineHeight: 1,
        textShadow: `0 0 20px ${color}60`,
      }}>
        {value}
      </div>
      <div style={{
        fontSize: 13, color: 'var(--text-secondary)',
        marginTop: 6, fontFamily: 'var(--font-mono)',
        letterSpacing: '0.05em',
      }}>
        {label}
      </div>
    </motion.div>
  )
}

function QueryExample({ text, onClick }) {
  return (
    <motion.button
      whileHover={{ scale: 1.01, x: 4 }}
      whileTap={{ scale: 0.99 }}
      onClick={onClick}
      style={{
        display: 'block', width: '100%', textAlign: 'left',
        padding: '14px 18px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 10, marginBottom: 8,
        color: 'var(--text-secondary)',
        fontSize: 14, cursor: 'pointer',
        fontFamily: 'var(--font-body)',
        transition: 'all 0.2s',
        display: 'flex', alignItems: 'center', gap: 12,
      }}
    >
      <span style={{ color: 'var(--accent-primary)', fontSize: 16 }}>◈</span>
      <span>"{text}"</span>
      <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>Try →</span>
    </motion.button>
  )
}

const EXAMPLE_QUERIES = [
  "What are the symptoms and treatment options for long COVID?",
  "What does the literature say about hypertension management?",
  "Summarize the key findings on diabetes and metformin",
  "What are current evidence-based guidelines for sepsis treatment?",
]

export default function Dashboard() {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  const { data: docs } = useQuery({
    queryKey: ['documents'],
    queryFn: () => documentsAPI.list({}).then(r => r.data),
  })

  const { data: sessions } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => chatAPI.listSessions().then(r => r.data),
  })

  const readyDocs = docs?.filter(d => d.status === 'ready')?.length || 0
  const processingDocs = docs?.filter(d => d.status === 'processing')?.length || 0

  const handleExampleQuery = async (query) => {
    const { data } = await chatAPI.createSession(query.slice(0, 40) + '...')
    navigate(`/chat/${data.id}`, { state: { initialQuery: query } })
  }

  return (
    <div style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
      {/* 3D Hero */}
      <div style={{ position: 'relative', height: 320, overflow: 'hidden' }}>
        <Suspense fallback={null}>
          <Scene3D />
        </Suspense>
        {/* Gradient overlay */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'linear-gradient(to bottom, rgba(2,4,8,0.3) 0%, rgba(2,4,8,0.0) 40%, rgba(2,4,8,0.95) 100%)',
        }} />
        {/* Grid overlay */}
        <div style={{
          position: 'absolute', inset: 0,
          backgroundImage: `
            linear-gradient(rgba(0,212,255,0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,212,255,0.04) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }} />
        {/* Hero text */}
        <div style={{
          position: 'absolute', bottom: 40, left: 0, right: 0,
          textAlign: 'center', padding: '0 20px',
        }}>
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'clamp(28px, 5vw, 52px)',
              fontWeight: 800,
              background: 'linear-gradient(135deg, #fff 30%, var(--accent-primary) 70%, var(--accent-secondary))',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              letterSpacing: '-1px',
              lineHeight: 1.1,
            }}
          >
            Healthcare Research Intelligence
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            style={{
              color: 'var(--text-secondary)',
              fontSize: 15, marginTop: 10,
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.1em',
            }}
          >
            RAG · VECTOR SEARCH · EVIDENCE-BASED CITATIONS
          </motion.p>
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: '0 32px 40px', maxWidth: 1200, margin: '0 auto' }}>

        {/* Stats */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 16, marginBottom: 36,
        }}>
          <StatCard icon="◫" label="READY DOCUMENTS" value={readyDocs} color="var(--accent-primary)" onClick={() => navigate('/documents')} />
          <StatCard icon="⟳" label="PROCESSING" value={processingDocs} color="var(--accent-warn)" />
          <StatCard icon="◈" label="CHAT SESSIONS" value={sessions?.length || 0} color="var(--accent-secondary)" onClick={() => navigate('/chat')} />
          <StatCard icon="⬡" label="TOTAL UPLOADS" value={docs?.length || 0} color="var(--accent-bio)" onClick={() => navigate('/documents')} />
        </div>

        {/* Two-column layout */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>

          {/* Quick actions */}
          <motion.div {...FADE_UP(0.2)} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 16, padding: 28,
          }}>
            <h2 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18, fontWeight: 700,
              marginBottom: 20,
              color: 'var(--text-primary)',
            }}>
              Quick Actions
            </h2>
            <button
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center', marginBottom: 12, padding: '14px 20px' }}
              onClick={() => navigate('/chat')}
            >
              ◈ Start Research Session
            </button>
            <button
              className="btn-ghost"
              style={{ width: '100%', justifyContent: 'center', padding: '14px 20px' }}
              onClick={() => navigate('/documents')}
            >
              ◫ Upload Documents
            </button>

            {/* Disclaimer */}
            <div style={{
              marginTop: 20, padding: '12px 14px',
              background: 'rgba(255, 107, 53, 0.08)',
              border: '1px solid rgba(255,107,53,0.2)',
              borderRadius: 8,
              fontSize: 12, color: 'var(--accent-warn)',
              lineHeight: 1.5,
            }}>
              ⚠️ Research tool only. Always consult qualified healthcare professionals for medical decisions.
            </div>
          </motion.div>

          {/* Example queries */}
          <motion.div {...FADE_UP(0.3)} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 16, padding: 28,
          }}>
            <h2 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18, fontWeight: 700,
              marginBottom: 20, color: 'var(--text-primary)',
            }}>
              Example Research Queries
            </h2>
            {EXAMPLE_QUERIES.map((q, i) => (
              <QueryExample key={i} text={q} onClick={() => handleExampleQuery(q)} />
            ))}
          </motion.div>
        </div>

        {/* Recent sessions */}
        {sessions?.length > 0 && (
          <motion.div {...FADE_UP(0.4)} style={{
            marginTop: 24,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 16, padding: 28,
          }}>
            <h2 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18, fontWeight: 700,
              marginBottom: 20, color: 'var(--text-primary)',
            }}>
              Recent Sessions
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
              {sessions.slice(0, 6).map(s => (
                <motion.div
                  key={s.id}
                  whileHover={{ scale: 1.02 }}
                  onClick={() => navigate(`/chat/${s.id}`)}
                  style={{
                    padding: '14px 16px',
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 10, cursor: 'pointer',
                    transition: 'border-color 0.2s',
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.title}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {new Date(s.updated_at).toLocaleDateString()}
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { chatAPI, documentsAPI, api } from '../../services/api'

// ── PDF Viewer Modal ──────────────────────────────────────────────────────────
function PDFViewerModal({ documentId, page, filename, onClose }) {
  if (!documentId) return null
  const pdfUrl = `/api/viewer/${documentId}/pdf#page=${page || 1}`

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        style={{
          width: '90%', maxWidth: 900, height: '85vh',
          background: 'var(--bg-surface)',
          borderRadius: 16, overflow: 'hidden',
          border: '1px solid var(--border-subtle)',
          display: 'flex', flexDirection: 'column',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{
          padding: '12px 20px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--bg-deep)',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-primary)' }}>
            {filename} {page ? `· Page ${page}` : ''}
          </span>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', fontSize: 18, padding: 4,
          }}>✕</button>
        </div>
        <iframe
          src={pdfUrl}
          style={{ flex: 1, border: 'none', width: '100%' }}
          title="PDF Viewer"
        />
      </motion.div>
    </motion.div>
  )
}

// ── Citation Card ─────────────────────────────────────────────────────────────
function CitationCard({ citation, onViewPDF }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderLeft: '3px solid var(--accent-primary)',
        borderRadius: '0 10px 10px 0',
        padding: '12px 14px',
        marginBottom: 8,
        cursor: 'pointer',
        transition: 'all 0.2s',
      }}
      onClick={() => setExpanded(e => !e)}
      whileHover={{ borderLeftColor: 'var(--accent-primary)', background: 'var(--bg-elevated)' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{
          width: 20, height: 20,
          background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
          borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontWeight: 700, color: 'var(--bg-void)',
          flexShrink: 0,
        }}>
          {citation.citation_index}
        </span>
        <span style={{ fontSize: 12, color: 'var(--accent-primary)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
          {citation.document_filename}
        </span>
        {citation.page_number && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>
            p.{citation.page_number}
          </span>
        )}
        <span style={{
          fontSize: 10, color: 'var(--accent-bio)',
          fontFamily: 'var(--font-mono)',
          background: 'var(--accent-bio-glow)',
          padding: '2px 6px', borderRadius: 4,
        }}>
          {Math.round(citation.relevance_score * 100)}%
        </span>
        {/* View PDF button */}
        {!citation.document_filename?.startsWith('PubMed:') && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onViewPDF?.(citation)
            }}
            style={{
              background: 'var(--accent-glow)', border: '1px solid var(--border-active)',
              borderRadius: 4, color: 'var(--accent-primary)',
              cursor: 'pointer', fontSize: 10, padding: '2px 6px',
              fontFamily: 'var(--font-mono)',
            }}
          >
            View PDF
          </button>
        )}
        {citation.document_filename?.startsWith('PubMed:') && (
          <a
            href={`https://pubmed.ncbi.nlm.nih.gov/${citation.document_filename.split(':')[1]}/`}
            target="_blank"
            rel="noopener"
            onClick={e => e.stopPropagation()}
            style={{
              fontSize: 10, color: 'var(--accent-bio)',
              fontFamily: 'var(--font-mono)',
              textDecoration: 'none',
              background: 'var(--accent-bio-glow)',
              padding: '2px 6px', borderRadius: 4,
            }}
          >
            PubMed →
          </a>
        )}
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
            <p style={{
              fontSize: 12, color: 'var(--text-secondary)',
              lineHeight: 1.6, marginTop: 8,
              fontFamily: 'var(--font-mono)',
              borderTop: '1px solid var(--border-subtle)',
              paddingTop: 8,
            }}>
              {citation.chunk_content}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Streaming Message ─────────────────────────────────────────────────────────
function StreamingMessage({ content, status, citations, metrics, onViewPDF }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ display: 'flex', gap: 12, marginBottom: 24, alignItems: 'flex-start' }}
    >
      <div style={{
        width: 32, height: 32, flexShrink: 0,
        background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-bio))',
        borderRadius: '50%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14,
      }}>🧬</div>

      <div style={{ maxWidth: '78%' }}>
        {/* Status indicator */}
        {status && !content && (
          <div style={{
            padding: '10px 16px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '4px 16px 16px 16px',
            display: 'flex', gap: 8, alignItems: 'center',
            marginBottom: 8,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: 'var(--accent-primary)',
              animation: 'pulse-glow 1s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {status}
            </span>
          </div>
        )}

        {/* Streaming content */}
        {content && (
          <div style={{
            padding: '16px 20px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '4px 16px 16px 16px',
            color: 'var(--text-primary)',
            fontSize: 14, lineHeight: 1.7,
          }}>
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
            {/* Blinking cursor while streaming */}
            {!metrics && (
              <span style={{
                display: 'inline-block', width: 2, height: 16,
                background: 'var(--accent-primary)',
                marginLeft: 2, verticalAlign: 'text-bottom',
                animation: 'blink 0.8s step-end infinite',
              }} />
            )}
          </div>
        )}

        {/* Metrics */}
        {metrics && (
          <div style={{
            display: 'flex', gap: 12, marginTop: 6, paddingLeft: 4,
            fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
          }}>
            <span>{metrics.latency_ms}ms</span>
            <span>{metrics.tokens_used} tokens</span>
            {metrics.confidence > 0 && (
              <span style={{ color: 'var(--accent-bio)' }}>
                ⬡ {Math.round(metrics.confidence * 100)}% confidence
              </span>
            )}
          </div>
        )}

        {/* Citations */}
        {citations?.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{
              fontSize: 11, color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)',
              marginBottom: 8, letterSpacing: '0.08em',
            }}>
              SOURCES ({citations.length})
            </div>
            {citations.map(c => (
              <CitationCard key={c.citation_index} citation={c} onViewPDF={onViewPDF} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ── Message Bubble (for history) ──────────────────────────────────────────────
function MessageBubble({ msg, onViewPDF }) {
  const isUser = msg.role === 'user'

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        gap: 12, marginBottom: 24,
        alignItems: 'flex-start',
      }}
    >
      <div style={{
        width: 32, height: 32, flexShrink: 0,
        background: isUser
          ? 'linear-gradient(135deg, var(--accent-secondary), var(--accent-primary))'
          : 'linear-gradient(135deg, var(--accent-primary), var(--accent-bio))',
        borderRadius: '50%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14,
      }}>
        {isUser ? '◈' : '🧬'}
      </div>

      <div style={{ maxWidth: '78%' }}>
        <div style={{
          padding: '16px 20px',
          background: isUser ? 'var(--bg-elevated)' : 'var(--bg-surface)',
          border: `1px solid ${isUser ? 'var(--border-active)' : 'var(--border-subtle)'}`,
          borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
          color: 'var(--text-primary)',
          fontSize: 14, lineHeight: 1.7,
        }}>
          {isUser ? (
            <p style={{ margin: 0 }}>{msg.content}</p>
          ) : (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {!isUser && (
          <div style={{
            display: 'flex', gap: 12, marginTop: 6, paddingLeft: 4,
            fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
          }}>
            {msg.latency_ms && <span>{msg.latency_ms}ms</span>}
            {msg.tokens_used && <span>{msg.tokens_used} tokens</span>}
            {msg.confidence_score > 0 && (
              <span style={{ color: 'var(--accent-bio)' }}>
                ⬡ {Math.round(msg.confidence_score * 100)}% confidence
              </span>
            )}
          </div>
        )}

        {msg.citations?.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{
              fontSize: 11, color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)',
              marginBottom: 8, letterSpacing: '0.08em',
            }}>
              SOURCES ({msg.citations.length})
            </div>
            {msg.citations.map(c => (
              <CitationCard key={c.citation_index} citation={c} onViewPDF={onViewPDF} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ── Main Chat Page ────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { sessionId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const bottomRef = useRef(null)

  const [input, setInput] = useState('')
  const [mode, setMode] = useState('qa')
  const [currentSession, setCurrentSession] = useState(sessionId || null)

  // Streaming state
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamContent, setStreamContent] = useState('')
  const [streamStatus, setStreamStatus] = useState('')
  const [streamCitations, setStreamCitations] = useState(null)
  const [streamMetrics, setStreamMetrics] = useState(null)

  // PDF viewer state
  const [pdfViewer, setPdfViewer] = useState(null)

  // Sessions
  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => chatAPI.listSessions().then(r => r.data),
  })

  // Messages
  const { data: messages = [] } = useQuery({
    queryKey: ['messages', currentSession],
    queryFn: () => chatAPI.getMessages(currentSession).then(r => r.data),
    enabled: !!currentSession,
  })

  // Docs
  const { data: docs = [] } = useQuery({
    queryKey: ['documents'],
    queryFn: () => documentsAPI.list({}).then(r => r.data),
  })
  const readyDocs = docs.filter(d => d.status === 'ready')

  // Create session
  const createSessionMut = useMutation({
    mutationFn: (q) => chatAPI.createSession(q.slice(0, 50)).then(r => r.data),
    onSuccess: (session) => {
      setCurrentSession(session.id)
      navigate(`/chat/${session.id}`, { replace: true })
      qc.invalidateQueries(['sessions'])
    },
  })

  // Scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamContent, streamStatus])

  // Handle initial query from navigation
  useEffect(() => {
    if (location.state?.initialQuery && currentSession) {
      handleSend(location.state.initialQuery)
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [currentSession])

  // ── Streaming send ──────────────────────────────────────────────────────
  const handleSend = async (text) => {
    const q = (text || input).trim()
    if (!q || isStreaming) return
    setInput('')

    let sid = currentSession
    if (!sid) {
      const session = await createSessionMut.mutateAsync(q)
      sid = session.id
    }

    // Reset streaming state
    setIsStreaming(true)
    setStreamContent('')
    setStreamStatus('Connecting...')
    setStreamCitations(null)
    setStreamMetrics(null)

    // Add user message optimistically
    qc.setQueryData(['messages', sid], (old = []) => [
      ...old,
      { id: `temp-${Date.now()}`, role: 'user', content: q, citations: [] }
    ])

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/api/chat/sessions/${sid}/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ question: q, mode }),
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            switch (eventType) {
              case 'status':
                setStreamStatus(data.message)
                break
              case 'token':
                setStreamContent(prev => prev + data.token)
                setStreamStatus('')
                break
              case 'citations':
                setStreamCitations(data.citations)
                break
              case 'done':
                setStreamMetrics(data)
                break
              case 'error':
                setStreamContent(`Error: ${data.error}`)
                break
            }
          }
        }
      }
    } catch (e) {
      setStreamContent(`Error: ${e.message}`)
    } finally {
      setIsStreaming(false)
      setStreamStatus('')
      // Refresh messages from server
      qc.invalidateQueries(['messages', sid])
      qc.invalidateQueries(['sessions'])
    }
  }

  const handleNewSession = () => {
    setCurrentSession(null)
    setStreamContent('')
    setStreamCitations(null)
    setStreamMetrics(null)
    navigate('/chat', { replace: true })
  }

  const handleDeleteSession = async (id) => {
    await chatAPI.deleteSession(id)
    qc.invalidateQueries(['sessions'])
    if (id === currentSession) handleNewSession()
  }

  const handleViewPDF = (citation) => {
    if (citation.document_filename?.startsWith('PubMed:')) return
    setPdfViewer({
      documentId: citation.document_id,
      page: citation.page_number,
      filename: citation.document_filename,
    })
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* PDF Viewer Modal */}
      <AnimatePresence>
        {pdfViewer && (
          <PDFViewerModal
            documentId={pdfViewer.documentId}
            page={pdfViewer.page}
            filename={pdfViewer.filename}
            onClose={() => setPdfViewer(null)}
          />
        )}
      </AnimatePresence>

      {/* Sessions sidebar */}
      <div style={{
        width: 240, flexShrink: 0,
        background: 'var(--bg-deep)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div style={{ padding: '16px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
          <button className="btn-primary" onClick={handleNewSession}
            style={{ width: '100%', justifyContent: 'center', fontSize: 13 }}>
            + New Session
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '8px 8px' }}>
          {sessions.map(s => (
            <div
              key={s.id}
              onClick={() => { setCurrentSession(s.id); navigate(`/chat/${s.id}`); setStreamContent(''); setStreamCitations(null); setStreamMetrics(null) }}
              style={{
                padding: '10px 10px',
                borderRadius: 8,
                cursor: 'pointer',
                background: currentSession === s.id ? 'var(--accent-glow)' : 'transparent',
                border: `1px solid ${currentSession === s.id ? 'var(--border-active)' : 'transparent'}`,
                marginBottom: 2,
                display: 'flex', alignItems: 'center', gap: 8,
                transition: 'all 0.15s',
              }}
            >
              <span style={{ fontSize: 12 }}>◈</span>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: currentSession === s.id ? 'var(--accent-primary)' : 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.title}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {new Date(s.updated_at).toLocaleDateString()}
                </div>
              </div>
              <button
                onClick={e => { e.stopPropagation(); handleDeleteSession(s.id) }}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12, padding: 2, opacity: 0.5 }}
              >×</button>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{
          height: 'var(--header-height)',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center',
          padding: '0 24px', gap: 16,
          background: 'var(--bg-deep)',
          flexShrink: 0,
        }}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>
            {currentSession ? sessions.find(s => s.id === currentSession)?.title || 'Research Session' : 'New Session'}
          </span>
          <div style={{ display: 'flex', gap: 4, marginLeft: 'auto', background: 'var(--bg-surface)', borderRadius: 8, padding: 3, border: '1px solid var(--border-subtle)' }}>
            {[['qa', '◈ Q&A'], ['summarize', '⬡ Summarize']].map(([m, label]) => (
              <button key={m} onClick={() => setMode(m)} style={{
                padding: '5px 12px', borderRadius: 6,
                background: mode === m ? 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))' : 'transparent',
                color: mode === m ? 'var(--bg-void)' : 'var(--text-secondary)',
                border: 'none', cursor: 'pointer', fontSize: 12,
                fontFamily: 'var(--font-display)', fontWeight: 600,
                transition: 'all 0.2s',
              }}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflow: 'auto', padding: '24px' }}>
          {messages.length === 0 && !isStreaming && (
            <div style={{ textAlign: 'center', paddingTop: 60 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🧬</div>
              <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--text-primary)', marginBottom: 8 }}>
                Start Your Research
              </h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 4 }}>
                Upload documents and ask questions to get evidence-based answers with citations.
              </p>
              <p style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                Now with streaming responses, PubMed search, and citation PDF viewer
              </p>
              {readyDocs.length === 0 && (
                <div style={{ marginTop: 20, padding: '12px 16px', background: 'rgba(255,107,53,0.08)', border: '1px solid rgba(255,107,53,0.2)', borderRadius: 10, display: 'inline-block', color: 'var(--accent-warn)', fontSize: 13 }}>
                  ⚠️ No documents indexed yet. <a href="/documents" style={{ color: 'var(--accent-primary)', textDecoration: 'none' }}>Upload documents →</a>
                </div>
              )}
            </div>
          )}

          {/* Historical messages */}
          {messages.filter(m => !(isStreaming && m.id?.startsWith('temp-'))).map(msg => (
            <MessageBubble key={msg.id} msg={msg} onViewPDF={handleViewPDF} />
          ))}

          {/* Currently streaming message */}
          {isStreaming && (
            <>
              {/* User message */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ display: 'flex', flexDirection: 'row-reverse', gap: 12, marginBottom: 24, alignItems: 'flex-start' }}
              >
                <div style={{
                  width: 32, height: 32, flexShrink: 0,
                  background: 'linear-gradient(135deg, var(--accent-secondary), var(--accent-primary))',
                  borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
                }}>◈</div>
                <div style={{
                  padding: '16px 20px', background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-active)',
                  borderRadius: '16px 4px 16px 16px',
                  color: 'var(--text-primary)', fontSize: 14,
                }}>
                  <p style={{ margin: 0 }}>{messages.find(m => m.id?.startsWith('temp-'))?.content}</p>
                </div>
              </motion.div>

              {/* Streaming response */}
              <StreamingMessage
                content={streamContent}
                status={streamStatus}
                citations={streamCitations}
                metrics={streamMetrics}
                onViewPDF={handleViewPDF}
              />
            </>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: '16px 24px 20px',
          background: 'var(--bg-deep)',
          borderTop: '1px solid var(--border-subtle)',
          flexShrink: 0,
        }}>
          <div style={{
            display: 'flex', gap: 12, alignItems: 'flex-end',
            background: 'var(--bg-surface)',
            border: `1px solid ${input ? 'var(--border-active)' : 'var(--border-subtle)'}`,
            borderRadius: 14, padding: '12px 16px',
            transition: 'border-color 0.2s',
            boxShadow: input ? '0 0 0 3px var(--accent-glow)' : 'none',
          }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
              }}
              placeholder={mode === 'qa'
                ? "Ask a research question... (Enter to send)"
                : "What would you like me to summarize?"}
              disabled={isStreaming}
              rows={1}
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                color: 'var(--text-primary)', fontSize: 14,
                fontFamily: 'var(--font-body)',
                resize: 'none', maxHeight: 140, overflow: 'auto', lineHeight: 1.5,
              }}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              className="btn-primary"
              style={{ flexShrink: 0, padding: '10px 18px', fontSize: 13 }}
            >
              {isStreaming ? '⟳ Streaming...' : '↑ Send'}
            </button>
          </div>
          <p style={{
            textAlign: 'center', marginTop: 8,
            fontSize: 11, color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}>
            ⚠️ NOT MEDICAL ADVICE · FOR RESEARCH PURPOSES ONLY
          </p>
        </div>
      </div>

      {/* Blink animation */}
      <style>{`
        @keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }
      `}</style>
    </div>
  )
}

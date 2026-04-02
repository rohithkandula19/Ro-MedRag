import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import { documentsAPI } from '../../services/api'

function StatusBadge({ status }) {
  const MAP = {
    ready:      { color: 'var(--accent-bio)',      bg: 'var(--accent-bio-glow)',      label: '✓ READY' },
    processing: { color: 'var(--accent-warn)',     bg: 'rgba(255,107,53,0.1)',         label: '⟳ PROCESSING' },
    pending:    { color: 'var(--text-muted)',      bg: 'var(--bg-elevated)',           label: '◌ PENDING' },
    failed:     { color: 'var(--accent-danger)',   bg: 'rgba(255,51,102,0.1)',         label: '✗ FAILED' },
  }
  const s = MAP[status] || MAP.pending
  return (
    <span style={{
      fontSize: 10, fontFamily: 'var(--font-mono)',
      color: s.color, background: s.bg,
      padding: '3px 8px', borderRadius: 4,
      letterSpacing: '0.05em', fontWeight: 600,
    }}>
      {s.label}
    </span>
  )
}

function FileSize({ bytes }) {
  const mb = bytes / 1024 / 1024
  return <span>{mb < 1 ? `${(bytes/1024).toFixed(0)} KB` : `${mb.toFixed(1)} MB`}</span>
}

function UploadProgress({ file, progress, status }) {
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      style={{
        padding: '12px 16px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 10, marginBottom: 8,
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 20 }}>📄</span>
        <span style={{ fontSize: 13, color: 'var(--text-primary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {file.name}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {status === 'done' ? '✓ Done' : `${progress}%`}
        </span>
      </div>
      <div style={{ height: 3, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          animate={{ width: `${progress}%` }}
          style={{
            height: '100%',
            background: status === 'done'
              ? 'var(--accent-bio)'
              : 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
            borderRadius: 2,
          }}
        />
      </div>
    </motion.div>
  )
}

export default function DocumentsPage() {
  const qc = useQueryClient()
  const [uploads, setUploads] = useState([]) // { file, progress, status }
  const [searchQ, setSearchQ] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['documents', searchQ, filterStatus],
    queryFn: () => documentsAPI.list({
      search: searchQ || undefined,
      status: filterStatus || undefined,
    }).then(r => r.data),
    refetchInterval: uploads.some(u => u.status === 'uploading') ? 3000 : false,
  })

  const uploadFile = async (file) => {
    const id = Date.now()
    setUploads(u => [...u, { id, file, progress: 0, status: 'uploading' }])
    try {
      await documentsAPI.upload(file, (prog) => {
        setUploads(u => u.map(x => x.id === id ? { ...x, progress: prog } : x))
      })
      setUploads(u => u.map(x => x.id === id ? { ...x, progress: 100, status: 'done' } : x))
      qc.invalidateQueries(['documents'])
      setTimeout(() => setUploads(u => u.filter(x => x.id !== id)), 3000)
    } catch (e) {
      setUploads(u => u.map(x => x.id === id ? { ...x, status: 'error' } : x))
    }
  }

  const onDrop = useCallback((accepted) => {
    accepted.forEach(uploadFile)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxSize: 50 * 1024 * 1024,
  })

  const handleDelete = async (id) => {
    if (!confirm('Delete this document and all its embeddings?')) return
    await documentsAPI.delete(id)
    qc.invalidateQueries(['documents'])
  }

  return (
    <div style={{ padding: '32px', maxWidth: 1000, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 32, fontWeight: 800,
          background: 'linear-gradient(135deg, var(--text-primary), var(--accent-primary))',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          marginBottom: 6,
        }}>
          Document Library
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
          Upload medical papers and clinical guidelines for AI-powered analysis
        </p>
      </div>

      {/* Drop zone */}
      <motion.div
        {...getRootProps()}
        whileHover={{ borderColor: 'var(--accent-primary)' }}
        style={{
          border: `2px dashed ${isDragActive ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
          borderRadius: 16,
          padding: '48px 24px',
          textAlign: 'center',
          cursor: 'pointer',
          background: isDragActive ? 'var(--accent-glow)' : 'var(--bg-surface)',
          transition: 'all 0.2s',
          marginBottom: 24,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <input {...getInputProps()} />

        {/* Animated rings */}
        {isDragActive && (
          <div style={{
            position: 'absolute', inset: 0,
            background: 'radial-gradient(ellipse at center, var(--accent-glow), transparent)',
            animation: 'pulse-glow 1s ease-in-out infinite',
          }} />
        )}

        <motion.div
          animate={{ scale: isDragActive ? 1.1 : 1 }}
          style={{ fontSize: 48, marginBottom: 16 }}
        >
          {isDragActive ? '⬇️' : '📂'}
        </motion.div>

        <h3 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 20, fontWeight: 700,
          color: isDragActive ? 'var(--accent-primary)' : 'var(--text-primary)',
          marginBottom: 8,
        }}>
          {isDragActive ? 'Drop PDF here' : 'Upload Medical Documents'}
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 16 }}>
          Drag & drop PDFs or click to browse
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
          {['PDF only', 'Max 50MB', 'Multiple files', 'Auto-indexed'].map(tag => (
            <span key={tag} style={{
              fontSize: 12, color: 'var(--text-muted)',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              padding: '4px 10px', borderRadius: 20,
              fontFamily: 'var(--font-mono)',
            }}>
              {tag}
            </span>
          ))}
        </div>
      </motion.div>

      {/* Upload progress */}
      <AnimatePresence>
        {uploads.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 8, letterSpacing: '0.05em' }}>
              UPLOADING
            </div>
            {uploads.map(u => (
              <UploadProgress key={u.id} file={u.file} progress={u.progress} status={u.status} />
            ))}
          </div>
        )}
      </AnimatePresence>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
        <input
          className="input-field"
          placeholder="Search documents..."
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          style={{ maxWidth: 280 }}
        />
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          style={{
            padding: '11px 14px',
            background: 'var(--bg-deep)', border: '1px solid var(--border-subtle)',
            borderRadius: 8, color: 'var(--text-primary)', fontSize: 14,
            fontFamily: 'var(--font-body)', outline: 'none', cursor: 'pointer',
          }}
        >
          <option value="">All Status</option>
          <option value="ready">Ready</option>
          <option value="processing">Processing</option>
          <option value="failed">Failed</option>
        </select>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-muted)' }}>
          {docs.length} document{docs.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Document list */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>Loading...</div>
      ) : docs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
          <p style={{ color: 'var(--text-secondary)' }}>No documents yet. Upload your first PDF above.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {docs.map((doc, i) => (
            <motion.div
              key={doc.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              style={{
                display: 'flex', alignItems: 'center', gap: 16,
                padding: '16px 20px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 12,
                transition: 'all 0.2s',
              }}
            >
              <span style={{ fontSize: 24, flexShrink: 0 }}>📄</span>

              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.filename}
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  <FileSize bytes={doc.file_size_bytes} />
                  {doc.chunk_count && <span>{doc.chunk_count} chunks</span>}
                  {doc.page_count && <span>{doc.page_count} pages</span>}
                  <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                </div>
              </div>

              <StatusBadge status={doc.status} />

              {doc.error_message && (
                <span style={{ fontSize: 11, color: 'var(--accent-danger)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.error_message}
                </span>
              )}

              <button
                onClick={() => handleDelete(doc.id)}
                style={{
                  background: 'none', border: '1px solid transparent',
                  borderRadius: 6, color: 'var(--text-muted)',
                  cursor: 'pointer', fontSize: 14, padding: '6px 8px',
                  transition: 'all 0.2s', flexShrink: 0,
                }}
                onMouseEnter={e => {
                  e.target.style.color = 'var(--accent-danger)'
                  e.target.style.borderColor = 'rgba(255,51,102,0.3)'
                  e.target.style.background = 'rgba(255,51,102,0.08)'
                }}
                onMouseLeave={e => {
                  e.target.style.color = 'var(--text-muted)'
                  e.target.style.borderColor = 'transparent'
                  e.target.style.background = 'none'
                }}
              >
                ✕
              </button>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

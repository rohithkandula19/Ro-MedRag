import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../../services/api'

function ArticleCard({ article, index }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 12,
        padding: '18px 20px',
        marginBottom: 10,
        transition: 'all 0.2s',
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{
          width: 36, height: 36, flexShrink: 0,
          background: 'linear-gradient(135deg, rgba(0,212,255,0.1), rgba(123,97,255,0.1))',
          borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: '1px solid rgba(0,212,255,0.12)',
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{
            fontSize: 14, fontWeight: 600,
            color: 'var(--text-primary)',
            lineHeight: 1.4, marginBottom: 6,
          }}>
            {article.title}
          </h3>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
            <span style={{
              fontSize: 11, color: 'var(--accent-primary)',
              fontFamily: 'var(--font-mono)',
              background: 'rgba(0,212,255,0.08)',
              padding: '2px 8px', borderRadius: 4,
            }}>
              PMID: {article.pmid}
            </span>
            <span style={{
              fontSize: 11, color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)',
            }}>
              {article.journal} ({article.year})
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
            {article.authors?.join(', ')}
          </div>

          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              background: 'none', border: 'none',
              color: 'var(--accent-primary)', cursor: 'pointer',
              fontSize: 12, padding: 0,
              fontFamily: 'var(--font-mono)',
            }}
          >
            {expanded ? '▲ Hide abstract' : '▼ Show abstract'}
          </button>

          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                style={{ overflow: 'hidden' }}
              >
                <p style={{
                  fontSize: 13, color: 'var(--text-secondary)',
                  lineHeight: 1.7, marginTop: 10,
                  paddingTop: 10,
                  borderTop: '1px solid var(--border-subtle)',
                }}>
                  {article.abstract}
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <a
          href={article.pubmed_url}
          target="_blank"
          rel="noopener"
          style={{
            flexShrink: 0,
            padding: '6px 12px',
            background: 'rgba(0,212,255,0.06)',
            border: '1px solid rgba(0,212,255,0.12)',
            borderRadius: 6,
            color: '#00d4ff',
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            textDecoration: 'none',
            display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          PubMed ↗
        </a>
      </div>
    </motion.div>
  )
}

export default function PubMedPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)

  const search = useMutation({
    mutationFn: (q) => api.get(`/pubmed/search?q=${encodeURIComponent(q)}&max_results=10`).then(r => r.data),
    onSuccess: (data) => setResults(data),
  })

  const handleSearch = () => {
    if (query.trim().length >= 3) {
      search.mutate(query.trim())
    }
  }

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
          PubMed Search
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
          Search 36M+ medical research articles from the National Library of Medicine
        </p>
      </div>

      {/* Search bar */}
      <div style={{
        display: 'flex', gap: 12, marginBottom: 32,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 14, padding: '12px 16px',
        boxShadow: query ? '0 0 0 3px var(--accent-glow)' : 'none',
        transition: 'box-shadow 0.2s',
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" style={{ flexShrink: 0, marginTop: 2 }}>
          <circle cx="11" cy="11" r="8"/>
          <line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleSearch()
          }}
          placeholder="Search medical literature... (e.g., 'immunotherapy lung cancer')"
          style={{
            flex: 1, background: 'none', border: 'none', outline: 'none',
            color: 'var(--text-primary)', fontSize: 14,
            fontFamily: 'var(--font-body)',
          }}
        />
        <button
          onClick={handleSearch}
          disabled={search.isPending || query.trim().length < 3}
          className="btn-primary"
          style={{ flexShrink: 0, padding: '8px 20px', fontSize: 13 }}
        >
          {search.isPending ? '⟳ Searching...' : 'Search'}
        </button>
      </div>

      {/* Loading */}
      {search.isPending && (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          <div style={{
            width: 40, height: 40, margin: '0 auto 16px',
            border: '3px solid var(--border-subtle)',
            borderTopColor: '#00d4ff',
            borderRadius: '50%',
            animation: 'spin-slow 0.8s linear infinite',
          }} />
          Searching PubMed...
        </div>
      )}

      {/* Results */}
      {results && !search.isPending && (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 16,
          }}>
            <span style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              Found <strong style={{ color: 'var(--text-primary)' }}>{results.count}</strong> articles for "{results.query}"
            </span>
          </div>

          {results.articles?.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
              No articles found. Try different search terms.
            </div>
          )}

          {results.articles?.map((article, i) => (
            <ArticleCard key={article.pmid} article={article} index={i} />
          ))}
        </>
      )}

      {/* Empty state */}
      {!results && !search.isPending && (
        <div style={{ textAlign: 'center', paddingTop: 60 }}>
          <div style={{
            width: 64, height: 64, margin: '0 auto 16px',
            background: 'rgba(0,212,255,0.06)',
            borderRadius: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid rgba(0,212,255,0.1)',
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.5">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </div>
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--text-primary)', marginBottom: 8 }}>
            Search Medical Literature
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, maxWidth: 400, margin: '0 auto', lineHeight: 1.6 }}>
            Search PubMed's database of over 36 million biomedical articles. 
            Try queries like "CRISPR gene therapy" or "COVID-19 vaccine efficacy".
          </p>
        </div>
      )}
    </div>
  )
}

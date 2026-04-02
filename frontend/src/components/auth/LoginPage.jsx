import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuthStore } from '../../store/authStore'
import Scene3D from '../3d/Scene3D'

export default function LoginPage() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const { login, register, isLoading, error } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    const ok = mode === 'login'
      ? await login(email, password)
      : await register(email, password, name)
    if (ok) navigate('/')
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-void)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      overflow: 'hidden',
    }}>
      <Scene3D />

      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at center, rgba(0,212,255,0.04) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
          linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '60px 60px',
        pointerEvents: 'none',
      }} />

      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: [0.34, 1.56, 0.64, 1] }}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 440,
          margin: '0 20px',
          background: 'rgba(6, 12, 20, 0.85)',
          backdropFilter: 'blur(30px)',
          border: '1px solid rgba(0,212,255,0.15)',
          borderRadius: 20,
          padding: '48px 40px',
          boxShadow: '0 40px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(0,212,255,0.1)',
        }}
      >
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{
            width: 56, height: 56, margin: '0 auto 16px',
            background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
            borderRadius: 14,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 26,
            boxShadow: '0 8px 24px var(--accent-glow)',
          }}>
            🧬
          </div>
          <h1 style={{
            fontFamily: "'Audiowide', sans-serif",
            fontSize: 30, fontWeight: 400,
            background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '3px',
          }}>
            RO MEDRAG
          </h1>
          <p style={{
            color: 'var(--text-secondary)',
            fontSize: 13,
            marginTop: 6,
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.05em',
          }}>
            HEALTHCARE RESEARCH INTELLIGENCE
          </p>
        </div>

        {/* Tabs */}
        <div style={{
          display: 'flex',
          background: 'var(--bg-deep)',
          borderRadius: 10,
          padding: 4,
          marginBottom: 28,
          border: '1px solid var(--border-subtle)',
        }}>
          {['login', 'register'].map(m => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, padding: '8px 0',
              background: mode === m ? 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))' : 'transparent',
              color: mode === m ? 'var(--bg-void)' : 'var(--text-secondary)',
              border: 'none', borderRadius: 7,
              fontFamily: 'var(--font-display)',
              fontWeight: 600, fontSize: 13,
              cursor: 'pointer',
              transition: 'all 0.2s',
              textTransform: 'capitalize',
            }}>
              {m === 'login' ? 'Sign In' : 'Register'}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          {mode === 'register' && (
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, fontFamily: 'var(--font-mono)' }}>
                FULL NAME
              </label>
              <input className="input-field" type="text" value={name}
                onChange={e => setName(e.target.value)} placeholder="Dr. Jane Smith" required />
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, fontFamily: 'var(--font-mono)' }}>
              EMAIL ADDRESS
            </label>
            <input className="input-field" type="email" value={email}
              onChange={e => setEmail(e.target.value)} placeholder="researcher@hospital.org" required />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, fontFamily: 'var(--font-mono)' }}>
              PASSWORD
            </label>
            <input className="input-field" type="password" value={password}
              onChange={e => setPassword(e.target.value)} placeholder="••••••••" required minLength={8} />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              style={{
                padding: '10px 14px',
                background: 'rgba(255, 51, 102, 0.1)',
                border: '1px solid rgba(255,51,102,0.3)',
                borderRadius: 8,
                color: 'var(--accent-danger)',
                fontSize: 13,
                marginBottom: 16,
              }}
            >
              {error}
            </motion.div>
          )}

          <button className="btn-primary" type="submit" disabled={isLoading}
            style={{ width: '100%', justifyContent: 'center', padding: '13px 20px', fontSize: 15 }}
          >
            {isLoading ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Spinner /> {mode === 'login' ? 'Authenticating...' : 'Creating account...'}
              </span>
            ) : (
              mode === 'login' ? 'Access Research Platform' : 'Create Account'
            )}
          </button>
        </form>

        <p style={{
          marginTop: 20,
          textAlign: 'center',
          fontSize: 11,
          color: 'var(--text-muted)',
          lineHeight: 1.5,
        }}>
          ⚠️ For research purposes only. Not medical advice.
        </p>
      </motion.div>
    </div>
  )
}

function Spinner() {
  return (
    <span style={{
      width: 14, height: 14,
      border: '2px solid rgba(0,0,0,0.2)',
      borderTopColor: 'rgba(0,0,0,0.7)',
      borderRadius: '50%',
      display: 'inline-block',
      animation: 'spin-slow 0.7s linear infinite',
    }} />
  )
}

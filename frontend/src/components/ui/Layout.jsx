import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthStore } from '../../store/authStore'
import { useThemeStore } from '../../store/themeStore'

const NAV = [
  {
    to: '/', label: 'Dashboard', exact: true,
    icon: (a) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={a?'#00d4ff':'rgba(255,255,255,0.35)'} strokeWidth="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>,
  },
  {
    to: '/chat', label: 'Research Chat',
    icon: (a) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={a?'#00d4ff':'rgba(255,255,255,0.35)'} strokeWidth="1.8"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>,
  },
  {
    to: '/documents', label: 'Documents',
    icon: (a) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={a?'#00d4ff':'rgba(255,255,255,0.35)'} strokeWidth="1.8"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>,
  },
  {
    to: '/evaluation', label: 'Evaluation',
    icon: (a) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={a?'#00d4ff':'rgba(255,255,255,0.35)'} strokeWidth="1.8"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>,
  },
  {
    to: '/pubmed', label: 'PubMed Search',
    icon: (a) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={a?'#00d4ff':'rgba(255,255,255,0.35)'} strokeWidth="1.8"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
  },
]

// Theme toggle icons
const SunIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.8"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
const MoonIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.8"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>

export default function Layout() {
  const { user, logout } = useAuthStore()
  const { theme, toggleTheme, initTheme } = useThemeStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [expanded, setExpanded] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => { initTheme() }, [])

  // Detect mobile
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth <= 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // Close mobile menu on navigate
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  const handleLogout = () => { logout(); navigate('/login') }

  const sidebarWidth = isMobile ? 220 : (expanded ? 220 : 68)

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-void)' }}>
      {/* Mobile overlay */}
      <AnimatePresence>
        {isMobile && mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
            style={{
              position: 'fixed', inset: 0, zIndex: 40,
              background: 'rgba(0,0,0,0.6)',
            }}
          />
        )}
      </AnimatePresence>

      {/* Mobile hamburger */}
      {isMobile && !mobileOpen && (
        <button
          onClick={() => setMobileOpen(true)}
          style={{
            position: 'fixed', top: 14, left: 14, zIndex: 50,
            width: 40, height: 40,
            background: 'var(--sidebar-bg)',
            border: '1px solid rgba(0,212,255,0.12)',
            borderRadius: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
      )}

      {/* Sidebar */}
      <motion.aside
        animate={{
          width: sidebarWidth,
          x: isMobile && !mobileOpen ? -220 : 0,
        }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        onMouseEnter={() => !isMobile && setExpanded(true)}
        onMouseLeave={() => !isMobile && setExpanded(false)}
        style={{
          flexShrink: 0,
          background: 'var(--sidebar-bg)',
          backdropFilter: 'blur(20px)',
          borderRight: '1px solid rgba(0,212,255,0.06)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          position: isMobile ? 'fixed' : 'relative',
          zIndex: isMobile ? 50 : 10,
          top: 0, bottom: 0, left: 0,
        }}
      >
        {/* Glow line */}
        <div style={{
          position: 'absolute', right: 0, top: 0, bottom: 0, width: 1,
          background: 'var(--glow-line)',
        }} />

        {/* Logo */}
        <div style={{
          padding: '20px 0',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 10,
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          minHeight: 72,
        }}>
          <div style={{
            width: 36, height: 36, flexShrink: 0,
            background: 'linear-gradient(135deg, #00d4ff, #7b61ff)',
            borderRadius: 10,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18,
            boxShadow: '0 4px 16px rgba(0,212,255,0.25)',
          }}>
            🧬
          </div>
          <AnimatePresence>
            {(expanded || isMobile) && (
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.15 }}
              >
                <div style={{
                  fontFamily: "'Audiowide', sans-serif",
                  fontWeight: 400, fontSize: 16,
                  background: 'linear-gradient(135deg, #00d4ff, #7b61ff)',
                  WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                  whiteSpace: 'nowrap', letterSpacing: '-0.3px',
                }}>
                  RO MEDRAG
                </div>
                <div style={{
                  fontSize: 9, color: 'rgba(255,255,255,0.25)',
                  fontFamily: 'var(--font-mono)', letterSpacing: '0.12em',
                }}>
                  RESEARCH AI v2
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '16px 0', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV.map(item => {
            const isActive = item.exact
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to)
            const showLabel = expanded || isMobile

            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.exact}
                style={{
                  display: 'flex', alignItems: 'center',
                  gap: 12,
                  padding: showLabel ? '10px 16px' : '10px 0',
                  justifyContent: showLabel ? 'flex-start' : 'center',
                  margin: '0 8px',
                  borderRadius: 10,
                  textDecoration: 'none',
                  background: isActive ? 'rgba(0,212,255,0.08)' : 'transparent',
                  border: `1px solid ${isActive ? 'rgba(0,212,255,0.12)' : 'transparent'}`,
                  transition: 'all 0.2s',
                  position: 'relative',
                }}
              >
                {isActive && (
                  <div style={{
                    position: 'absolute', left: -8,
                    top: '50%', transform: 'translateY(-50%)',
                    width: 3, height: 20,
                    background: 'linear-gradient(to bottom, #00d4ff, #7b61ff)',
                    borderRadius: 2,
                  }} />
                )}
                <span style={{ flexShrink: 0, lineHeight: 0 }}>
                  {item.icon(isActive)}
                </span>
                <AnimatePresence>
                  {showLabel && (
                    <motion.span
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -4 }}
                      transition={{ duration: 0.12 }}
                      style={{
                        fontSize: 13, fontWeight: isActive ? 600 : 400,
                        color: isActive ? '#00d4ff' : 'rgba(255,255,255,0.45)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {item.label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </NavLink>
            )
          })}
        </nav>

        {/* Theme toggle + User */}
        <div style={{
          padding: '12px 8px',
          borderTop: '1px solid rgba(255,255,255,0.04)',
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
            style={{
              display: 'flex', alignItems: 'center',
              justifyContent: expanded || isMobile ? 'flex-start' : 'center',
              gap: 10,
              padding: expanded || isMobile ? '8px 12px' : '8px 0',
              margin: '0 4px',
              background: 'var(--theme-toggle-bg)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 8,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            <AnimatePresence>
              {(expanded || isMobile) && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}
                >
                  {theme === 'dark' ? 'Light mode' : 'Dark mode'}
                </motion.span>
              )}
            </AnimatePresence>
          </button>

          {/* User */}
          <div
            onClick={expanded || isMobile ? handleLogout : undefined}
            title={expanded || isMobile ? 'Logout' : user?.full_name || 'User'}
            style={{
              display: 'flex', alignItems: 'center',
              justifyContent: expanded || isMobile ? 'flex-start' : 'center',
              gap: 10, padding: '8px',
              margin: '0 4px',
              borderRadius: 8,
              cursor: 'pointer',
              transition: 'background 0.2s',
            }}
          >
            <div style={{
              width: 32, height: 32, flexShrink: 0,
              background: 'linear-gradient(135deg, #7b61ff, #00d4ff)',
              borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700, color: '#020408',
            }}>
              {user?.full_name?.[0] || user?.email?.[0] || 'U'}
            </div>
            <AnimatePresence>
              {(expanded || isMobile) && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  style={{ flex: 1, overflow: 'hidden' }}
                >
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'rgba(255,255,255,0.8)', whiteSpace: 'nowrap' }}>
                    {user?.full_name || 'Researcher'}
                  </div>
                  <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.25)', fontFamily: 'var(--font-mono)' }}>
                    Logout
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </motion.aside>

      {/* Main */}
      <main style={{
        flex: 1, overflow: 'auto',
        display: 'flex', flexDirection: 'column',
        marginLeft: isMobile ? 0 : undefined,
        paddingTop: isMobile ? 56 : 0,
      }}>
        <Outlet />
      </main>
    </div>
  )
}

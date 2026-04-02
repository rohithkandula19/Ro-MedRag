import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { useThemeStore } from './store/themeStore'
import LoginPage from './components/auth/LoginPage'
import Dashboard from './components/dashboard/Dashboard'
import ChatPage from './components/chat/ChatPage'
import DocumentsPage from './components/documents/DocumentsPage'
import EvaluationPage from './components/evaluation/EvaluationPage'
import PubMedPage from './components/pubmed/PubMedPage'
import Layout from './components/ui/Layout'

function ProtectedRoute({ children }) {
  const token = useAuthStore(s => s.token)
  if (!token) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const loadUser = useAuthStore(s => s.loadUser)
  const initTheme = useThemeStore(s => s.initTheme)

  useEffect(() => {
    loadUser()
    initTheme()
  }, [])

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }>
        <Route index element={<Dashboard />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:sessionId" element={<ChatPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="pubmed" element={<PubMedPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

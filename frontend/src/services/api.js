import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: `${BASE}/api`,
  headers: { 'Content-Type': 'application/json' },
})

// Auto-attach token
api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('access_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// Handle 401
api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ─────────────────────────────────────────────────────────────────────
export const authAPI = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  register: (email, password, full_name) => api.post('/auth/register', { email, password, full_name }),
  me: () => api.get('/auth/me'),
}

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsAPI = {
  upload: (file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: e => onProgress?.(Math.round((e.loaded / e.total) * 100))
    })
  },
  list: (params) => api.get('/documents/', { params }),
  get: (id) => api.get(`/documents/${id}`),
  delete: (id) => api.delete(`/documents/${id}`),
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export const chatAPI = {
  createSession: (title, document_ids) => api.post('/chat/sessions', { title, document_ids }),
  listSessions: () => api.get('/chat/sessions'),
  getMessages: (id) => api.get(`/chat/sessions/${id}/messages`),
  query: (sessionId, question, mode = 'qa') =>
    api.post(`/chat/sessions/${sessionId}/query`, { question, mode }),
  deleteSession: (id) => api.delete(`/chat/sessions/${id}`),
}

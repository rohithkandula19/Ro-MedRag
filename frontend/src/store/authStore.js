import { create } from 'zustand'
import { authAPI } from '../services/api'

export const useAuthStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('access_token'),
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { data } = await authAPI.login(email, password)
      localStorage.setItem('access_token', data.access_token)
      const me = await authAPI.me()
      set({ token: data.access_token, user: me.data, isLoading: false })
      return true
    } catch (e) {
      set({ error: e.response?.data?.detail || 'Login failed', isLoading: false })
      return false
    }
  },

  register: async (email, password, full_name) => {
    set({ isLoading: true, error: null })
    try {
      await authAPI.register(email, password, full_name)
      return await get().login(email, password)
    } catch (e) {
      set({ error: e.response?.data?.detail || 'Registration failed', isLoading: false })
      return false
    }
  },

  loadUser: async () => {
    if (!get().token) return
    try {
      const { data } = await authAPI.me()
      set({ user: data })
    } catch {
      get().logout()
    }
  },

  logout: () => {
    localStorage.removeItem('access_token')
    set({ user: null, token: null })
  },
}))

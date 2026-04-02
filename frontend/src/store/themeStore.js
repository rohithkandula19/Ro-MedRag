import { create } from 'zustand'

export const useThemeStore = create((set, get) => ({
  theme: localStorage.getItem('ro-medrag-theme') || 'dark',

  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark'
    localStorage.setItem('ro-medrag-theme', next)
    document.documentElement.setAttribute('data-theme', next)
    set({ theme: next })
  },

  initTheme: () => {
    const saved = localStorage.getItem('ro-medrag-theme') || 'dark'
    document.documentElement.setAttribute('data-theme', saved)
    set({ theme: saved })
  },
}))

import { defineStore } from 'pinia'

import { createAuthApi } from './authApi.js'
import { browserAuthStorage } from './storage.js'


export function createAuthSession({ api, storage, sysCode = 'SUYUAN' }) {
  const persisted = storage.readSession()
  const session = {
    token: persisted.sysCode === sysCode ? persisted.token : '',
    user: persisted.sysCode === sysCode ? persisted.user : null,
    sysCode,
    loading: false,
    initialized: false,

    async bootstrap() {
      if (this.initialized) return this.user
      this.initialized = true
      if (!this.token) return null
      this.loading = true
      try {
        const response = await api.currentUser(this.token)
        this.user = response.result
        storage.writeSession({ token: this.token, sysCode, user: this.user })
        return this.user
      } catch (error) {
        this.clear()
        throw error
      } finally {
        this.loading = false
      }
    },

    async login(credentials) {
      this.loading = true
      try {
        const response = await api.login(credentials)
        this.token = response?.result?.accessToken || ''
        if (!this.token) throw new Error('Company login returned no access token')
        const current = await api.currentUser(this.token)
        this.user = current.result
        this.initialized = true
        storage.writeSession({ token: this.token, sysCode, user: this.user })
        return this.user
      } finally {
        this.loading = false
      }
    },

    async logout() {
      const token = this.token
      try {
        if (token) await api.logout(token)
      } finally {
        this.clear()
      }
    },

    clear() {
      this.token = ''
      this.user = null
      this.initialized = true
      storage.clear()
    }
  }
  if (persisted.sysCode && persisted.sysCode !== sysCode) storage.clear()
  return session
}


let browserSession

function getBrowserSession() {
  if (!browserSession) {
    const storage = browserAuthStorage()
    browserSession = createAuthSession({
      storage,
      api: createAuthApi({ storage }),
      sysCode: 'SUYUAN'
    })
  }
  return browserSession
}


export const useAuthStore = defineStore('suyuan-auth', {
  state: () => ({ token: '', user: null, loading: false, initialized: false }),
  getters: {
    isAuthenticated: state => Boolean(state.token && state.user)
  },
  actions: {
    _sync(session) {
      this.token = session.token
      this.user = session.user
      this.loading = session.loading
      this.initialized = session.initialized
    },
    async bootstrap() {
      const session = getBrowserSession()
      try { return await session.bootstrap() } finally { this._sync(session) }
    },
    async login(credentials) {
      const session = getBrowserSession()
      try { return await session.login(credentials) } finally { this._sync(session) }
    },
    async logout() {
      const session = getBrowserSession()
      try { await session.logout() } finally { this._sync(session) }
    },
    clear() {
      const session = getBrowserSession()
      session.clear()
      this._sync(session)
    }
  }
})

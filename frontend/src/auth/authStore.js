import { defineStore } from 'pinia'

import { createAuthApi } from './authApi.js'
import { browserAuthStorage } from './storage.js'


export function createAuthSession({
  api,
  storage,
  sysCode = 'SUYUAN',
  authMode = 'company',
  mockUser = null
}) {
  const persisted = storage.readSession()
  const isMock = authMode === 'mock' && Boolean(mockUser?.id)
  if (isMock) storage.clear()
  const session = {
    authMode: isMock ? 'mock' : 'company',
    mockUser: isMock ? mockUser : null,
    token: !isMock && persisted.sysCode === sysCode ? persisted.token : '',
    user: !isMock && persisted.sysCode === sysCode ? persisted.user : null,
    sysCode,
    loading: false,
    initialized: false,

    async bootstrap() {
      if (this.initialized) return this.user
      if (this.authMode === 'mock') {
        this.initialized = true
        this.user = this.mockUser
        return this.user
      }
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
      if (this.authMode === 'mock') {
        this.initialized = true
        this.user = this.mockUser
        return this.user
      }
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
      if (this.authMode === 'mock') {
        storage.clear()
        this.token = ''
        this.user = this.mockUser
        this.initialized = true
        return
      }
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
let browserRuntimeConfig = {
  authMode: 'company',
  sysCode: 'SUYUAN',
  mockUser: null
}


function configureBrowserSession(runtimeConfig) {
  browserRuntimeConfig = runtimeConfig
  browserSession = undefined
}

function getBrowserSession() {
  if (!browserSession) {
    const storage = browserAuthStorage()
    browserSession = createAuthSession({
      storage,
      api: createAuthApi({ storage }),
      sysCode: browserRuntimeConfig.sysCode || 'SUYUAN',
      authMode: browserRuntimeConfig.authMode,
      mockUser: browserRuntimeConfig.mockUser
    })
  }
  return browserSession
}


export const useAuthStore = defineStore('suyuan-auth', {
  state: () => ({
    authMode: 'company',
    token: '',
    user: null,
    loading: false,
    initialized: false
  }),
  getters: {
    isAuthenticated: state => Boolean(
      state.user && (state.authMode === 'mock' || state.token)
    )
  },
  actions: {
    _sync(session) {
      this.authMode = session.authMode
      this.token = session.token
      this.user = session.user
      this.loading = session.loading
      this.initialized = session.initialized
    },
    configure(runtimeConfig) {
      configureBrowserSession(runtimeConfig)
      this._sync(getBrowserSession())
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

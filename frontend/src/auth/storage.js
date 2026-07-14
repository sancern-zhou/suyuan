export const AUTH_STORAGE_KEYS = Object.freeze({
  token: 'Access-Token',
  sysCode: 'Access-Sys-Code',
  user: 'Access-User'
})


export function createAuthStorage(storage) {
  return {
    readSession() {
      let user = null
      try {
        const raw = storage.getItem(AUTH_STORAGE_KEYS.user)
        user = raw ? JSON.parse(raw) : null
      } catch {
        user = null
      }
      return {
        token: storage.getItem(AUTH_STORAGE_KEYS.token) || '',
        sysCode: storage.getItem(AUTH_STORAGE_KEYS.sysCode) || '',
        user
      }
    },

    writeSession({ token, sysCode, user }) {
      if (token) storage.setItem(AUTH_STORAGE_KEYS.token, token)
      else storage.removeItem(AUTH_STORAGE_KEYS.token)
      if (sysCode) storage.setItem(AUTH_STORAGE_KEYS.sysCode, sysCode)
      else storage.removeItem(AUTH_STORAGE_KEYS.sysCode)
      if (user) storage.setItem(AUTH_STORAGE_KEYS.user, JSON.stringify(user))
      else storage.removeItem(AUTH_STORAGE_KEYS.user)
    },

    clear() {
      Object.values(AUTH_STORAGE_KEYS).forEach(key => storage.removeItem(key))
    }
  }
}


export function browserAuthStorage() {
  return createAuthStorage(window.localStorage)
}

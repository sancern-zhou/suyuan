import { onAccountChanged } from './accountSession.js'

export function installAccountStoreReset(pinia, stopStreams) {
  const initialStates = new Map()
  pinia.use(({ store }) => {
    initialStates.set(store.$id, JSON.parse(JSON.stringify(store.$state)))
  })
  return onAccountChanged(() => {
    stopStreams()
    for (const store of pinia._s.values()) {
      if (store.$id === 'suyuan-auth') continue
      if (store.ws) {
        store.ws.onclose = store.ws.onmessage = store.ws.onerror = null
        store.ws.close()
      }
      if (store.resetAccountState) store.resetAccountState()
      else {
        const initial = initialStates.get(store.$id)
        if (initial) store.$patch(state => Object.assign(state, JSON.parse(JSON.stringify(initial))))
      }
    }
  })
}

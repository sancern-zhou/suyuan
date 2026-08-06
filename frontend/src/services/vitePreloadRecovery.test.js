import assert from 'node:assert/strict'
import test from 'node:test'

import { registerVitePreloadRecovery } from './vitePreloadRecovery.js'

function createWindow() {
  const values = new Map()
  const listeners = new Map()
  let reloads = 0

  return {
    addEventListener(type, listener) {
      listeners.set(type, listener)
    },
    removeEventListener(type, listener) {
      if (listeners.get(type) === listener) listeners.delete(type)
    },
    sessionStorage: {
      getItem(key) {
        return values.get(key) ?? null
      },
      setItem(key, value) {
        values.set(key, value)
      }
    },
    location: {
      reload() {
        reloads += 1
      }
    },
    dispatchPreloadError(message) {
      let prevented = false
      listeners.get('vite:preloadError')({
        payload: new Error(message),
        preventDefault() {
          prevented = true
        }
      })
      return prevented
    },
    reloadCount() {
      return reloads
    },
    hasPreloadListener() {
      return listeners.has('vite:preloadError')
    }
  }
}

test('reloads once for the same failed dynamic import', () => {
  const windowObject = createWindow()
  registerVitePreloadRecovery(windowObject)

  assert.equal(windowObject.dispatchPreloadError('Failed to fetch chunk-a.js'), true)
  assert.equal(windowObject.dispatchPreloadError('Failed to fetch chunk-a.js'), true)
  assert.equal(windowObject.reloadCount(), 1)
})

test('allows a later deployment with a different chunk to recover', () => {
  const windowObject = createWindow()
  registerVitePreloadRecovery(windowObject)

  windowObject.dispatchPreloadError('Failed to fetch chunk-a.js')
  windowObject.dispatchPreloadError('Failed to fetch chunk-b.js')
  assert.equal(windowObject.reloadCount(), 2)
})

test('recovers when a stale storage value is invalid', () => {
  const windowObject = createWindow()
  windowObject.sessionStorage.setItem('suyuan:vite-preload-reload-signatures', 'invalid-json')
  registerVitePreloadRecovery(windowObject)

  windowObject.dispatchPreloadError('Failed to fetch chunk-a.js')
  assert.equal(windowObject.reloadCount(), 1)
})

test('returns an unregister callback', () => {
  const windowObject = createWindow()
  const unregister = registerVitePreloadRecovery(windowObject)

  assert.equal(windowObject.hasPreloadListener(), true)
  unregister()
  assert.equal(windowObject.hasPreloadListener(), false)
})

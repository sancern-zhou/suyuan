import { v4 as uuidv4 } from 'uuid'


export function createCaptchaChallenge({
  previousKey = '',
  authBaseUrl = '/api',
  uuid = uuidv4,
  random = Math.random,
  now = Date.now
} = {}) {
  const key = uuid()
  const type = random() < 0.5 ? 1 : 3
  const params = new URLSearchParams({
    oldKey: previousKey,
    key,
    type: String(type),
    d: String(now())
  })

  return { key, url: `${authBaseUrl}/auth/token/captcha?${params}` }
}

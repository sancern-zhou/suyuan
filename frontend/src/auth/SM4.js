import gmCrypt from 'gm-crypt'


const SECRET_KEY = 'GJwsXX_BzW=gJWJW'
const cipher = new gmCrypt.sm4({
  key: SECRET_KEY,
  mode: 'cbc',
  iv: SECRET_KEY,
  cipherType: 'base64'
})


export const encryptSM4 = data => cipher.encrypt(data)
export const decryptSM4 = data => cipher.decrypt(data)

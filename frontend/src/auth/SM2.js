import smCrypto from 'sm-crypto'


const CIPHER_MODE_C1C3C2 = 1
const PUBLIC_KEY = '046644e1cb17328239b1cd1926758ab2dc69f9fbf896dab65e693a107fb48e9799a0814d45f3ce051b5823aa9a4bee8677efab57ff145c9caa9d2160ea31bc0fb8'


export function encryptSM2(data) {
  return smCrypto.sm2.doEncrypt(data, PUBLIC_KEY, CIPHER_MODE_C1C3C2)
}

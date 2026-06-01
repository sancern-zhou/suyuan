export const buildBindInstruction = (user) => {
  if (!user) return ''
  if (user.bind_instruction) return String(user.bind_instruction).trim()
  if (user.bind_code) return String(user.bind_code).trim()
  return ''
}

export const isUserBound = (user) => user?.status === 'active'

export const getOnboardingStep = ({ pendingUser, loginSuccess, bound }) => {
  if (!pendingUser) return 'profile'
  if (!loginSuccess) return 'qrcode'
  if (bound) return 'complete'
  return 'binding'
}

export const getPendingSteeringDisplay = (pendingSteeringInputs = []) => {
  if (!Array.isArray(pendingSteeringInputs) || pendingSteeringInputs.length === 0) {
    return {
      text: '',
      extraCount: 0
    }
  }

  const latest = pendingSteeringInputs[pendingSteeringInputs.length - 1]
  return {
    text: String(latest?.content || '').trim(),
    extraCount: Math.max(0, pendingSteeringInputs.length - 1)
  }
}

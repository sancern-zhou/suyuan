const fulfilledValue = (result) => (
  result?.status === 'fulfilled' ? result.value : null
)

export function collectSettledRefreshPayloads(results) {
  const [fileResult, graphResult, runsResult, evaluationResult, bindingResult] = results

  return {
    filePayload: fulfilledValue(fileResult),
    graphPayload: fulfilledValue(graphResult),
    runsPayload: fulfilledValue(runsResult),
    evaluationPayload: fulfilledValue(evaluationResult),
    bindingPayload: fulfilledValue(bindingResult),
    hasBlockingError: fileResult?.status === 'rejected'
  }
}

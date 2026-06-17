const fixedModelTierModes = new Set(['chart', 'social'])

export const shouldShowModelTierSelector = (mode) => !fixedModelTierModes.has(mode)

export const getEffectiveModelTier = (selectedTier, mode) => {
  if (!shouldShowModelTierSelector(mode)) return 'auto'
  return selectedTier
}

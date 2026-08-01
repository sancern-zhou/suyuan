import { buildResourceGroups, targetTab, topLevelProducts } from '../../services/resourceGroups.js'

export function summarizeRightPanelResources(resources = []) {
  const products = topLevelProducts(buildResourceGroups(resources))
  const counts = { files: products.length, document: 0, visualization: 0, board: 0 }
  for (const group of products) {
    const tab = targetTab(group)
    if (tab in counts && tab !== 'files') counts[tab] += 1
  }
  return {
    products,
    counts,
    availableTabs: ['files', 'document', 'visualization', 'board'].filter(tab => counts[tab] > 0),
    hasArtifacts: products.length > 0
  }
}

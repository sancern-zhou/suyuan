export function createProjectConfig(value) {
  const modules = new Set(value.modules)
  const features = Object.freeze({ ...value.frontend.features })
  const agentModeIds = Object.freeze([...(value.frontend.agentModes || [])])
  const defaultAgentMode = value.frontend.defaultAgentMode || agentModeIds[0] || 'assistant'
  const agentModeOverrides = Object.freeze(Object.fromEntries(
    Object.entries(value.frontend.agentModeOverrides || {}).map(([mode, override]) => [
      mode,
      Object.freeze({
        ...override,
        tags: override.tags ? Object.freeze([...override.tags]) : override.tags,
        iconPaths: override.iconPaths ? Object.freeze([...override.iconPaths]) : override.iconPaths,
        welcome: override.welcome
          ? Object.freeze({
              ...override.welcome,
              features: override.welcome.features
                ? Object.freeze([...override.welcome.features])
                : override.welcome.features
            })
          : override.welcome
      })
    ])
  ))
  return Object.freeze({
    schemaVersion: value.schemaVersion,
    project: value.project,
    modules: Object.freeze([...modules]),
    theme: value.frontend.theme,
    brandName: value.frontend.brandName || '风清气智',
    features,
    agentModeIds,
    defaultAgentMode,
    agentModeOverrides,
    agentPlatformLayout: value.frontend.agentPlatformLayout || 'scenes',
    hasModule: moduleId => modules.has(moduleId),
    hasFeature: featureId => features[featureId] === true,
    isFeatureEnabled: (featureId, defaultValue = false) => (
      features[featureId] === undefined ? defaultValue : features[featureId] === true
    )
  })
}


const injected = typeof __SUYUAN_PROJECT_CONFIG__ === 'undefined'
  ? {
      schemaVersion: 1,
      project: 'default',
      modules: ['core', 'legacy'],
      frontend: {
        theme: 'default',
        brandName: '风清气智',
        features: {},
        agentModes: ['assistant', 'ppt', 'expert', 'query', 'report', 'chart', 'board', 'ops'],
        defaultAgentMode: 'assistant',
        agentModeOverrides: {},
        agentPlatformLayout: 'scenes'
      }
    }
  : __SUYUAN_PROJECT_CONFIG__


export const projectConfig = createProjectConfig(injected)

export function resolveProjectDefaultAgentMode(config = projectConfig, validModeIds = []) {
  const allowedModes = validModeIds.length > 0 ? new Set(validModeIds) : null
  const projectModeIds = Array.isArray(config?.agentModeIds) ? config.agentModeIds : []
  const candidates = [config?.defaultAgentMode, projectModeIds[0], 'assistant']

  return candidates.find(mode => (
    typeof mode === 'string' &&
    (!allowedModes || allowedModes.has(mode)) &&
    (projectModeIds.length === 0 || projectModeIds.includes(mode))
  )) || 'assistant'
}

export function isProjectAgentMode(mode, config = projectConfig, validModeIds = []) {
  if (typeof mode !== 'string') return false
  if (validModeIds.length > 0 && !validModeIds.includes(mode)) return false

  const projectModeIds = Array.isArray(config?.agentModeIds) ? config.agentModeIds : []
  return projectModeIds.length === 0 || projectModeIds.includes(mode)
}

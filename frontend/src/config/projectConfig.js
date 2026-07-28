export function createProjectConfig(value) {
  const modules = new Set(value.modules)
  const features = Object.freeze({ ...value.frontend.features })
  return Object.freeze({
    schemaVersion: value.schemaVersion,
    project: value.project,
    modules: Object.freeze([...modules]),
    theme: value.frontend.theme,
    brandName: value.frontend.brandName || '风清气智',
    features,
    hasModule: moduleId => modules.has(moduleId),
    hasFeature: featureId => features[featureId] === true
  })
}


const injected = typeof __SUYUAN_PROJECT_CONFIG__ === 'undefined'
  ? {
      schemaVersion: 1,
      project: 'default',
      modules: ['core', 'legacy'],
      frontend: { theme: 'default', brandName: '风清气智', features: {} }
    }
  : __SUYUAN_PROJECT_CONFIG__


export const projectConfig = createProjectConfig(injected)

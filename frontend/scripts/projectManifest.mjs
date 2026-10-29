import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { parse } from 'yaml'


const IDENTIFIER = /^[a-z][a-z0-9_-]*$/
const AGENT_MODE_IDS = new Set(['assistant', 'ppt', 'expert', 'query', 'knowledge', 'report', 'chart', 'board', 'ops', 'gd_query', 'station_fault_diagnosis', 'operations_analysis'])
const AGENT_SCENE_IDS = new Set(['office', 'monitoring', 'operations'])
const SIDEBAR_AGENT_MODE_IDS = new Set(['query', 'knowledge', 'expert'])
const AGENT_PLATFORM_LAYOUTS = new Set(['scenes', 'environment-grid'])
const AGENT_MODE_OVERRIDE_KEYS = new Set([
  'name',
  'short_name',
  'description',
  'welcome',
  'tags',
  'accent',
  'icon_paths',
  'iconPaths'
])
const AGENT_SCENE_OVERRIDE_KEYS = new Set(['mode_ids', 'modeIds'])
const GUIDE_MODE_KEYS = new Set(['name', 'desc', 'example'])
const GUIDE_DATA_ROW_KEYS = new Set(['name', 'granularity', 'range', 'sync', 'desc'])


function readYaml(path) {
  const value = parse(readFileSync(path, 'utf8'))
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`manifest must be an object: ${path}`)
  }
  return value
}


function uniqueStrings(values, field) {
  if (!Array.isArray(values) || !values.every(value => typeof value === 'string')) {
    throw new Error(`${field} must be an array of strings`)
  }
  if (new Set(values).size !== values.length) {
    throw new Error(`${field} contains duplicate entries`)
  }
  return values
}


function normalizeAgentModeOverrides(value = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('frontend.agent_mode_overrides must be an object')
  }
  const overrides = {}
  for (const [modeId, rawOverride] of Object.entries(value)) {
    if (!AGENT_MODE_IDS.has(modeId)) throw new Error(`unknown agent mode override: ${modeId}`)
    if (!rawOverride || typeof rawOverride !== 'object' || Array.isArray(rawOverride)) {
      throw new Error(`frontend.agent_mode_overrides.${modeId} must be an object`)
    }
    const override = {}
    for (const [key, entryValue] of Object.entries(rawOverride)) {
      if (!AGENT_MODE_OVERRIDE_KEYS.has(key)) {
        throw new Error(`unknown agent mode override field: ${modeId}.${key}`)
      }
      const normalizedKey = key === 'short_name'
        ? 'shortName'
        : (key === 'icon_paths' ? 'iconPaths' : key)
      override[normalizedKey] = entryValue
    }
    if (override.tags !== undefined) {
      override.tags = uniqueStrings(override.tags, `frontend.agent_mode_overrides.${modeId}.tags`)
    }
    if (override.welcome !== undefined && (
      !override.welcome || typeof override.welcome !== 'object' || Array.isArray(override.welcome)
    )) {
      throw new Error(`frontend.agent_mode_overrides.${modeId}.welcome must be an object`)
    }
    if (override.welcome?.features !== undefined) {
      override.welcome.features = uniqueStrings(
        override.welcome.features,
        `frontend.agent_mode_overrides.${modeId}.welcome.features`
      )
    }
    overrides[modeId] = override
  }
  return overrides
}


function normalizeAgentSceneOverrides(value = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('frontend.agent_scene_overrides must be an object')
  }
  const overrides = {}
  for (const [sceneId, rawOverride] of Object.entries(value)) {
    if (!AGENT_SCENE_IDS.has(sceneId)) throw new Error(`unknown agent scene override: ${sceneId}`)
    if (!rawOverride || typeof rawOverride !== 'object' || Array.isArray(rawOverride)) {
      throw new Error(`frontend.agent_scene_overrides.${sceneId} must be an object`)
    }
    for (const key of Object.keys(rawOverride)) {
      if (!AGENT_SCENE_OVERRIDE_KEYS.has(key)) {
        throw new Error(`unknown agent scene override field: ${sceneId}.${key}`)
      }
    }
    const modeIds = uniqueStrings(
      rawOverride.mode_ids ?? rawOverride.modeIds ?? [],
      `frontend.agent_scene_overrides.${sceneId}.mode_ids`
    )
    for (const modeId of modeIds) {
      if (!AGENT_MODE_IDS.has(modeId)) throw new Error(`unknown agent mode: ${modeId}`)
    }
    overrides[sceneId] = { modeIds }
  }
  return overrides
}


function normalizeGuideMode(value, field) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${field} must be an object`)
  }
  const mode = {}
  for (const key of Object.keys(value)) {
    if (!GUIDE_MODE_KEYS.has(key)) throw new Error(`unknown guide mode field: ${field}.${key}`)
    if (typeof value[key] !== 'string' || !value[key].trim()) {
      throw new Error(`${field}.${key} must be a non-empty string`)
    }
    mode[key] = value[key]
  }
  for (const key of GUIDE_MODE_KEYS) {
    if (typeof mode[key] !== 'string') throw new Error(`${field}.${key} must be a non-empty string`)
  }
  return mode
}


function normalizeGuideDataRow(value, field) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${field} must be an object`)
  }
  const row = {}
  for (const key of Object.keys(value)) {
    if (!GUIDE_DATA_ROW_KEYS.has(key)) throw new Error(`unknown guide data row field: ${field}.${key}`)
    if (typeof value[key] !== 'string') throw new Error(`${field}.${key} must be a string`)
    row[key] = value[key]
  }
  if (typeof row.name !== 'string' || !row.name.trim()) {
    throw new Error(`${field}.name must be a non-empty string`)
  }
  if (typeof row.desc !== 'string' || !row.desc.trim()) {
    throw new Error(`${field}.desc must be a non-empty string`)
  }
  row.granularity = row.granularity ?? ''
  row.range = row.range ?? ''
  row.sync = row.sync ?? ''
  return row
}


function normalizePlatformGuide(value) {
  if (value === undefined || value === null) return null
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('frontend.platform_guide must be an object')
  }
  const PLATFORM_GUIDE_KEYS = new Set(['intro', 'mode_groups', 'usage_modes', 'mode_motto', 'data_groups', 'notices'])
  for (const key of Object.keys(value)) {
    if (!PLATFORM_GUIDE_KEYS.has(key)) throw new Error(`unknown platform guide field: ${key}`)
  }
  if (value.intro !== undefined && typeof value.intro !== 'string') {
    throw new Error('frontend.platform_guide.intro must be a string')
  }
  if (value.mode_motto !== undefined && typeof value.mode_motto !== 'string') {
    throw new Error('frontend.platform_guide.mode_motto must be a string')
  }
  const modeGroups = (value.mode_groups ?? []).map((group, index) => {
    const field = `frontend.platform_guide.mode_groups[${index}]`
    if (!group || typeof group !== 'object' || Array.isArray(group)) {
      throw new Error(`${field} must be an object`)
    }
    if (group.scene !== undefined && !AGENT_SCENE_IDS.has(group.scene)) {
      throw new Error(`${field}.scene must be a known agent scene id`)
    }
    for (const key of Object.keys(group)) {
      if (!['scene', 'scene_name', 'modes'].includes(key)) {
        throw new Error(`unknown guide mode group field: ${field}.${key}`)
      }
    }
    const modes = (group.modes ?? []).map((mode, modeIndex) => (
      normalizeGuideMode(mode, `${field}.modes[${modeIndex}]`)
    ))
    if (modes.length === 0) throw new Error(`${field}.modes must contain at least one mode`)
    return {
      scene: group.scene ?? '',
      sceneName: typeof group.scene_name === 'string' ? group.scene_name : '',
      modes
    }
  })
  const usageModes = (value.usage_modes ?? []).map((mode, index) => (
    normalizeGuideMode(mode, `frontend.platform_guide.usage_modes[${index}]`)
  ))
  if (modeGroups.length > 0 && usageModes.length > 0) {
    throw new Error('frontend.platform_guide cannot declare both mode_groups and usage_modes')
  }
  const dataGroups = (value.data_groups ?? []).map((group, index) => {
    const field = `frontend.platform_guide.data_groups[${index}]`
    if (!group || typeof group !== 'object' || Array.isArray(group)) {
      throw new Error(`${field} must be an object`)
    }
    for (const key of Object.keys(group)) {
      if (!['title', 'rows'].includes(key)) throw new Error(`unknown guide data group field: ${field}.${key}`)
    }
    if (typeof group.title !== 'string' || !group.title.trim()) {
      throw new Error(`${field}.title must be a non-empty string`)
    }
    const rows = (group.rows ?? []).map((row, rowIndex) => (
      normalizeGuideDataRow(row, `${field}.rows[${rowIndex}]`)
    ))
    if (rows.length === 0) throw new Error(`${field}.rows must contain at least one row`)
    return { title: group.title, rows }
  })
  const notices = value.notices === undefined ? [] : uniqueStrings(value.notices, 'frontend.platform_guide.notices')
  const guide = {
    intro: typeof value.intro === 'string' ? value.intro : '',
    modeGroups,
    usageModes,
    modeMotto: typeof value.mode_motto === 'string' ? value.mode_motto : '',
    dataGroups,
    notices
  }
  const isEmptyGuide = (
    !guide.intro
    && !guide.modeMotto
    && guide.modeGroups.length === 0
    && guide.usageModes.length === 0
    && guide.dataGroups.length === 0
    && guide.notices.length === 0
  )
  if (isEmptyGuide) return null
  return guide
}


export function loadProjectBuildConfig({ projectId, repoRoot }) {
  if (!IDENTIFIER.test(projectId)) {
    throw new Error(`invalid project identifier: ${projectId}`)
  }
  const manifest = readYaml(resolve(repoRoot, 'projects', projectId, 'project.yaml'))
  if (manifest.schema_version !== 1 || manifest.project !== projectId) {
    throw new Error(`invalid project manifest identity: ${projectId}`)
  }
  const selected = uniqueStrings(manifest.modules ?? [], 'modules')
  const agentModes = uniqueStrings(manifest.frontend?.agent_modes ?? [], 'frontend.agent_modes')
  for (const modeId of agentModes) {
    if (!AGENT_MODE_IDS.has(modeId)) throw new Error(`unknown agent mode: ${modeId}`)
  }
  const defaultAgentMode = manifest.frontend?.default_agent_mode ?? agentModes[0] ?? 'assistant'
  if (!AGENT_MODE_IDS.has(defaultAgentMode)) {
    throw new Error(`unknown default agent mode: ${defaultAgentMode}`)
  }
  if (agentModes.length > 0 && !agentModes.includes(defaultAgentMode)) {
    throw new Error('frontend.default_agent_mode must be declared in frontend.agent_modes')
  }
  const agentPlatformLayout = manifest.frontend?.agent_platform_layout ?? 'scenes'
  if (!AGENT_PLATFORM_LAYOUTS.has(agentPlatformLayout)) {
    throw new Error(`unknown agent platform layout: ${agentPlatformLayout}`)
  }
  const agentScenes = uniqueStrings(manifest.frontend?.agent_scenes ?? [], 'frontend.agent_scenes')
  for (const sceneId of agentScenes) {
    if (!AGENT_SCENE_IDS.has(sceneId)) throw new Error(`unknown agent scene: ${sceneId}`)
  }
  const sidebarAgentModes = uniqueStrings(manifest.frontend?.sidebar_agent_modes ?? ['query'], 'frontend.sidebar_agent_modes')
  for (const modeId of sidebarAgentModes) {
    if (!SIDEBAR_AGENT_MODE_IDS.has(modeId)) throw new Error(`unknown sidebar agent mode: ${modeId}`)
    if (agentModes.length > 0 && !agentModes.includes(modeId)) {
      throw new Error('frontend.sidebar_agent_modes entries must be declared in frontend.agent_modes')
    }
  }
  for (const moduleId of selected) {
    if (!IDENTIFIER.test(moduleId)) throw new Error(`invalid module identifier: ${moduleId}`)
    const moduleManifest = readYaml(resolve(repoRoot, 'modules', moduleId, 'module.yaml'))
    if (moduleManifest.schema_version !== 1 || moduleManifest.module !== moduleId) {
      throw new Error(`invalid module manifest identity: ${moduleId}`)
    }
    const dependencies = uniqueStrings(moduleManifest.dependencies ?? [], 'dependencies')
    for (const dependency of dependencies) {
      if (!selected.includes(dependency)) throw new Error(`${moduleId} requires ${dependency}`)
    }
  }
  return {
    schemaVersion: 1,
    project: projectId,
    modules: ['core', ...selected].sort(),
    frontend: {
      theme: manifest.frontend?.theme ?? 'default',
      brandName: manifest.frontend?.brand_name ?? '风清气智',
      features: manifest.frontend?.features ?? {},
      agentModes,
      defaultAgentMode,
      agentModeOverrides: normalizeAgentModeOverrides(manifest.frontend?.agent_mode_overrides),
      agentSceneOverrides: normalizeAgentSceneOverrides(manifest.frontend?.agent_scene_overrides),
      agentPlatformLayout,
      agentScenes,
      sidebarAgentModes,
      platformGuide: normalizePlatformGuide(manifest.frontend?.platform_guide)
    }
  }
}

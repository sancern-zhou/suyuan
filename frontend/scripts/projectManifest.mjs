import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { parse } from 'yaml'


const IDENTIFIER = /^[a-z][a-z0-9_-]*$/
const AGENT_MODE_IDS = new Set(['assistant', 'ppt', 'expert', 'query', 'knowledge', 'jiangsu_query', 'smart_inspection', 'operations_analysis', 'device_control', 'station_fault_diagnosis', 'report', 'chart', 'board', 'ops'])
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
      agentPlatformLayout
    }
  }
}

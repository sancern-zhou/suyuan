import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { parse } from 'yaml'


const IDENTIFIER = /^[a-z][a-z0-9_-]*$/


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


export function loadProjectBuildConfig({ projectId, repoRoot }) {
  if (!IDENTIFIER.test(projectId)) {
    throw new Error(`invalid project identifier: ${projectId}`)
  }
  const manifest = readYaml(resolve(repoRoot, 'projects', projectId, 'project.yaml'))
  if (manifest.schema_version !== 1 || manifest.project !== projectId) {
    throw new Error(`invalid project manifest identity: ${projectId}`)
  }
  const selected = uniqueStrings(manifest.modules ?? [], 'modules')
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
      features: manifest.frontend?.features ?? {}
    }
  }
}

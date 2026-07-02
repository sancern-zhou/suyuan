import { mergeMapPrograms } from '../components/queryDashboard/mapProgramMerge.js'

const asArray = (value) => Array.isArray(value) ? value : []

const extractMapProgram = (data = {}) => data?.map_program ||
  data?.metadata?.map_program ||
  data?.result?.map_program ||
  data?.result?.data?.map_program ||
  data?.result?.metadata?.map_program ||
  null

const extractMessagePayloads = (message = {}) => {
  const payloads = []
  if (message.data) payloads.push(message.data)
  if (message.metadata) payloads.push(message.metadata)

  asArray(message.content).forEach(block => {
    if (block?.type === 'tool_result') {
      payloads.push(block.content || block)
    }
    if (block?.data) payloads.push(block.data)
  })

  if (typeof message.content === 'object' && !Array.isArray(message.content)) {
    payloads.push(message.content)
  }

  return payloads
}

export function buildMapSceneFromMessages(messages = []) {
  let currentMapProgram = null
  const mapPrograms = []

  asArray(messages).forEach(message => {
    extractMessagePayloads(message).forEach(payload => {
      const mapProgram = extractMapProgram(payload)
      if (!mapProgram) return
      currentMapProgram = mergeMapPrograms(currentMapProgram, mapProgram)
      mapPrograms.push(mapProgram)
    })
  })

  return {
    currentMapProgram,
    mapPrograms
  }
}

export function restoreMapScene(targetState, sessionData = {}) {
  if (!targetState) return
  const metadataScene = sessionData.metadata?.map_scene || sessionData.map_scene || null
  let currentMapProgram = null
  let mapPrograms = []

  if (metadataScene?.current_map_program || metadataScene?.currentMapProgram) {
    currentMapProgram = metadataScene.current_map_program || metadataScene.currentMapProgram
    mapPrograms = asArray(metadataScene.map_programs || metadataScene.mapPrograms)
  }

  const messages = sessionData.conversation_history || sessionData.messages || []
  const scene = buildMapSceneFromMessages(messages)
  if (scene.currentMapProgram) {
    currentMapProgram = mergeMapPrograms(currentMapProgram, scene.currentMapProgram)
    mapPrograms = [...mapPrograms, ...scene.mapPrograms]
  }

  if (currentMapProgram) {
    targetState.currentMapProgram = currentMapProgram
    targetState.mapPrograms = mapPrograms
  }
}

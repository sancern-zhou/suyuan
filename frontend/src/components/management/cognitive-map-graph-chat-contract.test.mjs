import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { buildEntityRelationTree } from './cognitiveMapHierarchy.js'
import { buildGraphLinks } from './cognitiveMapGraphLinks.js'

const source = readFileSync(new URL('./CognitiveMapGraphChat.vue', import.meta.url), 'utf8')
const panelSource = readFileSync(new URL('./CognitiveMapPanel.vue', import.meta.url), 'utf8')

test('graph chat sends graph mode analysis with cognitive map context', () => {
  assert.match(source, /agentMode:\s*'graph'/)
  assert.match(source, /mapContext:\s*buildGraphMapContext\(\)/)
  assert.match(source, /preserveCurrentMode:\s*true/)
  assert.match(source, /active_map_id:\s*props\.currentMap\?\.id/)
  assert.match(source, /selected_item:/)
})

test('graph chat disables send without current map or input', () => {
  assert.match(source, /:disabled="!canSend"/)
  assert.match(source, /const canSend = computed/)
  assert.match(source, /props\.currentMap\?\.id/)
})

test('graph chat reuses the main conversation message list with a focused graph editor composer', () => {
  assert.match(source, /import ReActMessageList from '@\/components\/ReActMessageList\.vue'/)
  assert.match(source, /<ReActMessageList/)
  assert.match(source, /:hide-welcome="true"/)
  assert.match(source, /assistant-mode="graph"/)
  assert.match(source, /graph-chat-composer/)
  assert.match(source, /graph-chat-context/)
  assert.match(source, /graph-chat-send/)
  assert.doesNotMatch(source, /class="graph-chat-message"/)
})

test('graph chat does not render the redundant title map name and graph editor status header', () => {
  assert.doesNotMatch(source, /graph-chat-header/)
  assert.doesNotMatch(source, />对话编辑</)
  assert.doesNotMatch(source, /图谱编辑/)
  assert.doesNotMatch(source, /未选择地图/)
  assert.doesNotMatch(source, /currentMap\?\.name\s*\|\|\s*'未选择地图'/)
})

test('graph chat fills the drawer panel without an extra card container or bottom gap', () => {
  assert.match(panelSource, /class="inspector-section graph-chat-section"/)
  assert.match(panelSource, /:class="\{ 'graph-chat-detail': inspectorTab === 'graph-chat' \}"/)
  assert.match(panelSource, /\.drawer-body\s*\{[^}]*height:\s*100%/)
  assert.match(panelSource, /\.graph-chat-detail\s*\{[^}]*height:\s*100%/)
  assert.match(panelSource, /\.graph-chat-detail\s*\{[^}]*padding:\s*0/)
  assert.match(panelSource, /\.graph-chat-detail\s*\{[^}]*display:\s*flex/)
  assert.match(panelSource, /\.graph-chat-section\s*\{[^}]*height:\s*100%/)
  assert.match(panelSource, /\.graph-chat-section\s*\{[^}]*display:\s*flex/)
  assert.match(panelSource, /\.graph-chat-section\s*\{[^}]*overflow:\s*hidden/)
  assert.match(source, /\.graph-chat-panel\s*\{[^}]*height:\s*100%/)
  assert.match(source, /\.graph-chat-panel\s*\{[^}]*min-height:\s*0/)
  assert.match(source, /\.graph-chat-body\s*\{[^}]*overflow:\s*hidden/)
  assert.match(source, /\.graph-chat-message-list\s*\{[^}]*overflow-y:\s*auto/)
  assert.match(source, /\.graph-chat-composer\s*\{[^}]*flex:\s*0 0 auto/)
  assert.match(source, /\.graph-chat-composer\s*\{[^}]*position:\s*sticky/)
  assert.match(source, /\.graph-chat-composer\s*\{[^}]*bottom:\s*0/)
  assert.match(source, /\.graph-chat-composer\s*\{[^}]*z-index:\s*2/)
  assert.doesNotMatch(source, /\.graph-chat-panel\s*\{[^}]*border:\s*1px/)
  assert.doesNotMatch(source, /\.graph-chat-panel\s*\{[^}]*border-radius:\s*8px/)
  assert.doesNotMatch(source, /height:\s*min\(640px,\s*calc\(100vh - 180px\)\)/)
  assert.doesNotMatch(source, /min-height:\s*420px/)
})

test('cognitive map panel embeds graph chat as a drawer tab', () => {
  assert.match(panelSource, /import CognitiveMapGraphChat from '\.\/CognitiveMapGraphChat\.vue'/)
  assert.match(panelSource, /inspectorTab === 'graph-chat'/)
  assert.match(panelSource, /<CognitiveMapGraphChat/)
  assert.match(panelSource, /@graph-updated="handleGraphChatUpdated"/)
})

test('cognitive map panel renders an entity relation hierarchy instead of separate flat entity and relation trees', () => {
  assert.match(panelSource, /buildEntityRelationTree/)
  assert.match(panelSource, /entityHierarchyRows/)
  assert.match(panelSource, /relation-badge/)
  assert.doesNotMatch(panelSource, /v-for="group in entityTreeGroups"/)
  assert.doesNotMatch(panelSource, /v-for="group in relationTreeGroups"/)
})

test('cognitive map panel uses a dual-pane hierarchy workbench with top-level management tabs', () => {
  assert.match(panelSource, /management-tabs/)
  assert.match(panelSource, /hierarchy-workbench/)
  assert.match(panelSource, /hierarchy-list-pane/)
  assert.match(panelSource, /hierarchy-detail-pane/)
  assert.match(panelSource, /managementTabOptions/)
  assert.doesNotMatch(panelSource, /class="drawer-tree"/)
})

test('cognitive map panel does not render a drawer title and aggregate entity relation count header', () => {
  assert.doesNotMatch(panelSource, /class="drawer-header"/)
  assert.doesNotMatch(panelSource, /entities\.length\s*}}\s*个实体\s*\/\s*{{\s*relations\.length\s*}}\s*条关系/)
})

test('graph legend and relation filters use Chinese labels in one stacked bottom-left toolbar', () => {
  assert.match(panelSource, /FaultSymptom:\s*'故障现象'/)
  assert.match(panelSource, /DataMetric:\s*'数据指标'/)
  assert.match(panelSource, /CheckItem:\s*'检查项'/)
  assert.match(panelSource, /device_measures:\s*'设备监测'/)
  assert.match(panelSource, /station_has_device:\s*'站点配置设备'/)
  assert.match(panelSource, /fault_affects_metric:\s*'故障影响指标'/)
  assert.match(panelSource, /check_requires:\s*'检查要求'/)
  assert.match(panelSource, /data_source_validates:\s*'数据源校验'/)
  assert.match(panelSource, /<div v-if="relationCategories\.length" class="relation-filter">[\s\S]*<div class="graph-legend">/)
  assert.match(panelSource, /v-for="category in relationCategories"/)
  assert.match(panelSource, /backgroundColor: category\.itemStyle\.color/)
  assert.doesNotMatch(panelSource, /\.relation-filter\s*\{[^}]*position:\s*absolute/)
  assert.doesNotMatch(panelSource, /\.relation-filter\s*\{[^}]*bottom:\s*78px/)
})

test('graph toolbar only keeps the meaningful show-all action', () => {
  assert.match(panelSource, /显示全部/)
  assert.doesNotMatch(panelSource, /适配视图/)
  assert.doesNotMatch(panelSource, /fitGraph/)
})

test('graph panel supports canvas styling relation labels and dense relation rendering controls', () => {
  assert.match(panelSource, /showRelationLabels/)
  assert.match(panelSource, /关系标签/)
  assert.match(panelSource, /buildGraphLinks/)
  assert.match(panelSource, /background-image:\s*radial-gradient/)
})

test('graph links separate repeated relations and aggregate self loops', () => {
  const links = buildGraphLinks({
    relations: [
      {
        relation_id: 'rel_1',
        relation_type: 'contains',
        source_entity_id: 'station',
        target_entity_id: 'device'
      },
      {
        relation_id: 'rel_2',
        relation_type: 'measures',
        source_entity_id: 'station',
        target_entity_id: 'device'
      },
      {
        relation_id: 'rel_3',
        relation_type: 'calibrates',
        source_entity_id: 'device',
        target_entity_id: 'station'
      },
      {
        relation_id: 'self_1',
        relation_type: 'related_to',
        source_entity_id: 'device',
        target_entity_id: 'device'
      },
      {
        relation_id: 'self_2',
        relation_type: 'requires',
        source_entity_id: 'device',
        target_entity_id: 'device'
      }
    ],
    nodeIds: new Set(['station', 'device']),
    relationColorByType: new Map([
      ['contains', '#111111'],
      ['measures', '#222222'],
      ['calibrates', '#333333'],
      ['related_to', '#444444'],
      ['requires', '#555555']
    ]),
    isRelationTypeHidden: () => false,
    formatRelationType: type => `中文-${type}`,
    showRelationLabels: true
  })

  const normalLinks = links.filter(link => !link.raw.isSelfLoopGroup)
  assert.equal(normalLinks.length, 3)
  assert.deepEqual(
    normalLinks.map(link => link.lineStyle.curveness),
    [-0.36, 0, 0.36]
  )
  assert.equal(normalLinks[0].label.show, true)
  assert.equal(normalLinks[0].label.formatter, '中文-contains')

  const selfLoop = links.find(link => link.raw.isSelfLoopGroup)
  assert.equal(selfLoop.source, 'device')
  assert.equal(selfLoop.target, 'device')
  assert.equal(selfLoop.value, 'self_loop_group')
  assert.equal(selfLoop.raw.selfLoopRelations.length, 2)
  assert.equal(selfLoop.label.formatter, '自关联 2 条')
  assert.equal(selfLoop.lineStyle.curveness, 0.55)
})

test('entity relation hierarchy follows actual graph relations and keeps relation labels attached to child entities', () => {
  const tree = buildEntityRelationTree(
    [
      { entity_id: 'station_house', name: '智慧化站房' },
      { entity_id: 'gas_device', name: '气态污染物分析设备' },
      { entity_id: 'nox_analyzer', name: 'NOx分析仪' },
      { entity_id: 'power_device', name: '动力环境监控设备' },
      { entity_id: 'orphan', name: '未连接实体' }
    ],
    [
      {
        relation_id: 'rel_1',
        relation_type: 'contains',
        source_entity_id: 'station_house',
        target_entity_id: 'gas_device'
      },
      {
        relation_id: 'rel_2',
        relation_type: 'contains',
        source_entity_id: 'gas_device',
        target_entity_id: 'nox_analyzer'
      },
      {
        relation_id: 'rel_3',
        relation_type: 'contains',
        source_entity_id: 'station_house',
        target_entity_id: 'power_device'
      },
      {
        relation_id: 'rel_cycle',
        relation_type: 'installed_in',
        source_entity_id: 'nox_analyzer',
        target_entity_id: 'station_house'
      }
    ]
  )

  assert.equal(tree.roots.length, 1)
  assert.equal(tree.roots[0].entity.name, '智慧化站房')
  assert.equal(tree.roots[0].children.length, 2)
  assert.equal(tree.roots[0].children[0].entity.name, '气态污染物分析设备')
  assert.equal(tree.roots[0].children[0].relation.relation_type, 'contains')
  assert.equal(tree.roots[0].children[0].children[0].entity.name, 'NOx分析仪')
  assert.equal(tree.roots[0].children[0].children[0].children[0].cycle, true)
  assert.equal(tree.roots[0].children[0].children[0].children[0].entity.name, '智慧化站房')
  assert.equal(tree.orphans.length, 1)
  assert.equal(tree.orphans[0].entity.name, '未连接实体')
})

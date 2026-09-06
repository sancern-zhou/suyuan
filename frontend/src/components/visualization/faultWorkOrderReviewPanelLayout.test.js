import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('review comment is the final content section before archive actions', async () => {
  const source = await readFile(new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url), 'utf8')
  assert.match(source, /class="section review-comment-section">\s*<label class="field">[\s\S]*?v-model="form.review_comment"[\s\S]*?<\/label>\s*<\/section>\s*<\/div>\s*<footer class="panel-footer">/)
  assert(source.indexOf('class="section review-comment-section"') > source.indexOf('class="section exclusion-section"'))
})

test('fault work order review panel no longer renders the title badge header', async () => {
  const source = await readFile(
    new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url),
    'utf8'
  )

  assert.doesNotMatch(source, /panel-header/)
  assert.doesNotMatch(source, /panelEyebrow/)
  assert.doesNotMatch(source, /status-badge/)
  assert.doesNotMatch(source, /站点：/)
  assert.doesNotMatch(source, /activeModule === 'impact'/)
  assert.doesNotMatch(source, /label: '数据影响'/)
  assert.doesNotMatch(source, /<section class="decision-overview"/)
  assert.match(source, /panel-body/)
  assert.match(source, /剔除异常区间确认[\s\S]*v-if="dataImpacts\.length"/)
})

test('fault work order review panel surfaces structured review storage fields', async () => {
  const source = await readFile(
    new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url),
    'utf8'
  )

  assert.match(source, /reviewStatusDetail/)
  assert.match(source, /reviewFactCards/)
  assert.match(source, /reviewHistoryEntries/)
  assert.match(source, /evidenceCoverageGroups/)
  assert.match(source, /collectionNotes/)
  assert.match(source, /human_review_comment/)
  assert.doesNotMatch(source, /证据引用/)
  assert.doesNotMatch(source, /evidenceRefItems/)
})

test('fault work order review panel guards station access with a safe fallback', async () => {
  const source = await readFile(
    new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url),
    'utf8'
  )

  assert.match(source, /const station = computed\(\(\) => review\.value\?\.station \|\| \{\}\)/)
})

test('fault work order attachments use authenticated image loading', async () => {
  const source = await readFile(
    new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url),
    'utf8'
  )

  assert.match(source, /import AuthenticatedImage/)
  assert.match(source, /<AuthenticatedImage/)
  assert.match(source, /@resolved="url => setAttachmentPreviewUrl\(row\.key, url\)"/)
  assert.doesNotMatch(source, /<img :src="row\.contentUrl"/)
})

test('fault work order attachment previews open in an in-app lightbox', async () => {
  const source = await readFile(
    new URL('./FaultWorkOrderReviewPanel.vue', import.meta.url),
    'utf8'
  )

  assert.match(source, /import ImageLightbox/)
  assert.match(source, /<ImageLightbox/)
  assert.match(source, /@click="openAttachmentLightbox\(row\)"/)
  assert.doesNotMatch(source, /target="_blank"/)
})

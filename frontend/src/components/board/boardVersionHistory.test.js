import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isAcceptedBoardPayload,
  mapServerBoardVersions,
  shouldPreviewBoardCandidate
} from './boardVersionHistory.js'


test('maps durable versions and keeps quality candidates grouped by agent run', () => {
  const versions = mapServerBoardVersions([
    {
      version_id: 'v1',
      version_number: 1,
      source: 'manual',
      lifecycle_status: 'accepted',
      quality_status: 'passed',
      xml_ref: { read_url: '/api/file/v1' }
    },
    {
      version_id: 'v2',
      version_number: 2,
      source: 'agent',
      lifecycle_status: 'rejected',
      quality_status: 'warning',
      agent_run_id: 'run-1',
      screenshot_ref: { read_url: '/api/file/v2.png' }
    }
  ], 'v1')

  assert.equal(versions[0].id, 'v1')
  assert.equal(versions[0].is_current, true)
  assert.equal(versions[0].visibleInHistory, true)
  assert.equal(versions[1].visibleInHistory, false)
  assert.equal(versions[1].agentRunId, 'run-1')
  assert.equal(versions[1].screenshotUrl, '/api/file/v2.png')
})

test('only accepted tool payloads may replace the current board', () => {
  assert.equal(isAcceptedBoardPayload({ lifecycle_status: 'candidate', requires_visual_review: true }, true), false)
  assert.equal(isAcceptedBoardPayload({ lifecycle_status: 'rejected' }, false), false)
  assert.equal(isAcceptedBoardPayload({ lifecycle_status: 'accepted', candidate_accepted: true }, true), true)
  assert.equal(isAcceptedBoardPayload({ current_xml: '<mxfile />' }, true), true)
})

test('candidate preview is explicit and does not imply acceptance', () => {
  const preview = {
    lifecycle_status: 'candidate',
    preview_candidate: true,
    render_status: 'pending'
  }

  assert.equal(shouldPreviewBoardCandidate(preview), true)
  assert.equal(isAcceptedBoardPayload(preview, true), false)
  assert.equal(shouldPreviewBoardCandidate({ lifecycle_status: 'candidate' }), false)
  assert.equal(shouldPreviewBoardCandidate({ lifecycle_status: 'accepted', preview_candidate: true }), false)
})

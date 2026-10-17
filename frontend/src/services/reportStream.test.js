import assert from 'node:assert/strict'
import test from 'node:test'
import { readReportResponse } from './reportStream.js'

const responseFor = (text, chunkSize = 1) => {
  const bytes = new TextEncoder().encode(text)
  return new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunkSize) {
        controller.enqueue(bytes.slice(i, i + chunkSize))
      }
      controller.close()
    }
  }))
}

test('report stream survives split event headers, JSON, CRLF and Chinese UTF-8 bytes', async () => {
  const response = responseFor(
    ': keepalive\r\n\r\n' +
    'event: start\r\ndata: {"session_id":"report-1"}\r\n\r\n' +
    'event: streaming_text\r\ndata: {"chunk":"报告"}\r\n\r\n' +
    'event: complete\r\ndata: {"answer":"报告下载入口"}\r\n\r\n'
  )
  assert.deepEqual(await readReportResponse(response), {
    reportContent: '报告下载入口', sessionId: 'report-1'
  })
})

test('report stream reads the current response field and terminal session identity', async () => {
  assert.deepEqual(await readReportResponse(responseFor(
    'event: complete\ndata: {"response":"正文","session_id":"saved-1"}\n\n', 1024
  )), { reportContent: '正文', sessionId: 'saved-1' })
})

test('incomplete runs, errors, and missing terminal frames never become successful reports', async () => {
  for (const text of [
    'event: complete\ndata: {"answer":"未完","status":"incomplete"}\n\n',
    'event: fatal_error\ndata: {"error":"取数失败"}\n\n',
    'event: interrupted\ndata: {"reason":"用户暂停"}\n\n',
    'event: complete\ndata: {"session_id":"empty"}\n\n',
    'event: complete\ndata: {"answer":"截断"}',
    'event: streaming_text\ndata: {"chunk":"只有过程"}\n\n'
  ]) {
    await assert.rejects(readReportResponse(responseFor(text)))
  }
})

test('HTTP failures are reported before attempting to read a stream', async () => {
  await assert.rejects(readReportResponse(new Response('', { status: 404 })), /404/)
})

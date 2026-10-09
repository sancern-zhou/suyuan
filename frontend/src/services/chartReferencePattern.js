// [[chart:<visual_id>]] 占位符协议在前端的唯一定义。
// 与后端 app/utils/visual_ids.py 的 VISUAL_ID_PATTERN 保持一致
// （字符集 A-Za-z0-9_.-，长度 ≤100；契约测试 backend/tests/test_visual_id_protocol.py）。
// 新增消费方请导入 chartReferenceRegex，不要手写字符类。
export const VISUAL_ID_PATTERN_SOURCE = '[A-Za-z0-9_.-]{1,100}'

export function chartReferenceRegex() {
  return new RegExp(`\\[\\[chart:(${VISUAL_ID_PATTERN_SOURCE})\\]\\]`, 'g')
}

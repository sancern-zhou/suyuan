const GENERAL_PROMPT = '输入您的问题'
const SHORTCUT_GUIDE = '使用 / 选择技能，@ 引用对话文件'

export function withComposerShortcutGuide(basePlaceholder) {
  const base = String(basePlaceholder || '').trim().replace(/[.…]+$/u, '') || GENERAL_PROMPT
  return `${base}，${SHORTCUT_GUIDE}...`
}

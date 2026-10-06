// Keep nested chart placeholders such as [[chart:echarts_...]] intact.
export function wrapBracketMath(content) {
  // 【增强】识别方括号中的数学表达式 [公式内容]
  // ✅ 排除 Markdown 链接格式：[text](url)，避免误判
  return content.replace(/(?<!\[)\[(?!\[)([^\[\]]*?(?:\\[a-zA-Z]+|_[a-zA-Z0-9]+|\^[a-zA-Z0-9\{\}]+|\\frac|\\sum|\\int|\\prod|\\cdot|\\times|\\div|\\pm|\\mp|\\le|\\ge|\\ne|\\approx|\\equiv|\\partial|\\nabla|\\Delta|\\lambda|\\alpha|\\beta|\\gamma|\\delta|\\theta|\\pi|\\infty|\\sqrt|\{[^\[\]]*\})[^\[\]]*?)\](?!\()/g, (match, formula) => {
    // 如果方括号内容看起来像数学公式，用 $ 包裹
    if (formula.includes('\\') || formula.includes('^') || formula.includes('_') || formula.includes('frac') || formula.includes('sum') || formula.includes('int')) {
      return `$$${formula}$$`  // 使用 $$ 作为行间公式
    }
    return match  // 不是公式，保持原样
  })
}

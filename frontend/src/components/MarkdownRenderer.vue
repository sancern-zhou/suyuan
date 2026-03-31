<template>
  <div class="markdown-renderer" ref="markdownRef">
    <div v-html="renderedHtml" @click="handleImageClick"></div>
  </div>

  <ImageLightbox
    v-model:visible="lightboxVisible"
    :images="lightboxImages"
    v-model:start-index="currentImageIndex"
  />
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import markdownItKatex from '@traptitech/markdown-it-katex'
import markdownItMultimdTable from 'markdown-it-multimd-table'
import 'katex/dist/katex.min.css'
import ImageLightbox from './ImageLightbox.vue'

// 预处理后的内容
const processedContent = ref('')
const markdownRef = ref(null)

// 图片灯箱相关
const lightboxVisible = ref(false)
const lightboxImages = ref([])
const currentImageIndex = ref(0)

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true
}).use(markdownItMultimdTable, {
  multiline: true,  // 启用多行表格支持
  rowspan: true,    // 启用行跨列支持
  headerless: true  // 启用无头表格支持
}).use(markdownItKatex, {
  throwOnError: false,
  errorColor: '#cc0000'
})

// 自定义图片渲染规则，支持base64图片和相对路径图片
const defaultImageRender = md.renderer.rules.image || function (tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options)
}

md.renderer.rules.image = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  const srcIndex = token.attrIndex('src')

  if (srcIndex >= 0) {
    const src = token.attrs[srcIndex][1]
    const alt = token.content || ''

    // 处理base64图片
    if (src && src.startsWith('data:image/')) {
      return `<div class="md-image-wrapper">
        <img src="${src}" alt="${alt}" class="md-base64-image" />
        <p class="md-image-caption">${alt}</p>
      </div>`
    }

    // 处理外部URL图片（http/https）
    if (src && (src.startsWith('http://') || src.startsWith('https://'))) {
      return `<div class="md-image-wrapper">
        <img src="${src}" alt="${alt}" class="md-external-image" />
        <p class="md-image-caption">${alt}</p>
      </div>`
    }

    // 处理相对路径图片（/api/image/xxx）
    // 注意：后端现在返回完整URL，所以这个分支可能不会执行
    if (src && src.startsWith('/api/image/')) {
      // 使用相对路径，让浏览器自动处理（通过vite代理或同域访问）
      return `<div class="md-image-wrapper">
        <img src="${src}" alt="${alt}" class="md-external-image" />
        <p class="md-image-caption">${alt}</p>
      </div>`
    }
  }

  return defaultImageRender(tokens, idx, options, env, self)
}

// 自定义链接渲染：统一在新标签页打开，避免覆盖当前对话页面
const defaultLinkRender = md.renderer.rules.link_open || function (tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options)
}

md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  const token = tokens[idx]
  // 设置 target="_blank"
  const targetIndex = token.attrIndex('target')
  if (targetIndex < 0) {
    token.attrPush(['target', '_blank'])
  } else {
    token.attrs[targetIndex][1] = '_blank'
  }
  // 追加安全的 rel
  const relIndex = token.attrIndex('rel')
  if (relIndex < 0) {
    token.attrPush(['rel', 'noopener noreferrer'])
  } else {
    token.attrs[relIndex][1] = 'noopener noreferrer'
  }
  return defaultLinkRender(tokens, idx, options, env, self)
}

const defaultTableOpen = md.renderer.rules.table_open || function (tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options)
}

const defaultTableClose = md.renderer.rules.table_close || function (tokens, idx, options, env, self) {
  return self.renderToken(tokens, idx, options)
}

md.renderer.rules.table_open = function (tokens, idx, options, env, self) {
  return '<div class="md-table-wrapper">' + defaultTableOpen(tokens, idx, options, env, self)
}

md.renderer.rules.table_close = function (tokens, idx, options, env, self) {
  return defaultTableClose(tokens, idx, options, env, self) + '</div>'
}

const props = defineProps({
  content: {
    type: String,
    required: true
  },
  streaming: {
    type: Boolean,
    default: false
  }
})

// 监听content变化
// 【简化】现在后端统一返回完整URL，不需要预处理了
watch(() => props.content, (newContent) => {
  if (!newContent) {
    processedContent.value = ''
    return
  }

  // 直接使用原内容，markdown-it会自动处理http/https图片
  processedContent.value = newContent
}, { immediate: true })

// 已移除脱敏限制

// 【Vue 3 最佳实践】使用 computed + watch 组合确保响应式更新
const renderedHtml = computed(() => {
  // 明确声明依赖：props.content 和 props.streaming
  // Vue 3 会自动追踪这些依赖，当它们变化时重新计算
  const _content = props.content
  const _streaming = props.streaming

  let content = processedContent.value || _content || ''

  // 【调试】
  if (content.includes('|') && content.includes('------')) {
    console.log('[MarkdownRenderer] ===== 开始表格渲染 =====')
    console.log('[MarkdownRenderer] streaming:', _streaming)
    console.log('[MarkdownRenderer] content长度:', content.length)
    console.log('[MarkdownRenderer] content前100字符:', content.substring(0, 100))
  }

  // 【调试】检查原始内容的换行符
  if (content.includes('|') && content.includes('------')) {
    console.log('[MarkdownRenderer] 检测到表格内容，检查换行符')
    const lines = content.split('\n')
    const tableLineIndices = []
    lines.forEach((line, idx) => {
      if (line.includes('|')) {
        tableLineIndices.push(idx)
        console.log(`[MarkdownRenderer] 表格行 ${idx}: "${line.substring(0, 50)}..."`)
      }
    })
    console.log('[MarkdownRenderer] 表格行索引:', tableLineIndices)
  }

  // 【修复】处理字面量转义字符 \n -> 真正的换行符
  // 后端LLM可能返回包含 \n 字面量的字符串，需要转换为真正的换行符
  content = content.replace(/\\n/g, '\n')

  // 【修复】修复LLM生成的不规范表格格式 - 处理流式输出时缺少换行符的问题
  // 问题：流式输出时，表格行之间可能缺少换行符，导致类似 | ... || ... 的情况
  // 解决：将 || 替换为 |\n|（多次执行以确保完全修复）

  let oldContent = ''
  let iterations = 0
  const maxIterations = 10  // 防止无限循环

  // 循环替换，直到没有 || 为止
  while (content !== oldContent && iterations < maxIterations) {
    oldContent = content
    content = content.replace(/\|\|/g, '|\n|')
    iterations++
  }

  if (iterations > 0) {
    console.log(`[MarkdownRenderer] 表格格式修复: 执行了 ${iterations} 次替换，剩余 || 数量:`, (content.match(/\|\|/g) || []).length)
  }

  // 【增强】自动识别并包裹数学公式
  // 检测包含 LaTeX 语法的文本（如 \cdot, ^, _, \frac 等）并自动用 $ 包裹
  // 匹配模式：在行内，包含数学符号，但还没有被 $ 或 $$ 包裹的文本
  content = content.replace(/(?<!\$)(?<!\\)\b([a-zA-Z]\([^)]*\)\s*=\s*[^$\n]*?(?:\\[a-zA-Z]+|_[a-zA-Z0-9]+|\^[a-zA-Z0-9\{\}]+|\\frac|\\sum|\\int|\\prod|\\cdot|\\times|\\div|\\pm|\\mp|\\le|\\ge|\\ne|\\approx|\\equiv|\\partial|\\nabla|\\Delta|\\lambda|\\alpha|\\beta|\\gamma|\\delta|\\theta|\\pi|\\infty|\\sqrt)[^$]*)/g, (match) => {
    // 如果已经包含 $，则不处理
    if (match.includes('$')) return match
    // 用 $ 包裹公式
    return `$${match}$`
  })

  // 【增强】识别方括号中的数学表达式 [公式内容]
  content = content.replace(/\[([^\]]*?(?:\\[a-zA-Z]+|_[a-zA-Z0-9]+|\^[a-zA-Z0-9\{\}]+|\\frac|\\sum|\\int|\\prod|\\cdot|\\times|\\div|\\pm|\\mp|\\le|\\ge|\\ne|\\approx|\\equiv|\\partial|\\nabla|\\Delta|\\lambda|\\alpha|\\beta|\\gamma|\\delta|\\theta|\\pi|\\infty|\\sqrt|\{[^\]]*\})[^\]]*?)\]/g, (match, formula) => {
    // 如果方括号内容看起来像数学公式，用 $ 包裹
    if (formula.includes('\\') || formula.includes('^') || formula.includes('_') || formula.includes('frac') || formula.includes('sum') || formula.includes('int')) {
      return `$$${formula}$$`  // 使用 $$ 作为行间公式
    }
    return match  // 不是公式，保持原样
  })

  // 【调试】检查是否包含占位符
  if (content.includes('[ECHARTS_PLACEHOLDER:')) {
    console.log('[MarkdownRenderer] 收到包含占位符的内容，长度:', content.length)
    console.log('[MarkdownRenderer] 占位符数量:', (content.match(/\[ECHARTS_PLACEHOLDER:/g) || []).length)
  }

  // 【调试】检查是否包含base64图片
  const base64Matches = content.match(/!\[.*?\]\(data:image\/png;base64,[^\)]+\)/g)
  if (base64Matches) {
    console.log('[MarkdownRenderer] 发现base64图片数量:', base64Matches.length)
    base64Matches.forEach((match, index) => {
      const preview = match.substring(0, 100) + '...'
      console.log(`[MarkdownRenderer] base64图片${index + 1}预览:`, preview)
    })
  }

  // 【预处理】处理 %EMBED% 标记的内嵌图片（来自 insertChartsIntoPlaceholders）
  // 将 %EMBED%![alt](src)%EMBED% 转换为带有浮动样式的 HTML
  content = content.replace(/%EMBED%(!\[.*?\]\(data:image\/[^)]+\))%EMBED%/g, (match, markdownImage) => {
    // 转换为带有浮动样式的 HTML
    return `<div class="inline-chart-wrapper">${markdownImage}</div>`
  })

  // 【保留占位符】让ReActMessageList.vue处理截图注入，不在这里替换占位符

  const rendered = md.render(content)

  console.log('[MarkdownRenderer] ===== 渲染完成 =====')
  console.log('[MarkdownRenderer] streaming:', props.streaming)
  console.log('[MarkdownRenderer] HTML长度:', rendered.length)
  console.log('[MarkdownRenderer] HTML预览:', rendered.substring(0, 500))

  // 【调试】检查渲染后的HTML中是否包含img标签
  const imgTags = rendered.match(/<img[^>]*>/g)
  if (imgTags) {
    console.log('[MarkdownRenderer] 渲染后的img标签数量:', imgTags.length)
    imgTags.forEach((tag, index) => {
      console.log(`[MarkdownRenderer] img标签${index + 1}:`, tag.substring(0, 150))
    })
  } else {
    console.log('[MarkdownRenderer] 警告：渲染后的HTML中没有img标签！')
  }

  return rendered
})

// 收集Markdown中的所有图片
const collectImages = () => {
  nextTick(() => {
    if (!markdownRef.value) return

    // 等待所有图片加载完成后再收集
    const imgElements = markdownRef.value.querySelectorAll('img')
    const images = []

    imgElements.forEach((img, index) => {
      // 使用 getAttribute 确保获取到完整的 src
      const src = img.getAttribute('src') || img.currentSrc || img.src
      const alt = img.getAttribute('alt') || img.alt || `图片 ${index + 1}`

      console.log(`[MarkdownRenderer] 图片 ${index + 1}:`, {
        tagName: img.tagName,
        src: src,
        getAttribute_src: img.getAttribute('src'),
        img_src: img.src,
        img_currentSrc: img.currentSrc,
        complete: img.complete,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight
      })

      if (src) {
        images.push({ src, alt })
      }
    })

    lightboxImages.value = images
    console.log('[MarkdownRenderer] 收集到图片:', images.length, images)
  })
}

// 监听内容变化，重新收集图片
watch(renderedHtml, () => {
  // 等待下一帧，确保 DOM 完全渲染
  nextTick(() => {
    collectImages()

    // 再次等待，确保图片开始加载
    setTimeout(() => {
      collectImages()
    }, 100)
  })
})

// 处理图片点击 - 实时收集，确保获取最新状态
const handleImageClick = (e) => {
  if (e.target.tagName === 'IMG') {
    // 点击时实时收集图片信息
    const imgElements = markdownRef.value?.querySelectorAll('img') || []
    const images = []

    imgElements.forEach((img, index) => {
      const src = img.getAttribute('src') || img.currentSrc || img.src
      const alt = img.getAttribute('alt') || img.alt || `图片 ${index + 1}`
      if (src) {
        images.push({ src, alt })
      }
    })

    lightboxImages.value = images

    const clickedIndex = Array.from(imgElements).indexOf(e.target)
    if (clickedIndex !== -1) {
      currentImageIndex.value = clickedIndex
      lightboxVisible.value = true
      console.log('[MarkdownRenderer] 点击图片', {
        index: clickedIndex,
        targetSrc: e.target.src,
        targetGetAttribute: e.target.getAttribute('src'),
        images: lightboxImages.value
      })
    }
  }
}
</script>

<style lang="scss" scoped>
.markdown-renderer {
  line-height: 1.7;
  color: #2f2f2f;
  font-size: 14px;

  :deep(h1) {
    font-size: 24px;
    font-weight: 600;
    margin: 16px 0 12px;
    color: #1976D2;
  }
  
  :deep(h2) {
    font-size: 20px;
    font-weight: 600;
    margin: 14px 0 10px;
    color: #1976D2;
  }
  
  :deep(h3) {
    font-size: 18px;
    font-weight: 600;
    margin: 12px 0 8px;
    color: #333;
  }
  
  :deep(p) {
    margin: 8px 0;
    
    &:first-child {
      margin-top: 0;
    }
    
    &:last-child {
      margin-bottom: 0;
    }
  }
  
  :deep(ul),
  :deep(ol) {
    margin: 8px 0 8px 20px;
    padding-left: 16px;
    li {
      margin: 4px 0;
      padding-left: 4px;
    }
  }

  :deep(li) {
    line-height: 1.6;
  }
  
  :deep(strong) {
    font-weight: 600;
    color: #1976D2;
  }
  
  :deep(em) {
    font-style: italic;
    color: #666;
  }
  
  :deep(code) {
    background: #f5f5f5;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    color: #d63384;
  }
  
  :deep(a) {
    color: #1976D2;
    text-decoration: none;
    
    &:hover {
      text-decoration: underline;
    }
  }
  
  :deep(blockquote) {
    border-left: 4px solid #e0e0e0;
    padding-left: 12px;
    margin: 12px 0;
    color: #666;
    font-style: italic;
  }

  :deep(.md-table-wrapper) {
    width: fit-content;  // 根据内容自适应宽度
    max-width: 100%;  // 最大可以是100%页面宽度
    margin: 16px auto;  // 居中显示
    overflow-x: auto;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.3);
    background: linear-gradient(180deg, #ffffff 0%, #f8f9ff 100%);
  }

  // 图片样式 - 无边框样式
  :deep(.md-image-wrapper) {
    margin: 16px 0;
    text-align: center;

    img {
      cursor: zoom-in;
      transition: transform 0.2s;

      &:hover {
        transform: scale(1.02);
      }
    }
  }

  :deep(.md-base64-image) {
    max-width: 100%;
    height: auto;
    display: block;
  }

  :deep(.md-external-image) {
    max-width: 100%;
    height: auto;
    display: block;
  }

  :deep(.md-image-caption) {
    margin-top: 8px;
    font-size: 12px;
    color: #666;
    font-style: italic;
  }

  // 内联图表样式（来自 insertChartsIntoPlaceholders）
  :deep(.inline-chart-wrapper) {
    float: right;
    margin: 4px 0 8px 12px;
    clear: right;

    img {
      max-width: 280px;
      max-height: 200px;
      width: auto;
      height: auto;
      display: block;
    }
  }

  // 清除浮动
  :deep(.inline-chart-wrapper + p),
  :deep(.inline-chart-wrapper + *) {
    clear: both;
  }

  // 普通img标签样式 - 无边框样式
  :deep(img) {
    max-width: 60%;
    height: auto;
    display: block;
    margin: 12px auto;
    cursor: zoom-in;
    transition: transform 0.2s;

    &:hover {
      transform: scale(1.02);
    }
  }

  :deep(table) {
    width: auto;  // 根据内容自适应宽度
    border-collapse: separate;
    border-spacing: 0;
  }

  :deep(th),
  :deep(td) {
    padding: 10px 14px;
    border-right: 1px solid #e5e7eb;
    border-bottom: 1px solid #e5e7eb;
    text-align: left;
    font-size: 13px;
    line-height: 1.5;
    background-clip: padding-box;
    // 确保内容自动换行，避免表格过度撑大
    word-wrap: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
    max-width: 300px;  // 单个单元格最大宽度，超过后自动换行
  }

  :deep(th) {
    background: #f0f4ff;
    font-weight: 600;
    color: #1d3b8b;
  }

  :deep(tr:nth-child(even) td) {
    background: #fafbff;
  }

  :deep(tr:last-child td) {
    border-bottom: none;
  }

  :deep(th:last-child),
  :deep(td:last-child) {
    border-right: none;
  }

  // ==================== KaTeX 公式样式 ====================
  // 行内公式
  :deep(.katex) {
    font-size: 1.05em;
  }

  // 行间公式（显示公式）
  :deep(.katex-display) {
    margin: 16px 0;
    padding: 12px;
    background: #f8f9fa;
    border-radius: 6px;
    overflow-x: auto;
    text-align: center;
  }

  // 公式字体大小调整
  :deep(.katex .fontsize-ensurer) {
    font-size: 1em;
  }

  // 公式颜色
  :deep(.katex .mord) {
    color: #2f2f2f;
  }

  :deep(.katex .mop) {
    color: #1976d2;
  }

  :deep(.katex .mrel) {
    color: #e91e63;
  }

  :deep(.katex .mbin) {
    color: #ff9800;
  }

  :deep(.katex .mpunct) {
    color: #666;
  }

  // 分数样式
  :deep(.katex .mfrac) {
    margin: 0 0.1em;
  }

  // 上标下标
  :deep(.katex .msupsub) {
    vertical-align: -0.2em;
  }

  // 括号样式
  :deep(.katex .delim-size1) {
    font-size: 1.2em;
  }

  // 矩阵和数组
  :deep(.katex .arraycolsep) {
    margin: 0 0.2em;
  }

  // 确保公式在移动端也能正常显示
  @media (max-width: 768px) {
    :deep(.katex-display) {
      padding: 8px;
      margin: 12px 0;
      font-size: 0.9em;
    }
  }
}
</style>

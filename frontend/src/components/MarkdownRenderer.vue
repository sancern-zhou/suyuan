<template>
  <div class="markdown-renderer">
    <div v-html="renderedHtml"></div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import markdownItKatex from '@traptitech/markdown-it-katex'
import 'katex/dist/katex.min.css'

// 预处理后的内容
const processedContent = ref('')

const md = new MarkdownIt({
  html: true,
  linkify: true,
  breaks: true,
  typographer: true
}).use(markdownItKatex, {
  throwOnError: false,
  errorColor: '#cc0000'
})

// 自定义图片渲染规则，支持base64图片
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

const renderedHtml = computed(() => {
  let content = processedContent.value || props.content || ''

  // 【修复】处理字面量转义字符 \n -> 真正的换行符
  // 后端LLM可能返回包含 \n 字面量的字符串，需要转换为真正的换行符
  content = content.replace(/\\n/g, '\n')

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
  console.log('[MarkdownRenderer] 渲染后的HTML长度:', rendered.length)
  console.log('[MarkdownRenderer] 渲染后的HTML预览:', rendered.substring(0, 500))

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
    width: 100%;
    overflow-x: auto;
    margin: 16px 0;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.3);
    background: linear-gradient(180deg, #ffffff 0%, #f8f9ff 100%);
  }

  // 图片样式
  :deep(.md-image-wrapper) {
    margin: 16px 0;
    text-align: center;
    border: 2px solid #e0e0e0;
    padding: 10px;
    border-radius: 8px;
    background: #f9f9f9;
  }

  :deep(.md-base64-image) {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    min-height: 200px;
    display: block;
  }

  :deep(.md-external-image) {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    min-height: 200px;
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
      border-radius: 6px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
      border: 1px solid #e0e0e0;
      display: block;
    }
  }

  // 清除浮动
  :deep(.inline-chart-wrapper + p),
  :deep(.inline-chart-wrapper + *) {
    clear: both;
  }

  // 普通img标签样式
  :deep(img) {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    display: block;
    margin: 12px auto;
  }

  :deep(table) {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    min-width: 420px;
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
}
</style>

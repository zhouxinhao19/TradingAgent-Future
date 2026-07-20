import DOMPurify from 'dompurify'

/**
 * 轻量级 Markdown → HTML 渲染（专为 Commodity 报告优化）
 *
 * 支持:
 *  - **粗体**
 *  - `行内代码`
 *  - ``` 代码块
 *  - ## 标题
 *  - | pipe 表格
 *  - HTML 注释（移除）
 *  - 换行转 <br>
 *
 * 所有输出经由 DOMPurify 清洗，防止 XSS。
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = text
    // 清理备用名/品牌词
    .replace(/永安期货/gu, '')
    .replace(/永安/gu, '')
    .replace(/^# (.+)$/gm, '## $1')    // h1 → h2 归一化（同 h4 样式）
    // 转义 HTML 特殊字符
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 移除 HTML 注释 <!-- ... -->
    .replace(/<!--[\s\S]*?-->/g, '')
    // 代码块 ```...```
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const langAttr = lang ? ` class="language-${lang}"` : ''
      return `<pre><code${langAttr}>${code.trim()}</code></pre>`
    })
    // 行内代码
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // **粗体**
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // ## 标题
    .replace(/^## (.+)$/gm, '<h4 class="md-h4">$1</h4>')
    .replace(/^### (.+)$/gm, '<h5 class="md-h5">$1</h5>')
    // | pipe 表格
    .replace(/^\|(.+)\|$/gm, (line) => {
      const cells = line.split('|').filter(c => c.trim()).map(c => c.trim())
      if (cells.every(c => /^[-:]+$/.test(c.replace(/\s/g, '')))) {
        // 分隔行（|---||---|---|）— 跳过
        return ''
      }
      const tag = line.trim().startsWith('||') ? 'th' : 'td'
      const inner = cells.map(c => `<${tag}>${c}</${tag}>`).join('')
      return `<tr>${inner}</tr>`
    })
    // 包裹表格（如果连续多行包含 <tr>）
    .replace(/((?:<tr>.*?<\/tr>\n?)+)/g, '<table class="md-table">\n$1</table>')
    // 换行
    .replace(/\n/g, '<br>')

  // 最终清洗：移除所有不安全的 HTML 标签/属性，防止 XSS
  html = DOMPurify.sanitize(html)

  return html
}

/**
 * 检测文本是否包含 Markdown 表格
 */
export function hasMarkdownTable(text: string): boolean {
  return /^\|.+\|$/m.test(text)
}

/**
 * 截取文本到指定长度，保留完整句子
 */
export function truncateText(text: string, maxLen = 200): string {
  if (!text || text.length <= maxLen) return text
  const truncated = text.slice(0, maxLen)
  const lastPeriod = truncated.lastIndexOf('。')
  const lastNewline = truncated.lastIndexOf('\n')
  const cutAt = Math.max(lastPeriod, lastNewline)
  return (cutAt > maxLen * 0.6 ? truncated.slice(0, cutAt + 1) : truncated) + '…'
}

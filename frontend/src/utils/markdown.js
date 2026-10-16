/**
 * Markdown 渲染（问答与知识预览共用）。
 *
 * 安全约定：模型输出属于**不可信内容**——虽然来源是自家模型，
 * 但文档内容可能被注入，因此统一经 DOMPurify 净化后再写入 DOM。
 */

import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import MarkdownIt from 'markdown-it'

import 'highlight.js/styles/github.css'

// 按需注册：全量引入 highlight.js 会让该 chunk 达到 1MB，
// 而企业知识库场景只需覆盖常见几种语言；未注册的语言会退化为纯文本展示。
for (const [name, language] of Object.entries({ bash, java, javascript, json, python, sql, xml, yaml })) {
  hljs.registerLanguage(name, language)
}
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('html', xml)

const md = new MarkdownIt({
  html: false, // 不解析内联 HTML，从源头减少注入面
  linkify: true,
  breaks: true,
  highlight(code, language) {
    if (language && hljs.getLanguage(language)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(code, { language }).value}</code></pre>`
      } catch {
        /* 落入默认分支 */
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
  },
})

/** 渲染为可安全插入的 HTML 字符串 */
export function renderMarkdown(text) {
  return DOMPurify.sanitize(md.render(text || ''), {
    ADD_ATTR: ['target', 'rel'],
  })
}

/** 供代码块复制按钮等场景使用：把 HTML 转回纯文本 */
export function htmlToText(html) {
  const container = document.createElement('div')
  container.innerHTML = html
  return container.textContent || ''
}

export default md

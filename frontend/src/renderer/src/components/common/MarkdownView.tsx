import { memo, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { createHighlighter, type Highlighter } from 'shiki'
import { cn } from '@renderer/lib/utils'

let highlighterPromise: Promise<Highlighter> | null = null

function getHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: ['tokyo-night'],
      langs: [
        'ts',
        'tsx',
        'js',
        'jsx',
        'python',
        'bash',
        'shell',
        'json',
        'sql',
        'markdown',
        'yaml',
        'html',
        'css'
      ]
    })
  }
  return highlighterPromise
}

const ALIASES: Record<string, string> = {
  sh: 'bash',
  zsh: 'bash',
  console: 'bash',
  py: 'python',
  yml: 'yaml',
  md: 'markdown',
  text: 'markdown',
  plaintext: 'markdown'
}

function CodeBlock({ code, lang }: { code: string; lang: string }): React.JSX.Element {
  const [html, setHtml] = useState<string | null>(null)
  const resolved = ALIASES[lang] ?? lang

  useEffect(() => {
    let alive = true
    getHighlighter()
      .then((h) => {
        if (!alive) return
        setHtml(h.codeToHtml(code, { lang: resolved, theme: 'tokyo-night' }))
      })
      .catch(() => {
        if (alive) setHtml(null)
      })
    return () => {
      alive = false
    }
  }, [code, resolved])

  if (html) {
    return <div dangerouslySetInnerHTML={{ __html: html }} />
  }
  return (
    <pre className="bg-[#1a1b26]">
      <code>{code}</code>
    </pre>
  )
}

interface MarkdownViewProps {
  content: string
  className?: string
}

export const MarkdownView = memo(function MarkdownView({ content, className }: MarkdownViewProps) {
  return (
    <div className={cn('prose-kate', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }) {
            const child = Array.isArray(children) ? children[0] : children
            if (child && typeof child === 'object' && 'props' in child) {
              const { className: cls, children: codeChildren } = child.props as {
                className?: string
                children?: unknown
              }
              const lang = /language-(\w+)/.exec(cls ?? '')?.[1] ?? 'markdown'
              const code = String(codeChildren ?? '').replace(/\n$/, '')
              return <CodeBlock code={code} lang={lang} />
            }
            return <pre>{children}</pre>
          },
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            )
          }
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})

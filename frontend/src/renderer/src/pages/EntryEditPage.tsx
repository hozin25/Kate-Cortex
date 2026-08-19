import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { ArrowLeft, FolderOpen, Save } from 'lucide-react'
import { api } from '@renderer/api/client'
import { Spinner } from '@renderer/components/common/Badges'
import { toast } from '@renderer/stores/toast'
import { cn } from '@renderer/lib/utils'
import type { CollectionCount, Entry } from '@renderer/types'

interface FormState {
  title: string
  collections: string[]
  content: string
}

const EMPTY_FORM: FormState = { title: '', collections: [], content: '' }

export function EntryEditPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const isNew = !id
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [original, setOriginal] = useState<FormState | null>(isNew ? EMPTY_FORM : null)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [allCollections, setAllCollections] = useState<CollectionCount[]>([])

  useEffect(() => {
    api
      .get<CollectionCount[]>('/collections')
      .then(setAllCollections)
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (isNew) return
    api
      .get<Entry>(`/entries/${id}`)
      .then((e) => {
        const state = {
          title: e.title,
          collections: e.collections,
          content: e.content
        }
        setForm(state)
        setOriginal(state)
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : '条目加载失败'))
      .finally(() => setLoading(false))
  }, [id, isNew])

  const dirty =
    original !== null &&
    (form.title !== original.title ||
      form.collections.join(' ') !== original.collections.join(' ') ||
      form.content !== original.content)

  const toggleCollection = (name: string): void => {
    setForm((prev) => ({
      ...prev,
      collections: prev.collections.includes(name)
        ? prev.collections.filter((c) => c !== name)
        : [...prev.collections, name]
    }))
  }

  const handleSave = async (): Promise<void> => {
    if (!form.title.trim()) {
      toast.error('标题不能为空')
      return
    }
    setSaving(true)
    const payload = {
      title: form.title.trim(),
      collections: form.collections,
      content: form.content
    }
    try {
      const entry = isNew
        ? await api.post<Entry>('/entries', { ...payload, source: 'manual' })
        : await api.put<Entry>(`/entries/${id}`, payload)
      toast.success(isNew ? `已创建《${entry.title}》` : '已保存')
      navigate(`/entries/${entry.id}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-6 text-zinc-500" />
      </div>
    )
  }

  const selectable = Array.from(
    new Set([...allCollections.map((c) => c.name), ...form.collections])
  )

  return (
    <div className="flex h-full min-h-0 flex-col px-8 py-6">
      <div className="flex items-center gap-2 text-xs text-zinc-500">
        <Link
          to={isNew ? '/library' : `/entries/${id}`}
          className="flex items-center gap-1 transition hover:text-zinc-300"
        >
          <ArrowLeft className="size-3.5" />
          {isNew ? '知识库' : '条目详情'}
        </Link>
      </div>
      <div className="mt-3 flex items-center justify-between gap-4">
        <input
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          placeholder="标题"
          className="w-full border-b border-transparent bg-transparent font-display text-xl text-zinc-50 outline-none transition placeholder:text-zinc-700 focus:border-aurora-indigo/40"
        />
        <button
          onClick={() => void handleSave()}
          disabled={!dirty || saving}
          className={cn(
            'flex shrink-0 items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] font-medium transition',
            dirty && !saving
              ? 'bg-gradient-to-r from-aurora-indigo to-aurora-violet text-white shadow-lg shadow-aurora-indigo/25 hover:brightness-110'
              : 'border border-white/10 bg-white/[0.04] text-zinc-600'
          )}
        >
          {saving ? <Spinner className="size-4" /> : <Save className="size-4" />}
          {isNew ? '创建' : '保存'}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <FolderOpen className="size-3 text-zinc-600" />
          {selectable.length > 0 ? (
            selectable.map((name) => {
              const selected = form.collections.includes(name)
              return (
                <button
                  key={name}
                  onClick={() => toggleCollection(name)}
                  className={cn(
                    'rounded-full border px-2 py-0.5 text-[11px] transition',
                    selected
                      ? 'border-aurora-indigo/40 bg-aurora-indigo/15 text-aurora-indigo'
                      : 'border-white/[0.08] bg-white/[0.03] text-zinc-500 hover:text-zinc-300'
                  )}
                >
                  {name}
                </button>
              )
            })
          ) : (
            <span className="text-[11px] text-zinc-600">还没有合集，可在知识库页创建</span>
          )}
        </div>
      </div>

      <div className="glass mt-4 min-h-0 flex-1 overflow-hidden rounded-2xl">
        <CodeMirror
          value={form.content}
          onChange={(content) => setForm({ ...form, content })}
          extensions={[markdown()]}
          theme="dark"
          height="100%"
          className="h-full text-[14px]"
          placeholder="正文（Markdown）… 使用 [[slug]] 链接其他条目"
          basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false }}
        />
      </div>
    </div>
  )
}

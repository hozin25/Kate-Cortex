import { useEffect, useRef } from 'react'
import { motion } from 'motion/react'
import { MessagesSquare } from 'lucide-react'
import { ChatInput, RagToggle } from '@renderer/components/chat/ChatInput'
import { MessageBubble, StreamingBubble } from '@renderer/components/chat/MessageBubble'
import { SavedCard, SuggestCard } from '@renderer/components/chat/Cards'
import { CitationChips } from '@renderer/components/chat/CitationChips'
import { MemoryCard } from '@renderer/components/chat/MemoryCard'
import { MemoryRefChips } from '@renderer/components/chat/MemoryRefChips'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { GradientText } from '@renderer/components/common/Glass'
import { useChatStore } from '@renderer/stores/chat'
import { useSettingsStore } from '@renderer/stores/settings'

export function ChatPage(): React.JSX.Element {
  const store = useChatStore()
  const {
    messages,
    streaming,
    streamText,
    savedCards,
    suggestCards,
    citations,
    memoryCards,
    memoryRefs,
    currentId,
    error
  } = store
  const ragEnabled = store.ragEnabled
  const settings = useSettingsStore((s) => s.settings)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, streamText, savedCards.length, suggestCards.length, memoryCards.length])

  useEffect(() => {
    if (!currentId && store.sessions.length > 0) void store.selectSession(store.sessions[0].id)
  }, [currentId, store.sessions, store.selectSession, store])

  if (!currentId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-6">
        <EmptyState
          icon={<MessagesSquare className="size-6" />}
          title={
            settings?.provider_keys && Object.keys(settings.provider_keys).length > 0
              ? '开始一段新对话'
              : '先到设置页配置 API Key'
          }
          hint={
            settings?.provider_keys && Object.keys(settings.provider_keys).length > 0
              ? '左侧点击「新会话」，聊聊项目、记下想法；说「记一下」就能存进知识库。'
              : 'Kate 需要 DeepSeek 或 GLM 的 API Key 才能对话，配置后即可开始。'
          }
        />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between px-6 pb-2 pt-4">
        <div className="text-sm text-zinc-400">
          <GradientText>
            {store.sessions.find((s) => s.id === currentId)?.title ?? '对话'}
          </GradientText>
        </div>
        <RagToggle
          enabled={ragEnabled ?? settings?.rag_default ?? false}
          onChange={(v) => useChatStore.setState({ ragEnabled: v })}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-5 py-4">
          {messages.map((m, i) => (
            <MessageBubble
              key={m.id}
              message={m}
              isLast={i === messages.length - 1}
              streaming={streaming}
              onRegenerate={() => void store.regenerate()}
              onEdit={(content) => void store.editMessage(m.id, content)}
              onDelete={() => void store.deleteMessage(m.id)}
            />
          ))}

          {streaming && <StreamingBubble text={streamText} />}

          {!streaming && citations.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-start"
            >
              <CitationChips citations={citations} />
            </motion.div>
          )}

          {!streaming && memoryRefs.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-start"
            >
              <MemoryRefChips memories={memoryRefs} />
            </motion.div>
          )}

          {memoryCards.map((memory, i) => (
            <MemoryCard
              key={`${memory.entry_id}-${i}`}
              memory={memory}
              onUndo={() => store.undoMemory(memory.entry_id)}
            />
          ))}

          {savedCards.map((saved, i) => (
            <SavedCard key={`${saved.entry_id}-${i}`} saved={saved} />
          ))}

          {suggestCards.map((suggest, i) => (
            <SuggestCard
              key={`${suggest.title}-${i}`}
              suggest={suggest}
              conversationId={currentId}
              onDismiss={() => store.dismissSuggest(i)}
            />
          ))}

          {error && (
            <div className="mx-auto max-w-lg rounded-xl border border-rose-400/25 bg-rose-500/10 px-4 py-2.5 text-center text-[13px] text-rose-200">
              {error}
              <button
                onClick={store.clearError}
                className="ml-2 underline decoration-dotted hover:text-rose-100"
              >
                知道了
              </button>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="px-6 pb-4 pt-2">
        <ChatInput
          streaming={streaming}
          onSend={(c, imgs) => void store.sendMessage(c, imgs)}
          onStop={store.stopStreaming}
        />
      </div>
    </div>
  )
}

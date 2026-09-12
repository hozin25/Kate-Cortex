import type { ProviderName } from '@renderer/types'

export interface ProviderMeta {
  name: ProviderName
  label: string
  keyHint: string
  modelHint: string
}

/** 对话服务商元信息：设置页 Key 表单 / 默认模型 / Agent 指定模型共用 */
export const PROVIDERS: ProviderMeta[] = [
  { name: 'glm', label: 'GLM（智谱）', keyHint: '…xxx.Sxxxx', modelHint: 'glm-4.7-flash' },
  {
    name: 'siliconflow',
    label: '硅基流动（免费档）',
    keyHint: 'sk-…',
    modelHint: 'Qwen/Qwen3-8B'
  },
  {
    name: 'modelscope',
    label: '魔搭 ModelScope（每日 2000 次免费）',
    keyHint: 'ms-…',
    modelHint: 'Qwen/Qwen3-235B-A22B-Instruct-2507'
  },
  { name: 'deepseek', label: 'DeepSeek', keyHint: 'sk-…', modelHint: 'deepseek-chat' },
  {
    name: 'glm-coding',
    label: 'GLM 编程套餐',
    keyHint: '…xxx.Sxxxx（与智谱 API key 相同）',
    modelHint: 'glm-5.3'
  }
]

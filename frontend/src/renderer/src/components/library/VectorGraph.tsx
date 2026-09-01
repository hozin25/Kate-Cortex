/* eslint-disable react/no-unknown-property -- <points>/<pointsMaterial> 是 R3F
   内在元素，geometry/vertexColors 等是 three.js 属性而非 DOM 属性 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { FolderOpen, Move3d, RefreshCw } from 'lucide-react'
import { api } from '@renderer/api/client'
import { Spinner } from '@renderer/components/common/Badges'
import { EmptyState } from '@renderer/components/common/EmptyState'
import { cn } from '@renderer/lib/utils'
import { collectionColor, pointColor, primaryCollection } from './pointColors'
import type { Projection, ProjectionPoint } from '@renderer/types'

const METHOD_LABELS: Record<string, string> = {
  tsne: 't-SNE',
  pca: 'PCA 预览'
}

const POINT_SIZE = 0.12
const RAYCAST_THRESHOLD = 0.08

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}

/** 径向渐变软粒子贴图：additive blending 下呈辉光感，无需后处理 */
function makeSpriteTexture(): THREE.Texture {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')
  if (ctx) {
    const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    grad.addColorStop(0, 'rgba(255,255,255,1)')
    grad.addColorStop(0.5, 'rgba(255,255,255,0.85)')
    grad.addColorStop(0.75, 'rgba(255,255,255,0.25)')
    grad.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, size, size)
  }
  return new THREE.CanvasTexture(canvas)
}

interface PointCloudProps {
  points: ProjectionPoint[]
  allNames: string[]
  texture: THREE.Texture
  onHover: (index: number | null) => void
  onSelect: (point: ProjectionPoint) => void
}

function PointCloud({
  points,
  allNames,
  texture,
  onHover,
  onSelect
}: PointCloudProps): React.JSX.Element {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    const positions = new Float32Array(points.length * 3)
    const colors = new Float32Array(points.length * 3)
    const color = new THREE.Color()
    points.forEach((p, i) => {
      positions.set([p.x, p.y, p.z], i * 3)
      color.set(pointColor(p.collections, allNames))
      colors.set([color.r, color.g, color.b], i * 3)
    })
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    return geo
  }, [points, allNames])

  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    <points
      geometry={geometry}
      onPointerMove={(e) => {
        e.stopPropagation()
        if (typeof e.index === 'number') onHover(e.index)
      }}
      onPointerOut={() => onHover(null)}
      onClick={(e) => {
        if (typeof e.index === 'number') onSelect(points[e.index])
      }}
    >
      <pointsMaterial
        size={POINT_SIZE}
        vertexColors
        map={texture}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
        alphaTest={0.02}
      />
    </points>
  )
}

export function VectorGraph(): React.JSX.Element {
  const navigate = useNavigate()
  const [projection, setProjection] = useState<Projection | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set())
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [pointer, setPointer] = useState({ x: 0, y: 0 })
  const [webgl] = useState(webglAvailable)
  const texture = useMemo(() => makeSpriteTexture(), [])

  const load = useCallback(async (refresh = false) => {
    try {
      const data = refresh
        ? await api.post<Projection>('/embeddings/projection/refresh')
        : await api.get<Projection>('/embeddings/projection')
      setProjection(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '投影加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 挂载即取投影；setState 全在异步回调，避免级联渲染
  useEffect(() => {
    let cancelled = false
    api
      .get<Projection>('/embeddings/projection')
      .then((data) => {
        if (cancelled) return
        setProjection(data)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '投影加载失败')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const allNames = useMemo(() => {
    const names = new Set<string>()
    for (const p of projection?.points ?? []) {
      const primary = primaryCollection(p.collections)
      if (primary) names.add(primary)
    }
    return [...names]
  }, [projection])

  const visible = useMemo(
    () =>
      (projection?.points ?? []).filter((p) => {
        const primary = primaryCollection(p.collections)
        return primary === null || !hidden.has(primary)
      }),
    [projection, hidden]
  )

  const legend = useMemo(() => {
    const counts = new Map<string, number>()
    for (const p of projection?.points ?? []) {
      const primary = primaryCollection(p.collections)
      const key = primary ?? ''
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [projection])

  const toggleHidden = (name: string): void => {
    setHoverIndex(null)
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const hovered: ProjectionPoint | null = hoverIndex !== null ? (visible[hoverIndex] ?? null) : null

  if (error) {
    return (
      <GraphFrame>
        <EmptyState icon={<RefreshCw className="size-6" />} title="立体视图加载失败" hint={error} />
        <button
          onClick={() => void load()}
          className="mt-3 rounded-xl border border-aurora-indigo/30 bg-aurora-indigo/15 px-3 py-1.5 text-xs text-zinc-100 transition hover:brightness-125"
        >
          重试
        </button>
      </GraphFrame>
    )
  }

  if (loading && !projection) {
    return (
      <GraphFrame>
        <Spinner className="size-5 text-zinc-500" />
        <span className="mt-3 text-xs text-zinc-600">正在加载语义投影…</span>
      </GraphFrame>
    )
  }

  if (projection && !projection.available) {
    return (
      <GraphFrame>
        <EmptyState
          icon={<Move3d className="size-6" />}
          title="向量扩展不可用"
          hint="sqlite-vec 未加载或未配置 embedding，立体视图缺席（可在设置页检查语义检索状态）"
        />
      </GraphFrame>
    )
  }

  if (projection && projection.points.length < 3) {
    return (
      <GraphFrame>
        <EmptyState
          icon={<Move3d className="size-6" />}
          title="条目还太少"
          hint="至少需要 3 条已索引条目才能生成三维投影；先在对话里让 Kate 记几条吧"
        />
      </GraphFrame>
    )
  }

  if (!webgl) {
    return (
      <GraphFrame>
        <EmptyState
          icon={<Move3d className="size-6" />}
          title="WebGL 不可用"
          hint="当前环境没有启用硬件加速，无法渲染三维视图"
        />
      </GraphFrame>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between text-xs text-zinc-600">
        <span>
          {projection?.n ?? 0} 条 · {METHOD_LABELS[projection?.method ?? ''] ?? projection?.method}
          {projection && projection.computed_ms > 0 && ` · ${projection.computed_ms}ms`}
        </span>
        <button
          onClick={() => {
            setLoading(true)
            void load(true)
          }}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-zinc-500 transition hover:text-zinc-200 disabled:opacity-50"
        >
          {loading ? <Spinner className="size-3" /> : <RefreshCw className="size-3" />}
          重算投影
        </button>
      </div>

      <div
        className="relative mt-3 min-h-0 flex-1 overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-950/40"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          setPointer({ x: e.clientX - rect.left, y: e.clientY - rect.top })
        }}
      >
        <Canvas
          camera={{ position: [0, 0, 3], fov: 50 }}
          onCreated={({ raycaster }) => {
            raycaster.params.Points = { threshold: RAYCAST_THRESHOLD }
          }}
          dpr={[1, 2]}
        >
          <PointCloud
            points={visible}
            allNames={allNames}
            texture={texture}
            onHover={setHoverIndex}
            onSelect={(p) => navigate(`/entries/${p.entry_id}`)}
          />
          <OrbitControls enableDamping dampingFactor={0.1} />
        </Canvas>

        {/* 图例（右上角）：按合集着色，点击隐藏/显示 */}
        {legend.length > 0 && (
          <div className="glass absolute right-3 top-3 max-w-44 rounded-xl p-2.5">
            <div className="px-1 pb-1 text-[10px] uppercase tracking-widest text-zinc-600">
              合集
            </div>
            {legend.map(([name, count]) => {
              const isHidden = name !== '' && hidden.has(name)
              return (
                <button
                  key={name || '_uncollected'}
                  onClick={() => name && toggleHidden(name)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-xs transition',
                    name === '' ? 'cursor-default text-zinc-500' : 'hover:bg-white/[0.06]',
                    isHidden && 'opacity-35'
                  )}
                >
                  <span
                    className="size-2 shrink-0 rounded-full"
                    style={{
                      backgroundColor: collectionColor(allNames, name || null),
                      boxShadow: `0 0 6px ${collectionColor(allNames, name || null)}`
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate text-zinc-300">{name || '未合集'}</span>
                  <span className="text-[10px] text-zinc-600">{count}</span>
                </button>
              )
            })}
          </div>
        )}

        {/* 悬停 tooltip：标题 + 合集徽章 */}
        {hovered && (
          <div
            className="glass pointer-events-none absolute z-10 max-w-72 rounded-xl p-3"
            style={{
              left: pointer.x + 14,
              top: pointer.y + 14
            }}
          >
            <div className="text-sm font-medium leading-5 text-zinc-100">{hovered.title}</div>
            {hovered.collections.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {hovered.collections.map((c) => (
                  <span
                    key={c}
                    className="flex items-center gap-0.5 rounded-md border border-aurora-indigo/20 bg-aurora-indigo/10 px-1.5 py-0.5 text-[10px] text-aurora-indigo/90"
                  >
                    <FolderOpen className="size-2.5" />
                    {c}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-1.5 text-[10px] text-zinc-600">点击查看条目详情</div>
          </div>
        )}

        {/* 操作提示 */}
        <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-1.5 text-[10px] text-zinc-700">
          <Move3d className="size-3" />
          拖拽旋转 · 滚轮缩放 · 右键平移 · 点击跳转
        </div>
      </div>
    </div>
  )
}

function GraphFrame({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="mt-4 flex min-h-0 flex-1 flex-col items-center justify-center rounded-2xl border border-white/[0.06] bg-ink-950/40">
      {children}
    </div>
  )
}

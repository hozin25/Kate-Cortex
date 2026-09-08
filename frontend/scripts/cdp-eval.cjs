// 一次性 CDP 工具：在打包版 Kate Cortex 渲染进程里执行 JS。
// 用法：node scripts/cdp-eval.cjs "<js 表达式>"
const http = require('http')

function getPages() {
  return new Promise((resolve, reject) => {
    http
      .get('http://127.0.0.1:9222/json/list', (res) => {
        let raw = ''
        res.on('data', (d) => (raw += d))
        res.on('end', () => resolve(JSON.parse(raw)))
      })
      .on('error', reject)
  })
}

async function main() {
  const expr = process.argv[2]
  if (!expr) throw new Error('missing js expression')
  const pages = await getPages()
  const page = pages.find((p) => p.type === 'page')
  if (!page) throw new Error('no page target')
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((r, j) => {
    ws.onopen = r
    ws.onerror = j
  })
  const send = (id, method, params) =>
    ws.send(JSON.stringify({ id, method, params }))
  let nextId = 1
  const waiters = new Map()
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && waiters.has(msg.id)) {
      waiters.get(msg.id)(msg)
      waiters.delete(msg.id)
    }
  }
  const call = (method, params) =>
    new Promise((resolve) => {
      const id = nextId++
      waiters.set(id, resolve)
      send(id, method, params)
    })
  const result = await call('Runtime.evaluate', {
    expression: expr,
    awaitPromise: true,
    returnByValue: true
  })
  console.log(JSON.stringify(result.result, null, 2))
  ws.close()
}

main().catch((err) => {
  console.error(String(err))
  process.exit(1)
})

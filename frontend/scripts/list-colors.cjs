const { readdirSync, readFileSync, statSync } = require('node:fs')
const { join } = require('node:path')
const set = new Set()
;(function walk(d) {
  for (const f of readdirSync(d)) {
    const p = join(d, f)
    if (statSync(p).isDirectory()) walk(p)
    else if (/\.(tsx|ts)$/.test(f))
      String(readFileSync(p, 'utf8'))
        .split(/[\s'"`]/)
        .forEach((t) => {
          if (/(white|zinc|ink)[-/.[]/.test(t + '$') && /(^|:)(text|bg|border|ring|placeholder|decoration|from|to|shadow|divide|marker|fill|stroke|outline)-/.test(t))
            set.add(t)
        })
  }
})('src/renderer/src')
console.log([...set].sort().join('\n'))

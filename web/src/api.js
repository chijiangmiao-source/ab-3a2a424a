// 后端调用。生产环境由 nginx 同源代理 /api，开发环境由 vite 代理。
const BASE = ''

async function parseError(res) {
  let detail = `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail)) {
      detail = body.detail
        .map((d) => {
          const loc = Array.isArray(d.loc) ? d.loc.slice(1).join('.') : ''
          return loc ? `${loc}: ${d.msg}` : d.msg
        })
        .join('；')
    }
  } catch {
    /* 忽略非 JSON 错误体 */
  }
  return detail
}

export async function runAudit(payload) {
  const res = await fetch(`${BASE}/api/audit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    throw new Error(await parseError(res))
  }
  return res.json()
}

export async function fetchSample() {
  const res = await fetch(`${BASE}/api/sample`)
  if (!res.ok) throw new Error('示例加载失败')
  return res.json()
}

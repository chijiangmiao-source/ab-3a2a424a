import { useMemo, useState } from 'react'
import { fetchSample, runAudit } from './api.js'
import ResultView from './ResultView.jsx'

const NAMES = ['α 相', 'β 相', 'γ 相', 'δ 相', 'ε 相']
const RIDS = ['hkl-01', 'hkl-02', 'hkl-03']

function emptyInput() {
  return {
    phases: NAMES.slice(0, 3).map((id) => ({ id })),
    reflections: RIDS.map((id, i) => ({ id, cost: i + 1 })),
    // phaseId -> Set(reflectionId)
    occurrences: Object.fromEntries(NAMES.slice(0, 3).map((id) => [id, new Set()]))
  }
}

function fromSample(s) {
  return {
    phases: s.phases.map((p) => ({ id: p.id })),
    reflections: s.reflections.map((r) => ({ id: r.id, cost: r.cost })),
    occurrences: Object.fromEntries(
      s.phases.map((p) => [p.id, new Set(s.occurrences[p.id] ?? [])])
    )
  }
}

export default function App() {
  const [input, setInput] = useState(emptyInput)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const phaseIds = input.phases.map((p) => p.id)
  const reflIds = input.reflections.map((r) => r.id)

  const localError = useMemo(() => validate(phaseIds, reflIds, input.reflections), [
    input
  ])

  function update(mut) {
    setInput((prev) => {
      const next = structuredClone(prev)
      next.occurrences = {}
      for (const [k, v] of Object.entries(prev.occurrences)) {
        next.occurrences[k] = new Set(v)
      }
      mut(next)
      return next
    })
    setResult(null)
  }

  function renamePhase(index, nextId) {
    update((d) => {
      const oldId = d.phases[index].id
      d.phases[index].id = nextId
      // 仅在目标名尚未被其他相占用时迁移出现集合，避免覆盖
      if (nextId !== oldId && !(nextId in d.occurrences)) {
        d.occurrences[nextId] = d.occurrences[oldId] ?? new Set()
        delete d.occurrences[oldId]
      }
    })
  }

  function addPhase() {
    update((d) => {
      const id = uniqueId('相', (x) => d.phases.some((p) => p.id === x))
      d.phases.push({ id })
      d.occurrences[id] = new Set()
    })
  }

  function removePhase(index) {
    update((d) => {
      const [gone] = d.phases.splice(index, 1)
      delete d.occurrences[gone.id]
    })
  }

  function renameReflection(index, nextId) {
    update((d) => {
      const oldId = d.reflections[index].id
      if (nextId === oldId) return
      d.reflections[index].id = nextId
      // 重名时不迁移（编辑器会提示标识重复，禁止提交）
      if (d.reflections.some((r, i2) => i2 !== index && r.id === nextId)) return
      for (const set of Object.values(d.occurrences)) {
        if (set.has(oldId)) {
          set.delete(oldId)
          set.add(nextId)
        }
      }
    })
  }

  function setCost(index, cost) {
    update((d) => {
      d.reflections[index].cost = cost
    })
  }

  function addReflection() {
    update((d) => {
      const id = uniqueId('hkl-', (x) => d.reflections.some((r) => r.id === x), 2)
      d.reflections.push({ id, cost: 1 })
    })
  }

  function removeReflection(index) {
    update((d) => {
      const [gone] = d.reflections.splice(index, 1)
      for (const set of Object.values(d.occurrences)) set.delete(gone.id)
    })
  }

  function toggleOcc(phaseId, reflId) {
    update((d) => {
      const set = d.occurrences[phaseId]
      if (set.has(reflId)) set.delete(reflId)
      else set.add(reflId)
    })
  }

  function loadSample() {
    setError('')
    fetchSample()
      .then((s) => {
        setInput(fromSample(s))
        setResult(null)
      })
      .catch((e) => setError(e.message))
  }

  async function submit() {
    setError('')
    setLoading(true)
    const payload = {
      phases: input.phases.map((p) => ({ id: p.id })),
      reflections: input.reflections.map((r) => ({
        id: r.id,
        cost: Number(r.cost)
      })),
      occurrences: Object.fromEntries(
        input.phases.map((p) => [p.id, [...(input.occurrences[p.id] ?? [])]])
      )
    }
    try {
      const r = await runAudit(payload)
      // 成功或"全集不可分"都返回 200 + 结果体；输入原样保留在编辑器中
      setResult(r)
    } catch (e) {
      setResult(null)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="topbar">
        <h1>同步辐射粉末衍射复核 · 审计台</h1>
        <p className="subtitle">
          编辑候选晶相、诊断反射、预期出现关系与曝光代价，精确求解可区分每对候选相的
          <b> 最小总代价</b> 反射集（次级目标：反射数最少；同优时按反射标识序列取规范方案）。
        </p>
      </header>

      <section className="panel">
        <div className="panel-head">
          <h2>① 候选晶相（{phaseIds.length} / 18）</h2>
          <div className="row-actions">
            <button type="button" onClick={addPhase} disabled={phaseIds.length >= 18}>
              + 添加相
            </button>
          </div>
        </div>
        <div className="id-list">
          {input.phases.map((p, i) => (
            <div className="id-row" key={i}>
              <input
                value={p.id}
                onChange={(e) => renamePhase(i, e.target.value)}
                aria-label={`候选相 ${i + 1} 标识`}
              />
              <button
                type="button"
                className="ghost danger"
                onClick={() => removePhase(i)}
                disabled={phaseIds.length <= 2}
                title="删除该相"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>② 诊断反射与曝光代价（{reflIds.length} / 48）</h2>
          <button type="button" onClick={addReflection} disabled={reflIds.length >= 48}>
            + 添加反射
          </button>
        </div>
        <div className="id-list">
          {input.reflections.map((r, i) => (
            <div className="id-row" key={i}>
              <input
                value={r.id}
                onChange={(e) => renameReflection(i, e.target.value)}
                aria-label={`反射 ${i + 1} 标识`}
              />
              <input
                className="cost-input"
                type="number"
                min={1}
                step={1}
                value={r.cost}
                onChange={(e) => setCost(i, e.target.value)}
                aria-label={`反射 ${r.id} 曝光代价`}
              />
              <span className="unit">曝光代价（正整数）</span>
              <button
                type="button"
                className="ghost danger"
                onClick={() => removeReflection(i)}
                disabled={reflIds.length <= 1}
                title="删除该反射"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>③ 预期出现关系矩阵（勾选 = 该反射预期在该相中出现）</h2>
        <p className="hint">
          两相仅在某个所选反射上的出现位 <b>不同</b> 时，才算被该反射区分。
        </p>
        <div className="table-scroll">
          <table className="matrix edit-matrix">
            <thead>
              <tr>
                <th className="row-head-col">相 ＼ 反射</th>
                {input.reflections.map((r, j) => (
                  <th key={j}>{r.id}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {input.phases.map((p, i) => (
                <tr key={i}>
                  <th className="row-head">{p.id}</th>
                  {input.reflections.map((r, j) => {
                    const on = input.occurrences[p.id]?.has(r.id) ?? false
                    return (
                      <td key={j} className={on ? 'cell-on' : 'cell-off'}>
                        <label className="check-wrap">
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={() => toggleOcc(p.id, r.id)}
                          />
                          <span>{on ? '出现' : '—'}</span>
                        </label>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel actions-panel">
        <div>
          <button
            type="button"
            className="primary"
            onClick={submit}
            disabled={loading || !!localError}
          >
            {loading ? '审计中…' : '启动审计'}
          </button>
          <button type="button" className="ghost" onClick={loadSample}>
            载入示例
          </button>
        </div>
        {localError && <div className="error">⚠ {localError}</div>}
        {error && <div className="error">⚠ 接口错误：{error}</div>}
      </section>

      {result && <ResultView result={result} />}
    </div>
  )
}

function validate(phaseIds, reflIds, reflections) {
  if (phaseIds.length < 2 || phaseIds.length > 18) return '候选相数量须在 2 至 18 之间'
  if (reflIds.length < 1 || reflIds.length > 48) return '反射数量须在 1 至 48 之间'
  if (phaseIds.some((x) => !x.trim())) return '候选相标识不能为空'
  if (reflIds.some((x) => !x.trim())) return '反射标识不能为空'
  if (new Set(phaseIds.map((x) => x.trim())).size !== phaseIds.length)
    return '候选相标识必须唯一'
  if (new Set(reflIds.map((x) => x.trim())).size !== reflIds.length)
    return '反射标识必须唯一'
  for (const r of reflections) {
    const c = Number(r.cost)
    if (!Number.isInteger(c) || c <= 0) return `反射 ${r.id} 的代价必须是正整数`
  }
  return ''
}

function uniqueId(prefix, taken, pad = 0) {
  let i = 1
  while (taken(`${prefix}${String(i).padStart(pad, '0')}`)) i += 1
  return `${prefix}${String(i).padStart(pad, '0')}`
}

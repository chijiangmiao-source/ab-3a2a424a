import { useMemo, useState } from 'react'

const CLASS_META = {
  mandatory: { label: '必选', cls: 'tag-mandatory' },
  optional: { label: '可选', cls: 'tag-optional' },
  never: { label: '从不选', cls: 'tag-never' }
}

export default function ResultView({ result }) {
  if (!result.feasible) return <InfeasibleView result={result} />
  return <FeasibleView result={result} />
}

function InfeasibleView({ result }) {
  const pairs = result.indistinguishable_pairs
  return (
    <section className="panel result-panel">
      <h2 className="result-bad">④ 全集仍不能区分所有候选相</h2>
      <p className="hint">
        下列相对在 <b>全部 {result.reflection_ids.length} 个反射</b>上的出现位都相同，
        无论选择哪个反射集都无法区分。输入已保留，可调整出现关系或补充反射后重新审计。
      </p>
      <ul className="indist-list">
        {pairs.map((p, i) => (
          <li key={i}>
            <span className="phase-chip">{p[0]}</span>
            <span className="pair-x">≡</span>
            <span className="phase-chip">{p[1]}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function FeasibleView({ result }) {
  const {
    phase_ids: phases,
    reflection_ids: refs,
    costs,
    matrix,
    canonical_solution: chosen,
    total_cost,
    reflection_count,
    classification,
    pair_evidence: evidence
  } = result

  const chosenSet = useMemo(() => new Set(chosen), [chosen])
  const [activePair, setActivePair] = useState(null)

  // 浏览器端独立复算：代价与逐对区分，便于审计核对
  const recompute = useMemo(() => {
    const cost = chosen.reduce((s, r) => s + costs[r], 0)
    const idx = Object.fromEntries(refs.map((r, i) => [r, i]))
    const failures = []
    for (const e of evidence) {
      const ai = phases.indexOf(e.a)
      const bi = phases.indexOf(e.b)
      const witnesses = chosen.filter(
        (r) => matrix[ai][idx[r]] !== matrix[bi][idx[r]]
      )
      if (witnesses.length === 0) failures.push(`${e.a}/${e.b}`)
    }
    return {
      cost,
      costOk: cost === total_cost,
      pairCount: evidence.length,
      failures
    }
  }, [chosen, costs, refs, matrix, total_cost, evidence, phases])

  const activeWitnesses = useMemo(() => {
    if (!activePair) return new Set()
    const e = evidence.find((x) => x.a === activePair[0] && x.b === activePair[1])
    return new Set(e ? e.witnesses : [])
  }, [activePair, evidence])

  const counts = useMemo(() => {
    const c = { mandatory: 0, optional: 0, never: 0 }
    for (const r of Object.values(classification)) c[r] += 1
    return c
  }, [classification])

  return (
    <section className="panel result-panel">
      <h2 className="result-good">④ 审计完成 · 规范方案</h2>

      <div className="summary">
        <div className="stat">
          <span className="stat-num">{total_cost}</span>
          <span className="stat-label">最小总曝光代价</span>
        </div>
        <div className="stat">
          <span className="stat-num">{reflection_count}</span>
          <span className="stat-label">方案反射数</span>
        </div>
        <div className="stat">
          <span className="stat-num">{evidence.length}</span>
          <span className="stat-label">已区分相对数</span>
        </div>
        <div className="stat">
          <span className="stat-num">
            {counts.mandatory}/{counts.optional}/{counts.never}
          </span>
          <span className="stat-label">必选 / 可选 / 从不选</span>
        </div>
      </div>

      <div className="legend">
        {Object.entries(CLASS_META).map(([k, m]) => (
          <span key={k} className={`tag ${m.cls}`}>
            {m.label}
          </span>
        ))}
        <span className="legend-note">
          分类口径：在所有达到最优（总代价、反射数）两级的方案中，每个反射是否被选中。
          彩色列 = 规范方案选中；加粗边框 = 下方当前查看的区分证据反射。
        </span>
      </div>

      <div className="table-scroll">
        <table className="matrix result-matrix">
          <thead>
            <tr>
              <th className="row-head-col">相 ＼ 反射</th>
              {refs.map((r) => {
                const picked = chosenSet.has(r)
                const meta = CLASS_META[classification[r]]
                return (
                  <th
                    key={r}
                    className={[
                      'refl-head',
                      picked ? 'col-picked' : '',
                      activeWitnesses.has(r) ? 'col-witness' : ''
                    ].join(' ')}
                  >
                    <div className="refl-head-id">{r}</div>
                    <div className="refl-head-sub">
                      <span className={`tag ${meta.cls}`}>{meta.label}</span>
                      <span className="cost-pill">代价 {costs[r]}</span>
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {phases.map((p, i) => (
              <tr
                key={p}
                className={activePair && (p === activePair[0] || p === activePair[1]) ? 'row-active' : ''}
              >
                <th className="row-head">{p}</th>
                {refs.map((r, j) => (
                  <td
                    key={r}
                    className={[
                      matrix[i][j] ? 'cell-on' : 'cell-off',
                      chosenSet.has(r) ? 'in-solution' : '',
                      activeWitnesses.has(r) ? 'witness-cell' : ''
                    ].join(' ')}
                  >
                    {matrix[i][j] ? '1' : '0'}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="cost-row">
              <th className="row-head">计入代价</th>
              {refs.map((r) => (
                <td key={r} className={chosenSet.has(r) ? 'cost-on' : 'cost-off'}>
                  {chosenSet.has(r) ? `+${costs[r]}` : '·'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="chosen-line">
        规范方案（按标识序列）：
        {chosen.map((r, i) => (
          <span key={r}>
            <span className={`tag ${CLASS_META[classification[r]].cls}`}>{r}</span>
            {i < chosen.length - 1 ? '，' : ''}
          </span>
        ))}
        <span className="cost-eq">
          {chosen.map((r) => costs[r]).join(' + ')} = <b>{total_cost}</b>
        </span>
      </div>

      <RecomputeBox ok={recompute.costOk && recompute.failures.length === 0} recompute={recompute} />

      <h3 className="evidence-title">逐对区分证据（点击行可在矩阵中高亮证据反射）</h3>
      <div className="table-scroll">
        <table className="evidence-table">
          <thead>
            <tr>
              <th>相对</th>
              <th>规范方案中的见证反射（出现位不同）</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((e) => {
              const key = [e.a, e.b]
              const active = activePair && activePair[0] === e.a && activePair[1] === e.b
              return (
                <tr
                  key={`${e.a}|${e.b}`}
                  className={active ? 'ev-active' : ''}
                  onClick={() => setActivePair(active ? null : key)}
                >
                  <td className="pair-cell">
                    <span className="phase-chip">{e.a}</span>
                    <span className="pair-x">≠</span>
                    <span className="phase-chip">{e.b}</span>
                  </td>
                  <td>
                    {e.witnesses.map((r) => (
                      <span key={r} className={`tag ${CLASS_META[classification[r]].cls}`}>
                        {r}
                      </span>
                    ))}
                    <span className="witness-note">（{e.witnesses.length} 个见证）</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="meta-line">
        后端搜索节点数 {result.search_nodes ?? '-'}，耗时 {result.elapsed_ms} ms。
      </p>
    </section>
  )
}

function RecomputeBox({ ok, recompute }) {
  return (
    <div className={`recompute ${ok ? 'recompute-ok' : 'recompute-bad'}`}>
      {ok ? '✔ 浏览器端复算一致：' : '✘ 复算不一致：'}
      选中反射代价之和 = {recompute.cost}；全部 {recompute.pairCount} 个相对均至少有一个
      选中反射的出现位不同{recompute.failures.length > 0 &&
        `；异常相对：${recompute.failures.join('、')}`}。
    </div>
  )
}

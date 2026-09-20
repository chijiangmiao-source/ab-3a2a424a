import { useEffect, useState } from "react";
import { fetchHealth, runAudit } from "./api";
import { SAMPLE } from "./sampleData";

let keySeq = 1;
const uid = () => `k${keySeq++}`;

const ROLE_LABEL = { mandatory: "必选", optional: "可选", never: "从不选" };
const ROLE_DESC = {
  mandatory: "出现在全部前两级同优方案中",
  optional: "仅出现在部分前两级同优方案中",
  never: "不出现在任何前两级同优方案中",
};

function loadSample() {
  const phases = SAMPLE.phases.map((id) => ({ key: uid(), id }));
  const reflections = SAMPLE.reflections.map((r) => ({ key: uid(), id: r.id, cost: String(r.cost) }));
  const occ = {};
  for (const p of phases) {
    occ[p.key] = {};
    for (const r of reflections) occ[p.key][r.key] = !!SAMPLE.occurrence[p.id]?.[r.id];
  }
  return { phases, reflections, occ };
}

function loadBlank() {
  const phases = [{ key: uid(), id: "P1" }, { key: uid(), id: "P2" }];
  const reflections = [{ key: uid(), id: "R1", cost: "1" }];
  const occ = {};
  for (const p of phases) {
    occ[p.key] = {};
    for (const r of reflections) occ[p.key][r.key] = false;
  }
  return { phases, reflections, occ };
}

export default function App() {
  const [init] = useState(loadSample); // 惰性初始化一次，保证 key 一致
  const [phases, setPhases] = useState(init.phases);
  const [reflections, setReflections] = useState(init.reflections);
  const [occ, setOcc] = useState(init.occ);
  const [health, setHealth] = useState("checking");
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState([]);
  const [result, setResult] = useState(null); // { data, payload } — payload 为提交时快照，保证结果可复算

  useEffect(() => {
    let alive = true;
    const check = async () => {
      const ok = await fetchHealth();
      if (alive) setHealth(ok ? "ok" : "down");
    };
    check();
    const t = setInterval(check, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const applyState = (s) => {
    setPhases(s.phases);
    setReflections(s.reflections);
    setOcc(s.occ);
    setResult(null);
    setErrors([]);
  };

  // ---- 候选相编辑 ----
  const addPhase = () => {
    if (phases.length >= 18) return;
    const p = { key: uid(), id: `P${phases.length + 1}` };
    setPhases([...phases, p]);
    const row = {};
    for (const r of reflections) row[r.key] = false;
    setOcc({ ...occ, [p.key]: row });
  };
  const removePhase = (key) => {
    if (phases.length <= 2) return;
    setPhases(phases.filter((p) => p.key !== key));
    const next = { ...occ };
    delete next[key];
    setOcc(next);
  };
  const renamePhase = (key, id) =>
    setPhases(phases.map((p) => (p.key === key ? { ...p, id } : p)));

  // ---- 反射编辑 ----
  const addReflection = () => {
    if (reflections.length >= 48) return;
    const r = { key: uid(), id: `R${reflections.length + 1}`, cost: "1" };
    setReflections([...reflections, r]);
    const next = { ...occ };
    for (const p of phases) next[p.key] = { ...next[p.key], [r.key]: false };
    setOcc(next);
  };
  const removeReflection = (key) => {
    if (reflections.length <= 1) return;
    setReflections(reflections.filter((r) => r.key !== key));
    const next = { ...occ };
    for (const p of phases) {
      const row = { ...next[p.key] };
      delete row[key];
      next[p.key] = row;
    }
    setOcc(next);
  };
  const updateReflection = (key, patch) =>
    setReflections(reflections.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const toggleOcc = (pk, rk) =>
    setOcc({ ...occ, [pk]: { ...occ[pk], [rk]: !occ[pk]?.[rk] } });

  // ---- 校验与提交 ----
  const buildPayload = () => ({
    phases: phases.map((p) => p.id.trim()),
    reflections: reflections.map((r) => ({ id: r.id.trim(), cost: Number(r.cost) })),
    occurrence: Object.fromEntries(
      phases.map((p) => [
        p.id.trim(),
        Object.fromEntries(reflections.map((r) => [r.id.trim(), !!occ[p.key]?.[r.key]])),
      ])
    ),
  });

  const validate = (payload) => {
    const errs = [];
    if (payload.phases.length < 2 || payload.phases.length > 18)
      errs.push(`候选相数量须为 2–18（当前 ${payload.phases.length}）`);
    if (payload.reflections.length < 1 || payload.reflections.length > 48)
      errs.push(`反射数量须为 1–48（当前 ${payload.reflections.length}）`);
    if (payload.phases.some((id) => !id)) errs.push("候选相标识不能为空");
    if (payload.reflections.some((r) => !r.id)) errs.push("反射标识不能为空");
    if (new Set(payload.phases).size !== payload.phases.length)
      errs.push("候选相标识必须唯一");
    const rids = payload.reflections.map((r) => r.id);
    if (new Set(rids).size !== rids.length) errs.push("反射标识必须唯一");
    payload.reflections.forEach((r, i) => {
      if (!Number.isInteger(r.cost) || r.cost < 1)
        errs.push(`反射 ${r.id || `#${i + 1}`} 的代价须为正整数`);
    });
    return errs;
  };

  const submit = async () => {
    const payload = buildPayload();
    const errs = validate(payload);
    setErrors(errs);
    if (errs.length) return;
    setLoading(true);
    setResult(null);
    try {
      const resp = await runAudit(payload);
      if (resp.ok) {
        setResult({ data: resp.data, payload });
        setErrors([]);
      } else if (resp.status === 422 && resp.data?.detail) {
        const detail = resp.data.detail;
        if (Array.isArray(detail)) {
          setErrors(detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`));
        } else {
          setErrors([String(detail)]);
        }
      } else {
        setErrors([`服务返回 ${resp.status}: ${resp.data?.detail || "未知错误"}`]);
      }
    } catch (e) {
      setErrors([`无法连接 API 服务：${e.message}`]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <h1>同步辐射粉末衍射 · 相区分审计台</h1>
          <p className="subtitle">
            精确选择能区分每对候选相的诊断反射集：先最小化总曝光代价，再最小化反射数，最后按反射标识序列裁决规范方案
          </p>
        </div>
        <div className={`health health-${health}`} title="API 健康状态">
          <span className="dot" /> API {health === "ok" ? "在线" : health === "down" ? "离线" : "检测中"}
        </div>
      </header>

      <section className="editors">
        <div className="card">
          <div className="card-head">
            <h2>候选相（{phases.length}/18）</h2>
            <button onClick={addPhase} disabled={phases.length >= 18}>+ 添加相</button>
          </div>
          <ul className="edit-list">
            {phases.map((p) => (
              <li key={p.key}>
                <input value={p.id} onChange={(e) => renamePhase(p.key, e.target.value)} placeholder="相标识" />
                <button className="icon" onClick={() => removePhase(p.key)} disabled={phases.length <= 2} title="删除">×</button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-head">
            <h2>诊断反射（{reflections.length}/48）</h2>
            <button onClick={addReflection} disabled={reflections.length >= 48}>+ 添加反射</button>
          </div>
          <ul className="edit-list">
            {reflections.map((r) => (
              <li key={r.key}>
                <input value={r.id} onChange={(e) => updateReflection(r.key, { id: e.target.value })} placeholder="反射标识" />
                <input className="cost" type="number" min="1" step="1" value={r.cost}
                  onChange={(e) => updateReflection(r.key, { cost: e.target.value })} title="曝光代价（正整数）" />
                <button className="icon" onClick={() => removeReflection(r.key)} disabled={reflections.length <= 1} title="删除">×</button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>预期出现关系（勾选表示该相在此反射上预期出现）</h2>
        </div>
        <div className="matrix-wrap">
          <table className="matrix">
            <thead>
              <tr>
                <th className="rowhead">相 \ 反射</th>
                {reflections.map((r) => (
                  <th key={r.key}><div className="colid">{r.id || "…"}</div></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {phases.map((p) => (
                <tr key={p.key}>
                  <th className="rowhead">{p.id || "…"}</th>
                  {reflections.map((r) => (
                    <td key={r.key}>
                      <input type="checkbox" checked={!!occ[p.key]?.[r.key]} onChange={() => toggleOcc(p.key, r.key)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="actions">
        <button className="primary" onClick={submit} disabled={loading}>
          {loading ? "审计中…" : "运行审计"}
        </button>
        <button onClick={() => applyState(loadSample())}>载入示例</button>
        <button onClick={() => applyState(loadBlank())}>清空</button>
      </div>

      {errors.length > 0 && (
        <section className="card error-card">
          <h2>输入校验未通过</h2>
          <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </section>
      )}

      {result && result.data.status === "infeasible" && (
        <section className="card infeasible-card">
          <h2>全集仍无法区分所有候选相</h2>
          <p>即使选择全部 {result.payload.reflections.length} 个反射，以下候选相对在所有反射上的出现位完全相同，无法区分。输入已保留，请补充诊断反射或修正出现关系。</p>
          <ul className="pair-list">
            {result.data.indistinguishablePairs.map((pr, i) => (
              <li key={i}><strong>{pr.a}</strong> ↔ <strong>{pr.b}</strong></li>
            ))}
          </ul>
        </section>
      )}

      {result && result.data.status === "feasible" && (
        <ResultView data={result.data} payload={result.payload} />
      )}
    </div>
  );
}

function ResultView({ data, payload }) {
  const canonical = new Set(data.canonicalReflections);
  const reflById = Object.fromEntries(payload.reflections.map((r) => [r.id, r]));
  const totalCost = data.canonicalReflections.reduce((s, id) => s + reflById[id].cost, 0);

  return (
    <>
      <section className="card">
        <h2>审计结果</h2>
        <div className="stats">
          <div className="stat"><div className="stat-num">{data.totalCost}</div><div className="stat-label">总曝光代价</div></div>
          <div className="stat"><div className="stat-num">{data.reflectionCount}</div><div className="stat-label">反射数量</div></div>
          <div className="stat wide"><div className="stat-num mono">{data.canonicalReflections.join(", ")}</div><div className="stat-label">规范方案（标识序列字典序最小）</div></div>
          <div className="stat"><div className="stat-num">{data.stats?.elapsedMs ?? "—"}<small> ms</small></div><div className="stat-label">求解耗时（{data.stats?.decisionCalls ?? "—"} 次决策 / {data.stats?.nodes ?? "—"} 节点）</div></div>
        </div>
        <div className="legend">
          {Object.entries(ROLE_LABEL).map(([role, label]) => (
            <span key={role} className={`badge badge-${role}`} title={ROLE_DESC[role]}>{label}</span>
          ))}
          <span className="legend-note">角色在“全部总代价与反射数同优的方案”中统计；高亮列为规范方案。</span>
        </div>
      </section>

      <section className="card">
        <h2>出现关系矩阵 · 规范方案与分类</h2>
        <div className="matrix-wrap">
          <table className="matrix result-matrix">
            <thead>
              <tr>
                <th className="rowhead">相 \ 反射</th>
                {payload.reflections.map((r) => (
                  <th key={r.id} className={canonical.has(r.id) ? "canonical" : ""}>
                    <div className="colid">{r.id}</div>
                    <div className="colcost">代价 {r.cost}</div>
                    <span className={`badge badge-${data.classification[r.id]}`}>{ROLE_LABEL[data.classification[r.id]]}</span>
                  </th>
                ))}
                <th className="codecol">编码</th>
              </tr>
            </thead>
            <tbody>
              {payload.phases.map((pid) => (
                <tr key={pid}>
                  <th className="rowhead">{pid}</th>
                  {payload.reflections.map((r) => (
                    <td key={r.id} className={canonical.has(r.id) ? "canonical" : ""}>
                      <span className={payload.occurrence[pid][r.id] ? "dot-on" : "dot-off"}>
                        {payload.occurrence[pid][r.id] ? "●" : "○"}
                      </span>
                    </td>
                  ))}
                  <td className="codecol mono">{data.codes[pid]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          复算：规范方案总代价 = {data.canonicalReflections.map((id) => reflById[id].cost).join(" + ")} = {totalCost}；
          每行“编码”为该相在规范方案各反射上的出现位，全部编码两两不同即方案有效。
        </p>
      </section>

      <section className="card">
        <h2>逐对区分证据（{data.pairs.length} 对）</h2>
        <div className="pairs-wrap">
          <table className="pairs">
            <thead>
              <tr><th>候选相对</th><th>规范方案内可区分该对的反射</th><th>数量</th></tr>
            </thead>
            <tbody>
              {data.pairs.map((ev, i) => (
                <tr key={i}>
                  <td className="mono">{ev.a} ↔ {ev.b}</td>
                  <td>{ev.reflections.map((rid) => <span key={rid} className="chip">{rid}</span>)}</td>
                  <td>{ev.reflections.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

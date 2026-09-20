export async function fetchHealth() {
  try {
    const r = await fetch("/api/health", { cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  }
}

export async function runAudit(payload) {
  const res = await fetch("/api/audit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* 非 JSON 响应 */
  }
  return { status: res.status, ok: res.ok, data };
}

"""FastAPI 入口：健康检查与审计接口。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import AuditRequest, AuditResponse
from .solver import SolverTimeoutError, run_audit

app = FastAPI(title="同步辐射粉末衍射相区分审计 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/audit", response_model=AuditResponse)
def audit(req: AuditRequest) -> AuditResponse:
    phases = list(req.phases)
    reflection_ids = [r.id for r in req.reflections]
    costs = [r.cost for r in req.reflections]
    occurrence = [[req.occurrence[p][r] for r in reflection_ids] for p in phases]
    try:
        result = run_audit(phases, reflection_ids, costs, occurrence)
    except SolverTimeoutError as exc:
        raise HTTPException(status_code=503, detail=f"求解超出节点预算: {exc}")
    if result.feasible:
        return AuditResponse(
            status="feasible",
            totalCost=result.total_cost,
            reflectionCount=result.reflection_count,
            canonicalReflections=result.canonical,
            classification=result.roles,
            codes=result.codes,
            pairs=result.pairs,
            stats=result.stats,
        )
    return AuditResponse(
        status="infeasible",
        indistinguishablePairs=result.indistinguishable,
        stats=result.stats,
    )

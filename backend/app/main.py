"""FastAPI：粉末衍射审计台后端。

接口：
  GET  /health       健康检查
  GET  /api/sample   示例输入
  POST /api/audit    校验输入并执行精确审计
"""

from __future__ import annotations

from typing import Dict, List
from typing import FrozenSet

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .solver import solve_audit

MAX_PHASES = 18
MIN_PHASES = 2
MAX_REFLECTIONS = 48
MIN_REFLECTIONS = 1

app = FastAPI(title="Powder Diffraction Audit Console", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PhaseIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)


class ReflectionIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    cost: int = Field(gt=0, le=10 ** 9)

    @field_validator("id")
    @classmethod
    def strip_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reflection id must not be blank")
        return v


class AuditRequest(BaseModel):
    phases: List[PhaseIn] = Field(min_length=MIN_PHASES, max_length=MAX_PHASES)
    reflections: List[ReflectionIn] = Field(
        min_length=MIN_REFLECTIONS, max_length=MAX_REFLECTIONS
    )
    # phase_id -> 在该相中出现的 reflection_id 列表
    occurrences: Dict[str, List[str]]

    @field_validator("phases")
    @classmethod
    def _check_phases(cls, v: List[PhaseIn]) -> List[PhaseIn]:
        ids = [p.id.strip() for p in v]
        if any(not x for x in ids):
            raise ValueError("phase id must not be blank")
        if len(set(ids)) != len(ids):
            raise ValueError("phase ids must be unique")
        return [PhaseIn(id=x) for x in ids]

    @field_validator("reflections")
    @classmethod
    def _check_reflections(cls, v: List[ReflectionIn]) -> List[ReflectionIn]:
        ids = [r.id for r in v]
        if len(set(ids)) != len(ids):
            raise ValueError("reflection ids must be unique")
        return v


SAMPLE = {
    "phases": [
        {"id": "Quartz"},
        {"id": "Cristobalite"},
        {"id": "Tridymite"},
        {"id": "Amorphous"},
    ],
    "reflections": [
        {"id": "R1-20.85", "cost": 2},
        {"id": "R2-26.64", "cost": 3},
        {"id": "R3-36.55", "cost": 5},
        {"id": "R4-39.47", "cost": 2},
        {"id": "R5-50.14", "cost": 4},
        {"id": "R6-60.00", "cost": 6},
    ],
    "occurrences": {
        "Quartz": ["R1-20.85", "R2-26.64", "R3-36.55", "R5-50.14"],
        "Cristobalite": ["R2-26.64", "R4-39.47", "R5-50.14"],
        "Tridymite": ["R1-20.85", "R4-39.47", "R6-60.00"],
        "Amorphous": [],
    },
}


@app.get("/health")
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "audit-api"}


@app.get("/api/sample")
def sample() -> dict:
    return SAMPLE


@app.post("/api/audit")
def audit(req: AuditRequest) -> dict:
    phase_ids = [p.id for p in req.phases]
    reflection_ids = [r.id for r in req.reflections]
    costs = {r.id: r.cost for r in req.reflections}
    phase_set = set(phase_ids)
    refl_set = set(reflection_ids)

    # 出现表的键与引用必须指向已声明的标识
    unknown_phases = [p for p in req.occurrences if p not in phase_set]
    if unknown_phases:
        raise _http_422(f"occurrences reference unknown phases: {unknown_phases}")

    occurrences: Dict[str, FrozenSet[str]] = {}
    for pid in phase_ids:
        refs = req.occurrences.get(pid, [])
        unknown = [x for x in refs if x not in refl_set]
        if unknown:
            raise _http_422(
                f"occurrences of phase {pid!r} reference unknown reflections: {unknown}"
            )
        if len(set(refs)) != len(refs):
            raise _http_422(f"duplicate occurrence entries for phase {pid!r}")
        occurrences[pid] = frozenset(refs)

    return solve_audit(phase_ids, reflection_ids, costs, occurrences)


def _http_422(msg: str):
    from fastapi import HTTPException

    return HTTPException(status_code=422, detail=msg)

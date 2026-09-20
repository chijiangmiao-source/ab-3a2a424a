"""请求 / 响应模型与输入校验。"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, StringConstraints, model_validator

IdStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Cost = Annotated[StrictInt, Field(ge=1)]  # 代价为正整数（严格整数，拒绝布尔/浮点/字符串）


class ReflectionSpec(BaseModel):
    id: IdStr
    cost: Cost


class AuditRequest(BaseModel):
    phases: list[IdStr] = Field(min_length=2, max_length=18)
    reflections: list[ReflectionSpec] = Field(min_length=1, max_length=48)
    # occurrence[相标识][反射标识] = 是否预期出现，必须完整覆盖所有 相×反射
    occurrence: dict[str, dict[str, bool]]

    @model_validator(mode="after")
    def check_consistency(self) -> "AuditRequest":
        if len(set(self.phases)) != len(self.phases):
            raise ValueError("候选相标识必须唯一")
        rids = [r.id for r in self.reflections]
        if len(set(rids)) != len(rids):
            raise ValueError("反射标识必须唯一")
        rid_set = set(rids)
        phase_set = set(self.phases)
        extra_phases = sorted(set(self.occurrence) - phase_set)
        if extra_phases:
            raise ValueError(f"出现关系包含未知候选相: {extra_phases}")
        for p in self.phases:
            row = self.occurrence.get(p)
            if row is None:
                raise ValueError(f"缺少候选相 {p!r} 的出现关系行")
            missing = sorted(rid_set - set(row))
            extra = sorted(set(row) - rid_set)
            if missing:
                raise ValueError(f"候选相 {p!r} 缺少反射的出现位: {missing}")
            if extra:
                raise ValueError(f"候选相 {p!r} 包含未知反射: {extra}")
        return self


class PairEvidence(BaseModel):
    a: str
    b: str
    reflections: list[str]


class PairRef(BaseModel):
    a: str
    b: str


class AuditResponse(BaseModel):
    status: str  # "feasible" | "infeasible"
    totalCost: int | None = None
    reflectionCount: int | None = None
    canonicalReflections: list[str] = []
    # 每个反射在全部前两级同优方案中的角色: mandatory(必选)/optional(可选)/never(从不选)
    classification: dict[str, str] = {}
    codes: dict[str, str] = {}  # 各相在规范方案上的出现位串
    pairs: list[PairEvidence] = []  # 逐对区分证据（规范方案内能区分该对的反射）
    indistinguishablePairs: list[PairRef] = []
    stats: dict = {}

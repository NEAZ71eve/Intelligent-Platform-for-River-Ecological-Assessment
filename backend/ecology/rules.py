"""河道生态评估规则引擎：检测框聚合 → 大类统计 → 扣分 → 等级 + 原因。

规则版本化：assess() 优先从 DB RuleSet 加载匹配版本，缺省回退到代码内置 RULE_V1。
任务固定记录 rule_version，历史不回写。
"""
from dataclasses import dataclass


# 代码内置 v1 规则；与 RuleSet.definition 同构
RULE_V1 = {
    "base": 100,
    "floating_debris": {
        "count_steps": [(0, 0), (1, 5), (4, 12), (11, 20)],
        "area_steps": [(0.0, 0), (0.01, 5), (0.05, 10)],
    },
    "bloom_blackwater": {
        "area_steps": [(0.0, 0), (0.05, 8), (0.20, 15)],
    },
    "outfall_discharge": {"per_instance": 25, "cap": 40},
    "bank_problem": {"per_instance": 6, "cap": 18},
}

GRADES = [(85, "优"), (70, "良"), (50, "中"), (0, "差")]


def _load_rule(rule_version: str) -> dict:
    """按版本号加载规则定义；DB 优先，缺省回退到内置 RULE_V1。"""
    if rule_version == "v1":
        return RULE_V1
    from .models import RuleSet
    rs = RuleSet.objects.filter(version=rule_version).first()
    if rs is not None:
        return rs.definition
    raise ValueError(f"Unknown rule version: {rule_version}")


def _stat(detections: list) -> dict:
    """按 eval_category 聚合 count 与 area_ratio 总和。"""
    stat = {}
    for d in detections:
        c = stat.setdefault(d["eval_category"], {"count": 0, "area_ratio": 0.0})
        c["count"] += 1
        c["area_ratio"] += float(d.get("area_ratio", 0.0))
    return stat


def _step(steps, value) -> int:
    """阶跃扣分：返回 value 所达最高档对应的扣分。"""
    penalty = 0
    for threshold, pts in steps:
        if value >= threshold:
            penalty = pts
    return penalty


def assess(detections: list, rule_version: str = "v1") -> dict:
    """检测框列表 → {score, grade, causes, issues, rule_version}。"""
    r = _load_rule(rule_version)
    stat = _stat(detections)
    score = r["base"]

    fd = stat.get("floating_debris")
    if fd:
        score -= _step(r["floating_debris"]["count_steps"], fd["count"])
        score -= _step(r["floating_debris"]["area_steps"], fd["area_ratio"])

    bw = stat.get("bloom_blackwater")
    if bw:
        score -= _step(r["bloom_blackwater"]["area_steps"], bw["area_ratio"])

    od = stat.get("outfall_discharge")
    if od:
        score -= min(od["count"] * r["outfall_discharge"]["per_instance"],
                      r["outfall_discharge"]["cap"])

    bp = stat.get("bank_problem")
    if bp:
        score -= min(bp["count"] * r["bank_problem"]["per_instance"],
                      r["bank_problem"]["cap"])

    score = max(0, min(100, score))
    grade = next(g for t, g in GRADES if score >= t)

    causes = []
    if fd and fd["count"] >= 4 and bp:
        causes.append({"rule": "fd_bank",
                       "text": "漂浮物与岸带垃圾并存，提示周边垃圾清运或倾倒管控问题"})
    if bw:
        causes.append({"rule": "bloom",
                       "text": "存在水华或水体颜色异常，富营养化倾向，建议核查上游氮磷来源"})
    if od:
        causes.append({"rule": "outfall",
                       "text": "检出疑似排污口或污水直排，建议溯源排查"})

    return {"score": score, "grade": grade, "causes": causes,
            "issues": stat, "rule_version": rule_version}

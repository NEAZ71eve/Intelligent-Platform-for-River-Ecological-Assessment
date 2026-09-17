"""类别映射配置加载与校验。

评估大类（4）：floating_debris / bloom_blackwater / outfall_discharge / bank_problem
训练用细类，评估聚合到大类。配置版本化，修改必须递增 version。
"""
import yaml
from pathlib import Path

def load_mapping(path: Path = None) -> dict:
    """加载 class_mapping.yaml。"""
    path = Path(path) if path else Path(__file__).parent.parent / "data" / "class_mapping.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def eval_categories(mapping: dict) -> list:
    """返回评估大类名称列表。"""
    return list(mapping["eval_categories"].keys())

def fine_to_eval(mapping: dict, fine: str) -> str:
    """细粒度标签 → 评估大类。未知标签抛 KeyError。"""
    return mapping["fine_labels"][fine]["eval"]

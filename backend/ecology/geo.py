"""定位 → 最近监测站 → 关联水体（Haversine）。

用途：河道巡查上报时根据上传点定位匹配最近的 active 水环境监测站，
返回其所属 water_body 与 station id，超出 MATCH_RADIUS_M 则返回 None
（前端兜底让用户手动选择河段）。
"""
import math

EARTH_R = 6371000.0
MATCH_RADIUS_M = 2000.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点间球面距离（米）。"""
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def match_water_body(lat: float, lng: float):
    """查找半径 MATCH_RADIUS_M 内最近的水环境监测站所属水体。

    返回 dict: {water_body_id, station_id, distance_m}；无匹配返回 None。
    """
    from .models import Station
    qs = (Station.objects.select_related("place", "water_body")
          .filter(is_active=True, kind=Station.Kind.WATER,
                  place__latitude__isnull=False, place__longitude__isnull=False))
    best, best_d = None, MATCH_RADIUS_M
    for s in qs:
        d = _haversine(lat, lng, s.place.latitude, s.place.longitude)
        if d < best_d:
            best, best_d = s, d
    if best is None or best.water_body_id is None:
        return None
    return {"water_body_id": best.water_body_id, "station_id": best.id,
            "distance_m": round(best_d)}

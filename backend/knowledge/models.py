from django.core.exceptions import ValidationError
from django.db import models

from ecology.models import ValidatedModel


class Content(ValidatedModel):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    body = models.TextField()
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[("draft", "草稿"), ("published", "已发布")], default="draft")
    category = models.CharField(max_length=20, choices=[("plants", "植物知识"), ("water", "水资源保护"), ("green", "绿色生活"), ("travel", "生态智游")], default="green")
    place = models.ForeignKey("ecology.Place", null=True, blank=True, on_delete=models.SET_NULL, related_name="contents")
    plant_label = models.SlugField(blank=True)
    source = models.CharField(max_length=500, blank=True)
    is_demo = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["status", "category"])]

    def __str__(self):
        return self.title


class Route(ValidatedModel):
    region = models.ForeignKey("ecology.Region", on_delete=models.PROTECT, related_name="routes")
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    published = models.BooleanField(default=False)
    source = models.CharField(max_length=500, blank=True)
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.pk and self.stops.exclude(place__region_id=self.region_id).exists():
            raise ValidationError({"region": "路线所属区域必须与现有节点一致。"})


class RouteStop(ValidatedModel):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    place = models.ForeignKey("ecology.Place", on_delete=models.PROTECT, related_name="route_stops")
    order = models.PositiveIntegerField()
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["route", "order"], name="route_stop_order_unique")]

    def clean(self):
        if self.route_id and self.place_id and self.route.region_id != self.place.region_id:
            raise ValidationError({"place": "路线节点必须位于路线所属区域。"})

    def __str__(self):
        return f"{self.route.title} / {self.order}. {self.place.name}"

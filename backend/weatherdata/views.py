from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WeatherLocation
from .provider import configured
from .services import location_data, summary


class LocationList(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.query_params:
            raise ValidationError('地点列表不接受额外参数。')
        return Response({'items': [location_data(item) for item in WeatherLocation.objects.filter(is_active=True)], 'enabled': configured()})


class WeatherSummary(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if set(request.query_params) != {'location'} or len(request.query_params.getlist('location')) != 1:
            raise ValidationError('仅允许提供一个管理员已配置的 location。')
        location = WeatherLocation.objects.filter(slug=request.query_params['location'], is_active=True).first()
        if location is None:
            raise NotFound('天气查询地点不存在。')
        return Response(summary(location))

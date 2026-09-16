from django.urls import path
from .views import AssetContent, AssetDetail, UploadView

urlpatterns = [path('uploads/', UploadView.as_view()), path('uploads/<uuid:pk>/', AssetDetail.as_view()), path('uploads/<uuid:pk>/content/', AssetContent.as_view())]


from django.urls import path
from .views import DevLoginView, LoginView, LogoutView, MeView

urlpatterns = [path('auth/dev/', DevLoginView.as_view()), path('auth/wechat/', LoginView.as_view()), path('auth/logout/', LogoutView.as_view()), path('me/', MeView.as_view())]


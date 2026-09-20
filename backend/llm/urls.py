from django.urls import path
from .views import SessionDetail, Sessions, Status, TurnDetail, Turns

urlpatterns = [
    path('llm/status/', Status.as_view()),
    path('llm/sessions/', Sessions.as_view()),
    path('llm/sessions/<uuid:pk>/', SessionDetail.as_view()),
    path('llm/sessions/<uuid:pk>/turns/', Turns.as_view()),
    path('llm/turns/<uuid:pk>/', TurnDetail.as_view()),
]

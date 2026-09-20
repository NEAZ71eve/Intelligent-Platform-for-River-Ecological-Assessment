from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LLMTurn
from .serializers import ScopeInput, SessionInput, SessionSerializer, TurnInput, TurnSerializer
from .services import create_session, delete_session, enqueue_turn, status, visible_sessions


def requested_scope(request):
    if len(request.query_params.getlist('scope')) > 1:
        raise ValidationError({'scope': '请只选择一个对话板块。'})
    values = ScopeInput(data=request.query_params)
    values.is_valid(raise_exception=True)
    return values.validated_data['scope']


class Status(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status(request.user, scope=requested_scope(request)))


class Sessions(generics.ListCreateAPIView):
    serializer_class = SessionSerializer

    def get_queryset(self):
        sessions = visible_sessions(self.request.user)
        return sessions.filter(scope=requested_scope(self.request)) if 'scope' in self.request.query_params else sessions

    def create(self, request, *args, **kwargs):
        data = SessionInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(SessionSerializer(create_session(request.user, data.validated_data)).data, status=201)


class SessionDetail(generics.RetrieveDestroyAPIView):
    serializer_class = SessionSerializer

    def get_queryset(self):
        return visible_sessions(self.request.user)

    def perform_destroy(self, instance):
        delete_session(self.request.user, instance.pk)


class Turns(generics.ListCreateAPIView):
    serializer_class = TurnSerializer

    def get_queryset(self):
        session = get_object_or_404(visible_sessions(self.request.user), pk=self.kwargs['pk'])
        return LLMTurn.objects.filter(session=session)

    def create(self, request, *args, **kwargs):
        data = TurnInput(data=request.data)
        data.is_valid(raise_exception=True)
        turn, created = enqueue_turn(request.user, self.kwargs['pk'], data.validated_data)
        return Response(TurnSerializer(turn).data, status=201 if created else 200)


class TurnDetail(generics.RetrieveAPIView):
    serializer_class = TurnSerializer

    def get_queryset(self):
        return LLMTurn.objects.filter(session__in=visible_sessions(self.request.user))

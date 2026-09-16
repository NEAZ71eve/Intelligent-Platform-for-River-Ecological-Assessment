from rest_framework import serializers
from .models import RecognitionJob


class JobSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RecognitionJob
        fields = ('id', 'asset_id', 'status', 'result', 'error_code', 'message', 'model_version', 'created_at', 'started_at', 'finished_at', 'duration_ms', 'expires_at')


class JobInput(serializers.Serializer):
    asset_id = serializers.UUIDField()


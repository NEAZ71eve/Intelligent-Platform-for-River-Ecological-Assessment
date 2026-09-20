from rest_framework import serializers
from .models import LLMSession, LLMTurn
from .services import CONSENT_VERSION, image_available


class SessionInput(serializers.Serializer):
    recognition_job_id = serializers.UUIDField(required=False)
    assessment_job_id = serializers.UUIDField(required=False)
    consent_version = serializers.ChoiceField(choices=[CONSENT_VERSION])
    include_image = serializers.BooleanField(required=True)

    def validate(self, attrs):
        if ('recognition_job_id' in attrs) == ('assessment_job_id' in attrs):
            raise serializers.ValidationError('请选择且仅选择一条本人的花卉识别或河道观察记录。')
        return attrs


class SessionSerializer(serializers.ModelSerializer):
    image_available = serializers.SerializerMethodField()
    recognition_job_id = serializers.UUIDField(read_only=True, allow_null=True)
    assessment_job_id = serializers.UUIDField(read_only=True, allow_null=True)

    def get_image_available(self, obj):
        return image_available(obj)

    class Meta:
        model = LLMSession
        fields = ('id', 'kind', 'title', 'context_summary', 'include_image', 'image_available',
                  'recognition_job_id', 'assessment_job_id', 'created_at', 'expires_at')


class TurnInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    question = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class TurnSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = LLMTurn
        fields = ('id', 'session_id', 'question', 'answer', 'status', 'error_code', 'message', 'created_at',
                  'finished_at', 'used_image', 'model', 'usage')

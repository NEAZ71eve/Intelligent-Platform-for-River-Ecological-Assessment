from rest_framework import serializers
from ecology.models import Place
from knowledge.models import Content
from .models import Favorite, Feedback, History, Visit


class TargetInput(serializers.Serializer):
    place_id = serializers.UUIDField(required=False)
    content_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if ('place_id' in attrs) == ('content_id' in attrs):
            raise serializers.ValidationError('请选择一个地点或一篇文章')
        if 'place_id' in attrs and not Place.objects.filter(pk=attrs['place_id'], is_published=True).exists():
            raise serializers.ValidationError('地点不存在或未发布')
        if 'content_id' in attrs and not Content.objects.filter(pk=attrs['content_id'], status='published').exists():
            raise serializers.ValidationError('文章不存在或未发布')
        return attrs


class RecordSerializer(serializers.ModelSerializer):
    place = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    place_id = serializers.UUIDField(read_only=True, allow_null=True)
    content_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Favorite
        fields = ('id', 'place', 'content', 'place_id', 'content_id', 'created_at')

    def get_place(self, obj):
        return {'id': str(obj.place_id), 'name': obj.place.name} if obj.place_id and obj.place.is_published else None

    def get_content(self, obj):
        return {'id': str(obj.content_id), 'title': obj.content.title} if obj.content_id and obj.content.status == 'published' else None


class HistorySerializer(RecordSerializer):
    class Meta(RecordSerializer.Meta):
        model = History
        fields = RecordSerializer.Meta.fields + ('viewed_at',)


class VisitSerializer(serializers.ModelSerializer):
    place = serializers.SerializerMethodField()
    place_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Visit
        fields = ('id', 'place', 'place_id', 'visited_at', 'visited_on')

    def get_place(self, obj):
        return {'id': str(obj.place_id), 'name': obj.place.name} if obj.place.is_published else None


class FeedbackSerializer(serializers.ModelSerializer):
    body = serializers.CharField(min_length=1, max_length=1000, trim_whitespace=True)
    reply = serializers.SerializerMethodField()
    resolved_at = serializers.SerializerMethodField()

    class Meta:
        model = Feedback
        fields = ('id', 'body', 'status', 'created_at', 'reply', 'resolved_at')
        read_only_fields = ('id', 'status', 'created_at', 'reply', 'resolved_at')

    def get_reply(self, obj):
        return obj.reply if obj.status == 'resolved' else ''

    def get_resolved_at(self, obj):
        if obj.status == 'resolved' and obj.resolved_at is not None:
            return serializers.DateTimeField().to_representation(obj.resolved_at)
        return None

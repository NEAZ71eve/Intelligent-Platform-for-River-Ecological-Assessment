import hashlib
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .models import AuthSession


class BearerAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b'bearer' or len(parts[1]) > 256:
            raise AuthenticationFailed('登录凭证无效')
        digest = hashlib.sha256(parts[1]).hexdigest()
        session = AuthSession.objects.select_related('user').filter(token_digest=digest, expires_at__gt=timezone.now(), user__is_active=True).first()
        if not session:
            raise AuthenticationFailed('登录已过期，请重新登录')
        return session.user, session

    def authenticate_header(self, request):
        return 'Bearer'


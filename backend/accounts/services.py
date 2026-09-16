import hashlib
import json
import secrets
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.utils import timezone
from common.exceptions import ServiceError
from .models import AuthSession


def issue_session(user):
    token = secrets.token_urlsafe(32)
    expires = timezone.now() + timedelta(days=settings.AUTH_SESSION_DAYS)
    AuthSession.objects.filter(user=user).delete()
    AuthSession.objects.create(user=user, token_digest=hashlib.sha256(token.encode()).hexdigest(), expires_at=expires)
    return token, expires


def exchange_wechat_code(code):
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        raise ServiceError('微信登录尚未配置，开发阶段请使用模拟登录', 'WECHAT_NOT_CONFIGURED', 503)
    query = urlencode({'appid': settings.WECHAT_APP_ID, 'secret': settings.WECHAT_APP_SECRET, 'js_code': code, 'grant_type': 'authorization_code'})
    try:
        with urlopen('https://api.weixin.qq.com/sns/jscode2session?' + query, timeout=8) as response:
            data = json.loads(response.read(64 * 1024))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        raise ServiceError('微信登录服务暂不可用', 'WECHAT_UNAVAILABLE', 503) from None
    if not isinstance(data, dict) or data.get('errcode') or not isinstance(data.get('openid'), str) or not data['openid'] or len(data['openid']) > 128:
        raise ServiceError('微信登录凭证无效，请重新登录', 'WECHAT_CODE_INVALID', 400)
    # session_key is neither stored nor returned; never log the upstream payload.
    return data['openid']

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class ServiceError(APIException):
    status_code = 400

    def __init__(self, message, code='REQUEST_FAILED', status=400):
        self.status_code = status
        super().__init__(message, code=code)


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(getattr(exc, 'message_dict', exc.messages))
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    codes = {400: 'VALIDATION_ERROR', 401: 'AUTH_REQUIRED', 403: 'FORBIDDEN', 404: 'NOT_FOUND', 405: 'METHOD_NOT_ALLOWED', 413: 'FILE_TOO_LARGE', 415: 'UNSUPPORTED_MEDIA', 429: 'RATE_LIMITED'}
    code = str(exc.get_codes()) if isinstance(exc, ServiceError) else codes.get(response.status_code, 'REQUEST_FAILED')
    details = response.data
    message = str(details.get('detail', '请求参数不正确')) if isinstance(details, dict) else '请求未能完成'
    response.data = {'error': {'code': code, 'message': message, 'details': details}}
    return response


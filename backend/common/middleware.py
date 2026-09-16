import logging
import time
import uuid

logger = logging.getLogger('hyhq.request')


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        started = time.monotonic()
        response = self.get_response(request)
        response['X-Request-ID'] = request.request_id
        if request.path.startswith('/api/'):
            # No query, request body, cookies or auth headers in logs.
            logger.info('request_id=%s method=%s path=%s status=%s duration_ms=%d', request.request_id,
                        request.method, request.path, response.status_code, (time.monotonic() - started) * 1000)
            response['Cache-Control'] = 'no-store'
        return response


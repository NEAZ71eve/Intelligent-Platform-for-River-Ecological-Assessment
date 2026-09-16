from rest_framework.renderers import JSONRenderer


class EnvelopeJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        context = renderer_context or {}
        response = context.get('response')
        request_id = getattr(context.get('request'), 'request_id', None)
        if response is not None and response.status_code == 204:
            return b''
        if response is not None and response.status_code >= 400:
            payload = data if isinstance(data, dict) and 'error' in data else {'error': {'code': 'REQUEST_FAILED', 'message': '请求未能完成', 'details': data}}
        elif isinstance(data, dict) and 'data' in data and 'meta' in data:
            payload = dict(data)
        else:
            payload = {'data': data}
        payload['request_id'] = request_id
        return super().render(payload, accepted_media_type, context)


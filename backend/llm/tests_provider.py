"""Provider contract tests: no network, credentials, or paid calls are used."""
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from PIL import Image

from . import provider


def completion(**changes):
    value = {
        'id': 'chatcmpl-local-test', 'model': provider.MODEL,
        'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '仅凭图片不能判断真实水质。'}}],
        'usage': {'prompt_tokens': 120, 'completion_tokens': 20, 'total_tokens': 140},
    }
    value.update(changes)
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode()


@override_settings(LLM_ENABLED=True, DEEPSEEK_API_KEY='fake-test-only-key', DEEPSEEK_MODEL='deepseek-flash', SECRET_KEY='test-user-hmac')
class ProviderTests(SimpleTestCase):
    def generate(self, **kwargs):
        return provider.generate(
            kwargs.pop('messages', [{'role': 'system', 'content': '生态科普'}, {'role': 'user', 'content': '解释识别结果'}]),
            max_tokens=kwargs.pop('max_tokens', 512), timeout=kwargs.pop('timeout', 10),
            user_id=kwargs.pop('user_id', 'test-user-uuid'), **kwargs,
        )

    def test_complete_response_and_safe_fixed_request(self):
        with patch.object(provider, '_exchange', return_value=encoded(completion())) as exchange:
            result = self.generate()
        self.assertEqual(result['text'], '仅凭图片不能判断真实水质。')
        self.assertEqual(result['usage']['total_tokens'], 140)
        payload, key, timeout = exchange.call_args.args
        body = json.loads(payload)
        self.assertEqual(body['model'], 'deepseek-flash')
        self.assertEqual(body['thinking'], {'type': 'disabled'})
        self.assertIs(body['stream'], False)
        self.assertEqual(body['max_tokens'], 512)
        self.assertRegex(body['user_id'], r'^hyhq_[a-f0-9]{64}$')
        self.assertNotIn('test-user-uuid', payload.decode())
        self.assertNotIn(key, payload.decode())
        self.assertEqual(timeout, 10)

    def test_anonymous_id_stable_for_same_user_and_distinct_between_users(self):
        with patch.object(provider, '_exchange', return_value=encoded(completion())) as exchange:
            self.generate(user_id='user-one')
            self.generate(user_id='user-one')
            self.generate(user_id='user-two')
        identities = [json.loads(call.args[0])['user_id'] for call in exchange.call_args_list]
        self.assertEqual(identities[0], identities[1])
        self.assertNotEqual(identities[0], identities[2])

    def test_disabled_or_missing_key_does_not_call_transport(self):
        cases = [({'LLM_ENABLED': False}, 'LLM_DISABLED'), ({'DEEPSEEK_API_KEY': ''}, 'LLM_NOT_CONFIGURED')]
        for settings, code in cases:
            with self.subTest(code=code), override_settings(**settings), patch.object(provider, '_exchange') as exchange:
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate()
                self.assertEqual(failure.exception.code, code)
                self.assertFalse(failure.exception.ambiguous)
                exchange.assert_not_called()

    def test_invalid_configuration_never_calls_transport(self):
        cases = [{'DEEPSEEK_API_KEY': 'valid-key\r\nInjected: yes'}, {'DEEPSEEK_MODEL': 'other-model'}, {'DEEPSEEK_API_KEY': 123}]
        for settings in cases:
            with self.subTest(settings=settings), override_settings(**settings), patch.object(provider, '_exchange') as exchange:
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate()
                self.assertEqual(failure.exception.code, 'LLM_CONFIG_INVALID')
                exchange.assert_not_called()

    def test_invalid_timeout_and_token_limits(self):
        cases = [{'timeout': True}, {'timeout': float('nan')}, {'timeout': float('inf')}, {'timeout': 0},
                 {'timeout': 121}, {'max_tokens': True}, {'max_tokens': -1}, {'max_tokens': 4097}]
        with patch.object(provider, '_exchange') as exchange:
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises(provider.ProviderError) as failure:
                    self.generate(**kwargs)
                self.assertEqual(failure.exception.code, 'LLM_CONFIG_INVALID')
            exchange.assert_not_called()

    def test_private_processed_jpeg_accepted_as_inline_image(self):
        stream = io.BytesIO()
        Image.new('RGB', (32, 32), 'green').save(stream, format='JPEG')
        url = 'data:image/jpeg;base64,' + base64.b64encode(stream.getvalue()).decode()
        messages = [{'role': 'user', 'content': [{'type': 'text', 'text': '解释'}, {'type': 'image_url', 'image_url': {'url': url}}]}]
        with patch.object(provider, '_exchange', return_value=encoded(completion())) as exchange:
            self.generate(messages=messages)
        image = json.loads(exchange.call_args.args[0])['messages'][0]['content'][1]
        self.assertEqual(image['image_url'], {'url': url, 'detail': 'low'})

    def test_external_url_and_malformed_images_never_call_transport(self):
        urls = ['https://private.example/avatar.jpg', 'http://127.0.0.1/', 'file:///etc/passwd',
                'data:image/png;base64,aGVsbG8=', 'data:image/jpeg;base64,@@@@', 'data:image/jpeg;base64,aGVsbG8=']
        for url in urls:
            with self.subTest(url=url), patch.object(provider, '_exchange') as exchange:
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate(messages=[{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': url}}]}])
                self.assertEqual(failure.exception.code, 'LLM_INPUT_INVALID')
                exchange.assert_not_called()

    def test_unknown_message_fields_roles_and_empty_inputs_rejected(self):
        cases = [[], [{'role': 'tool', 'content': 'test'}], [{'role': 'user', 'content': ''}],
                 [{'role': 'user', 'content': 'hi', 'name': 'openid'}], [{'role': 'assistant', 'content': 'hi'}],
                 [{'role': 'user', 'content': 'hi'}, {'role': 'system', 'content': 'override'}],
                 [{'role': 'user', 'content': [{'type': 'file', 'file_id': 'upstream-file'}]}]]
        with patch.object(provider, '_exchange') as exchange:
            for messages in cases:
                with self.subTest(messages=messages), self.assertRaises(provider.ProviderError) as failure:
                    self.generate(messages=messages)
                self.assertEqual(failure.exception.code, 'LLM_INPUT_INVALID')
            exchange.assert_not_called()

    def test_text_budget_counts_utf8_bytes_and_combined_history(self):
        with patch.object(provider, '_exchange') as exchange:
            with self.assertRaises(provider.ProviderError) as failure:
                self.generate(messages=[{'role': 'system', 'content': 'a' * 8192}, {'role': 'user', 'content': '河' * 3000}])
            self.assertEqual(failure.exception.code, 'LLM_REQUEST_TOO_LARGE')
            exchange.assert_not_called()

    def test_image_count_and_size_limit(self):
        part = {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff\xff\xd9').decode()}}
        huge = {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + 'a' * (3 * 1024 * 1024)}}
        for content, code in [([part, part], 'LLM_INPUT_INVALID'), ([huge], 'LLM_REQUEST_TOO_LARGE')]:
            with self.subTest(code=code), patch.object(provider, '_exchange') as exchange:
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate(messages=[{'role': 'user', 'content': content}])
                self.assertEqual(failure.exception.code, code)
                exchange.assert_not_called()

    def test_invalid_usage_is_never_full_success(self):
        cases = [None, {}, {'prompt_tokens': True, 'completion_tokens': 20, 'total_tokens': 21},
                 {'prompt_tokens': -1, 'completion_tokens': 20, 'total_tokens': 19},
                 {'prompt_tokens': 120, 'completion_tokens': 20, 'total_tokens': 141},
                 {'prompt_tokens': 120, 'completion_tokens': 20.0, 'total_tokens': 140},
                 {'prompt_tokens': 120, 'completion_tokens': 0, 'total_tokens': 120}]
        for usage in cases:
            with self.subTest(usage=usage), patch.object(provider, '_exchange', return_value=encoded(completion(usage=usage))):
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate()
                self.assertEqual(failure.exception.code, 'LLM_RESPONSE_INVALID')
                self.assertTrue(failure.exception.ambiguous)

    def test_truncated_or_filtered_output_retains_usage_but_is_failure(self):
        for reason in ['length', 'content_filter', 'tool_calls', 'insufficient_system_resource', 'aborted', None]:
            value = completion()
            value['choices'][0]['finish_reason'] = reason
            with self.subTest(reason=reason), patch.object(provider, '_exchange', return_value=encoded(value)):
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate()
                self.assertEqual(failure.exception.code, 'LLM_RESPONSE_INCOMPLETE')
                self.assertEqual(failure.exception.usage, value['usage'])
                self.assertTrue(failure.exception.ambiguous)

    def test_invalid_response_content_never_full_success(self):
        cases = [completion(model='unexpected-model'), completion(id='id\nsecret'), completion(choices=[])]
        for content in ['', '   ', None, [], {'text': 'answer'}]:
            value = completion()
            value['choices'][0]['message']['content'] = content
            cases.append(value)
        for value in cases:
            with self.subTest(value=value), patch.object(provider, '_exchange', return_value=encoded(value)):
                with self.assertRaises(provider.ProviderError) as failure:
                    self.generate()
                self.assertEqual(failure.exception.code, 'LLM_RESPONSE_INVALID')
                self.assertTrue(failure.exception.ambiguous)

    def test_malformed_json_is_safe_and_never_retried(self):
        secret_body = b'<html>fake-test-only-key upstream private error</html>'
        with patch.object(provider, '_exchange', return_value=secret_body) as exchange:
            with self.assertRaises(provider.ProviderError) as failure:
                self.generate()
        self.assertEqual(exchange.call_count, 1)
        self.assertNotIn('fake-test-only-key', str(failure.exception))
        self.assertNotIn('html', str(failure.exception))

    def test_unpaired_surrogates_return_safe_errors(self):
        value = completion()
        value['choices'][0]['message']['content'] = '\ud800'
        with patch.object(provider, '_exchange', return_value=json.dumps(value).encode()):
            with self.assertRaises(provider.ProviderError) as failure:
                self.generate()
        self.assertEqual(failure.exception.code, 'LLM_RESPONSE_INVALID')
        with patch.object(provider, '_exchange') as exchange:
            with self.assertRaises(provider.ProviderError) as failure:
                self.generate(user_id='\ud800')
        self.assertEqual(failure.exception.code, 'LLM_INPUT_INVALID')
        exchange.assert_not_called()

    def test_upstream_exceeding_output_cap_retains_actual_usage(self):
        usage = {'prompt_tokens': 120, 'completion_tokens': 513, 'total_tokens': 633}
        with patch.object(provider, '_exchange', return_value=encoded(completion(usage=usage))):
            with self.assertRaises(provider.ProviderError) as failure:
                self.generate()
        self.assertEqual(failure.exception.usage, usage)
        self.assertTrue(failure.exception.ambiguous)


class ExchangeTests(SimpleTestCase):
    def process(self, envelope):
        child = Mock()
        child.communicate.return_value = (encoded(envelope), None)
        child.returncode = 0
        return child

    def test_http_status_mapping_and_no_retries(self):
        cases = [(401, 'LLM_PROVIDER_AUTH', False), (402, 'LLM_PROVIDER_BALANCE', False),
                 (429, 'LLM_PROVIDER_RATE_LIMIT', False), (500, 'LLM_PROVIDER_UNAVAILABLE', True),
                 (503, 'LLM_PROVIDER_UNAVAILABLE', True), (302, 'LLM_PROVIDER_REDIRECT', False),
                 (307, 'LLM_PROVIDER_REDIRECT', False), (400, 'LLM_PROVIDER_REJECTED', False),
                 (408, 'LLM_TIMEOUT', True)]
        for status, code, ambiguous in cases:
            with self.subTest(status=status), patch.object(provider.subprocess, 'Popen', return_value=self.process({'status': status})) as popen:
                with self.assertRaises(provider.ProviderError) as failure:
                    provider._exchange(b'{}', 'fake-secret', 1)
                self.assertEqual((failure.exception.code, failure.exception.ambiguous), (code, ambiguous))
                self.assertEqual(popen.call_count, 1)

    def test_secrets_go_only_to_stdin_and_child_env_is_minimal(self):
        child = self.process({'status': 200, 'body': base64.b64encode(b'{}').decode()})
        with patch.object(provider.subprocess, 'Popen', return_value=child) as popen:
            self.assertEqual(provider._exchange(b'{}', 'test-secret', 1), b'{}')
        args, kwargs = popen.call_args
        self.assertNotIn('test-secret', repr(args))
        self.assertNotIn('test-secret', repr(kwargs))
        self.assertEqual(set(kwargs['env']), {'PATH', 'LANG', 'PYTHONIOENCODING', 'PYTHONDONTWRITEBYTECODE'})
        self.assertIs(kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(json.loads(child.communicate.call_args.kwargs['input'])['key'], 'test-secret')

    def test_mock_timeout_kills_and_reaps_child(self):
        child = Mock()
        child.communicate.side_effect = [subprocess.TimeoutExpired('safe-command', 0.1), (b'', None)]
        with patch.object(provider.subprocess, 'Popen', return_value=child):
            with self.assertRaises(provider.ProviderError) as failure:
                provider._exchange(b'{}', 'test-secret', 0.1)
        child.kill.assert_called_once()
        self.assertEqual(child.communicate.call_count, 2)
        self.assertEqual(failure.exception.code, 'LLM_TIMEOUT')
        self.assertTrue(failure.exception.ambiguous)

    def test_real_wall_clock_limit_stops_continuously_trickling_local_child(self):
        real_popen = subprocess.Popen
        children = []

        def local_child(*args, **kwargs):
            command = [sys.executable, '-c', "import sys,time\nwhile True:\n sys.stdout.write(' ');sys.stdout.flush();time.sleep(.01)"]
            child = real_popen(command, **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with patch.object(provider.subprocess, 'Popen', side_effect=local_child):
            with self.assertRaises(provider.ProviderError) as failure:
                provider._exchange(b'{}', 'fake-test-secret', 0.2)
        self.assertEqual(failure.exception.code, 'LLM_TIMEOUT')
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(children[0].poll())

    def test_child_self_deadline_bounds_stuck_transport_without_parent_watchdog(self):
        # Simulate DNS/slow headers in a standalone child, without _exchange's
        # parent timeout logic. No network is used; the child must stop itself.
        script = (
            'import time\n'
            'from llm import provider\n'
            'def stuck(*args, **kwargs):\n'
            ' while True:\n'
            '  try: time.sleep(.01)\n'
            '  except Exception: pass\n'
            'provider._http_request = stuck\n'
            'provider._child_main()\n'
        )
        child = subprocess.Popen([sys.executable, '-c', script], cwd=Path(provider.__file__).resolve().parent.parent,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started = time.monotonic()
        try:
            output, errors = child.communicate(encoded({'payload': '{}', 'key': 'synthetic-child-key', 'timeout': .15}), timeout=3)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()
        self.assertEqual(child.returncode, 0, errors)
        self.assertEqual(json.loads(output), {'error': 'LLM_TIMEOUT'})
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(errors, b'')

    def test_child_rejects_invalid_deadline_before_any_transport(self):
        script = 'from llm.provider import _child_main; _child_main()'
        child = subprocess.Popen([sys.executable, '-c', script], cwd=Path(provider.__file__).resolve().parent.parent,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, errors = child.communicate(encoded({'payload': '{}', 'key': 'synthetic-child-key', 'timeout': 0}), timeout=3)
        self.assertEqual(json.loads(output), {'error': 'LLM_TRANSPORT_ERROR'})
        self.assertEqual(errors, b'')

    def test_child_failure_and_unknown_error_cannot_leak_stderr_or_details(self):
        for envelope in [{'error': 'my-secret-token'}, [], {'status': True}, {'status': 200, 'body': '@invalid'}]:
            with self.subTest(envelope=envelope), patch.object(provider.subprocess, 'Popen', return_value=self.process(envelope)):
                with self.assertRaises(provider.ProviderError) as failure:
                    provider._exchange(b'{}', 'my-secret-token', 1)
                self.assertEqual(failure.exception.code, 'LLM_TRANSPORT_ERROR')
                self.assertNotIn('my-secret-token', str(failure.exception))

    def test_child_start_failure_is_unambiguous_and_safe(self):
        with patch.object(provider.subprocess, 'Popen', side_effect=OSError('private-path and key')):
            with self.assertRaises(provider.ProviderError) as failure:
                provider._exchange(b'{}', 'key', 1)
        self.assertFalse(failure.exception.ambiguous)
        self.assertEqual(failure.exception.code, 'LLM_LOCAL_ERROR')
        self.assertNotIn('private-path', str(failure.exception))

    def test_oversize_envelope_and_body_rejected(self):
        child = self.process({'status': 200, 'body': base64.b64encode(b'a' * (provider.MAX_RESPONSE_BYTES + 1)).decode()})
        with patch.object(provider.subprocess, 'Popen', return_value=child):
            with self.assertRaises(provider.ProviderError) as failure:
                provider._exchange(b'{}', 'test-secret', 1)
        self.assertEqual(failure.exception.code, 'LLM_RESPONSE_TOO_LARGE')


class ChildHTTPTests(SimpleTestCase):
    def response(self, *, status=200, chunks=None, headers=None):
        response = Mock()
        response.status = status
        response.getheader.side_effect = lambda key, default=None: (headers or {}).get(key, default)
        response.read1.side_effect = chunks if chunks is not None else [b'{}', b'']
        return response

    def request(self, response):
        connection = Mock()
        connection.getresponse.return_value = response
        with patch.object(provider.http.client, 'HTTPSConnection', return_value=connection) as constructor:
            result = provider._http_request(b'{}', 'test-token', 5)
        return result, connection, constructor

    def test_fixed_verified_tls_host_and_path(self):
        result, connection, constructor = self.request(self.response())
        self.assertEqual(result['status'], 200)
        self.assertEqual(constructor.call_args.args[0], 'api.deepseek.com')
        context = constructor.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, provider.ssl.CERT_REQUIRED)
        self.assertEqual(connection.request.call_args.args, ('POST', '/chat/completions'))
        headers = connection.request.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-token')
        self.assertEqual(headers['Accept-Encoding'], 'identity')
        connection.close.assert_called_once()

    def test_redirect_and_error_body_never_read(self):
        for status in [301, 302, 307, 308, 401, 402, 429, 500]:
            response = self.response(status=status)
            result, connection, _ = self.request(response)
            self.assertEqual(result, {'status': status})
            response.read1.assert_not_called()
            self.assertEqual(connection.request.call_count, 1)

    def test_oversize_content_length_or_chunked_body_and_compression_rejected(self):
        cases = [(self.response(headers={'Content-Length': str(provider.MAX_RESPONSE_BYTES + 1)}), 'LLM_RESPONSE_TOO_LARGE'),
                 (self.response(chunks=[b'a' * (provider.MAX_RESPONSE_BYTES + 1)]), 'LLM_RESPONSE_TOO_LARGE'),
                 (self.response(headers={'Content-Encoding': 'gzip'}), 'LLM_RESPONSE_INVALID')]
        for response, code in cases:
            result, _, _ = self.request(response)
            self.assertEqual(result, {'error': code})

    def test_timeout_has_safe_stable_code(self):
        response = self.response()
        response.read1.side_effect = TimeoutError('secret body')
        result, _, _ = self.request(response)
        self.assertEqual(result, {'error': 'LLM_TIMEOUT'})

    def test_monotonic_deadline_checked_between_keepalive_reads(self):
        with patch.object(provider.time, 'monotonic', side_effect=[0, 0.1, 6]):
            result, _, _ = self.request(self.response(chunks=[b' ', b'never-read']))
        self.assertEqual(result, {'error': 'LLM_TIMEOUT'})

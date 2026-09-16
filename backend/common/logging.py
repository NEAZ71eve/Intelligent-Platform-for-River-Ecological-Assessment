import logging
import re


class RedactFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        message = re.sub(r'(?i)Bearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]', message)
        message = re.sub(r'(?i)((?:token|secret|password|session_key|openid|js_code|api_key)\s*[=:]\s*)[^\s& ,]+', r'\1[REDACTED]', message)
        record.msg, record.args = message, ()
        return True


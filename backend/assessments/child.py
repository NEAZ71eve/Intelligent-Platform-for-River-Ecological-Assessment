"""Exec entry point. Never import Django or inherit database credentials."""
import json
import resource
import signal
import sys
from pathlib import Path


def main():
    # The OS default handler terminates even while native inference holds the GIL.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, 30)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    raw = sys.stdin.buffer.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError('oversized child request')
    payload = json.loads(raw)
    timeout = float(payload['timeout'])
    if not 0 < timeout <= 120:
        raise ValueError('invalid timeout')
    signal.setitimer(signal.ITIMER_REAL, timeout)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from assessments.detector import infer, validate_model
    from recognition.artifacts import ModelError
    try:
        if payload.get('validate_only'):
            validate_model(payload['snapshot'], payload['model_root'])
            result = {'validated': True}
        else:
            result = infer(payload['snapshot'], payload['image_path'], payload['model_root'], payload['media_root'])
        print(json.dumps({'result': result}, ensure_ascii=False, allow_nan=False), flush=True)
    except ModelError as exc:
        print(json.dumps({'error_code': exc.code}), flush=True)
    except Exception:
        print(json.dumps({'error_code': 'MODEL_INFERENCE_FAILED'}), flush=True)


if __name__ == '__main__':
    main()

"""Single-host execution lock and bounded exec subprocess; no Django imports."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .artifacts import ModelError


@contextmanager
def execution_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
        else:
            yield fd
    finally:
        # Do not unlink or LOCK_UN: a surviving child must keep the inherited lock.
        os.close(fd)


def kill_and_wait(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_child(snapshot, image_path, model_root, media_root, timeout, lock_fd, *, validate_only=False):
    payload = json.dumps({'snapshot': snapshot, 'image_path': str(image_path), 'model_root': str(model_root), 'media_root': str(media_root), 'timeout': timeout, 'validate_only': validate_only}, allow_nan=False).encode()
    if len(payload) > 256 * 1024 or not 0 < timeout <= 120:
        raise ModelError('MODEL_CONFIG_INVALID')
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if key in os.environ}
    environment.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    command = [sys.executable, '-I', str(Path(__file__).with_name('child.py'))]
    # A file avoids unbounded communicate() buffers from native-library output.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
                                   env=environment, close_fds=True, pass_fds=(lock_fd,), start_new_session=True)
        try:
            try:
                process.communicate(input=payload, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                kill_and_wait(process)
                raise ModelError('INFERENCE_TIMEOUT') from exc
            if process.returncode == -signal.SIGALRM:
                raise ModelError('INFERENCE_TIMEOUT')
            if process.returncode != 0:
                raise ModelError('INFERENCE_PROCESS_EXITED')
            output.seek(0)
            raw = output.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                raise ModelError('MODEL_OUTPUT_INVALID')
            try:
                message = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise ModelError('MODEL_OUTPUT_INVALID') from exc
            if 'error_code' in message:
                raise ModelError(message['error_code'])
            if not isinstance(message.get('result'), dict):
                raise ModelError('MODEL_OUTPUT_INVALID')
            return message['result']
        finally:
            kill_and_wait(process)

#!/usr/bin/env python3
"""Start the built app and run real Playwright checks in one process namespace."""
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

def main():
    env = dict(os.environ)
    # Local release checks must not spend model budget, even when the developer
    # normally uses a configured Foundry endpoint in this shell.
    for key in ('FOUNDRY_API_KEY', 'FOUNDRY_RESPONSES_URL', 'FOUNDRY_MODEL'):
        env.pop(key, None)
    port = int(env.get('AFTER90_TEST_PORT', '8765'))
    base = f'http://127.0.0.1:{port}'
    env['AFTER90_BASE_URL'] = base
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.matchlens.api:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('local test server exited before readiness')
            try:
                with urlopen(base + '/api/health', timeout=1) as result:
                    if result.status == 200: break
            except (URLError, OSError): time.sleep(.1)
        else: raise RuntimeError('local test server did not become ready')
        return subprocess.run(['npm', 'run', 'test:browser'], cwd=ROOT/'frontend', env=env, check=False).returncode
    finally:
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait(timeout=5)

if __name__ == '__main__':
    raise SystemExit(main())

"""Internal gated process launcher. No child starts before the parent attaches a job.

Only the trusted ExecAdapter supplies this stdin payload; never feed agent output.
"""
import json
import os
import subprocess
import sys
import threading

MAX_STREAM = 16 * 1024 * 1024

def pump(source, destination):
    total = 0
    while True:
        chunk = source.read1(65536)
        if not chunk:
            return
        total += len(chunk)
        if total > MAX_STREAM:
            os._exit(70)  # Parent's job/group owns and terminates remaining children.
        destination.write(chunk)
        destination.flush()

def main():
    raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        return 70
    request = json.loads(raw.decode('utf-8'))
    proc = subprocess.Popen(request['argv'], cwd=request['cwd'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    out = threading.Thread(target=pump, args=(proc.stdout,sys.stdout.buffer), daemon=True)
    err = threading.Thread(target=pump, args=(proc.stderr,sys.stderr.buffer), daemon=True)
    out.start(); err.start()
    try:
        proc.stdin.write(request['prompt'].encode('utf-8'))
        proc.stdin.close()
    except BrokenPipeError:
        pass
    code=proc.wait()
    out.join(); err.join()
    return code

if __name__=='__main__':
    raise SystemExit(main())

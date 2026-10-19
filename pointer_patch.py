import ctypes
import hashlib
import json
import os
import subprocess
import sys

EXPECTED_SHA256 = 'da558f18ff3ec47281fd8f645b9a1f76663c66af44be1dd4607a57cb842c3910'
with open('/usr/sbin/lginput2', 'rb') as executable:
    if hashlib.sha256(executable.read()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError('Unsupported lginput2 binary; no changes made')

TARGETS = [(0x66D9C, '70b58cb0'), (0x6705C, '2de9f043'), (0x67144, '2de9f04f')]
PATCH = bytes.fromhex('00207047')
libc = ctypes.CDLL(None, use_errno=True)
libc.ptrace.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
libc.ptrace.restype = ctypes.c_long

def trace(request, pid, address=0, data=0):
    ctypes.set_errno(0)
    result = libc.ptrace(request, pid, address, data)
    error = ctypes.get_errno()
    if result == -1 and error:
        raise OSError(error, os.strerror(error))
    return result

pid = int(subprocess.check_output(['pidof', 'lginput2']).strip())
with open('/proc/%d/maps' % pid) as source:
    mapping = next(line for line in source if '/usr/sbin/lginput2' in line and 'r-xp' in line)
base = int(mapping.split('-')[0], 16)
if int(mapping.split()[2], 16) != 0:
    raise RuntimeError('Unexpected executable mapping')
threads = sorted(int(value) for value in os.listdir('/proc/%d/task' % pid))
attached = []
changed = []
restore = '--restore' in sys.argv
try:
    for tid in threads:
        trace(16, tid)
        attached.append(tid)
        os.waitpid(tid, 0x40000000)
    for tid in attached:
        registers = (ctypes.c_uint32 * 18)()
        trace(12, tid, 0, ctypes.addressof(registers))
        for offset, _ in TARGETS:
            if base + offset <= registers[15] < base + offset + 4:
                raise RuntimeError('Thread is at patch location; retry later')
    for offset, expected_hex in TARGETS:
        address = base + offset
        expected = bytes.fromhex(expected_hex)
        current = (trace(1, pid, address) & 0xffffffff).to_bytes(4, 'little')
        if current not in (expected, PATCH):
            raise RuntimeError('Unexpected instructions at %s: %s' % (hex(address), current.hex()))
    for offset, expected_hex in TARGETS:
        address = base + offset
        replacement = bytes.fromhex(expected_hex) if restore else PATCH
        original = trace(1, pid, address) & 0xffffffff
        trace(4, pid, address, int.from_bytes(replacement, 'little'))
        changed.append((address, original))
        if (trace(1, pid, address) & 0xffffffff) != int.from_bytes(replacement, 'little'):
            raise RuntimeError('Patch verification failed')
    print(json.dumps({'pid': pid, 'status': 'restored' if restore else 'patched', 'functions': len(TARGETS)}))
except BaseException:
    for address, original in reversed(changed):
        trace(4, pid, address, original)
    raise
finally:
    for tid in reversed(attached):
        trace(17, tid)

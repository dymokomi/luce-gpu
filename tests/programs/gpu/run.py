#!/usr/bin/env python3
"""Exercise GPU contracts and pixels with temporary, automatically cleaned builds.

LUCE_TEST_GPU=required requires a Metal device on supported macOS hosts; optional
records missing hardware coverage. LUCE_TEST_WINDOW follows the existing window
suite's required/optional/off desktop policy. Platform-independent checks always
run. Metal API validation is enabled for every process exercising the backend.
"""
from pathlib import Path
import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
DEPENDENCY = ('    def dependency "luce-gpu" {\n        str owner = "dymokomi"\n        str version = "^0.1.0"\n'
              f'        str path = "{Path(__file__).resolve().parents[3]}"\n    }}\n'
              '    def dependency "luce-window" {\n        str owner = "dymokomi"\n        str version = "^0.1.0"\n'
              f'        str path = "{Path(__file__).resolve().parents[4] / "luce-window"}"\n    }}\n')
SOURCE = Path(__file__).resolve().parent
COMPILER = Path(sys.argv[1]).resolve()


def run(command, *, expected=None, timeout=90):
    environment = dict(os.environ, MTL_DEBUG_LAYER='1')
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, env=environment)
    if result.returncode or (expected is not None and result.stdout.strip() != expected):
        raise AssertionError(f'{command}\nstatus={result.returncode}\n{result.stdout}{result.stderr}')
    return result.stdout.strip()


def desktop_available():
    graphics = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    foundation = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    graphics.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
    foundation.CFRelease.argtypes = [ctypes.c_void_p]
    session = graphics.CGSessionCopyCurrentDictionary()
    if session:
        foundation.CFRelease(session)
    return bool(session)


def record_skip(message):
    print(message, flush=True)
    (ROOT / 'build').mkdir(exist_ok=True)
    with (ROOT / 'build/hardware-skip.txt').open('a') as record:
        record.write(message + '\n')


def main():
    mac = platform.system() == 'Darwin' and platform.machine() == 'arm64'
    gpu_policy = os.environ.get('LUCE_TEST_GPU', 'required')
    window_policy = os.environ.get('LUCE_TEST_WINDOW', 'optional')
    if gpu_policy not in {'required', 'optional'}:
        raise ValueError('LUCE_TEST_GPU must be required or optional')
    if window_policy not in {'required', 'optional', 'off'}:
        raise ValueError('LUCE_TEST_WINDOW must be required, optional, or off')
    desktop = mac and window_policy != 'off' and desktop_available()
    if mac and window_policy == 'required' and not desktop:
        raise AssertionError('GPU presentation tests require a logged-in macOS desktop')
    hardware = None
    gui = False
    with tempfile.TemporaryDirectory(prefix='luce-gpu-test-') as temporary:
        work = Path(temporary)
        for source in SOURCE.glob('*.lucb'):
            shutil.copy2(source, work / source.name)
        (work / 'package.prisma').write_text('#prisma 4.0\ndef package "gpu-test" {\n' + DEPENDENCY + '}\n')
        modes = [(f'native-{level}', ['--native', '--opt', str(level)]) for level in range(4)]
        modes += [('c', ['--backend=c']), ('c-release', ['--backend=c', '--release'])]
        for name, flags in modes:
            binary = work / name
            entry = work / ('probe.lucb' if mac else 'unsupported.lucb')
            run([str(COMPILER), 'build', str(entry), *flags, '-o', str(binary)])
            # Linux has a Vulkan backend, so the unsupported-target program only runs
            # where neither backend exists; tests/programs/vulkan covers Vulkan.
            if mac or platform.system() != 'Linux':
                run([str(binary)], expected='ok GPU contracts without hardware' if mac else 'ok unsupported GPU target')
            if mac:
                rejected = subprocess.run([str(binary), 'wrong-thread'], capture_output=True, text=True, timeout=10)
                assert rejected.returncode == 1 and 'an object belongs to another runtime thread' in rejected.stderr, rejected
                outcome = run([str(binary), 'device'])
                assert outcome in {'ok GPU device', 'skip no Metal device'}, outcome
                available = outcome == 'ok GPU device'
                if hardware is not None:
                    assert hardware == available, 'device availability changed between compiler modes'
                hardware = available
                if gpu_policy == 'required' and not hardware:
                    raise AssertionError('GPU tests require a Metal device')
                gui = hardware and desktop
                if gui:
                    run([str(binary), 'gui'], expected='ok GPU pixels, sRGB, resize, acquisition, ownership, and isolation')
                assert 'SDL' not in run(['otool', '-L', str(binary)])
            print(f'ok gpu {name}' + (' (pixels and presentation)' if gui else ' (contracts)'), flush=True)

        # Importing portable GPU values must not link any native graphics library.
        (work / 'package.prisma').write_text('#prisma 4.0\ndef package "gpu_values" {\n' + DEPENDENCY + '}\n')
        values = work / 'values.lucb'
        values.write_text('import gpu\npub func main(arguments: str[]) -> i32:\n    discard(arguments)\n    let color = gpu.Color(red = 0.5)\n    assert(color.red == 0.5 and color.green == 0.0)\n    return 0\n')
        for name, flags in [('native', ['--native']), ('c', ['--backend=c'])]:
            binary = work / ('values-' + name)
            run([str(COMPILER), 'build', str(values), *flags, '-o', str(binary)])
            run([str(binary)])
            if mac:
                dependencies = run(['otool', '-L', str(binary)])
                assert all(lib not in dependencies for lib in ['AppKit', 'Metal', 'QuartzCore', 'SDL', 'libobjc'])

        # Cross-target emission must type-check the public API without importing
        # test-only Cocoa helpers. Native Linux must contain no Apple linkage.
        for target in ['arm64-macos', 'x86_64-macos', 'arm64-linux', 'x86_64-linux', 'x86_64-windows']:
            run([str(COMPILER), 'build', str(work / 'unsupported.lucb'), '--target', target, '--emit=c', '-o', str(work / (target + '.c'))])
        assembly = work / 'linux.s'
        run([str(COMPILER), 'build', str(work / 'unsupported.lucb'), '--target', 'x86_64-linux', '--emit=asm', '-o', str(assembly)])
        assert all(symbol not in assembly.read_text() for symbol in ['objc_msgSend', 'MTLCreateSystemDefaultDevice', 'CGColorSpaceCreateWithName', 'NSDefaultRunLoopMode'])
        print('ok gpu target emission and optional framework linkage', flush=True)

        if mac:
            # Device ownership does not initialize/link a window system.
            (work / 'package.prisma').write_text('#prisma 4.0\ndef package "gpu_device" {\n' + DEPENDENCY + '}\n')
            device = work / 'device.lucb'
            device.write_text('import gpu\npub func main(arguments: str[]) -> i32!:\n    discard(arguments)\n    var device = gpu.Device.open() catch failure:\n        if failure.code == gpu.unavailable:\n            return 0\n        error(failure.code, failure.message)\n    device.destroy()\n    return 0\n')
            for name, flags in [('native', ['--native']), ('c', ['--backend=c'])]:
                binary = work / ('device-' + name)
                run([str(COMPILER), 'build', str(device), *flags, '-o', str(binary)])
                run([str(binary)])
                dependencies = run(['otool', '-L', str(binary)])
                assert 'AppKit' not in dependencies and 'QuartzCore' not in dependencies
    if mac and not hardware:
        record_skip('skip gpu hardware: no Metal device; portable contracts passed')
    if mac and not gui:
        record_skip('skip gpu presentation/pixels: no device or desktop session, or LUCE_TEST_WINDOW=off')


if __name__ == '__main__':
    main()

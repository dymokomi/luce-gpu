#!/usr/bin/env python3
"""Build and run the Vulkan batching contracts on Linux, where the backend runs.

LUCE_TEST_GPU=required (the default) fails when no Vulkan device opens; optional
records the missing hardware. When the Khronos validation layer is installed the
program runs under it with synchronization validation, and any message fails.
"""
from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent
COMPILER = Path(sys.argv[1]).resolve()
DEPENDENCY = ('    def dependency "luce-gpu" {\n        str owner = "dymokomi"\n        str version = "^0.1.0"\n'
              f'        str path = "{ROOT}"\n    }}\n'
              '    def dependency "luce-window" {\n        str owner = "dymokomi"\n        str version = "^0.1.0"\n'
              f'        str path = "{ROOT.parent / "luce-window"}"\n    }}\n')


def validation_available():
    return any(Path(folder, 'VkLayer_khronos_validation.json').exists()
               for folder in ['/usr/share/vulkan/explicit_layer.d', '/usr/local/share/vulkan/explicit_layer.d',
                              os.path.expanduser('~/.local/share/vulkan/explicit_layer.d')])


def main():
    if platform.system() != 'Linux':
        print('skip vulkan batching: runs on Linux hosts', flush=True)
        return
    policy = os.environ.get('LUCE_TEST_GPU', 'required')
    with tempfile.TemporaryDirectory(prefix='luce-gpu-vulkan-') as temporary:
        work = Path(temporary)
        shutil.copy2(SOURCE / 'batching.lucb', work / 'batching.lucb')
        (work / 'package.prisma').write_text('#prisma 4.0\ndef package "vulkan-test" {\n' + DEPENDENCY + '}\n')
        for name, flags in [('native', ['--native']), ('c', ['--backend=c'])]:
            binary = work / name
            subprocess.run([str(COMPILER), 'build', str(work / 'batching.lucb'), *flags, '-o', str(binary)], check=True, timeout=900)
            environment = dict(os.environ)
            log = work / f'validation-{name}.log'
            if validation_available():
                environment.update(VK_INSTANCE_LAYERS='VK_LAYER_KHRONOS_validation', VK_LAYER_VALIDATE_SYNC='1',
                                   VK_LAYER_DEBUG_ACTION='VK_DBG_LAYER_ACTION_LOG_MSG', VK_LAYER_REPORT_FLAGS='error,warn',
                                   VK_LAYER_LOG_FILENAME=str(log))
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=600, env=environment)
            output = result.stdout.strip().splitlines()
            if result.returncode or not output:
                raise AssertionError(f'{binary}\nstatus={result.returncode}\n{result.stdout}{result.stderr}')
            if 'skip no Vulkan device' in output:
                if policy == 'required':
                    raise AssertionError('the Vulkan batching tests require a Vulkan device')
                print('skip vulkan batching: no Vulkan device', flush=True)
                return
            assert 'ok Vulkan batching' in output, result.stdout
            messages = log.read_text() if log.exists() else ''
            assert 'Validation' not in messages, messages
            print(f'ok vulkan batching {name}' + (' (validation, sync validation)' if validation_available() else ''), flush=True)


if __name__ == '__main__':
    main()

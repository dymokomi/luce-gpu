#!/usr/bin/env python3
"""Compare Vulkan layouts and named constants with the Khronos header oracle."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', required=True, type=Path)
parser.add_argument('--headers', required=True, type=Path, help='directory containing vulkan/vulkan.h')
args = parser.parse_args()
bindings = (ROOT / 'src/luce_gpu/gpu/vulkan/bindings.lucb').read_text(encoding='utf-8')
native = ['#define VK_USE_PLATFORM_WIN32_KHR', '#include <windows.h>',
          '#include <vulkan/vulkan.h>', '#include <stdio.h>', '#include <stddef.h>', 'int main(void) {']
test_bindings = re.sub(r'^extern func .*\n', '', bindings, flags=re.MULTILINE)
# Extern records keep their C names. Give this independent layout fixture its
# own names so it can coexist with the embedded GPU module in generated C.
test_bindings = re.sub(r'\bVk\w+\b', lambda match: 'Oracle' + match[0], test_bindings)
# Standard modules may use intrinsic names as fields; ordinary test modules may not.
test_bindings = re.sub(r'^    (\w+):', r'    vk_\1:', test_bindings, flags=re.MULTILINE)
base = ['import c', test_bindings, 'pub func main(arguments: str[]) -> i32:']
structures = re.findall(r'extern struct (\w+):\n((?:    [^\n]+\n)+)', bindings)
for name, body in structures:
    expressions = [f'sizeof({name})', f'alignof({name})']
    expressions += [f'offsetof({name}, {field})' for field in re.findall(r'    (\w+):', body)]
    base_expressions = [re.sub(r'\bVk\w+\b', lambda match: 'Oracle' + match[0],
                             re.sub(r', (\w+)\)', r', vk_\1)', item)) for item in expressions]
    base.append('    print(f"' + name + ' ' + ' '.join('{' + item + '}' for item in base_expressions) + '")')
    native.append('printf("' + name + ' ' + ' '.join(['%zu'] * len(expressions)) + '\\n", ' +
                  ', '.join(item.replace('alignof(', '_Alignof(').replace('offsetof(VkDescriptorPoolSize, descriptorType)', 'offsetof(VkDescriptorPoolSize, type)') for item in expressions) + ');')
constants = re.findall(r'^let (VK_\w+): (u32|i32|c.str) =', bindings, re.MULTILINE)
for name, kind in constants:
    if kind == 'c.str':
        base.append(f'    print(f"{name} {{(str){name}}}")')
        native.append(f'printf("{name} %s\\n", {name});')
    else:
        base.append(f'    print(f"{name} {{(i64){name}}}")')
        native.append(f'printf("{name} %lld\\n", (long long){name});')
base.append('    return 0')
native.append('return 0; }')
with tempfile.TemporaryDirectory(prefix='luce-vulkan-abi-') as folder:
    work = Path(folder)
    (work / 'abi.c').write_bytes(('\n'.join(native)).encode("utf-8"))
    (work / 'abi.lucb').write_bytes(('\n'.join(base)).encode("utf-8"))
    subprocess.run(['gcc', '-std=c11', '-I' + str(args.headers), str(work / 'abi.c'), '-o', str(work / 'c.exe')], check=True)
    expected = subprocess.check_output([work / 'c.exe']).splitlines()
    for flags in (['--native'], ['--backend=c']):
        subprocess.run([args.compiler.resolve(), 'build', work / 'abi.lucb', *flags, '-o', work / 'base.exe'], check=True)
        actual = subprocess.check_output([work / 'base.exe']).splitlines()
        if actual != expected:
            for left, right in zip(actual, expected):
                if left != right:
                    print('BASE', left.decode(), '\nSDK ', right.decode())
            raise SystemExit('Vulkan ABI mismatch')
        print(f'PASS {len(structures)} Vulkan layouts and {len(constants)} constants ({flags[0]})')

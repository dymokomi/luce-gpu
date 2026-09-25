#!/usr/bin/env python3
"""Keep native presentation in the presentation adapter, out of the Vulkan core."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

for module in ('device', 'surface', 'pipeline', 'render'):
    relative = f'src/luce_gpu/gpu/vulkan/{module}.lucb'
    text = (ROOT / relative).read_text(encoding='utf-8')
    assert not re.search(r'GetModuleHandle|CreateWin32Surface|VK_KHR_win32_surface|VkWin32Surface', text), \
        f'{relative}: native presentation belongs in the presentation adapter'
# Vulkan is loaded at run time: a direct extern would be an undefined symbol on
# Linux and Windows, where nothing links against the loader.
for source in (ROOT / 'src/luce_gpu/gpu/vulkan').rglob('*.lucb'):
    text = source.read_text(encoding='utf-8')
    assert not re.search(r'^extern func vk', text, re.MULTILINE), \
        f'{source.relative_to(ROOT)}: call Vulkan through vulkan/entry.lucb, not a direct extern'
print('PASS GPU presentation boundary')

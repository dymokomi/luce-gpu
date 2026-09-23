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
print('PASS GPU presentation boundary')

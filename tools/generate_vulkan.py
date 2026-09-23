#!/usr/bin/env python3
"""Generate the standard GPU backend's Vulkan ABI subset from Khronos vk.xml.

The generated Base declarations have no C shim or runtime SDK dependency.
Regeneration requires the Vulkan SDK registry; builds use the checked-in output.
"""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = '''
vkCreateInstance vkDestroyInstance vkEnumeratePhysicalDevices
vkGetPhysicalDeviceQueueFamilyProperties vkGetPhysicalDeviceMemoryProperties
vkGetPhysicalDeviceFormatProperties vkCreateDevice vkDestroyDevice vkGetDeviceQueue
vkCreateWin32SurfaceKHR vkGetPhysicalDeviceWin32PresentationSupportKHR vkDestroySurfaceKHR vkGetPhysicalDeviceSurfaceSupportKHR
vkGetPhysicalDeviceSurfaceCapabilitiesKHR vkGetPhysicalDeviceSurfaceFormatsKHR
vkCreateSwapchainKHR vkDestroySwapchainKHR vkGetSwapchainImagesKHR
vkAcquireNextImageKHR vkQueuePresentKHR vkQueueSubmit vkQueueWaitIdle vkDeviceWaitIdle
vkCreateImageView vkDestroyImageView vkCreateImage vkDestroyImage
vkGetImageMemoryRequirements vkAllocateMemory vkFreeMemory vkBindImageMemory
vkCreateBuffer vkDestroyBuffer vkGetBufferMemoryRequirements vkBindBufferMemory
vkMapMemory vkUnmapMemory vkCreateRenderPass vkDestroyRenderPass
vkCreateFramebuffer vkDestroyFramebuffer vkCreateShaderModule vkDestroyShaderModule
vkCreatePipelineLayout vkDestroyPipelineLayout vkCreateGraphicsPipelines vkDestroyPipeline
vkCreateCommandPool vkDestroyCommandPool vkAllocateCommandBuffers vkResetCommandPool
vkBeginCommandBuffer vkEndCommandBuffer vkCmdBeginRenderPass vkCmdEndRenderPass
vkCmdBindPipeline vkCmdSetViewport vkCmdSetScissor vkCmdBindVertexBuffers vkCmdDraw
vkCreateSemaphore vkDestroySemaphore vkCreateFence vkDestroyFence
vkWaitForFences vkResetFences
vkCreateDescriptorSetLayout vkDestroyDescriptorSetLayout vkCreateDescriptorPool vkDestroyDescriptorPool
vkAllocateDescriptorSets vkUpdateDescriptorSets vkCmdBindDescriptorSets vkCmdPushConstants
'''.split()


def vulkan(node):
    return 'vulkan' in node.get('api', 'vulkan').split(',')


def members(node):
    return [member for member in node.findall('member') if vulkan(member)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registry', type=Path)
    args = parser.parse_args()
    registry = ET.parse(args.registry).getroot()
    types = {t.get('name') or t.findtext('name'): t for t in registry.findall('types/type') if vulkan(t)}
    commands = {c.findtext('proto/name'): c for c in registry.findall('commands/command') if c.find('proto') is not None and vulkan(c)}
    values = {}
    aliases = {}
    result_names = {e.get('name') for e in registry.findall("enums[@name='VkResult']/enum")}
    for e in registry.findall('.//enum'):
        if e.get('value'):
            values[e.get('name')] = e.get('value')
        elif e.get('bitpos'):
            values[e.get('name')] = str(1 << int(e.get('bitpos')))
        elif e.get('alias'):
            aliases[e.get('name')] = e.get('alias')
        elif e.get('offset'):
            extension = e.get('extnumber')
            if extension:
                value = 1000000000 + (int(extension) - 1) * 1000 + int(e.get('offset'))
                values[e.get('name')] = str(-value if e.get('dir') == '-' else value)
        if e.get('extends') == 'VkResult':
            result_names.add(e.get('name'))
    for extension in registry.findall('extensions/extension'):
        for e in extension.findall('require/enum'):
            if e.get('offset'):
                value = 1000000000 + (int(e.get('extnumber', extension.get('number'))) - 1) * 1000 + int(e.get('offset'))
                values[e.get('name')] = str(-value if e.get('dir') == '-' else value)

    def constant_value(name):
        if name in aliases:
            return constant_value(aliases[name])
        value = values[name]
        if value.startswith('"'):
            return 'c.str', value
        # Registry sentinel constants use C unsigned complements and suffixes.
        complement = re.fullmatch(r'\(~(\d+)U\)', value)
        if complement:
            value = str(0xffffffff ^ int(complement.group(1)))
        value = re.sub(r'[uU]$', '', value)
        return ('i32' if name in result_names else 'u32'), value

    needed = set()
    scalars = {'void': 'void', 'char': 'u8', 'float': 'f32', 'double': 'f64',
               'int32_t': 'i32', 'uint32_t': 'u32', 'int64_t': 'i64', 'uint64_t': 'u64',
               'uint8_t': 'u8', 'uint16_t': 'u16', 'size_t': 'usize',
               'HINSTANCE': 'void*?', 'HWND': 'void*?', 'HANDLE': 'void*?',
               'LPCWSTR': 'u16*?', 'SECURITY_ATTRIBUTES': 'void', 'DWORD': 'u32'}

    def base_type(name):
        if name in scalars:
            return scalars[name]
        item = types[name]
        if item.get('alias'):
            return base_type(item.get('alias'))
        category = item.get('category')
        if category in ('struct', 'union'):
            if name not in needed:
                needed.add(name)
                for member in members(item):
                    declaration(member)
            return name
        if category == 'handle':
            return 'u64'
        if category == 'enum':
            return 'i32' if name == 'VkResult' else 'u32'
        if category == 'funcpointer':
            return 'void*?'
        if category in ('bitmask', 'basetype'):
            return base_type(item.findtext('type'))
        raise ValueError((name, category))

    def declaration(node):
        name = node.findtext('name')
        kind = node.findtext('type')
        # Registry comments can contain brackets such as STORAGE_BUFFER[_DYNAMIC].
        # Only declaration tokens may contribute a fixed array extent.
        text = (node.text or '') + ''.join(
            (''.join(child.itertext()) if child.tag != 'comment' else '') + (child.tail or '')
            for child in node)
        before = text.split(name)[0]
        depth = before.count('*')
        if kind == 'VkAllocationCallbacks':
            return name, 'void*?'
        result = base_type(kind)
        if depth:
            if kind == 'char':
                result = 'c.str' + ('*?' * (depth - 1))
            else:
                result += '*?' * depth
        array = re.search(r'\[([^\]]+)\]', text.split(name, 1)[1])
        if array:
            length = array.group(1)
            length = values.get(length, length)
            result += f'[{length}]'
        return name, result

    functions = []
    for name in COMMANDS:
        command = commands[name]
        parameters = [declaration(p) for p in command.findall('param') if vulkan(p)]
        result = base_type(command.findtext('proto/type'))
        params = ', '.join(f'{n}: {t}' for n, t in parameters)
        functions.append(f'extern func {name}({params})' + (f' -> {result}' if result != 'void' else ''))
    lines = [
             '#==============================================================================================',
             '#',
             '#   bindings - Vulkan structures, handles and functions from the Khronos registry',
             '#',
             '#   DESCRIPTION:',
             '#       Generated from the Khronos Vulkan registry by tools/generate_vulkan.py.',
             '#       Handles use the 64-bit Vulkan ABI; no Vulkan headers are required.',
             '#',
             '#==============================================================================================',
             '',
             '# mark: Vulkan bindings =======================================================================',
             '']
    authored = ROOT / 'src/luce_gpu/gpu/vulkan'
    constants = set()
    for source in authored.rglob('*.lucb'):
        if source.name not in ('bindings.lucb', 'shaders.lucb'):
            constants.update(re.findall(r'\bVK_[A-Z0-9_]+\b', source.read_text(encoding='utf-8')))
    constants.discard('VK_MAKE_API_VERSION')  # documented expression, not an enum
    # Structure tags are emitted alongside their declarations below.
    for name in sorted(constants):
        if not name.startswith('VK_STRUCTURE_TYPE_'):
            kind, value = constant_value(name)
            lines.append(f'let {name}: {kind} = {value}')
    lines.append('')
    for name in sorted(needed):
        item = types[name]
        # Clear unions have a fixed 16-byte ABI; color floats also store depth/stencil.
        if name == 'VkClearValue':
            lines += ['extern struct VkClearValue:', '    color: f32[4]', '']
            continue
        if item.get('category') == 'union':
            continue
        lines.append(f'extern struct {name}:')
        for member in members(item):
            n, t = declaration(member)
            lines.append(f'    {"descriptorType" if n == "type" else n}: {t}')
        lines.append('')
        tag = item.find('member[@values]')
        if tag is not None:
            constant = tag.get('values')
            lines += [f'let {constant}: u32 = {values[constant]}', '']
    lines += functions
    output = ROOT / 'src/luce_gpu/gpu/vulkan/bindings.lucb'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(('\n'.join(lines) + '\n').encode("utf-8"))
    print(f'wrote {output.relative_to(ROOT)} ({len(needed)} structures, {len(functions)} functions)')


if __name__ == '__main__':
    main()

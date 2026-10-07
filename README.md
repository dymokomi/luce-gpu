# luce-gpu

GPU devices, textures, shaders, compute kernels, masks and frames, presenting to luce-window windows. Shaders are GLSL compiled ahead of time and embedded (`tools/embed_shaders.py`); the Vulkan bindings are generated from the Khronos headers (`tools/generate_vulkan.py`).

## Modules

| import | what it holds |
| --- | --- |
| `import gpu` | Portable devices, canvases and frames |

## Using it

Add the dependency to `package.prisma`; the modules keep their short names:

```prisma
def dependency "luce-gpu" {
    str owner = "dymokomi"
    str version = "^0.1.0"
}
```

## Depends on

- luce-std
- luce-window

## Platforms

macOS (Metal), Windows and Linux (Vulkan).

Native libraries it links, by platform (declared in `package.prisma`, linked only when the program reaches code that needs them):

- macos: objc, Metal, CoreGraphics, QuartzCore

On Windows and Linux nothing is linked: the system's Vulkan loader (`vulkan-1.dll`, `libvulkan.so.1`) is opened when the first device is, so building needs no Vulkan SDK or development package. Linux presents to X11 windows (Xlib surfaces), which covers Wayland desktops through XWayland.

## Tests

`luc test` runs `tests/gpu`, the device, pixel, window and linkage checks (Metal on macOS, Vulkan batching on Linux), and `tests/boundaries`. `docs/GPU.md` describes them.

## License

MIT or Apache-2.0, at your option.

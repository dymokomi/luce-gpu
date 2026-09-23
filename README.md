# luce-gpu

GPU devices, textures, shaders, masks and frames, presenting to luce-window windows. Shaders are GLSL compiled ahead of time and embedded (`tools/embed_shaders.py`); the Vulkan bindings are generated from the Khronos headers (`tools/generate_vulkan.py`).

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
- windows: vulkan-1

## Tests

`./test.sh` runs every module's `test` blocks and the unit tests through the native and C backends, then the program checks under `tests/programs`. It expects the compiler beside this checkout at `../luce-base/build/luce-base` (or `--base PATH`).

## License

MIT or Apache-2.0, at your option.

# GPU devices and presentation

`gpu` is a luce-base standard module with a portable application API, a Metal
backend for arm64 macOS and a Vulkan backend for x64 Windows. It opens devices,
attaches a surface to a standard `window`, owns textures, and records colored
triangles, coverage masks and image draws into scoped drawing regions that end on
the screen or in a texture. All implementation code is Base calling system APIs
directly. There is no SDL dependency or C/Objective-C implementation shim.

Client fragment shaders and compute kernels are written once in GLSL and
embedded for both backends. The API remains provisional while those contracts
are exercised.

## Retained geometry (Base API)

`Geometry.create(device, vertices, lines=false)` uploads immutable storage once.
The returned manual owner has `is_open()` and idempotent `destroy()`. Copies
borrow; destroy exactly one owner. All calls follow the device's main-thread
contract. Creation validates finite data and limits a buffer to 4,194,304
32-byte records (128 MiB); clients split larger data into separate batches.

Triangles use ordinary `Vertex` position/color records, in multiples of three.
Line records pack the start in `x/y/z` and end in `red/green/blue`, one record per
segment. `draw_geometry(target_pointer, geometry, matrix, color, width, bias, slope_bias)`
records an owned reference and 112 bytes of parameters. Matrix is 16 column-major
world-to-clip floats; color, logical-pixel width and depth bias apply to lines.
The vertex shader clips lines at near/far planes and expands them on the GPU.
Triangles and lines use the frame's depth buffer. Geometry belongs to one device;
mixing devices is a checked error. Retained-only frames need no dynamic vertices.

`slope_bias` defaults to zero. For triangle fills it reserves a depth allowance
proportional to the rasterized surface's maximum screen-space depth gradient.
Its factor is in logical pixels and is scaled to backing pixels, so coplanar
wire overlays need not use a large constant depth pull. The same option exists
on `RenderTarget.triangles`; `Canvas.triangles` takes the factor directly in
backing pixels. It requires depth testing, accepts only nonnegative finite
values, and is reset for every draw. Lines retain their independent constant
`bias` and cannot request fill slope bias. Metal and Vulkan use their native
slope-scale rasterizer state (zero constant factor and clamp); no geometry or
shaders are regenerated. A zero clamp needs no optional Vulkan clamp feature.

Destroying a geometry owner after recording is safe. The canvas retains it until
clear/close; Metal command buffers retain bound resources, and Vulkan buffers
retire after their last submission fence. Backend destruction uses the device's
hook, so portable ownership finalizers do not link optional platform symbols.
The same GLSL vertex source generates SPIR-V and MSL; no scene/CAD logic lives
here. macOS pixel/lifetime tests and cross-target compilation are covered;
Vulkan runtime verification requires Windows/Linux hardware.

## Buffers and mesh draws (Base API)

`Buffer.create(device, bytes)` uploads device storage (4 bytes up to the
device's `limits().buffer_bytes`, a multiple of four); `buffer.upload(offset,
bytes)` rewrites part of it. Compute uses the same buffers; see Compute below. The copy
is ordered on the device's queue: draws recorded before it read the old bytes,
later ones the new, and nothing waits for work in flight (Metal blits from a
staging copy; Vulkan copies from the upload ring, then a barrier makes the
bytes visible to the vertex and fragment stages). Recorded draws retain their
buffers until the frame finishes, so destroying an owner after recording is
safe.

`draw_mesh(target, buffers, vertices, parameters, kind, slope_bias)` draws an
indexed mesh by vertex pulling from up to seven buffers (`MeshBuffers`,
bindings 8..14 of `shaders/mesh.glsl`) with one parameter block (binding 15;
`mesh_parameter_count` floats, 496 bytes, at the `mesh_*` offsets).

The block only grows at its end. A new parameter is appended after the last
one, and its default, zero, leaves its feature off (`mesh_curvature`, added
after the first layout, is read only by the curvature shading). `draw_mesh`
takes any block from `mesh_base_parameter_count` (120, the first layout,
through `mesh_accent`) to `mesh_parameter_count` floats and fills what a
shorter block leaves out with zeros, so a caller written against an older
layout keeps drawing as it did. Shorter or longer blocks are rejected
(`invalid_geometry`).

| Buffer | Contents |
| --- | --- |
| `triangles` | Surfaces and ids: 3 corner ids per triangle. Wires: 2 point ids per edge. |
| `corners` | The point of each corner (u32). |
| `positions` | x, y, z per point (f32). |
| `normals`, `colors` | 3 floats per element of the domain `mode.y` / `mode.z` names (0 point, 1 corner, 2 face, 3 detail; -1 none). |
| `faces` | The face of each triangle (u32). |
| `flags` | Bits per face; flagged faces take the `accent` color. |

`MeshKind.surface` shades per fragment per `Shading`: `lit` (Lambert from the
ambient sum and up to four directional lights, on the side facing the eye, so
inside-out and open meshes light on both sides), `flat` (the triangle's
normal), `zebra` (reflected stripes of a cylinder or plane around
`zebra_axis`, antialiased with `fwidth` and fading to their mean before they
alias), `isophote` (lines of equal N · axis), `normals`, `unlit` and
`curvature` (a blue-green-red map of a value of the principal curvatures the
colors buffer carries unclamped, over `mesh_curvature`'s range). `MeshKind.wires` expands point pairs into constant-pixel-width lines.
`MeshKind.ids` writes `id base + face + 1` little-endian into an `rgba8_linear`
target for picking; zero is nothing. Shading is a parameter, so changing it
re-uploads no buffer. tests/gpu/mesh_pixels.lucb checks pixels on
Metal and, through tests/gpu/batching.lucb, on Vulkan hosts.

## Run the example

```sh
luce-base build tests/gpu/surface.lucb -o build/gpu-window
./build/gpu-window
```

The default native compiler produces the executable. It displays a blue window;
Escape or the close button exits. The complete event loop is in the example.
The graphics setup itself is:

```luce
from luce_gpu import gpu
from luce_window import window

var device = try gpu.Device.open()
defer device.destroy()
var target = try window.Window.open(window.Options(title = "Luce GPU"))
defer target.destroy()
var surface = try gpu.Surface.open(device, target)
defer surface.destroy()
try target.show()
_ = try surface.clear_present(gpu.Color(red = 0.025, green = 0.06, blue = 0.15))
try surface.wait_idle()
```

Backend link requirements are automatic. A normal package needs no `[native]`
framework or library list for standard `window`/`gpu`. Requirements live beside
the backend in `links.json`; the compiler inspects the emitted object’s actual
unresolved symbols before selecting them. This applies to native builds, C
comparison builds, and Luce applications using Base packages.

Device-only programs need Metal and objc, without AppKit initialization or
linkage. Using just portable values such as `gpu.Color` needs none of these
frameworks. The compiler's C backend remains a comparison path in tests; the
library and example normally compile through the native backend.

## Public contract

| Operation or type | Contract |
| --- | --- |
| `supported(backend)` | Reports implementation availability for this build, not hardware availability. |
| `Device.open()` | Selects the implemented native backend. On arm64 macOS this is Metal. A machine without an available device returns `unavailable`. |
| `Device.open(Backend.metal)` | Explicit backend selection. Unsupported selections fail without fallback. `Backend.vulkan` is reserved and currently returns `unsupported`. |
| `Surface.open(device, window, blending)` | Creates one exclusive presentation surface for the window. A second attachment returns `window.presentation_in_use`. `blending` is `Blending.linear` (the default) or `Blending.encoded`; see Encoded surfaces. |
| `Color` | Three finite linear-light sRGB components in 0..1. Presentation is opaque with alpha one. Invalid components, including NaN and infinities, return `invalid_color`. |
| `Surface.size()` | Returns logical points, backing pixels, and scale using `window.Size`. |
| `clear_present(color)` | Refreshes backing dimensions, clears the full surface, and queues display-synchronized presentation. Returns `submitted` or `skipped`. |
| `wait_idle()` | Waits for this surface's submitted GPU work and reports execution errors. It does not wait for display scanout. |
| `destroy()` | Idempotent on that value. Surface destruction drains pending work and releases ownership. Call `wait_idle` first to observe execution errors. |

All device and surface operations currently require the main thread. Fallible
operations return `wrong_thread`; destruction of a live resource on another
thread traps. The zero value is closed. Copies alias ownership: borrow them and
destroy exactly one owner. These are manual Base resources, not reference-counted
application values.

Each surface retains the underlying device. Destroying the public `Device`
handle does not invalidate existing surfaces. Each surface also owns an exclusive
`window.Presentation` lease. Destroying the window closes it and detaches input
callbacks immediately; its native host remains allocated until the surface is
and all recording frames are released. Rendering and size queries then return `window.closed`, while
`wait_idle` and destruction remain valid. Surface-first destruction returns the
lease and permits a new surface on the same window.

`submitted` describes queue submission, not proof that a frame reached a display.
`skipped` covers hidden/minimized windows, zero backing extent, or a drawable
temporarily unavailable from the backend. Keep polling window events and try on
a later frame. A window fully covered by another window is still eligible for
rendering. Resizes and display-scale changes are applied on the next frame.

The first Metal backend caps each backing dimension at 16,384 pixels, a
conservative baseline for the supported Mac GPU families. A valid window size in
points can exceed this on a Retina display. Such a frame returns
`surface_too_large` before acquiring a drawable; resize smaller and retry on the
same surface. Newer hardware's larger limits can be exposed by a later capability
API. The limit is in the backend, not the portable window or color types.

This first implementation permits at most one pending command per surface. The
next frame waits for the preceding command before acquiring a drawable, reporting
any execution error. Execution failure is sticky until the surface is recreated.
Drawable acquisition may block: Metal's timeout is approximately one second, and
GPU completion waits have no application deadline. This API is not a nonblocking
render loop or a latency guarantee. Pipelined frames and explicit synchronization
belong with the later command/resource API.

## Encoded surfaces

A surface opened with `Blending.encoded` blends on encoded values rather than in
linear light. Web content blends that way (Skia's raster, Chrome and the browser's CPU
player do), as does most 2D drawing, so a page's layers can be composited straight onto
the window instead of into a linear frame texture that a last pass decodes.

| | `Blending.linear` | `Blending.encoded` |
| --- | --- | --- |
| Attachment | 8-bit sRGB (Metal `BGRA8Unorm_sRGB`; Vulkan `B8G8R8A8_SRGB`) | 8-bit UNORM in the sRGB color space (Metal `BGRA8Unorm` on a layer whose color space is sRGB; Vulkan `B8G8R8A8_UNORM` with `SRGB_NONLINEAR`) |
| Blending | in linear light; the hardware encodes on write | on the stored, encoded values |
| luce-gpu's draws (`triangles`, `mask`, `draw_image`, `copy_image`, clears) | linear colors, encoded by the hardware | the built-in shader encodes its straight linear color before premultiplying; the clear color is encoded on the CPU |
| Client shaders (`shade`, `shade_instances`) | output is linear, encoded by the hardware | output is written as is: encoded values |

So solid colors and opaque images look the same on either surface; only what blends
differs (half-alpha white over black is 188 on a linear surface, 128 on an encoded one).
A pipeline made for surfaces (`format` none) draws on both; Metal builds its state for
the UNORM format the first time it draws there, Vulkan a pipeline per swapchain format.
Mesh draws, whose fragment stages write linear light, are refused on an encoded surface
(`wrong_target`). `Surface.blending()` and `RenderTarget.blending()` say which a target
is (texture targets report `linear`; their format says how they store values).

## Scoped recording and composition

`Surface.frame()` returns an owned `Frame` and allows one recording scope per
surface. A second acquisition returns `frame_in_use`. `Frame.target()` grants a
checked `RenderTarget` view; no public canvas pointer escapes. In Luce, these are
ordinary objects, constructed or returned through the interop ownership contract.
Base explicitly releases returned references/views.

```luce
let frame = try surface.frame()
defer frame.release()
let target = try frame.value().target()
defer target.release()
let widget = try target.value().region(gpu.Rect(x = 20.0, y = 20.0, width = 200.0, height = 150.0))
defer widget.release()
try widget.value().triangles(vertices, true)
_ = try frame.value().present()
```

Rectangles use logical points. The frame snapshots logical and backing extents;
`region` selects a local viewport and intersects its parent’s clip. `clipped`
narrows the clip while preserving that viewport. Child clipping cannot expand a
parent clip. GPU vertices remain homogeneous clip coordinates; depth-enabled
triangles share the frame’s depth attachment and compare smaller depth as nearer.
Pixel scissors round outward at fractional backing coordinates.

Presentation ends the frame on success, skipped acquisition, or failure. Explicit
`close()` cancels recording and is idempotent. Both invalidate every target and
bound method immediately. Keeping a view alive retains only the storage needed
for safe expiry checks. Resize rejects stale drawing with `frame_resized`; begin
a new frame. Window or surface closure also rejects drawing. A frame keeps the
surface’s physical resources alive until closure; a closed surface releases its
window presentation lease when its last frame finishes.

`Frame(window.Size(...))` records portable commands without a presentation surface;
its `present` returns `unavailable` and ends the scope. This supports CPU-only
layout/recording tests and Luce interop without native graphics libraries.
Frames, views and their bound methods belong to the creating ownership context;
cross-thread access is rejected by the standard ownership checks. Attached
frames are created and disposed on the window’s main thread. Allocation failure
before publication leaves no active frame and permits retry.

OS event translation remains in `window`/`input`; hit testing, focus and framework
signal dispatch belong to UI. `gpu` neither interprets input nor accesses widget
internals. UI and 3D consume the same portable drawing scope. Vulkan requests
continue to return `unsupported` until that backend is implemented.

## Backend boundary

The files under `src/gpu/` share one standard module scope:

| Files | Responsibility |
| --- | --- |
| `module.lucb` | Portable values, errors, validation, and thread policy. |
| `device.lucb`, `surface.lucb`, `frame.lucb`, `texture.lucb`, `shader.lucb` | Public ownership, device references, window leases, textures, shaders, pipelines, and API contracts. |
| `shaders/`, `shaders.lucb` | The vertex stage (Vulkan) and built-in fill fragment in GLSL, and the module `tools/embed_shaders.py` generates from them for both backends. |
| `buffer.lucb`, `metal/buffer.lucb` | Buffers: allocation, uploads, reads and shared views. |
| `mesh.lucb`, `mesh_shaders.lucb`, `metal/mesh.lucb`, `vulkan/mesh.lucb` | Mesh draws: the portable API, the embedded mesh stages (`shaders/mesh*.vert`, `mesh.frag`, `mesh_id.frag`), and each backend's pipelines and bindings (Vulkan's buffers too). |
| `compute.lucb`, `compute_shaders.lucb`, `metal/compute.lucb`, `vulkan/compute.lucb` | Kernels and compute passes: the portable recording, the built-in fill kernel (`shaders/fill.comp`), and each backend's pipelines and encoding. |
| `params.lucb`, `canvas.lucb`, `mask.lucb` | The recorded command list and the 48-byte per-draw parameters both shaders read. |
| `backend.lucb` | Backend selection and device dispatch using opaque device payloads. |
| `presentation.lucb`, `resources.lucb` | Surface and texture dispatch using opaque payloads; a device alone never reaches them. |
| `metal/objc.lucb` | Exact typed system ABI declarations, including native aggregates. |
| `metal/device.lucb` | Metal device and queue creation and release. |
| `metal/drawing.lucb` | The vertex library, the built-in fill pipeline per color format, client libraries and pipelines, samplers, depth state and the shared render pass. |
| `readback.lucb` | Read batches over the readback ring, and `Texture.read` on them. |
| `metal/texture.lucb` | Private textures, blit uploads, offscreen passes. |
| `metal/transfer.lucb`, `vulkan/transfer.lucb` | The staging rings: readback slots (and Vulkan's upload slots), allocated once and mapped for good. |
| `metal/surface.lucb` | CAMetalLayer, sRGB color space, drawable sizing, presentation, completion, and teardown. |
| `vulkan/*` | The same contract on Vulkan: `device`, `texture` (images, samplers, transfers), `pipeline` (passes and pipelines per format), `shader` (client modules and their per-format pipelines), `render` (uploads, descriptors, encoding), `surface` (swapchain). |

Application-facing GPU signatures contain no native graphics objects. The
`window.Presentation.macos_view()` bridge exists for backend implementers; it
returns a borrowed NSView and is not required by application drawing code. Future
window backends can provide host-specific accessors without adding graphics
dependencies to `window` or changing application GPU calls.

A Vulkan implementation can keep its instance/device/queues in its device
payload and its native surface, swapchain, and synchronization objects in its
surface payload. The dispatch contract leaves acquisition and resize recovery
inside that backend. It must implement the same opaque sRGB target, lifetime,
completion, and skipped-frame semantics. Vulkan support will also require Linux
window hosting, capability/format checks, swapchain recreation, and an actual
cross-platform validation matrix; reserving the enum does not implement these.

Portable shader source will be designed together with resource bindings and
pipeline validation. No application-facing Metal shader strings or native
pipeline handles are introduced by this increment.

## Validation

```sh
LUCE_TEST_WINDOW=required luc test
```

`luc test` runs `tests/gpu`, which builds the device programs beside it and runs each
in its own process (`LUCE_TEST_GPU=optional` lets a host without a device pass; on
Linux and Windows that is `batching`, Vulkan's drawing and compute checks), and
`tests/boundaries`, which keeps native presentation out of the Vulkan core.
On macOS it enables Metal API validation and tests actual rendered pixels through
a test-only blit to shared memory. This checks channel order, linear-to-sRGB
conversion, alpha, full target coverage, aggregate calling conventions, and
backing extent after resize. It also exercises skipped acquisition, hidden
windows, duplicate attachment, invalid colors, worker-thread rejection, separate
windows, repeated recreation, and both destruction orders with pending work.
Scoped-frame tests also cover escaped targets, nested clipping/depth pixels, resize, parent closure, failed allocation and reuse after cancellation. A Luce fixture exercises constructors, regions and an expired retained bound method in all six modes.
Oversized backing width and height are rejected before Metal validation can
abort, and pixel readback verifies recovery after resizing smaller.
Allocation refusal is injected at each Base device/surface construction stage;
the suite verifies returned leases and balanced Base storage after cleanup.

The pixel observer temporarily replaces `nextDrawable` inside its own process,
retains the returned drawable and texture, then restores the method and releases
them. Because AppKit can constrain window height to the display, a scoped override
of one view's backing conversion exercises the oversized-height case; the width
case uses a real native resize. Readback is enabled only on the test surface.
Production targets remain
framebuffer-only and the standard library contains no injection hooks. The tests
do not require screen capture or accessibility permission.

Portable contracts run even without graphics hardware. `LUCE_TEST_GPU=optional`
records unavailable Metal hardware, while `LUCE_TEST_WINDOW=optional` records a
missing desktop. `LUCE_TEST_WINDOW=off` explicitly omits presentation checks.
Required modes fail when their resource is missing. Unsupported targets exercise
ordinary `unsupported` errors and link no macOS frameworks. All generated test
sources and binaries live in automatically removed temporary directories.

Platform contracts were checked against the installed macOS SDK's Metal,
QuartzCore, and CoreGraphics headers and these primary references:
[Apple's custom Metal view](https://developer.apple.com/documentation/metal/creating-a-custom-metal-view),
[CAMetalLayer drawable acquisition](https://developer.apple.com/documentation/quartzcore/cametallayer/nextdrawable()),
[Metal implementation limits](https://developer.apple.com/metal/Metal-Feature-Set-Tables.pdf),
and [Vulkan window-system integration](https://docs.vulkan.org/spec/latest/chapters/VK_KHR_surface/wsi.html).

## Portable drawing and widget regions

`Canvas` owns a reusable command list. `triangles` copies homogeneous clip-space
vertices (x/y in -w..w, z in 0..w), straight-alpha linear colors, a pixel scissor,
and optional pixel viewport. A borrowed `RenderTarget` combines a canvas with
its viewport and clip, allowing UI and 3D packages to share one frame without
sharing platform objects. `Surface.render` copies/uploads input before returning.
It retains GPU resources through completion, so CPU input may be reused at once.

Depth-enabled draws compare less and write depth; overlays leave depth untouched.
Depth starts at 1 each frame. Draw order is preserved, culling is disabled, and
colors blend in linear space before sRGB encoding. Empty clipped regions do no
work. Invalid geometry is rejected before recording. A canvas allows up to
1,048,576 vertices and 4,096 draws by default; failed growth preserves its recorded contents.
Dense 3D clients may call `RenderTarget.allow_vertices` (or `Canvas.allow_vertices`)
to raise the shared frame budget up to 8,388,608 vertices. This allocates nothing
until triangles are appended and leaves ordinary UI frames unchanged. In the same way
`RenderTarget.allow_draws` (or `Canvas.allow_draws`) raises the draw limit up to
65,536, for a frame several clients share, such as a window whose page and interface
draw into it together; past the limit a draw returns `command_limit`.

`RenderTarget.pixel_format()` is the texel format of the texture a target draws into,
or none for a presentation surface (and a standalone frame): the format a client
pipeline drawing there must be made for.
`clear` retains capacity; `destroy` releases it.

The built-in pipeline's fragment stage is written once in GLSL
(`shaders/fill.frag`) and embedded for both backends by
`tools/embed_shaders.py`: SPIR-V words for Vulkan and Metal Shading Language
cross-compiled from them by spirv-cross. On macOS the tool compiles each
Metal translation with `xcrun metal` before writing, because spirv-cross
passes through GLSL names that Metal reserves (a helper named `level`), which
the device would otherwise refuse only at run time. The vertex stage is per backend (they
disagree on clip-space Y): `shaders/quad.vert` for Vulkan and a Metal source in
`metal/drawing.lucb`. Fragments emit premultiplied color and blend with One /
OneMinusSourceAlpha, so vertex colors, coverage masks and textures all
composite the same way. Application transforms are computed before recording.
Packages depend only on `gpu`, so both backends serve the same drawing code.

Pixel tests additionally cover depth occlusion, clipping, linear alpha blending,
resize of depth storage, and releasing CPU commands before GPU completion.

## Textures and offscreen frames

`Texture.create(device, width, height, format, storage = false, mipmaps = false)` allocates a
texture of a tightly packed, top-down, straight-alpha format: `rgba8`
(sRGB-encoded, sampled as linear light), `rgba8_linear`, `rgba16_float` and
`r8` (samples as red with alpha one), and the 32-bit `rgba32_float`,
`r32_float`, `rg32_float` and `r32_uint` that compute kernels write (see
Compute). Dimensions are 1..16384. `upload(pixels, region?)` replaces
a region from CPU bytes and `read(pixels, region?)` copies one back. Both are
ordered after earlier submissions; `upload` does not wait for its copy (the bytes
may be reused at once), and `read` waits, so `read` after a frame sees that
frame. Pixel lengths must equal the region's texels times `texel_bytes(format)`,
or `invalid_pixels` is returned.

**Mipmaps.** `Texture.create(..., mipmaps = true)` gives a texture the full chain of
smaller levels down to one texel (`levels()` says how many), for an image drawn smaller
than it is. Uploads, frames and copies write the first level; `generate_mipmaps()` then
fills each later level from the one before it (a box filter), on the queue like
`upload`, without waiting (Metal's blit encoder `generateMipmapsForTexture`; on Vulkan a
chain of linear `vkCmdBlitImage`s, refused with `unsupported` where the device cannot
blit or filter the format). Sampling with `Filter.trilinear` picks levels by the draw's
scale and blends between them; `nearest` and `linear` read the first level only. Only
the formats frames render into have mipmaps, and not as storage images
(`invalid_geometry`).

Transfers go through host memory each device allocates once, keeps mapped and
reuses (a readback ring of three 32 MiB slots, host-cached where the device has
it; on Vulkan an upload ring of four 8 MiB slots too): no allocation per read or
upload. `ReadBatch.begin(device)` holds one readback slot for many reads at a
time. `reserve(bytes)` hands out an aligned offset (none when the batch is
full), `copy(texture, region, offset, row_texels?)` records a copy there with
rows `row_texels` apart, so tiles side by side land as one scanline-contiguous
strip, and `add(texture, region)` does both, tightly packed. `submit()` sends
every copy as one submission without waiting; `wait()` waits once; then
`bytes(offset, length)` views the result in place until `reset()` records again
into the slot or `finish()` gives it back. A batch keeps the textures it copies
from alive until it is submitted. At most three batches are held at once per
device, so one can be on the GPU while the caller works through another.
`read` is a batch of one, split into runs of rows when a region is larger than a
slot. `tests/readbench` times each phase on a device; `tests/framebench` times
frames and the driver memory they leave (see Per-draw memory below).

`texture.frame()` begins a recording frame whose target is the texture (points
equal texels). Its `present(color)` clears to `color` — alpha included — draws
and returns `submitted` without waiting; the pass is ordered before every later
submission, so the texture can be read or sampled at once. `texture.frame(keep = true)`
draws over the texture's contents instead (its `present` color is unused): a frame adds
to what earlier frames, uploads and copies left, as a tile that changed in one place is
updated (Metal's load action `load`; on Vulkan a render pass that loads the attachment,
compatible with the clearing one). A texture destroyed
while submitted work still uses it is released when that work completes.
**Clip masks.** An `r8` texture is a render target like the other 8- and 16-bit
formats, which makes it a clip mask: a frame renders a clip's coverage into it, and
later draws sample it (as red) and multiply their output by it. Nested clips need no
stencil: drawing the inner clip's coverage `c` over the mask as color 0 with alpha
`1 - c` (an ordinary `over` draw) leaves `mask * c`, and a clip path's coverage from
an atlas works the same way. A mask is one byte a pixel (256 KiB for a 512-pixel
tile), rendered in its own frame before the frame that samples it.

`device.memory_pages()` counts the pooled memory pages textures are carved from
(Vulkan; zero on Metal), a diagnostic for tests and memory reports. A frame
cannot sample the texture it renders into (`invalid_geometry`), and a texture
sampled by a frame must belong to the frame's device (`wrong_device`).

`copy_texture(source, region, target, x, y)` copies texels between two textures of
one device and one format exactly as stored, with `region`'s top left landing at
(`x`, `y`). It is a blit on the queue, like `upload`: outside any frame, ordered after
every earlier submission and before every later one, without waiting (Metal's blit
encoder `copyFromTexture`, Vulkan's `vkCmdCopyImage`). Scrolling by a few pixels can
move the previous frame's texture into another this way and draw only the strip it
uncovers, and an atlas can be compacted without a round trip through the CPU. A copy
within one texture is refused (`invalid_geometry`), as are different formats
(`invalid_pixels`) and textures of two devices (`wrong_device`). Do not confuse it with
`copy_image` below, which is a draw: it puts a texture into a frame's target, scaled
and filtered, among the frame's other draws.

`draw_image(target, texture, rectangle, source?, opacity, filter)` draws a texel
region scaled onto a rectangle of a `RenderTarget`, clipped like every other
draw, with `nearest` or `linear` sampling. Its texels are straight alpha and
composite over what is drawn, premultiplied, like every draw.
`copy_image(target, texture, rectangle, source?, filter, straighten)` instead
writes texels as they are stored, for filling a target cleared to transparent
with pieces that do not overlap: straight alpha stays straight and premultiplied
stays premultiplied, so a texture in either form moves between textures without
drift. With `straighten` the texels are premultiplied and are written straight,
which turns a premultiplied drawing into straight-alpha storage. `device_of(target)` returns an owned
handle to the device the target's frame draws on, so drawing code can create
textures for it; a standalone frame has none. These two are functions rather
than `RenderTarget` methods because textures and devices are Base resources: a
method mentioning them would hide the whole view from Luce.

A recorded image draw retains its texture until the canvas is cleared or
destroyed, so destroying the handle after recording is safe. Like devices and
surfaces, textures are manual Base resources: the zero value is closed, copies
alias ownership, and exactly one owner destroys them on the main thread.

## Client fragment shaders

A package can ship fragment programs of its own. Write them in GLSL 4.5 for
Vulkan against this contract, and run `tools/embed_shaders.py OUTPUT.lucb
FILE.frag...` (`--public` for a module other packages import) to generate a
Base module holding, per shader, `<stem>_frag_words: u32[]` and
`<stem>_frag_msl: c.str`. glslangValidator and spirv-cross are needed only when
a shader changes; the generated module is checked in. `#include "name.glsl"`
resolves beside the shader and then in each `-I DIR` given, so packages share
one include file instead of copying it.

```glsl
#version 450
layout(location = 0) in vec4 vertex_color;      // the draw's color
layout(location = 1) flat in vec4 data0;        // an instance's values (optional;
layout(location = 2) flat in vec4 data1;        //   zero under `shade`)
layout(location = 3) flat in vec4 data2;
layout(location = 0) out vec4 fragment_color;   // premultiplied
layout(push_constant) uniform Params { ... } params;   // up to 128 bytes
layout(set = 0, binding = 1) uniform sampler2D first;  // bindings 1..4
```

`gl_FragCoord` is in backing pixels of the target. Binding 5 is reserved for
the built-in coverage buffer.

`Shader.create(device, words, msl, fast_math = false)` compiles the program
(`invalid_shader` when either form is rejected). Built-in drawing uses fast
math; client shaders are IEEE unless they opt in. A client shader keeps IEEE
float rules on Metal as on Vulkan: no infinities or NaNs dropped, no
reassociation, so an edge on an exact pixel diagonal lands where Skia puts it.
Embedding with `--fast-math STEM` records `<stem>_frag_fast_math = true`;
passing it lets Metal relax those rules for speed. The built-in fill shader
does no inf- or NaN-sensitive work and keeps fast math, which saves about 12%
of a heavy frame's GPU time. `Pipeline.create(device, shader, blend, format?)`
binds it to a `Blend` — `over` (One / OneMinusSourceAlpha), `replace` (no
blending) or `add` (One / One) — and a target: a texture `Format`, or `none`
for presentation surfaces. `shade(target, pipeline, rectangle, uniforms?,
images?, filter, color)` draws a rectangle of a `RenderTarget` with it: the
uniform bytes fill the push-constant block (zero-padded to 128; Metal binds the
whole block since a padded struct may be larger than the bytes given), the
images sample at bindings 1.. with `filter`, and `color` is the vertex color.
`shade_instances(target, pipeline, instances, uniforms?, images?, filter)` draws many
rectangles with one pipeline in one draw. Each `ShadeInstance` has a `rect` (x, y,
width, height in points of the target, like `shade`'s rectangle) and twelve floats of
`data` its fragments read flat at locations 1..3; the uniforms, images and filter are
the draw's, and the vertex color is opaque white. One call counts as one draw against
the frame's draw limit however many rectangles it holds (up to 1,048,576 a frame), so
a run of glyphs from one atlas, or a list of rounded rectangles, is one draw instead of
hundreds. Rectangles draw in order, clipped like every draw; instances are copied. The
vertex stage stays luce-gpu's, so the same fragment program serves `shade` (locations
1..3 zero) and `shade_instances`: Metal builds a second pipeline state for a pipeline
the first time it is drawn instanced (`luce_instance` reads the instances from vertex
buffer 1 by `instance_id`, `drawPrimitives` with an instance count), and Vulkan a
second pipeline with an instance-rate vertex binding (`shaders/instance.vert`,
`vkCmdDraw(6, count, 0, first)`).

`shade_triangles(target, pipeline, vertices, uniforms?, images?, filter)` draws
clip-space triangles (`Vertex` records, mapped onto the target as
`RenderTarget.triangles` maps them) with a client pipeline; each vertex's color
reaches location 0 interpolated with perspective, so it can carry coordinates in
0..1 (a volume's texture coordinates, say). A pipeline made with
`Pipeline.create(..., depth_test = true)` tests its fragments against the frame's
depth (nearer passes) and writes none: translucent geometry, such as the slabs
luce-3d ray-marches fog volumes through, then hides behind nearer meshes, shows
over farther ones, and layers over itself. Metal sets a less-without-write depth
state for such draws; Vulkan builds the pipeline with depth testing on and
writes off. tests/gpu/depth_read.lucb checks the pixels on both.

A pipeline recorded into a frame of another target format is refused at
`present` with `wrong_target`; one from another device with `wrong_device`.
Shaders and pipelines are manual Base resources like textures, and a draw
keeps them alive until its canvas is cleared.

## Compute

Compute runs GLSL compute shaders on the device's one queue, beside drawing.
If you know CUDA, a `Kernel` is a compiled `__global__` function, a dispatch is
a launch with a grid of workgroups (CUDA's blocks), and a `Compute` is a stream
you fill and then submit once. In Metal terms a `Compute` is one command buffer;
in Vulkan terms one submitted command buffer with the barriers already placed.

### Writing a kernel

Write the kernel in GLSL 4.5 against this contract:

```glsl
#version 450
layout(local_size_x = 64) in;                                  // the workgroup size
layout(set = 0, binding = 0, std430) readonly buffer X { float x[]; };
layout(set = 0, binding = 1, std430) buffer Y { float y[]; };   // bindings 0..15
layout(push_constant) uniform Params { float a; uint n; } params;   // up to 128 bytes

void main() {
    uint i = gl_GlobalInvocationID.x;
    if (i < params.n)
        y[i] = params.a * x[i] + y[i];
}
```

Everything lives in descriptor set 0 at bindings 0..15, one resource per
binding: storage buffers, storage images, sampled images and samplers. Set 1
is reserved for a texture table (see below). Small
per-dispatch values go in the push-constant block. Uniform buffers, separate
images outside a texture table and arrays of resources are refused when
embedding. Pass counts in
push constants instead of calling `.length()` on a runtime array, which Metal
cannot answer without an extra buffer. Atomics on storage buffers (`atomicAdd`,
`atomicMin`, `atomicMax`, `atomicExchange`, `atomicCompSwap` on 32-bit ints)
work everywhere; image atomics are refused. Adding floats atomically
(`GL_EXT_shader_atomic_float`'s `atomicAdd` on a `float` in a buffer) works
where `limits().float_atomic_add` says so.
Subgroup operations (`GL_KHR_shader_subgroup_*`: `subgroupAdd`,
`subgroupBallot`, `subgroupShuffle` and the rest) work where
`limits().subgroup_ops` says so; they need `--target-env vulkan1.1` or later,
and spirv-cross turns them into Metal's `simd_*` functions. The subgroup size
differs by device (32 on Apple and NVIDIA GPUs, 64 on AMD's by default), so
read it from `limits().subgroup_size` or `gl_SubgroupSize` rather than
assuming one.

`tools/embed_shaders.py OUTPUT.lucb --public FILE.comp...` turns each kernel
into four declarations, the arguments of `Kernel.create`:

| Name | Holds |
| --- | --- |
| `<stem>_comp_words` | SPIR-V for Vulkan |
| `<stem>_comp_msl` | Metal Shading Language 3.0 from spirv-cross, entry `luce_compute`, push constants moved to buffer index 30 |
| `<stem>_comp_group` | the workgroup size, read from the shader |
| `<stem>_comp_bindings` | what each binding holds (`BindingKind`) |
| `<stem>_comp_fast_math` | whether Metal may use fast math for it (`--fast-math STEM`) |
| `<stem>_comp_table` | whether it reads a texture table (set 1) |

On macOS the tool compiles each Metal translation with `xcrun metal`, so a
kernel Metal would refuse fails here rather than at run time. Kernels that need
newer SPIR-V (ray queries) take `--target-env vulkan1.2`.

Kernels follow IEEE float rules on both backends: division by zero gives
infinities, `min` and `max` order them, and `isnan`/`isinf` see NaNs and
infinities. Vulkan drivers compile SPIR-V that way, while Metal compiles with
fast math unless told otherwise, so luce-gpu turns it off for every kernel.
`--fast-math STEM` lets Metal relax those rules for one kernel when speed
matters more than inf/NaN behaviour; Vulkan ignores it. A ray-slab test that
divides by a zero direction component needs the default.

Two features keep shared GLSL manageable across many kernels:

- **Includes.** `#include "name.glsl"` resolves beside the kernel, then in each
  `-I DIR`. `--depfile FILE` writes a Makefile rule naming every source and
  include the output came from, so a build script can re-embed when a shared
  library changes.
- **Variants.** `FILE.comp:STEM:NAME=VALUE,...` embeds one source under another
  stem with preprocessor defines. `trace.comp:trace:SPECTRAL=1
  trace.comp:trace_rgb:SPECTRAL=0` gives `trace_comp_*` and `trace_rgb_comp_*`.
  Variants are fixed when embedding; specialization constants (below) choose
  values when a kernel is created. The workgroup size must be a number, not
  `local_size_x_id`.

### Specialization constants

A kernel may declare constants whose values are chosen when it is created, as
Vulkan's specialization constants and Metal's function constants do (Cycles
specializes its kernels to a scene this way):

```glsl
layout(constant_id = 0) const uint SAMPLER = 0u;
layout(constant_id = 1) const bool MOTION_BLUR = false;
```

The compiler folds them and drops the branches they rule out, which a uniform
cannot do. A constant is a `uint`, `int`, `float` or `bool`. Embedding records
the kernel's constants as `<stem>_comp_constant_ids`, `_kinds`, `_defaults`
(their 32 bits) and `_names`. `Kernel.create(..., constants = values)` takes a
value for each constant to change, as a `gpu.Constant`:
`Constant.uint32(id, value)`, `int32`, `float32` or `boolean`. Constants
without a value keep their defaults. A value for an id the kernel does not
declare, of another kind, or given twice is refused with `invalid_shader`.
Each specialization is a pipeline of its own: Vulkan passes a
`VkSpecializationInfo`, and Metal builds the function with
`MTLFunctionConstantValues`.

Building a kernel compiles it, and a specialized kernel compiles anew for each
set of values. On the M4 Max a small kernel takes about 2.5 ms (33 ms the first
time a process compiles one); on RADV, 0.3 to 0.8 ms. Two features keep that
off the frame:

- **Background builds.** `Kernel.create(..., background = true)` returns at once
  (about 12 µs) and builds on a thread of its own. Metal and Vulkan create
  pipelines from any thread. `kernel.ready() -> bool!` polls it from the main
  thread, so a renderer can keep dispatching its general kernel and swap in a
  specialized one when it is ready. A dispatch of a kernel still building waits
  for it, and destroying one waits for its thread.
- **The device's kernel cache.** The device keeps its open kernels by what they
  were built from: the code's hash, the workgroup, the bindings, the flags and
  the constants, in any order. Creating one of them again shares it (about
  3 µs, built or still building) instead of compiling again.

Caches on disk are left to the drivers. Metal already keeps compiled functions
between runs (a second process compiles the same kernel in 2 ms, not 33 ms), as
do Mesa's and NVIDIA's shader caches. `MTLBinaryArchive` and a saved
`VkPipelineCache` would add little.

### Kernels, passes and dispatches

```luce
var saxpy = try gpu.Kernel.create(device, kernels.saxpy_comp_words, kernels.saxpy_comp_msl,
                                  kernels.saxpy_comp_group, kernels.saxpy_comp_bindings)
defer saxpy.destroy()
var pass = try gpu.Compute.begin(device)
defer pass.close()
let bindings: gpu.Binding[2] = [gpu.Binding(buffer = x), gpu.Binding(buffer = y)]
try pass.dispatch(saxpy, bindings, uniforms, (count + 63) // 64)
try pass.submit()
try pass.wait()
try y.read(0, result)
```

| Operation | Contract |
| --- | --- |
| `Kernel.create(device, words, msl, group, bindings, fast_math = false, table = false, constants = none, background = false)` | Builds the pipeline, specialized with `constants`, on a thread of its own with `background`; `ready()` says when it is built. `invalid_shader` when either form is rejected or the workgroup exceeds `limits()`. `group()` returns the size. |
| `Compute.begin(device)` | Starts recording. Commands are recorded portably and encoded at `submit`, so other work on the device (uploads, frames, reads) goes on meanwhile. |
| `dispatch(kernel, bindings, uniforms, x, y = 1, z = 1, textures = none)` | Runs `x * y * z` workgroups. Element `n` of `bindings` is binding `n`; bindings the kernel does not use may be left closed (`Binding()`). `uniforms` fill the push-constant block (at most 128 bytes, zero-padded). A zero count records nothing. |
| `dispatch_indirect(kernel, bindings, uniforms, arguments, offset)` | Takes the three u32 workgroup counts from `arguments` at `offset`, as earlier commands left them (Vulkan's `vkCmdDispatchIndirect`, Metal's indirect threadgroups). |
| `copy(source, source_offset, destination, destination_offset, bytes)` | Copies between buffers; ranges four-byte aligned and apart when the buffer is the same. |
| `fill(buffer, offset, bytes, value = 0)` | Sets every 32-bit word in the range. Metal fills bytes, so a value whose four bytes differ runs a small built-in kernel. |
| `timestamp()` | Records a GPU timestamp: when every command before it has finished. Returns its index; at most 64 per pass, where `limits().timestamps`. On Metal each one ends a command buffer, a few microseconds of overhead. |
| `submit()` | Sends the commands as one submission and returns at once. |
| `submission()` | The pass's `Submission`, for `Device.done`, `wait` and `gpu_time`. |
| `timestamps(out)` | After the pass finished: its timestamps in nanoseconds, as many as were recorded. |
| `done()` | Polls for completion without waiting. |
| `wait()` | Waits; `execution_failed` if the GPU failed, reported again on later calls. |
| `close()` | Ends the pass. An unsubmitted recording is dropped; submitted work finishes on its own. Idempotent. |

Each command sees everything the commands before it wrote: Metal encodes
dispatches into a serial compute encoder over hazard-tracked buffers, and
Vulkan puts a memory barrier between commands. Ten or twenty dependent
dispatches in one pass (a reduction, a compaction feeding an indirect dispatch)
need no synchronization from you. Independent dispatches pay for that ordering
too; an option to waive it between chosen dispatches can come later without
changing these calls.

Work is ordered by when it reaches the queue: `upload` and `read` act when
called, a `Compute` when submitted. A frame, read or pass submitted after a
`Compute` sees its results. Resources may be destroyed as soon as they are
recorded: the pass, and then the submitted work, keep them alive. Like every GPU
call, recording happens on the main thread.

### Images for compute

A texture created with `storage = true` binds as a storage image
(`image2D`, `uimage2D`) that a kernel loads and stores; any texture binds as a
sampled image (`sampler2D`), filtered as `Binding.filter` says. Pass either as
`Binding(texture = ...)`; the kernel's declaration decides which it is.

```glsl
layout(set = 0, binding = 0, rgba32f) writeonly uniform image2D color;
layout(set = 0, binding = 1, r32ui) uniform uimage2D ids;
layout(set = 0, binding = 2) uniform sampler2D environment;
```

The formats for kernel output are `rgba32_float`, `r32_float`, `rg32_float`
and `r32_uint`, beside `rgba16_float` and the 8-bit ones. Metal writes
`rg32_float` only from images declared `readonly` or `writeonly`; the others
can be read and written in one kernel. Frames do not render into the 32-bit
formats, but everything else does: `read` and `upload`, `ReadBatch`, and, except
for `r32_uint`, which holds integers, `draw_image` and `copy_image` to show
the result in a view. Where a device cannot filter a format linearly (32-bit
floats on some Vulkan devices), sampling falls back to nearest. On Vulkan a
storage image is in the general layout during a pass and goes back to the
sampling layout after it; on Metal the textures are created with shader-write
usage.

### Buffer addresses and texture tables

Some data does not fit fixed bindings: a scene's meshes in many buffers, its
materials' textures in a table indexed per hit. Two features cover that, in
the spirit of CUDA pointers and Vulkan's bindless descriptors.

**Buffer addresses.** `buffer.address() -> u64` is the buffer's address on the
GPU, where `limits().buffer_addresses`. Store it in a buffer or push constants
and reach the buffer through `GL_EXT_buffer_reference` (embed such kernels with
`--target-env vulkan1.2`):

```glsl
#extension GL_EXT_buffer_reference : require
#extension GL_EXT_shader_explicit_arithmetic_types_int64 : require
layout(buffer_reference, std430) readonly buffer Positions { vec4 positions[]; };
layout(set = 0, binding = 0, std430) readonly buffer Meshes { uint64_t meshes[]; };
...
Positions mesh = Positions(meshes[id]);
vec4 p = mesh.positions[index];
```

Once a buffer's address has been taken, every compute pass submitted while the
buffer lives counts as using it: Metal makes it resident in each pass, and
Vulkan keeps it until those passes finish. A kernel can therefore reach any
buffer whose address it is given without the pass naming it. Destroying the
buffer still ends its life, so keep buffers alive while addresses to them are
in use.

**Texture tables.** A `TextureTable` holds textures in numbered slots that a
kernel indexes at run time, where `limits().texture_tables`. Declare it as
set 1, binding 0, with a sampler in set 0, and pass the kernel's `_table` flag
to `Kernel.create`:

```glsl
#extension GL_EXT_nonuniform_qualifier : require
layout(set = 0, binding = 2) uniform sampler point;          // Binding(filter = ...)
layout(set = 1, binding = 0) uniform texture2D textures[];
...
vec4 c = textureLod(sampler2D(textures[nonuniformEXT(slot)], point), uv, 0.0);
```

```luce
var table = try gpu.TextureTable.create(device, 1024)
try table.set(3, albedo)
try pass.dispatch(shade, bindings, uniforms, groups, textures = table)
```

The table holds a reference to each texture in it; `clear(index)` empties a
slot, and a kernel must not read an empty one. Changing a slot while
submitted work may still read the table would race on the GPU, so `set` and
`clear` first wait for the last pass that used the table. Change tables
between frames, or keep two. Metal stores the textures' `gpuResourceID`s in an
argument buffer (embed_shaders.py moves it to buffer index 29) and makes them
resident for each dispatch. Vulkan keeps one descriptor set of sampled images,
updated after bind. Only sampled textures go in tables; storage images and
buffers stay bound, or reached by address.

### Ray queries

Where `limits().ray_query`, kernels trace rays against triangle meshes with
`GL_EXT_ray_query`, the inline ray tracing of Vulkan's `VK_KHR_ray_query`,
Metal's `intersection_query` and DXR's `RayQuery`. There are no ray-tracing
pipelines or shader tables: a kernel starts a query, steps it and reads the
committed hit. The scene lives in two levels of acceleration structure:

- **`Blas`** holds one mesh's triangles: `Triangles` names world-space float3
  positions (`stride` bytes apart, 12 by default) and three u32 indices per
  triangle, with offsets into their buffers. `opaque` triangles skip any-hit
  handling. `Blas.create(device, triangles, refit = true)` sizes storage from
  the counts; build it on a pass.
- **`Tlas`** holds instances: `Instance { blas, transform, id, mask }`, where
  `transform` is the object-to-world matrix as 3 rows of 4 (row-major, as in
  Vulkan and DXR), `id` the 24-bit custom index a query reports and `mask` the
  bits a ray's cull mask must share. `Tlas.create(device, capacity)`.

Builds are recorded on a `Compute` pass, ordered with its dispatches by the
same automatic barriers:

| Operation | Contract |
| --- | --- |
| `build_blas(blas, triangles)` | Builds from the counts the Blas was created for. |
| `refit_blas(blas, triangles)` | After vertices move, same counts and indices: faster than a build, and tracing quality degrades only with large motion. Needs `refit`. |
| `build_tlas(tlas, instances)` | Up to its capacity of built Blases. The Tlas holds those Blases until it is built again. |
| `update_tlas(tlas, instances)` | New transforms, ids and masks for the same Blases in the same order; also needed after a Blas is refitted. |

Scratch memory is the pass's own. A kernel binds a Tlas with
`Binding(accel = tlas)` at an `accelerationStructureEXT` binding; on Metal
every Blas behind it is made resident for the dispatch. Embed ray-query
kernels with `--target-env vulkan1.2`:

```glsl
#extension GL_EXT_ray_query : require
layout(set = 0, binding = 0) uniform accelerationStructureEXT scene;
...
rayQueryEXT query;
rayQueryInitializeEXT(query, scene, gl_RayFlagsOpaqueEXT, 0xff, origin, 0.0, direction, tmax);
while (rayQueryProceedEXT(query)) {}
if (rayQueryGetIntersectionTypeEXT(query, true) == gl_RayQueryCommittedIntersectionTriangleEXT) {
    float t = rayQueryGetIntersectionTEXT(query, true);
    vec2 uv = rayQueryGetIntersectionBarycentricsEXT(query, true);      // weights of vertices 1 and 2
    int triangle = rayQueryGetIntersectionPrimitiveIndexEXT(query, true);
    int id = rayQueryGetIntersectionInstanceCustomIndexEXT(query, true);  // Instance.id
}
```

A shadow ray adds `gl_RayFlagsTerminateOnFirstHitEXT` and only asks whether
anything was hit. Blases, Tlases and the buffers they were built from may be
destroyed once recorded: the pass, and then the submitted work, keep them.
Compaction is not offered yet.

On Metal, a Blas is a primitive acceleration structure and a Tlas an instance
acceleration structure with user-id instance descriptors. Storage grows at a
build whose descriptor needs more, since a Tlas's size depends on the Blases it
instances. On Vulkan, the device enables `VK_KHR_acceleration_structure`,
`VK_KHR_ray_query` and `VK_KHR_deferred_host_operations` where offered, with
buffer addresses. Builds use `vkCmdBuildAccelerationStructuresKHR`, and a Tlas's
instances go in a buffer of their own for each build.

### Buffers for compute

`Buffer.allocate(device, bytes, memory = Memory.device)` makes a zeroed buffer.
`Memory.device` is the GPU's own memory (Metal private storage, Vulkan
device-local). `Memory.shared` is also mapped for the CPU (Metal shared
storage, Vulkan host-visible and coherent): `view()` returns the bytes the GPU
uses, not a copy, so write them only while no submitted work uses the buffer.
`read(offset, out)` waits for earlier work and copies through the readback
ring; `ReadBatch.copy_buffer(buffer, offset, bytes, slot_offset)` reads
without waiting, beside texture reads. Every buffer can be a storage buffer, a
copy source or destination, indirect arguments, or mesh data.

`device.limits()` reports what the device allows:

| Field | Meaning | Metal | Vulkan |
| --- | --- | --- | --- |
| `buffer_bytes` | largest buffer | `maxBufferLength` | `maxStorageBufferRange`, capped by the largest allocation |
| `group_threads` | invocations per workgroup | 1024 | `maxComputeWorkGroupInvocations` |
| `group_size` | workgroup size per dimension | 1024 each | `maxComputeWorkGroupSize` |
| `group_count` | workgroups per dispatch dimension | 2^32 - 1 | `maxComputeWorkGroupCount` |
| `shared_bytes` | GLSL `shared` memory | `maxThreadgroupMemoryLength` | `maxComputeSharedMemorySize` |
| `float_atomic_add` | `atomicAdd` on floats in buffers | Metal 3 GPUs | `VK_EXT_shader_atomic_float` |
| `subgroup_size` | `gl_SubgroupSize` (SIMD group, wave, warp) | 32 | `VkPhysicalDeviceSubgroupProperties` |
| `subgroup_ops` | basic, vote, arithmetic, ballot and shuffle in kernels | true | those five in the compute stage |
| `timestamps` | submissions and passes are timed | true | the queue's `timestampValidBits` > 0 |
| `buffer_addresses` | `Buffer.address` | Metal 3 GPUs (`gpuAddress`) | `bufferDeviceAddress` and `shaderInt64` |
| `texture_tables` | `TextureTable` | argument buffers tier 2 | descriptor indexing: runtime arrays, nonuniform indexing, partially bound, variable count, update after bind |
| `texture_table_size` | slots per table | 65536 | `maxDescriptorSetUpdateAfterBindSampledImages`, at most 65536 |
| `ray_query` | `Blas`, `Tlas` and `GL_EXT_ray_query` | `supportsRaytracing` | `VK_KHR_acceleration_structure`, `VK_KHR_ray_query` |

### Completion and GPU time

Every submission luce-gpu makes on a device's queue has a serial: frames on
surfaces and textures (keep frames too), uploads, `copy_texture`, reads and
compute passes. A `Submission` holds one:
a plain value you can keep and compare, like a CUDA event or a Vulkan
timeline-semaphore value. `device.done(submission)` polls it,
`device.wait(submission)` blocks until it finishes (reporting
`execution_failed`), and `device.gpu_time(submission)` returns a `GpuTime`
with the nanoseconds the GPU started and finished it. The zero `Submission()`
counts as finished.

Times are on the GPU's clock: compare them with each other (`elapsed()`), not
with the CPU's clock. The device keeps them for its last `timed_submissions`
(32) submissions; older ones report none. Metal takes them from each command
buffer's `GPUStartTime` and `GPUEndTime`. Vulkan writes a timestamp query at
the start and end of the submission and scales it by `timestampPeriod`.

Inside a pass, `timestamp()` marks points between commands. In this pass the
two dispatches are timed separately:

```luce
try pass.dispatch(first, bindings, uniforms, groups)
_ = try pass.timestamp()
try pass.dispatch(second, bindings, uniforms, groups)
_ = try pass.timestamp()
try pass.submit()
try pass.wait()
var stamps: u64[2]
try pass.timestamps(stamps)
let span = (try device.gpu_time(try pass.submission())) else return
# span.start ≤ stamps[0] ≤ stamps[1] ≤ span.end
```

Frames hand out theirs: after `present` returns `submitted`,
`frame.value().submission()` is the frame's submission (zero for a skipped or
standalone frame). A benchmark measuring how long the GPU spends on each frame
waits for it and reads its time:

```luce
_ = try frame.value().present(background)
let submission = frame.value().submission()
...
try device.wait(submission)          # or poll device.done(submission)
if let time = try device.gpu_time(submission):
    record(time.elapsed())           # GPU nanoseconds for this frame
```

On Vulkan a surface frame already waits for the queue before `present`
returns, so its submission is finished at once. On Metal it runs while the
next frame records. Metal keeps a submission's command buffers only while they
run, so drawables go back to their layer as before.

Texture frames, uploads, copies and mipmap generation are recorded into the
device's open command buffer instead of a command buffer each. The open buffer
is submitted when a read or a compute pass is submitted, when `Device.done`,
`wait` or `gpu_time` asks about its submission, or after 64 recordings. On
Metal a surface's present also submits it, with the surface frame's own pass,
as one submission. On Vulkan it is submitted just before the surface frame,
which waits on the swapchain's semaphores in a submission of its own. Texture
frames and transfers since the last submission share a submission, so a
heavy frame is one or two submissions instead of one per pass.

### Per-draw memory

A pass's vertices, coverage words and shader instances, and the bytes of every
upload, are copied into an upload ring instead of buffers of their own: a few
8 MiB buffers the device makes once, filled front to back and reused once the
GPU has finished the submission that read them. A frame needing more adds a
chunk, and a single larger request gets a chunk of its size. Committing frees
chunks no work uses, beyond two kept for the next frames. Before the ring,
every pass made three short-lived buffers and every upload a staging buffer,
and the Metal driver grew its pools by 8 MiB with them and kept them. Vulkan
keeps the same kind of ring for draw data (host-visible, mapped for good),
where each pass used to make a buffer and a memory allocation of its own. Its
texture uploads already went through the upload ring described under Textures
and offscreen frames.

`tests/framebench` measures a frame's CPU time and the memory the driver keeps
on a heavy scene (16 tiles drawn into textures, an upload and about 1000
rectangles a frame), an app-like one (text-like coverage masks, a mipmapped
image uploaded, regenerated and read back now and then) and a blank one.

On Apple silicon the driver itself keeps memory once a process first uses each
kind of encoder: about 230 MB for render passes, and 160 MB more for blit or
compute work. It is dirty, resident memory (`footprint` lists it as
"IOAccelerator (graphics)"), and a 20-line Objective-C program shows the same.
So drawing work on Metal never opens a blit or compute encoder. Texture
uploads, `copy_texture`, mipmap generation, buffer uploads and clears, and
readback are render passes: a pass into the texture's region, through an unorm
view of an sRGB texture so bytes are written as they are, reads texels from
the upload ring, another texture or the level above. Readback and buffer work
are passes with no attachments whose fragments write a buffer. Only explicit
compute (`Compute` passes and acceleration structure builds) opens compute and
blit encoders. On the M4 Max the heavy scene keeps 266 MB and the app-like one
292 MB, against 427 MB and 450 MB with blits. The rest above the 229 MB baseline
is luce-gpu's own allocations: the upload ring, the readback ring and the depth
attachment.

### Long-running work

A submission that runs for seconds stalls everything else on the queue,
presentation included, and the system may reset a GPU that does not finish
(Windows' TDR allows about two seconds). Split long work, such as a path
tracer's samples, into passes a few milliseconds to tens of milliseconds long.
Each UI frame, submit the next pass only once `done()` reports the last one
finished. The UI never waits, and the GPU always has work. Recording a pass
takes microseconds, so the main-thread rule costs nothing here.

### Backends

Metal compiles each kernel's MSL into a compute pipeline state and encodes a
pass as one command buffer: runs of dispatches share a serial compute encoder,
runs of copies and fills a blit encoder. Vulkan builds one compute pipeline per
kernel with its own descriptor set layout and a 128-byte push-constant range,
and records a pass as one submission on the device's submission ring, with a
descriptor pool freed when it completes. The device runs at Vulkan 1.2 where
the loader and device support it, and enables `VK_EXT_shader_atomic_float`'s
buffer float atomics when offered.

Metal compiles kernels as MSL 3.0, which read-write textures and float atomics
need.

`tests/gpu/compute.lucb` runs on Metal (the probe) and on Vulkan (`batching`,
on Linux and Windows): saxpy, a twelve-dispatch reduction, compaction with
atomics feeding an indirect dispatch, fills, copies, shared views, a 256 MiB
buffer, kernels and buffers destroyed before their pass is submitted, IEEE
infinities and NaNs (the same bits on every backend), subgroup operations, storage
images of each 32-bit format written, sampled, read and written in place, read
back and drawn for display, float atomics, submissions, GPU times and
timestamps, buffers reached by address, texture tables, and (in `rays.lucb`)
ray queries checked against a CPU intersector: closest hits and shadow rays,
a refit, two instances with transforms, ids and masks, and structures
destroyed after recording.

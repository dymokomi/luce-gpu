# GPU devices and presentation

`gpu` is a luce-base standard module with a portable application API, a Metal
backend for arm64 macOS and a Vulkan backend for x64 Windows. It opens devices,
attaches a surface to a standard `window`, owns textures, and records colored
triangles, coverage masks and image draws into scoped drawing regions that end on
the screen or in a texture. All implementation code is Base calling system APIs
directly. There is no SDL dependency or C/Objective-C implementation shim.

Client fragment shaders are written once in GLSL and embedded for both
backends; compute is a subsequent increment. The API remains provisional while
those contracts are exercised.

## Run the example

```sh
./build/luce-base build tests/programs/gpu/main.lucb -o build/gpu-window
./build/gpu-window
```

The default native compiler produces the executable. It displays a blue window;
Escape or the close button exits. The complete event loop is in the example.
The graphics setup itself is:

```luce
import gpu
import window

var device = try gpu.Device.open()
defer device.destroy()
var target = try window.Window.open(window.Options(title = "Luce GPU"))
defer target.destroy()
var surface = try gpu.Surface.open(device, target)
defer surface.destroy()
try target.show()
discard(try surface.clear_present(gpu.Color(red = 0.025, green = 0.06, blue = 0.15)))
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
| `Surface.open(device, window)` | Creates one exclusive presentation surface for the window. A second attachment returns `window.presentation_in_use`. |
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
discard(try frame.value().present())
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

The files under `src/luce_gpu/gpu/` share one standard module scope:

| Files | Responsibility |
| --- | --- |
| `module.lucb` | Portable values, errors, validation, and thread policy. |
| `device.lucb`, `surface.lucb`, `frame.lucb`, `texture.lucb`, `shader.lucb` | Public ownership, device references, window leases, textures, shaders, pipelines, and API contracts. |
| `shaders/`, `shaders.lucb` | The vertex stage (Vulkan) and built-in fill fragment in GLSL, and the module `tools/embed_shaders.py` generates from them for both backends. |
| `params.lucb`, `canvas.lucb`, `mask.lucb` | The recorded command list and the 48-byte per-draw parameters both shaders read. |
| `backend.lucb` | Backend selection and device dispatch using opaque device payloads. |
| `presentation.lucb`, `resources.lucb` | Surface and texture dispatch using opaque payloads; a device alone never reaches them. |
| `metal/objc.lucb` | Exact typed system ABI declarations, including native aggregates. |
| `metal/device.lucb` | Metal device and queue creation and release. |
| `metal/drawing.lucb` | The vertex library, the built-in fill pipeline per color format, client libraries and pipelines, samplers, depth state and the shared render pass. |
| `metal/texture.lucb` | Private textures, blit uploads and readbacks, offscreen passes. |
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
LUCE_TEST_GPU=required LUCE_TEST_WINDOW=required tests/programs/gpu/check.sh
LUCE_TEST_WINDOW=required tests/programs/native_window/check.sh
```

The GPU suite runs native optimization levels 0–3 and C debug/release comparisons.
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
1,048,576 vertices and 4,096 draws; failed growth preserves its recorded contents.
`clear` retains capacity; `destroy` releases it.

The built-in pipeline's fragment stage is written once in GLSL
(`shaders/fill.frag`) and embedded for both backends by
`tools/embed_shaders.py`: SPIR-V words for Vulkan and Metal Shading Language
cross-compiled from them by spirv-cross. The vertex stage is per backend (they
disagree on clip-space Y): `shaders/quad.vert` for Vulkan and a Metal source in
`metal/drawing.lucb`. Fragments emit premultiplied color and blend with One /
OneMinusSourceAlpha, so vertex colors, coverage masks and textures all
composite the same way. Application transforms are computed before recording.
Packages depend only on `gpu`, so both backends serve the same drawing code.

Pixel tests additionally cover depth occlusion, clipping, linear alpha blending,
resize of depth storage, and releasing CPU commands before GPU completion.

## Textures and offscreen frames

`Texture.create(device, width, height, format)` allocates a texture of one of
four tightly packed, top-down, straight-alpha formats: `rgba8` (sRGB-encoded,
sampled as linear light), `rgba8_linear`, `rgba16_float` and `r8` (samples as
red with alpha one). Dimensions are 1..16384. `upload(pixels, region?)` replaces
a region from CPU bytes and `read(pixels, region?)` copies one back; both wait
for the copy and are ordered after earlier submissions, so `read` after a frame
sees that frame. Pixel lengths must equal the region's texels times
`texel_bytes(format)`, or `invalid_pixels` is returned.

`texture.frame()` begins a recording frame whose target is the texture (points
equal texels). Its `present(color)` clears to `color` — alpha included — draws,
waits for completion and returns `submitted`; the texture can then be read or
sampled. A frame cannot sample the texture it renders into (`invalid_geometry`),
and a texture sampled by a frame must belong to the frame's device
(`wrong_device`).

`draw_image(target, texture, rectangle, source?, opacity, filter)` draws a texel
region scaled onto a rectangle of a `RenderTarget`, clipped like every other
draw, with `nearest` or `linear` sampling. `device_of(target)` returns an owned
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
a shader changes; the generated module is checked in.

```glsl
#version 450
layout(location = 0) in vec4 vertex_color;      // the draw's color
layout(location = 0) out vec4 fragment_color;   // premultiplied
layout(push_constant) uniform Params { ... } params;   // up to 128 bytes
layout(set = 0, binding = 1) uniform sampler2D first;  // bindings 1..4
```

`gl_FragCoord` is in backing pixels of the target. Binding 5 is reserved for
the built-in coverage buffer.

`Shader.create(device, words, msl)` compiles the program (`invalid_shader` when
either form is rejected). `Pipeline.create(device, shader, blend, format?)`
binds it to a `Blend` — `over` (One / OneMinusSourceAlpha), `replace` (no
blending) or `add` (One / One) — and a target: a texture `Format`, or `none`
for presentation surfaces. `shade(target, pipeline, rectangle, uniforms?,
images?, filter, color)` draws a rectangle of a `RenderTarget` with it: the
uniform bytes fill the push-constant block (zero-padded to 128; Metal binds the
whole block since a padded struct may be larger than the bytes given), the
images sample at bindings 1.. with `filter`, and `color` is the vertex color.
A pipeline recorded into a frame of another target format is refused at
`present` with `wrong_target`; one from another device with `wrong_device`.
Shaders and pipelines are manual Base resources like textures, and a draw
keeps them alive until its canvas is cleared.

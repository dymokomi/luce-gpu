#version 450
// The vertex stage of `shade_quads`: one quad per instance, a triangle strip of
// four corners, pulled from a buffer a compute pass may have written. Record r
// is `stride` vec4s at r * stride: the clip-space center (x, y, z, w; y up, as
// ordinary vertices are), the two half axes in clip units (a.xy, b.xy, already
// multiplied by w), then up to three vec4s its fragments read flat at
// locations 1..3. Instance i draws record i, or record order[i] with an order.
// Location 0 carries the corner's quad coordinates (u, v) in -1..1, with z 0
// and w 1, interpolated across the quad.
layout(std430, binding = 6) readonly buffer Records { vec4 records[]; };
layout(std430, binding = 7) readonly buffer Parameters {
    vec4 control;  // stride in vec4s, data vec4s, 1 with an order, clip-space Y sign
} p;
layout(std430, binding = 8) readonly buffer Order { uint order[]; };
layout(location = 0) out vec4 vertex_color;
layout(location = 1) flat out vec4 data0;
layout(location = 2) flat out vec4 data1;
layout(location = 3) flat out vec4 data2;

void main() {
    uint instance = uint(gl_InstanceIndex);
    uint record = instance;
    if (p.control.z > 0.5) record = order[instance];
    uint stride = uint(p.control.x);
    uint data = uint(p.control.y);
    uint base = record * stride;
    vec4 center = records[base];
    vec4 axes = records[base + 1u];
    // Strip corners: (-1, -1), (1, -1), (-1, 1), (1, 1).
    uint corner = uint(gl_VertexIndex) & 3u;
    vec2 uv = vec2((corner & 1u) != 0u ? 1.0 : -1.0, (corner & 2u) != 0u ? 1.0 : -1.0);
    vec4 position = center;
    position.xy += uv.x * axes.xy + uv.y * axes.zw;
    position.y *= p.control.w;
    gl_Position = position;
    vertex_color = vec4(uv, 0.0, 1.0);
    // Branches, not selects: a record's data past `data` may lie past the buffer.
    data0 = vec4(0.0);
    data1 = vec4(0.0);
    data2 = vec4(0.0);
    if (data > 0u) data0 = records[base + 2u];
    if (data > 1u) data1 = records[base + 3u];
    if (data > 2u) data2 = records[base + 4u];
}

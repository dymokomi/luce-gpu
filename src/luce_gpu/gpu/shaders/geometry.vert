#version 450
// World-space triangle vertices or pairs of line endpoints, uploaded once.
struct Vertex { vec4 position; vec4 color; };
layout(std430, binding = 6) readonly buffer Geometry { Vertex vertices[]; };
layout(std430, binding = 7) readonly buffer Parameters {
    mat4 matrix;
    vec4 tint;
    vec4 control; // width (0 for triangles), logical viewport width/height, Y sign
    vec4 extra;   // depth bias
} p;
layout(location = 0) out vec4 vertex_color;
bool clip_plane(inout vec4 a, inout vec4 b, float da, float db) {
    if (da < 0.0 && db < 0.0) return false;
    if (da < 0.0) a = mix(a, b, da / (da - db));
    else if (db < 0.0) b = mix(b, a, db / (db - da));
    return true;
}
void main() {
    uint id = uint(gl_VertexIndex);
    if (p.control.x == 0.0) {
        Vertex v = vertices[id];
        gl_Position = p.matrix * v.position;
        vertex_color = v.color;
    } else {
        Vertex v = vertices[id / 6u];
        vec4 a = p.matrix * vec4(v.position.xyz, 1.0);
        vec4 b = p.matrix * vec4(v.color.xyz, 1.0);
        bool shown = clip_plane(a, b, a.z, b.z);
        shown = shown && clip_plane(a, b, a.w - a.z, b.w - b.z);
        vec2 delta = (b.xy / max(b.w, 1e-20) - a.xy / max(a.w, 1e-20)) * p.control.yz;
        float len = length(delta);
        if (!shown || len < 1e-6) {
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        } else {
            uint corner = id % 6u;
            bool end = corner == 1u || corner == 2u || corner == 4u;
            float side = corner == 0u || corner == 1u || corner == 3u ? 1.0 : -1.0;
            gl_Position = end ? b : a;
            gl_Position.xy += side * vec2(-delta.y, delta.x) / len * p.control.x / p.control.yz * gl_Position.w;
            gl_Position.z -= p.extra.x * gl_Position.w;
        }
        vertex_color = p.tint;
    }
    gl_Position.y *= p.control.w;
}

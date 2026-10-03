#version 450
#extension GL_GOOGLE_include_directive : require
// Constant-pixel-width wires pulled from point pairs and positions: six
// vertices per edge, clipped at the near and far planes. Nothing is baked on
// the CPU, so a moved mesh redraws its wires from the new positions.
#include "mesh.glsl"
layout(location = 0) out vec4 vertex_color;
layout(location = 1) out vec3 world_normal;
layout(location = 2) out vec3 world_position;
layout(location = 3) flat out uint face_id;

bool clip_plane(inout vec4 a, inout vec4 b, float da, float db) {
    if (da < 0.0 && db < 0.0) return false;
    if (da < 0.0) a = mix(a, b, da / (da - db));
    else if (db < 0.0) b = mix(b, a, db / (db - da));
    return true;
}

void main() {
    uint id = uint(gl_VertexIndex);
    uint edge = id / 6u;
    vec3 pa = point_at(triangles[edge * 2u]);
    vec3 pb = point_at(triangles[edge * 2u + 1u]);
    vec4 a = p.clip * vec4(pa, 1.0);
    vec4 b = p.clip * vec4(pb, 1.0);
    bool shown = clip_plane(a, b, a.z, b.z);
    shown = shown && clip_plane(a, b, a.w - a.z, b.w - b.z);
    vec2 delta = (b.xy / max(b.w, 1e-20) - a.xy / max(a.w, 1e-20)) * p.line.yz;
    float len = length(delta);
    if (!shown || len < 1e-6) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    } else {
        uint corner = id % 6u;
        bool end = corner == 1u || corner == 2u || corner == 4u;
        float side = corner == 0u || corner == 1u || corner == 3u ? 1.0 : -1.0;
        gl_Position = end ? b : a;
        gl_Position.xy += side * vec2(-delta.y, delta.x) / len * p.line.x / p.line.yz * gl_Position.w;
        gl_Position.z -= p.line.w * gl_Position.w;
    }
    gl_Position.y *= p.eye.w;
    vertex_color = vec4(p.tint.rgb, 0.0);
    world_normal = vec3(0.0);
    world_position = pa;
    face_id = edge;
}

#version 450
#extension GL_GOOGLE_include_directive : require
// Vertex pulling for indexed meshes: triangle corner -> point -> position, and
// the normal and color of whichever domain carries them. Every mode shades per
// fragment; the vertex color is the unlit base, its alpha the selection
// accent's weight.
#include "mesh.glsl"
layout(location = 0) out vec4 vertex_color;
layout(location = 1) out vec3 world_normal;
layout(location = 2) out vec3 world_position;
layout(location = 3) flat out uint face_id;

vec3 normal_at(uint index) {
    return vec3(normals[index * 3u], normals[index * 3u + 1u], normals[index * 3u + 2u]);
}

vec3 color_at(uint index) {
    return vec3(colors[index * 3u], colors[index * 3u + 1u], colors[index * 3u + 2u]);
}

// The element of `domain` (0 point, 1 corner, 2 face, 3 detail) this vertex reads.
uint element(int domain, uint point, uint corner, uint face) {
    return domain == 0 ? point : (domain == 1 ? corner : (domain == 2 ? face : 0u));
}

void main() {
    uint id = uint(gl_VertexIndex);
    uint triangle = id / 3u;
    uint corner = triangles[id];
    uint point = corner_points[corner];
    uint face = triangle_faces[triangle];
    vec3 local = point_at(point);
    vec3 a = point_at(corner_points[triangles[triangle * 3u]]);
    vec3 b = point_at(corner_points[triangles[triangle * 3u + 1u]]);
    vec3 c = point_at(corner_points[triangles[triangle * 3u + 2u]]);
    vec3 n = cross(b - a, c - a);
    int shading = int(p.mode.x);
    int normal_domain = int(p.mode.y);
    if (shading != shade_flat && normal_domain >= 0) {
        vec3 supplied = normal_at(element(normal_domain, point, corner, face));
        if (dot(supplied, supplied) > 1e-18) n = supplied;
    }
    vec3 wn = (p.normal_matrix * vec4(n, 0.0)).xyz;
    float wl = length(wn);
    wn = wl > 1e-30 ? wn / wl : vec3(0.0);
    vec3 base = vec3(1.0);
    int color_domain = int(p.mode.z);
    if (color_domain >= 0) base = clamp(color_at(element(color_domain, point, corner, face)), 0.0, 1.0);
    float accent = 0.0;
    if (p.accent.w > 0.0 && ((face_flags[face / 32u] >> (face % 32u)) & 1u) != 0u)
        accent = p.accent.w;
    vertex_color = vec4(p.tint.rgb * base, accent);
    world_normal = wn;
    world_position = (p.world * vec4(local, 1.0)).xyz;
    face_id = face;
    gl_Position = p.clip * vec4(local, 1.0);
    gl_Position.y *= p.eye.w;
}

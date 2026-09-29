#version 450
#extension GL_GOOGLE_include_directive : require
// Mesh fragments: Lambert lighting of the vertex stage's base color, lit on
// the side facing the eye (inside-out and open meshes light on both sides),
// or an analysis mode. Zebra reflects stripes of an infinite cylinder (or plane) around the model
// in the surface, so tangent and curvature breaks show as kinks and jumps;
// isophotes are lines of equal N . axis. Stripes are antialiased with fwidth
// over a band a little wider than a pixel, and fade to their mean as they
// approach a third of a pixel (dense stripes on bumpy surfaces would alias).
#include "mesh.glsl"
layout(location = 0) in vec4 vertex_color;
layout(location = 1) in vec3 world_normal;
layout(location = 2) in vec3 world_position;
layout(location = 0) out vec4 fragment_color;

const float tau = 6.283185307179586;

float stripe(float x, float duty) {
    float s = fract(x);
    float w = fwidth(x) * 1.5;
    float rising = smoothstep(duty - w, duty + w, s) * (1.0 - smoothstep(1.0 - w, 1.0 + w, s));
    float value = rising + (1.0 - smoothstep(-w, w, s));
    return mix(clamp(value, 0.0, 1.0), 1.0 - duty, clamp((w - 0.3) * 4.0, 0.0, 1.0));
}

void main() {
    int shading = int(p.mode.x);
    vec3 base = vertex_color.rgb;
    if (shading == shade_unlit || ((shading == shade_lit || shading == shade_flat) && p.tint.a < 0.5)) {
        fragment_color = vec4(mix(base, p.accent.rgb, vertex_color.a), 1.0);
        return;
    }
    vec3 n = world_normal;
    float nl = length(n);
    n = nl > 1e-30 ? n / nl : vec3(0.0, 1.0, 0.0);
    vec3 view = p.eye.xyz - world_position;
    float vl = length(view);
    view = vl > 1e-30 ? view / vl : vec3(0.0, 0.0, 1.0);
    // Two-sided: shade the side facing the eye.
    if (dot(n, view) < 0.0) n = -n;
    if (shading == shade_lit || shading == shade_flat) {
        vec3 light = p.ambient.rgb;
        for (int at = 0; at < 4; at++) {
            if (p.light_direction[at].w > 0.5)
                light += p.light_color[at].rgb * max(0.0, dot(n, p.light_direction[at].xyz));
        }
        fragment_color = vec4(mix(min(vec3(1.0), base * light), p.accent.rgb, vertex_color.a), 1.0);
        return;
    }
    if (shading == shade_normals) {
        fragment_color = vec4(n * 0.5 + 0.5, 1.0);
        return;
    }
    vec3 axis = normalize(p.zebra_axis.xyz);
    vec3 direction = shading == shade_zebra ? reflect(-view, n) : n;
    float t;
    if (shading == shade_zebra && p.zebra.z < 0.5) {
        vec3 helper = abs(axis.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
        vec3 u = normalize(cross(axis, helper));
        vec3 v = cross(axis, u);
        t = atan(dot(direction, u), dot(direction, v)) / tau;
    } else {
        t = dot(direction, axis) * 0.5;
    }
    float light = stripe(t * p.zebra.x, p.zebra.y);
    vec3 color = mix(p.zebra_dark.rgb, p.zebra_light.rgb, light);
    if (p.zebra.w < 0.5 && p.light_direction[0].w > 0.5)
        color *= 0.85 + 0.15 * max(0.0, dot(n, p.light_direction[0].xyz));
    fragment_color = vec4(color, 1.0);
}

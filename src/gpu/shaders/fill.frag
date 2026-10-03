// The built-in fragment: vertex color, optionally multiplied by a coverage
// image (mode 1) or a sampled texture (mode 2). Emits premultiplied color.
// Modes 3 and 4 copy a texture instead: mode 3 emits each sample as stored,
// mode 4 a premultiplied sample made straight.
// Bindings follow the client contract in docs/GPU.md: uniforms are the push
// constant block, sampled images are bindings 1..4, and the coverage words
// are binding 5, which client shaders never use.
#version 450
layout(location = 0) in vec4 vertex_color;
layout(location = 0) out vec4 fragment_color;
layout(push_constant) uniform Params {
    float x, y, width, height;
    uint columns, rows, offset, mode;
    float u0, v0, u1, v1;
} params;
layout(set = 0, binding = 1) uniform sampler2D image;
layout(set = 0, binding = 5, std430) readonly buffer Coverage { uint data[]; };
float coverage(ivec2 p) {
    p = clamp(p, ivec2(0), ivec2(params.columns - 1, params.rows - 1));
    uint i = params.offset + uint(p.y) * params.columns + uint(p.x);
    return float((data[i / 4] >> ((i % 4) * 8)) & 255u) / 255.0;
}
void main() {
    vec4 c = vertex_color;
    vec2 p = (gl_FragCoord.xy - vec2(params.x, params.y)) / vec2(params.width, params.height);
    if (params.mode == 1u) {
        vec2 q = p * vec2(params.columns, params.rows) - 0.5;
        ivec2 i = ivec2(floor(q));
        vec2 f = fract(q);
        c.a *= mix(mix(coverage(i), coverage(i + ivec2(1, 0)), f.x),
                   mix(coverage(i + ivec2(0, 1)), coverage(i + ivec2(1, 1)), f.x), f.y);
    } else if (params.mode == 2u) {
        c *= texture(image, mix(vec2(params.u0, params.v0), vec2(params.u1, params.v1), p));
    } else if (params.mode >= 3u) {
        vec4 t = texture(image, mix(vec2(params.u0, params.v0), vec2(params.u1, params.v1), p));
        fragment_color = params.mode == 3u ? t : vec4(t.a > 0.0 ? t.rgb / t.a : vec3(0.0), t.a);
        return;
    }
    fragment_color = vec4(c.rgb * c.a, c.a);
}

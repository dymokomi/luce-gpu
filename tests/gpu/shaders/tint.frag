// Test fragment: the vertex color times a uniform tint, times image 1 sampled
// across the rectangle, plus image 2's red channel as a uniform-scaled offset.
#version 450
layout(location = 0) in vec4 vertex_color;
layout(location = 0) out vec4 fragment_color;
layout(push_constant) uniform Params { vec4 tint; vec4 rectangle; float offset_scale; } params;
layout(set = 0, binding = 1) uniform sampler2D first;
layout(set = 0, binding = 2) uniform sampler2D second;
void main() {
    vec2 p = (gl_FragCoord.xy - params.rectangle.xy) / params.rectangle.zw;
    vec4 c = vertex_color * params.tint * texture(first, p);
    c.r += texture(second, p).r * params.offset_scale;
    fragment_color = vec4(c.rgb * c.a, c.a);
}

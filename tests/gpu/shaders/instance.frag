// An instanced rectangle's color: data0 (straight rgb, alpha), times data1.x,
// times the uniform scale; plain `shade` hands zeros, so it draws nothing but
// the vertex color's alpha times `base`.
#version 450
layout(location = 0) in vec4 vertex_color;
layout(location = 1) flat in vec4 data0;
layout(location = 2) flat in vec4 data1;
layout(location = 3) flat in vec4 data2;
layout(location = 0) out vec4 fragment_color;
layout(push_constant) uniform Params {
    float scale;
    float base;
} params;
void main() {
    vec4 c = data0 * data1.x * params.scale + data2 + vec4(0.0, 0.0, params.base, params.base) * vertex_color.a;
    fragment_color = vec4(c.rgb * c.a, c.a);
}

// A shade_quads fragment: data0's straight color, premultiplied; or, with
// `show_uv`, the quad coordinates mapped from -1..1 to 0..1 in red and green.
// data1 carries a second color for quads that set it (blue added), checking
// the vertex stage passes every data vec4 a record holds.
#version 450
layout(location = 0) in vec4 vertex_color;
layout(location = 1) flat in vec4 data0;
layout(location = 2) flat in vec4 data1;
layout(location = 3) flat in vec4 data2;
layout(location = 0) out vec4 fragment_color;
layout(push_constant) uniform Params {
    float show_uv;
} params;
void main() {
    if (params.show_uv > 0.5) {
        fragment_color = vec4(vertex_color.x * 0.5 + 0.5, vertex_color.y * 0.5 + 0.5, data2.x, 1.0);
        return;
    }
    vec4 c = data0 + vec4(0.0, 0.0, data1.b, 0.0);
    fragment_color = vec4(c.rgb * c.a, c.a);
}

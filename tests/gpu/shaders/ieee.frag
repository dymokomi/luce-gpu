#version 450
// IEEE float rules in a fragment shader: red is 1 when 0/0 is a NaN, green when
// 1/0 is an infinity, blue when an infinity orders above every float. The
// zero comes from the push constants, so nothing folds at compile time.
layout(location = 0) in vec4 vertex_color;
layout(location = 0) out vec4 fragment_color;
layout(push_constant) uniform Params { float zero; float one; } params;

void main() {
    float nan = params.zero / params.zero;
    float infinity = params.one / params.zero;
    fragment_color = vec4(isnan(nan) ? 1.0 : 0.0, isinf(infinity) ? 1.0 : 0.0, max(infinity, 3.0e38) > 3.0e38 ? 1.0 : 0.0, 1.0);
}

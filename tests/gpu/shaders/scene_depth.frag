// Test fragment: the scene depth at the fragment's pixel (binding 4) times a
// uniform mask, opaque.
#version 450
layout(location = 0) in vec4 vertex_color;
layout(location = 0) out vec4 fragment_color;
layout(push_constant) uniform Params { vec4 mask; } params;
layout(set = 0, binding = 4) uniform sampler2D scene_depth;
void main() {
    float depth = texelFetch(scene_depth, ivec2(gl_FragCoord.xy), 0).r;
    fragment_color = vec4(params.mask.rgb * depth, 1.0);
}

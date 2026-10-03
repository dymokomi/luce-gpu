#version 450
#extension GL_GOOGLE_include_directive : require
// Face identities for GPU picking: the draw's id base plus the face, plus one
// (zero is "nothing"), packed little-endian into an rgba8_linear target.
#include "mesh.glsl"
layout(location = 3) flat in uint face_id;
layout(location = 0) out vec4 fragment_color;

void main() {
    uint id = floatBitsToUint(p.mode.w) + face_id + 1u;
    fragment_color = vec4(float(id & 255u), float((id >> 8u) & 255u), float((id >> 16u) & 255u), float(id >> 24u)) / 255.0;
}

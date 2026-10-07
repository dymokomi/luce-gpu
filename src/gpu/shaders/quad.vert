// The vertex stage of ordinary draws: a clip-space position and a straight
// color per vertex. Locations 1..3 are what an instanced draw hands its
// fragment stage (shaders/instance.vert); here they are zero, so one fragment
// program serves both `shade` and `shade_instances`.
#version 450
layout(location = 0) in vec4 position;
layout(location = 1) in vec4 color;
layout(location = 0) out vec4 vertex_color;
layout(location = 1) flat out vec4 data0;
layout(location = 2) flat out vec4 data1;
layout(location = 3) flat out vec4 data2;
void main() {
    gl_Position = vec4(position.x, -position.y, position.z, position.w);
    vertex_color = color;
    data0 = vec4(0.0);
    data1 = vec4(0.0);
    data2 = vec4(0.0);
}

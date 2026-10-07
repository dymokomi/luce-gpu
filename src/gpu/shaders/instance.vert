// The vertex stage of `shade_instances`: one rectangle per instance, as two
// triangles of six vertices. `rect` is the rectangle in clip space (left, top,
// right, bottom, y up, as the ordinary vertices are); its twelve floats reach
// the fragment stage flat at locations 1..3, and the color at location 0 is
// opaque white.
#version 450
layout(location = 0) in vec4 rect;
layout(location = 1) in vec4 instance0;
layout(location = 2) in vec4 instance1;
layout(location = 3) in vec4 instance2;
layout(location = 0) out vec4 vertex_color;
layout(location = 1) flat out vec4 data0;
layout(location = 2) flat out vec4 data1;
layout(location = 3) flat out vec4 data2;
void main() {
    // Corners of the triangles (0, 1, 2) and (0, 2, 3): top left, top right,
    // bottom right, bottom left.
    int corner = gl_VertexIndex == 3 ? 0 : (gl_VertexIndex == 4 ? 2 : (gl_VertexIndex == 5 ? 3 : gl_VertexIndex));
    float x = corner == 1 || corner == 2 ? rect.z : rect.x;
    float y = corner >= 2 ? rect.w : rect.y;
    gl_Position = vec4(x, -y, 0.0, 1.0);
    vertex_color = vec4(1.0);
    data0 = instance0;
    data1 = instance1;
    data2 = instance2;
}

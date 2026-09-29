// The mesh draw contract of luce-gpu's mesh shaders (gpu/mesh.lucb): indexed
// arrays pulled from storage buffers at bindings 8..14, and one parameter
// block at 15 read by both stages. Keep mesh.lucb's parameter offsets in step.
layout(std430, binding = 8) readonly buffer Triangles { uint triangles[]; };   // wires: point pairs
layout(std430, binding = 9) readonly buffer Corners { uint corner_points[]; };
layout(std430, binding = 10) readonly buffer Positions { float positions[]; };
layout(std430, binding = 11) readonly buffer Normals { float normals[]; };
layout(std430, binding = 12) readonly buffer Colors { float colors[]; };
layout(std430, binding = 13) readonly buffer Faces { uint triangle_faces[]; };
layout(std430, binding = 14) readonly buffer Flags { uint face_flags[]; };
layout(std430, binding = 15) readonly buffer Parameters {
    mat4 clip;               // object to clip space
    mat4 world;              // object to world
    mat4 normal_matrix;      // object to world for normals: the inverse transpose
    vec4 tint;               // rgb; a > 0.5: lit
    vec4 ambient;            // rgb, the ambient lights' sum
    vec4 light_direction[4]; // xyz toward the light; w > 0.5: present
    vec4 light_color[4];     // rgb times intensity
    vec4 eye;                // xyz world eye; w: clip-space y sign
    vec4 mode;               // x shading; y normal domain; z color domain; w id base (bits)
    vec4 zebra;              // x stripes; y duty; z model (0 cylinder, 1 planar); w > 0.5: stripes only
    vec4 zebra_axis;         // xyz world stripe axis
    vec4 zebra_dark;         // rgb
    vec4 zebra_light;        // rgb
    vec4 line;               // x wire width in pixels; y, z logical viewport size; w depth bias
    vec4 accent;             // rgb selection highlight; w > 0: flagged faces take it
} p;

// Shading modes (mode.x).
const int shade_lit = 0;
const int shade_flat = 1;
const int shade_zebra = 2;
const int shade_isophote = 3;
const int shade_normals = 4;
const int shade_unlit = 5;

vec3 point_at(uint point) {
    return vec3(positions[point * 3u], positions[point * 3u + 1u], positions[point * 3u + 2u]);
}

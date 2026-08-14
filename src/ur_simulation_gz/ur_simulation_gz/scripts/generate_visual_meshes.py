"""Generate simple STL meshes for robot visual upgrades.

Keeps collision geometry untouched in xacro files; only visual is replaced.
All meshes are exported in ASCII STL (universal, no extra deps).

Meshes produced:
  torso_shell.stl       — rounded cylinder (M7.1 torso)
  head_shell.stl        — rounded box (M7.1 head)
  head_camera_lens.stl  — lens barrel + glass
  head_camera_window.stl — camera front window plate
  chassis_shell.stl     — rounded box (mobile base chassis)
  arm_pillar_shell.stl  — rounded cylinder (arm mounting pillar)
  head_display.stl      — screen panel (M7 Stage 3)
"""
import os
import math
from typing import List, Tuple

Vec3 = Tuple[float, float, float]


def write_ascii_stl(path: str, name: str, triangles: List[Tuple[Vec3, Vec3, Vec3, Vec3]]) -> None:
    """Write an ASCII STL file. triangles = list of (normal, v1, v2, v3)."""
    with open(path, "w") as f:
        f.write(f"solid {name}\n")
        for n, a, b, c in triangles:
            f.write(f"  facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
            f.write("    outer loop\n")
            for v in (a, b, c):
                f.write(f"      vertex {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {name}\n")


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def normalize(v: Vec3) -> Vec3:
    m = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if m == 0:
        return (0.0, 0.0, 1.0)
    return (v[0] / m, v[1] / m, v[2] / m)


def tri(a: Vec3, b: Vec3, c: Vec3) -> Tuple[Vec3, Vec3, Vec3, Vec3]:
    n = normalize(cross(sub(b, a), sub(c, a)))
    return (n, a, b, c)


def quad(a: Vec3, b: Vec3, c: Vec3, d: Vec3, tris: List) -> None:
    tris.append(tri(a, b, c))
    tris.append(tri(a, c, d))


def gen_cylinder(
    radius: float,
    height: float,
    segments: int = 32,
    capped: bool = True,
) -> List:
    """Generate a cylinder mesh centered at origin, axis = Z."""
    tris: List = []
    h = height / 2.0
    if capped:
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            p0 = (radius * math.cos(a0), radius * math.sin(a0), h)
            p1 = (radius * math.cos(a1), radius * math.sin(a1), h)
            p2 = (radius * math.cos(a1), radius * math.sin(a1), -h)
            p3 = (radius * math.cos(a0), radius * math.sin(a0), -h)
            quad(p0, p1, p2, p3, tris)
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            top_a = (radius * math.cos(a0), radius * math.sin(a0), h)
            top_b = (radius * math.cos(a1), radius * math.sin(a1), h)
            tris.append(tri((0, 0, h), top_a, top_b))
            bot_a = (radius * math.cos(a1), radius * math.sin(a1), -h)
            bot_b = (radius * math.cos(a0), radius * math.sin(a0), -h)
            tris.append(tri((0, 0, -h), bot_a, bot_b))
    return tris


def gen_box(size_x: float, size_y: float, size_z: float) -> List:
    """Generate a box mesh centered at origin."""
    hx, hy, hz = size_x / 2.0, size_y / 2.0, size_z / 2.0
    v = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    faces = [
        (0, 1, 2, 3), (4, 7, 6, 5),
        (0, 4, 5, 1), (1, 5, 6, 2),
        (2, 6, 7, 3), (3, 7, 4, 0),
    ]
    tris: List = []
    for f in faces:
        quad(v[f[0]], v[f[1]], v[f[2]], v[f[3]], tris)
    return tris


def gen_torus(r_major: float, r_minor: float, segments: int = 24, tube_segments: int = 12) -> List:
    """Torus in XY plane (axis Z)."""
    tris: List = []
    for i in range(segments):
        theta0 = 2 * math.pi * i / segments
        theta1 = 2 * math.pi * (i + 1) / segments
        for j in range(tube_segments):
            phi0 = 2 * math.pi * j / tube_segments
            phi1 = 2 * math.pi * (j + 1) / tube_segments
            p = lambda th, ph: (
                (r_major + r_minor * math.cos(ph)) * math.cos(th),
                (r_major + r_minor * math.cos(ph)) * math.sin(th),
                r_minor * math.sin(ph),
            )
            p00 = p(theta0, phi0)
            p10 = p(theta1, phi0)
            p11 = p(theta1, phi1)
            p01 = p(theta0, phi1)
            quad(p00, p10, p11, p01, tris)
    return tris


def build_torso_shell() -> List:
    """Industrial robot waist: trapezoidal (wider bottom, narrower top)."""
    tris: List = []
    bottom_r = 0.18
    top_r = 0.13
    height = 0.5
    segments = 36
    h = height / 2.0
    for i in range(segments):
        a0 = 2 * math.pi * i / segments
        a1 = 2 * math.pi * (i + 1) / segments
        b0 = (bottom_r * math.cos(a0), bottom_r * math.sin(a0), -h)
        b1 = (bottom_r * math.cos(a1), bottom_r * math.sin(a1), -h)
        t0 = (top_r * math.cos(a0), top_r * math.sin(a0), h)
        t1 = (top_r * math.cos(a1), top_r * math.sin(a1), h)
        quad(b0, b1, t1, t0, tris)
    for i in range(segments):
        a0 = 2 * math.pi * i / segments
        a1 = 2 * math.pi * (i + 1) / segments
        tris.append(tri(
            (0, 0, h),
            (top_r * math.cos(a0), top_r * math.sin(a0), h),
            (top_r * math.cos(a1), top_r * math.sin(a1), h),
        ))
        tris.append(tri(
            (0, 0, -h),
            (bottom_r * math.cos(a1), bottom_r * math.sin(a1), -h),
            (bottom_r * math.cos(a0), bottom_r * math.sin(a0), -h),
        ))
    return tris


def build_head_shell() -> List:
    """Rounded box, taller than wide, with front camera window indent."""
    tris: List = []
    sx, sy, sz = 0.14, 0.20, 0.12
    tris.extend(gen_box(sx, sy, sz))
    return tris


def build_head_camera_lens() -> List:
    """Camera lens: short cylinder + front glass disc."""
    tris: List = []
    r = 0.025
    seg = 24
    h_back = 0.015
    h_front = 0.025
    for i in range(seg):
        a0 = 2 * math.pi * i / seg
        a1 = 2 * math.pi * (i + 1) / seg
        b0 = (r * math.cos(a0), r * math.sin(a0), 0)
        b1 = (r * math.cos(a1), r * math.sin(a1), 0)
        f0 = (r * math.cos(a0), r * math.sin(a0), h_front)
        f1 = (r * math.cos(a1), r * math.sin(a1), h_front)
        quad(b0, b1, f1, f0, tris)
    for i in range(seg):
        a0 = 2 * math.pi * i / seg
        a1 = 2 * math.pi * (i + 1) / seg
        tris.append(tri(
            (0, 0, h_front),
            (r * math.cos(a0), r * math.sin(a0), h_front),
            (r * math.cos(a1), r * math.sin(a1), h_front),
        ))
        tris.append(tri(
            (0, 0, 0),
            (r * math.cos(a1), r * math.sin(a1), 0),
            (r * math.cos(a0), r * math.sin(a0), 0),
        ))
    return tris


def build_head_camera_window() -> List:
    """Front camera window - slightly recessed dark plate."""
    return gen_box(0.08, 0.08, 0.005)


def build_chassis_shell() -> List:
    """Rounded chassis box with beveled top edges."""
    return gen_box(1.4, 0.5, 0.3)


def build_arm_pillar_shell() -> List:
    return gen_cylinder(0.08, 0.2, segments=24)


def build_head_display() -> List:
    """Front display panel for showing Runtime status."""
    return gen_box(0.10, 0.06, 0.005)


def build_status_led() -> List:
    """LED status bar (front of chassis)."""
    return gen_box(0.3, 0.03, 0.02)


def build_status_led_ring() -> List:
    """Ring LED around head camera, for state visualization."""
    return gen_torus(0.05, 0.008, segments=24, tube_segments=12)


def build_led_strip() -> List:
    """LED status strip on chassis."""
    return gen_box(0.4, 0.04, 0.015)


def main() -> None:
    out_dir = os.path.join(os.path.dirname(__file__), "..", "meshes")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    items = [
        ("torso_shell.stl", "torso_shell", build_torso_shell),
        ("head_shell.stl", "head_shell", build_head_shell),
        ("head_camera_lens.stl", "head_camera_lens", build_head_camera_lens),
        ("head_camera_window.stl", "head_camera_window", build_head_camera_window),
        ("chassis_shell.stl", "chassis_shell", build_chassis_shell),
        ("arm_pillar_shell.stl", "arm_pillar_shell", build_arm_pillar_shell),
        ("head_display.stl", "head_display", build_head_display),
        ("status_led_strip.stl", "status_led_strip", build_led_strip),
        ("head_led_ring.stl", "head_led_ring", build_status_led_ring),
    ]

    for filename, name, builder in items:
        path = os.path.join(out_dir, filename)
        tris = builder()
        write_ascii_stl(path, name, tris)
        size = os.path.getsize(path)
        print(f"  {filename:<32} {len(tris):>5} triangles  {size:>6} bytes")


if __name__ == "__main__":
    main()
"""Direct mesh construction avoids context-dependent bpy operators."""
import math
import bpy
from mathutils import Vector
from ..scene_setup import mark


def mesh_data(builder, key, vertices, faces, material):
    if key in builder.mesh_cache:
        return builder.mesh_cache[key]
    mesh = mark(bpy.data.meshes.new("GH_MESH_" + key))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(material)
    builder.mesh_cache[key] = mesh
    return mesh


def box_mesh(builder, key, dimensions, material):
    x, y, z = (d / 2 for d in dimensions)
    vertices = [(-x,-y,-z), (x,-y,-z), (x,y,-z), (-x,y,-z),
                (-x,-y,z), (x,-y,z), (x,y,z), (-x,y,z)]
    faces = [(3,2,1,0), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    return mesh_data(builder, key, vertices, faces, material)


def box(builder, name, dimensions, location, group, material, asset_type, key=None, parent=None, **props):
    mesh = box_mesh(builder, key or name, dimensions, material)
    obj = builder.object(name, mesh, group, parent, asset_type, **props)
    obj.location = location
    return obj


def tube_mesh(builder, key, points, radius, material, sides=8):
    vertices, faces = [], []
    pts = [Vector(p) for p in points]
    for i, point in enumerate(pts):
        tangent = (pts[min(i + 1, len(pts)-1)] - pts[max(0, i-1)]).normalized()
        reference = Vector((1, 0, 0)) if abs(tangent.x) < 0.9 else Vector((0, 1, 0))
        u = tangent.cross(reference).normalized()
        v = tangent.cross(u).normalized()
        for j in range(sides):
            angle = 2 * math.pi * j / sides
            vertices.append(tuple(point + radius * (math.cos(angle) * u + math.sin(angle) * v)))
    for i in range(len(pts) - 1):
        for j in range(sides):
            a, b = i*sides+j, i*sides+(j+1)%sides
            faces.append((a, b, b+sides, a+sides))
    faces.extend([tuple(reversed(range(sides))), tuple((len(pts)-1)*sides+j for j in range(sides))])
    return mesh_data(builder, key, vertices, faces, material)


def grid_surface(builder, key, xs, ys, z_func, material, skip=None):
    vertices = [(x, y, z_func(y)) for x in xs for y in ys]
    faces, stride = [], len(ys)
    for i in range(len(xs)-1):
        for j in range(len(ys)-1):
            if skip and skip((xs[i]+xs[i+1])/2, (ys[j]+ys[j+1])/2):
                continue
            a = i*stride+j
            faces.append((a, a+stride, a+stride+1, a+1))
    return mesh_data(builder, key, vertices, faces, material)

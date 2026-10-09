"""Small reusable industrial parts, all in meters; dimensions are visual approximations."""
import math
from mathutils import Vector
from .primitives import mesh_data, box
from ..asset_metadata import annotate


class MeshParts:
    """Accumulate low-poly parts into one reusable mesh with material slots."""
    def __init__(self):
        self.vertices=[]
        self.faces=[]
        self.slots=[]

    def add(self,vertices,faces,slot=0):
        base=len(self.vertices)
        self.vertices.extend(tuple(v) for v in vertices)
        self.faces.extend(tuple(base+i for i in face) for face in faces)
        self.slots.extend([slot]*len(faces))

    def box(self,center,size,slot=0):
        c=Vector(center); x,y,z=(v/2 for v in size)
        self.add([c+Vector(v) for v in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]],
                 [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],slot)

    def cylinder(self,a,b,radius,slot=0,sides=12):
        a,b=Vector(a),Vector(b)
        axis=(b-a).normalized()
        ref=Vector((0,0,1)) if abs(axis.z)<0.9 else Vector((0,1,0))
        u=axis.cross(ref).normalized(); v=axis.cross(u)
        vertices=[p+radius*(math.cos(j*2*math.pi/sides)*u+math.sin(j*2*math.pi/sides)*v) for p in (a,b) for j in range(sides)]
        faces=[(j,(j+1)%sides,(j+1)%sides+sides,j+sides) for j in range(sides)]
        faces += [tuple(reversed(range(sides))),tuple(range(sides,2*sides))]
        self.add(vertices,faces,slot)

    def sphere(self,center,radius,slot=0,sides=8,rings=4):
        c=Vector(center)
        vertices=[c+Vector((0,0,-radius))]
        for i in range(1,rings):
            lat=-math.pi/2+i*math.pi/rings
            vertices += [c+radius*Vector((math.cos(lat)*math.cos(j*2*math.pi/sides),math.cos(lat)*math.sin(j*2*math.pi/sides),math.sin(lat))) for j in range(sides)]
        top=len(vertices); vertices.append(c+Vector((0,0,radius)))
        faces=[(0,1+(j+1)%sides,1+j) for j in range(sides)]
        for i in range(rings-2):
            for j in range(sides):
                a=1+i*sides+j; b=1+i*sides+(j+1)%sides
                faces.append((a,b,b+sides,a+sides))
        faces += [(top,1+(rings-2)*sides+j,1+(rings-2)*sides+(j+1)%sides) for j in range(sides)]
        self.add(vertices,faces,slot)

    def torus_y(self,center,major,minor,segments=20,sides=6):
        c=Vector(center)
        vertices=[]
        for i in range(segments):
            a=i*math.tau/segments
            for j in range(sides):
                b=j*math.tau/sides
                vertices.append(c+Vector(((major+minor*math.cos(b))*math.cos(a),minor*math.sin(b),(major+minor*math.cos(b))*math.sin(a))))
        faces=[(i*sides+j,((i+1)%segments)*sides+j,((i+1)%segments)*sides+(j+1)%sides,i*sides+(j+1)%sides) for i in range(segments) for j in range(sides)]
        self.add(vertices,faces)

    def build(self,builder,key,materials):
        if key in builder.mesh_cache:
            return builder.mesh_cache[key]
        used=sorted(set(self.slots))
        mesh=mesh_data(builder,key,self.vertices,self.faces,materials[used[0]])
        for index in used[1:]: mesh.materials.append(materials[index])
        remap={slot:i for i,slot in enumerate(used)}
        for polygon,slot in zip(mesh.polygons,self.slots): polygon.material_index=remap[slot]
        return mesh


def assembly(builder,name,group,asset_type,location=(0,0,0),parent=None,source="drawing_supported",pages="",**props):
    obj=builder.object(name,None,group,parent,asset_type,**props)
    obj.location=location
    return annotate(obj,source,drawing_pages=pages)


def part_box(builder,name,size,location,group,material,parent,role="equipment_part"):
    key="PART_BOX_"+str(tuple(size))+"_"+material.name
    return annotate(box(builder,name,size,location,group,material,role,key=key,parent=parent))


def cylinder(builder,name,radius,length,location,group,material,parent,axis="Z",role="equipment_part",sides=12):
    key=f"CYL_{radius}_{length}_{axis}_{sides}_{material.name}"
    index="XYZ".index(axis)
    a=[0,0,0]; b=[0,0,0]; a[index]=-length/2; b[index]=length/2
    geo=MeshParts(); geo.cylinder(a,b,radius,sides=sides)
    obj=builder.object(name,geo.build(builder,key,[material]),group,parent,role)
    obj.location=location
    return annotate(obj)


def gear(builder,name,radius,thickness,location,group,material,parent,teeth=12):
    geo=MeshParts()
    # Alternating radii produce visible teeth, with the gear rotating about X.
    count=teeth*4
    vertices=[(x,(radius if j%4 in (0,3) else radius*1.22)*math.cos(j*2*math.pi/count),
                (radius if j%4 in (0,3) else radius*1.22)*math.sin(j*2*math.pi/count))
              for x in (-thickness/2,thickness/2) for j in range(count)]
    faces=[(j,(j+1)%count,(j+1)%count+count,j+count) for j in range(count)]
    faces += [tuple(reversed(range(count))),tuple(range(count,2*count))]
    geo.add(vertices,faces)
    obj=builder.object(name,geo.build(builder,f"GEAR_{radius}_{thickness}_{material.name}",[material]),group,parent,"pinion")
    obj.location=location
    return annotate(obj,drawing_pages="40")

"""Approximate windbreak and end closures; door location is an explicit placeholder."""
from .equipment_primitives import assembly, part_box
from .primitives import mesh_data
from ..geometry_math import span_bounds, span_centers, span_x_range, arch_height, roof_arch_radius
from ..asset_metadata import annotate
from ..orientation import end_positions,door_dimensions


def create_sidewalls(builder,config,mats):
    s,g=config['sidewalls'],config['greenhouse']
    if not s['enabled']: return
    length=g['length']; width=g['span_count']*g['span_width']; e=g['eave_height']['value']
    h=s['fixed_lower_wall_height']; clearance=config['side_curtains']['frame_clearance']
    for side,sign in (('LEFT',-1),('RIGHT',1)):
        group='GH_SIDEWALL_'+side
        x0,x1=span_x_range(g,1 if sign<0 else g['span_count'])
        obj=part_box(builder,group+'_FIXED',(x1-x0,0.045,h),((x0+x1)/2,sign*(width/2+clearance),h/2),group,mats['sidewall_fixed'],builder.groups[group],'sidewall_fixed')
        annotate(obj,'drawing_supported',note='Windbreak existence supported; lower height and thickness approximate',position='approximate')
        if not config['side_curtains']['enabled']:
            part_box(builder,group+'_UPPER',(x1-x0,0.018,e-h),((x0+x1)/2,sign*(width/2+clearance),(e+h)/2),group,mats['curtain'],builder.groups[group],'sidewall_closure')
    bounds=span_bounds(g['span_count'],g['span_width'])
    def front_offset(y):
        # Local x of the front plane behind X1; at a span boundary the longer span wins.
        spans=[j for j in range(1,g['span_count']+1) if bounds[j-1]-1e-9<=y<=bounds[j]+1e-9]
        return min(span_x_range(g,j)[0] for j in spans)+length/2
    door_y,door_width,door_height=door_dimensions(config)
    door_min,door_max=door_y-door_width/2,door_y+door_width/2
    for label,sign in (('FRONT',-1),('REAR',1)):
        root=assembly(builder,'GH_'+label+'_WALL','GH_SIDEWALLS','end_wall',end_positions(config)[label.lower()],source='drawing_supported',pages='6' if label=='FRONT' else '10',axis_reference='X1' if label=='FRONT' else 'X23',end_side='negative_x' if label=='FRONT' else 'positive_x')
        # Vertical strips give a true doorway aperture, avoiding coplanar door overlap.
        ys={-width/2,0,width/2}
        for center in span_centers(g['span_count'],g['span_width']):
            ys.update(center-g['span_width']/2+i*g['span_width']/g['roof']['segments_per_span'] for i in range(g['roof']['segments_per_span']+1))
        # Both ends share the doorway breaks so curved-roof sampling stays identical.
        ys.update((door_min,door_max))
        ys=sorted(ys); vertices=[]; faces=[]
        slots=[]
        def top(y):
            center=min(span_centers(g['span_count'],g['span_width']),key=lambda c:abs(c-y))
            return arch_height(y-center,g['span_width'],e,g['ridge_height']['value'],roof_arch_radius(g))
        for a,b in zip(ys,ys[1:]):
            bottom=door_height if label=='FRONT' and door_min<(a+b)/2<door_max else 0
            x=front_offset((a+b)/2) if label=='FRONT' else 0
            index=len(vertices)
            vertices += [(x,a,bottom),(x,b,bottom),(x,b,e),(x,a,e)]
            faces.append(tuple(index+i for i in range(4)))
            slots.append(0 if (a+b)/2>0 else 1)
            index=len(vertices)
            vertices += [(x,a,e),(x,b,e),(x,b,top(b)),(x,a,top(a))]
            faces.append(tuple(index+i for i in range(4))); slots.append(1)
        mesh=mesh_data(builder,label+'_CLOSURE',vertices,faces,mats['end_cladding'])
        mesh.materials.append(mats['end_windbreak'])
        for polygon,slot in zip(mesh.polygons,slots): polygon.material_index=slot
        obj=builder.object(root.name+'_SHELL',mesh,'GH_SIDEWALLS',root,'end_closure')
        annotate(obj,'drawing_supported',note='Positive Y: sandwich cladding; negative Y: windbreak; roof-height adaptation approximate',drawing_pages='6' if label=='FRONT' else '10')
        # Six nominal end-post bays per span, adapted to the provisional roof profile.
        for i in range(g['span_count']*6+1):
            y=-width/2+i*g['span_width']/6
            bottom=door_height if label=='FRONT' and door_min<y<door_max else 0
            height=top(y)-bottom
            x=front_offset(y) if label=='FRONT' else 0
            part_box(builder,f'GH_{label}_WALL_POST_{i+1:02d}',(0.06,0.045,height),(x+sign*0.04,y,bottom+height/2),'GH_SIDEWALLS',mats['frame'],root,'end_wall_post')
        # Rails break wherever the front plane steps between spans.
        steps=[b for b in bounds[1:-1] if label=='FRONT' and front_offset(b-1e-6)!=front_offset(b+1e-6)]
        for j,z in enumerate((h,e),1):
            cuts=[-width/2]+steps+[width/2]
            intervals=list(zip(cuts,cuts[1:]))
            if label=='FRONT' and z<door_height:
                intervals=[piece for a,b in intervals for piece in ((a,min(b,door_min)),(max(a,door_max),b)) if piece[1]-piece[0]>1e-9]
            for k,(a,b) in enumerate(intervals):
                x=front_offset((a+b)/2) if label=='FRONT' else 0
                part_box(builder,f'GH_{label}_WALL_RAIL_{j}_{k}',(0.06,b-a,0.045),(x+sign*0.04,(a+b)/2,z),'GH_SIDEWALLS',mats['frame'],root,'end_wall_rail')
        for y in steps:
            # The exposed side of the longer span between the two front planes.
            a,b=front_offset(y+1e-6),front_offset(y-1e-6)
            a,b=min(a,b),max(a,b)
            step=builder.object(f'GH_FRONT_STEP_WALL_Y{bounds.index(y)+1:02d}',mesh_data(builder,f'FRONT_STEP_{b-a:g}',[(a,y,0),(b,y,0),(b,y,e),(a,y,e)],[(0,1,2,3)],mats['end_windbreak']),'GH_SIDEWALLS',root,'end_closure')
            annotate(step,'drawing_supported',note='Stepped front between X1 and X3 (drawing pages 2, 4); closure material approximate',drawing_pages='2,4')
    front=next(o for o in builder.groups['GH_SIDEWALLS'].children if o.name=='GH_FRONT_WALL')
    door=assembly(builder,'GH_FRONT_DOOR','GH_SIDEWALLS','door_placeholder',(front_offset(door_y),door_y,0),front,source='drawing_supported',pages='6',geometry_confidence='approximate',axis_reference='X1')
    annotate(door,'drawing_supported',note='Approximate doorway in Y4-Y3 region of front elevation; dimensions visually estimated, not surveyed',drawing_pages='6',position='approximate')
    part_box(builder,'GH_FRONT_DOOR_PANEL',(0.045,door_width,door_height),(0,0,door_height/2),'GH_SIDEWALLS',mats['end_cladding'],door,'door_panel')
    for side in (-1,1):
        part_box(builder,'GH_FRONT_DOOR_JAMB_'+str(side),(0.09,0.06,door_height),(0,side*door_width/2,door_height/2),'GH_SIDEWALLS',mats['frame'],door)
    part_box(builder,'GH_FRONT_DOOR_HEADER',(0.09,door_width+0.06,0.06),(0,0,door_height),'GH_SIDEWALLS',mats['frame'],door)
    part_box(builder,'GH_FRONT_DOOR_CENTER_SEAM',(0.052,0.025,door_height),(0,0,door_height/2),'GH_SIDEWALLS',mats['frame'],door,'door_detail')
    for i,y in enumerate((-0.12,0.12)):
        part_box(builder,f'GH_FRONT_DOOR_HANDLE_{i}',(0.055,0.025,0.25),(-0.065,y,door_height*0.45),'GH_SIDEWALLS',mats['frame'],door,'door_detail')

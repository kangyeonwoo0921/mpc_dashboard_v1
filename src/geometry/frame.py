from .primitives import box, tube_mesh, grid_surface
from ..geometry_math import make_stations, secondary_stations, span_bounds, span_centers, span_x_range, gridline_x_start, stations_from
from ..naming import column_name


def create_frame(builder, config, mats):
    g, s = config["greenhouse"], config["structure"]
    length, width, count, height = g["length"], g["span_width"], g["span_count"], g["eave_height"]["value"]
    main = make_stations(length, s["main_column_spacing"])
    secondary = secondary_stations(length, s["secondary_column_spacing"], s["main_column_spacing"])
    boundaries = span_bounds(count, width)
    for kind, stations in (("MAIN", main), ("SECONDARY", secondary)):
        section = s[kind.lower() + "_column"]
        for j, y in enumerate(boundaries, 1):
            # Station indices stay global so a stepped footprint keeps drawing X numbering.
            for i, x in stations_from(stations, gridline_x_start(g, j)):
                box(builder, column_name(kind, i, j), (section["width"], section["depth"], height),
                    (x, y, height/2), "GH_COLUMNS_" + kind, mats["frame"], kind.lower() + "_column",
                    key=kind + "_COLUMN", station_index=i, grid_index=j)
    radius = s["visual_frame_radius"]
    truss = tube_mesh(builder, "TRUSS", [(0,-width/2,0), (0,width/2,0)], radius, mats["frame"])
    for j, y in enumerate(span_centers(count, width), 1):
        for i, x in stations_from(main, span_x_range(g, j)[0]):
            obj = builder.object(f"GH_TRUSS_X{i:03d}_S{j:02d}", truss, "GH_TRUSSES", asset_type="truss", span_index=j)
            obj.location = (x, y, height-radius)
    for j, y in enumerate(boundaries, 1):
        x0 = gridline_x_start(g, j)
        box(builder, f"GH_GUTTER_Y{j:02d}", (length/2-x0, radius*4, radius*2), ((x0+length/2)/2,y,height),
            "GH_GUTTERS", mats["frame"], "gutter", key="GUTTER" if x0==-length/2 else f"GUTTER_{x0+length/2:g}")
    # A longitudinal ridge member complements the repeated transverse rafters.
    for j, y in enumerate(span_centers(count, width), 1):
        x0, x1 = span_x_range(g, j)
        ridge = tube_mesh(builder, "RIDGE" if x0==-length/2 else f"RIDGE_{x0+length/2:g}", [(x0,0,0), (x1,0,0)], radius, mats["frame"])
        obj = builder.object(f"GH_RIDGE_S{j:02d}", ridge, "GH_ROOF_FRAME", asset_type="roof_frame", span_index=j)
        obj.location = (0,y,g["ridge_height"]["value"])


def create_ground(builder, config, mats):
    if not config["ground"]["enabled"]:
        return
    g, margin = config["greenhouse"], config["ground"]["margin"]
    lx, wy = g["length"]/2+margin, g["span_width"]*g["span_count"]/2+margin
    mesh = grid_surface(builder, "GROUND", [-lx,lx], [-wy,wy], lambda y: 0, mats["ground"])
    builder.object("GH_GROUND_PLANE", mesh, "GH_GROUND", asset_type="ground")

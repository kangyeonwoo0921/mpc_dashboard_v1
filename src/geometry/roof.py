from .primitives import tube_mesh
from ..geometry_math import generate_arch_points, make_stations, roof_arch_radius, span_centers, span_x_range, stations_from
from ..naming import rafter_name


def create_roof(builder, config, mats):
    g, s = config["greenhouse"], config["structure"]
    profile = generate_arch_points(g["span_width"], g["eave_height"]["value"], g["ridge_height"]["value"], g["roof"]["segments_per_span"], roof_arch_radius(g))
    mesh = tube_mesh(builder, "RAFTER", [(0,y,z) for y,z in profile], s["visual_frame_radius"], mats["frame"])
    stations = make_stations(g["length"], s["rafter_spacing"])
    for j, y in enumerate(span_centers(g["span_count"], g["span_width"]), 1):
        for i, x in stations_from(stations, span_x_range(g, j)[0]):
            obj = builder.object(rafter_name(i,j), mesh, "GH_RAFTERS", asset_type="rafter", span_index=j, station_index=i)
            obj.location = (x,y,0)

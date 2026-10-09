from .primitives import box
from ..geometry_math import span_centers, span_x_range, bed_y_positions
from ..naming import bed_name


def create_beds(builder, config, mats):
    beds,g = config["crop_beds"],config["greenhouse"]
    if not beds["enabled"] or not beds["rows_per_span"]:
        return
    for j,center in enumerate(span_centers(g["span_count"],g["span_width"]),1):
        x0,x1 = span_x_range(g,j)
        dimensions = (x1-x0-2*beds["length_margin"],beds["width"],beds["height"])
        for r,y in enumerate(bed_y_positions(center,g["span_width"],beds["rows_per_span"]),1):
            box(builder,bed_name(j,r),dimensions,((x0+x1)/2,y,beds["z"]+beds["height"]/2),"GH_BEDS",mats["bed"],"crop_bed",
                key="BED" if x1-x0==g["length"] else f"BED_{x1-x0:g}",span_index=j,row_index=r)

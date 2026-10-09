"""Pure, sampled-envelope calculations for visualization (never construction values)."""
from .geometry_math import arch_height, roof_arch_radius


def screen_visible_width(config, height):
    g=config['greenhouse']; width=g['span_width']
    if not config['visual_refinement']['clip_screens_to_interior']:
        return width
    # Linear interpolation follows the actual polygon roof, rather than its ideal curve.
    n=g['roof']['segments_per_span']
    points=[(width*i/n,arch_height(width*i/n,width,g['eave_height']['value'],g['ridge_height']['value'],roof_arch_radius(g))) for i in range(n//2+1)]
    target=height+0.025
    if target>=points[0][1]:
        raise ValueError('Screen has no visible interior area below the ridge')
    for (y0,z0),(y1,z1) in zip(points,points[1:]):
        if z1<target<=z0:
            return 2*(y0+(y1-y0)*(z0-target)/(z0-z1))
    return width

"""Drawing references mapped to the existing right-handed model axes."""
def end_positions(config):
    half=config['greenhouse']['length']/2
    return {'front':(-half,0.0,0.0),'rear':(half,0.0,0.0)}


def door_dimensions(config):
    g=config['greenhouse']; d=config['end_walls']
    width=g['span_count']*g['span_width']
    return width*d['door_center_y_ratio'],min(d['door_width'],width*0.25),min(d['door_height'],g['eave_height']['value']*0.8)

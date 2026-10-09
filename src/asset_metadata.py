"""Evidence describes existence separately from geometry and position accuracy."""


def annotate(obj, source="approximate", note="Approximate low-poly visualization", drawing_pages="", position="approximate", **properties):
    obj["source_confidence"] = source
    obj["existence_confidence"] = "drawing_supported" if drawing_pages else source
    obj["geometry_confidence"] = "placeholder" if source=="placeholder" else "approximate"
    obj["position_confidence"] = position
    obj["verified_position"] = False
    obj["verified"] = False
    obj["source_note"] = note
    if drawing_pages:
        obj["drawing_pages"] = drawing_pages
    for key,value in properties.items():
        obj[key] = value
    return obj

import bpy


def save_blend(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    prefs = bpy.context.preferences.filepaths
    previous = prefs.save_version
    preview = prefs.file_preview_type if hasattr(prefs, "file_preview_type") else None
    try:
        prefs.save_version = 0
        if preview is not None:
            prefs.file_preview_type = "NONE"
        result = bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=False)
        if "FINISHED" not in result:
            raise RuntimeError(f"BLEND save did not finish: {result}")
    finally:
        prefs.save_version = previous
        if preview is not None:
            prefs.file_preview_type = preview

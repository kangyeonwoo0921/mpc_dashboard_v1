"""Create a separate, keyed .blend and checked motion report; production GLB is static."""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from src.main import generate
from src.motion import create_motion_smoke_test
from src.export.save_blend import save_blend


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/greenhouse.json')
    parser.add_argument('--output-dir',default='tmp/motion_preview')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    directory=(ROOT/args.output_dir).resolve()
    generate(ROOT/args.config,directory)
    report=create_motion_smoke_test()
    snapshots={}
    for frame in (1,60,120):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        snapshots[frame]={o.name:[v for row in o.matrix_world for v in row] for o in bpy.context.scene.objects if o.animation_data and o.animation_data.action}
    bpy.context.scene.frame_set(1)
    path=directory/'greenhouse_motion.blend'
    save_blend(path)
    # Reopen the saved artifact and verify that keyed transforms persist across file load.
    bpy.ops.wm.open_mainfile(filepath=str(path))
    for frame,percent in ((1,0),(60,50),(120,100)):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name,matrix in snapshots[frame].items():
            actual=[v for row in bpy.data.objects[name].matrix_world for v in row]
            if not all(math.isclose(a,b,abs_tol=2e-5) for a,b in zip(matrix,actual)):
                raise ValueError('Saved motion transform failed: '+name)
        for obj in bpy.context.scene.objects:
            if obj.get('asset_type')=='screen_pivot':
                expected=max(1-percent/100,1e-6)
                if abs(obj.scale["xy".index(obj.get('retract_axis','x'))]-expected)>1e-6: raise ValueError('Saved motion scale failed: '+obj.name)
            if obj.get('asset_type') in ('vent_pivot','screen_pivot','side_curtain'):
                if abs(obj['opening_percent']-percent)>1e-4: raise ValueError('Saved motion metadata failed: '+obj.name)
    report['saved_blend_reopened']=True
    report['blend']=str(path)
    (directory/'motion_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('[MOTION SUCCESS]',path)

if __name__=='__main__': main()

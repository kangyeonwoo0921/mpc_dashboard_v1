"""Open in Blender Text Editor and Run Script, or use blender --background --python."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from src.main import generate


def main():
    parser = argparse.ArgumentParser(description="Generate a Phase 1 greenhouse from JSON")
    parser.add_argument("--config",default="config/greenhouse.json")
    parser.add_argument("--output-dir",default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    try:
        generate(ROOT / args.config,args.output_dir)
    except Exception as exc:
        print(str(exc))
        # --python-exit-code 1 converts this exception to a nonzero headless exit code.
        raise


if __name__ == "__main__":
    main()

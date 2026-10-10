# Phase 1.6 운영형 파라메트릭 온실 생성기

> 프론트엔드 개발자: 작업 범위·시작 방법은 [frontend_handoff.md](markdown/frontend_handoff.md), API·3D 모델·채널 매핑 규칙은 [frontend_api_contract.md](markdown/frontend_api_contract.md)를 보세요.

`config/greenhouse.json → Blender scene → greenhouse.blend + greenhouse.glb + generation_report.json`

기준 문서는 [Phase 1.6 구현 명세](reference/greenhouse_phase1_6_visual_refinement_spec.md)다. [Phase 1.5 명세](markdown/greenhouse_phase1_5_operational_3d_spec.md)의 자산·제어 계약도 유지한다. [Phase 1 명세](markdown/greenhouse_phase1_codex_implementation_spec.md)의 입력 파이프라인, 이름, 기존 부모 관계, 제어 semantics와 acceptance를 유지한다. 입력은 사람이 수정하는 JSON이며 실행 중 PDF를 읽지 않는다. 기본 모델은 8m × 97.5m, 4연동(총폭 32m)이다. 좌표는 X=길이, Y=폭, Z=높이이고 원점은 footprint 중앙 바닥이다. 1 Blender Unit = 1m다.

기본 scene에는 베드 20개와 공유 mesh 방울토마토 900개, 천창 구동부 4세트, 스크린 구동부 8세트, 측면 커튼 2개, 양액 설비, 공급/배액 라인 및 **미확인 sensor placeholder 3개**가 포함된다. crop mesh는 개별 생성하지 않고 하나를 공유한다. 실제 재배 주수나 실제 장비 좌표를 뜻하지 않는다.

## 실행

Blender 설치 외에 `pip install`은 필요 없다. 생성기는 Blender에 포함된 Python, `bpy`, `mathutils`, 표준 라이브러리만 사용한다. 프로젝트 루트에서 실행한다.

이 PC에서 확인한 실행 파일은 **Blender 5.2.2 LTS**다.

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background --python-exit-code 1 `
  --python scripts/generate_greenhouse.py `
  -- --config config/greenhouse.json --output-dir dist
```

Blender가 PATH에 있다면:

```sh
blender --background --python-exit-code 1 --python scripts/generate_greenhouse.py -- --config config/greenhouse.json --output-dir dist
```

성공하면 다음 세 파일을 생성하고 `[SUCCESS]`를 출력한다.

| 파일 | 용도 |
|---|---|
| `dist/greenhouse.blend` | Collection, 객체, 재질, 카메라, 조명이 포함된 Blender 파일 |
| `dist/greenhouse.glb` | 생성한 모델의 glTF 2.0 binary; 객체 이름·부모 관계·custom properties 포함 |
| `dist/generation_report.json` | 치수, 실제 객체 수, 검증 항목, 잠정값 경고, 출력 경로와 크기 |

상대 config/출력 경로는 프로젝트 루트 기준이다. 절대 경로도 지원한다. `--output-dir`을 생략하면 config의 `export` 경로를 사용한다. 지정하면 세 파일의 디렉터리만 바꾸고 파일명은 config 값을 유지한다.

`--python-exit-code 1`은 검증/생성 오류를 종료 코드 1로 전달한다. 설정 오류는 `[CONFIG ERROR]`와 필드 경로·입력값·요구 조건을 먼저 표시한다. 생성 과정 실패는 `status: failed` 보고서에 기록한다. 실패 시 이전 출력 일부가 남을 수 있으므로 파일 존재만으로 성공을 판단하지 말고 종료 코드와 보고서를 확인한다. 설정 읽기/검증 실패는 scene을 변경하지 않으며 새 보고서를 생성하지 않는다.

## Blender GUI 실행

1. Blender에서 **Scripting** workspace를 연다.
2. Text Editor의 **Open**으로 `scripts/generate_greenhouse.py`를 연다. 파일의 원래 위치를 유지한다.
3. **Run Script**를 누른다. 별도 인자 없이 프로젝트의 기본 config를 읽는다.
4. Outliner에서 `GH_ROOT`, `GH_VENTS`, `GH_SCREENS`, `GH_INTERIOR`를 확인한다.
5. 세 산출물은 자동으로 저장된다. 다른 config는 Python Console에서 아래처럼 실행한다.

```python
from src.main import generate
from src.config_loader import PROJECT_ROOT
generate(PROJECT_ROOT / "config/greenhouse.json", PROJECT_ROOT / "dist")
```

생성기 실행 후 `src`를 import할 수 있다. 새 Blender 세션에서 `.blend`만 열었다면 먼저 프로젝트 루트를 `sys.path`에 추가한다.

```python
import sys
sys.path.insert(0, r"C:\경로\mpc_dashboard_v1")
```

재실행하면 생성기 소유 표시가 있는 객체·Collection만 정리한다. 생성 객체 아래에 연결한 사용자 객체는 월드 위치를 보존하고 scene으로 옮긴다. 필수 이름과 사용자 객체 이름이 충돌하면 `.001`을 붙이지 않고 오류를 낸다. 기존 사용자 객체는 `.blend`에 남지만 `.glb`에는 생성기 모델만 export한다.

Phase 1.5의 명시적 예외는 `scene_cleanup.remove_default_cube=true`다. 정확히 `Cube`라는 이름의 mesh이며 generator metadata가 없는 객체만 제거한다. `Cube.001`, 다른 이름의 사용자 객체, generator metadata가 있는 Cube는 보존한다. 기본 Camera/Light 제거 옵션은 기본 `false`이며 역시 정확한 이름과 타입만 대상으로 한다. 기존 Phase 1 JSON에서 옵션을 생략하면 Cube를 포함해 보존한다.

## Config 변경

기존 필드의 이름과 기본값은 명세 6절을 따른다. Schema는 `config/greenhouse.schema.json`에 있다. 필수 키·오타·타입·범위 및 높이/배치 조건을 검사한다. Blender 내부 경량 검증기는 이 schema에서 쓰는 규칙을 처리하며 범용 JSON Schema 엔진은 아니다.

| 설정 | 효과 |
|---|---|
| `greenhouse.span_count: 3` | 총폭 24m, 천창 3개, 베드 15개 |
| `greenhouse.length: 60` | 길이 60m, 기본 margin 적용 시 베드 길이 52m |
| `greenhouse.span_width` | span 폭·경계·베드·지붕·천창 폭 재계산 |
| `greenhouse.eave_height.value` / `ridge_height.value` | 아치 및 기둥 높이; ridge는 eave보다 커야 함 |
| `structure.*_spacing` | station 재계산; 끝점은 반드시 유지 |
| `roof_vents.opening_percent` | 0=닫힘, 100=최대 각도 |
| `shade_screen.opening_percent` / `diffuse_screen.opening_percent` | 0=펼침, 100=수납 |
| `crop_beds.rows_per_span` | 각 span의 베드 수; 0이면 베드 없음 |
| 각 설비의 `enabled` | 해당 mesh 생성 여부; 제어용 그룹 이름은 유지 |
| `render.add_camera` / `add_lights` | 생성기 카메라/조명 생성 여부 |

높이는 `{ "value": 4.2, "verified": false, "note": "..." }` 형태로 출처와 잠정 상태를 보존한다. 도면 검증 없이 `verified: true`로 바꾸지 않는다.

베드의 `z`는 바닥면 높이이고 `height`는 베드 자체 두께다. 길이는 `length - 2*length_margin`이다. 각 span을 같은 폭의 행 구간으로 나눠 중앙에 베드를 놓는다. 폭이 구간을 채워 통로를 없애거나 끝 margin이 베드 길이를 없애는 설정은 거부한다.

대표 천창의 최소 보완 필드는 다음과 같다. 원래 명세 JSON처럼 생략하면 Schema에 기록한 동일 기본값으로 보완한다.

| 필드 | 기본값·의미 |
|---|---|
| `panel_length_ratio` | 0.8: 온실 전체 길이 대비 panel 길이 |
| `panel_width_ratio` | 0.15: span 폭 대비 수평 투영 폭, 최대 0.5 |
| `x_center_ratio` | 0.5: X 음의 끝에서 양의 끝까지의 상대 중심 위치 |
| `side` | `positive_y`; `negative_y`이면 개방 회전 부호 반전 |
| `assumption` | 미검증 대표 panel이라는 설명 |

천창이 지붕 밖으로 넘어가는 비율 조합은 거부한다. 차광 `transmittance_visual=0.25`는 설명용 값이며 물리 투과율 계산에 사용하지 않는다. 스크린 재질의 alpha는 `visual_opacity`로 설정한다. 기존 `crop_beds.show_plants`는 호환성을 위해 `false`로 유지하고, 작물 생성은 새 `crops.enabled`로 제어한다.

## Phase 1.5 설정과 호환성

| 설정 | 기본 동작 |
|---|---|
| `crops.enabled` | 모든 생성된 bed에 방울토마토 배치 |
| `plant_spacing`, `max_visual_plants_per_bed` | 0.7m 요청 간격, 베드당 최대 45개; 상한 적용 시 균등 visual spacing 재계산 |
| `plant_height`, `detail_level` | 2.2m, `medium`; `low`는 잎 수 감소 |
| `instance_mode` | `linked`만 지원; 모든 plant가 mesh 공유 |
| `tomato_clusters` | red/green 열매 cluster 생성 여부 |
| `roof_vents.mechanism_enabled` | shaft/rack/pinion/bearing/motor 생성 |
| `shade_screen.drive_enabled`, `diffuse_screen.drive_enabled` | span별 drum/shaft/roller 생성 |
| `side_curtains.enabled`, `opening_percent` | 양 측면 curtain, 0=닫힘/펼침, 100=개방/수납 |
| `fertigation.show_*` | tank/pump/filter/blower/control panel 및 supply/drain 표시 |
| `fertigation.asset_scale` | low-poly 장비 치수 배율; 좁은 온실은 폭 24m 기준으로 추가 축소 |
| `fertigation.placement.mode` | `end_service_strip`: 현재 길이·bed margin에 맞춰 X 음의 끝 서비스 영역 계산 |
| `fertigation.placement.mode: absolute` | 입력 `x/y/z` 사용; 좌표는 계속 `verified=false` |
| `sensors.items` | 고유 ID, 종류, meter position `[x,y,z]`, `verified:false`, 설명 |
| `visualization.cover_mode` | `opaque` / `transparent` / `hidden` |
| `visualization.cover_opacity` | 외피 전용 alpha, 기본 0.15; 천창 panel 재질과 분리 |
| `visualization.interior_preview` | 내부 preview에서 스크린과 curtain을 수납해 작물·설비 확인 |

신규 섹션이 없는 기존 JSON도 실행된다. 생략된 신규 설비는 비활성, 기존 외피 opacity와 Cube 보존 정책은 유지된다. 원래 설정을 `tests/fixtures/phase1.json`에 보존했다. 현재 기본 입력은 `metadata.phase=1.6`다.

센서의 `verified_positions`와 개별 `verified`는 이번 단계에서 반드시 `false`다. 실제 위치를 확인하기 전 true로 바꾸는 입력은 오류로 처리한다. 중복 sensor ID, 비유효 좌표, 지붕/스크린을 관통하는 crop 높이, 서비스 영역이 부족한 margin을 사전에 검사한다. 기본 장비 배치는 도면 좌표 복원이 아닌 한쪽 끝 서비스 영역의 provisional zoning이다. `end_service_strip`에서는 x/y 입력을 사용하지 않고 현재 footprint에서 계산한다.

## Scene 구조와 개폐

```text
GH_ROOT
├─ GH_STRUCTURE
│  ├─ GH_COLUMNS_MAIN
│  ├─ GH_COLUMNS_SECONDARY
│  ├─ GH_RAFTERS
│  ├─ GH_TRUSSES
│  └─ GH_GUTTERS
├─ GH_ROOF
│  ├─ GH_ROOF_FRAME
│  └─ GH_ROOF_COVER
├─ GH_VENTS
│  └─ GH_VENT_S01_01_PIVOT → GH_VENT_S01_01 → frame
├─ GH_SCREENS
│  ├─ GH_SHADE_SCREEN → 기존 per-span pivot → panel
│  │  └─ GH_SHADE_SCREEN_DRIVE → per-span drive → drum/shaft/rollers
│  └─ GH_DIFFUSE_SCREEN → 기존 per-span pivot → panel + 별도 DRIVE
├─ GH_CURTAINS (기존 호환 그룹/Collection)
├─ GH_SIDEWALLS → GH_SIDEWALL_LEFT / RIGHT → FIXED + GH_SIDE_CURTAIN_LEFT / RIGHT
│  └─ GH_FRONT_WALL, GH_REAR_WALL, GH_FRONT_DOOR
├─ GH_INTERIOR → GH_BEDS, GH_CROPS
├─ GH_FERTIGATION → GH_FERTIGATION_UNIT, GH_IRRIGATION_SUPPLY, GH_IRRIGATION_DRAIN
├─ GH_SENSORS → GH_SENSOR_*_ANCHOR → sensor mesh
├─ GH_GROUND
└─ GH_SCENE → Camera_Main, Light_Key, Light_Fill
```

Blender의 Collection은 glTF의 노드 계층과 다르므로 주요 그룹을 같은 이름의 Empty 부모로도 만든다. 모든 mesh를 합치지 않는다. GLB에는 모델과 Empty 계층이 들어가며 preview 카메라·조명은 `.blend`에만 저장한다. Blender 좌표 Z-up은 표준 glTF Y-up으로 export된다. 재import 시 월드 좌표와 치수가 복원되는지 검증한다.

이름은 `GH_COL_MAIN_X001_Y01`, `GH_RAFTER_X005_S02`, `GH_VENT_S01_01`, `GH_BED_S03_R04`처럼 1부터 시작한다. 객체에는 역할에 따라 `asset_type`, `span_index`, `row_index`, `controllable`, `control_variable`을 넣고 GLB extras로 내보낸다.

Blender Python Console에서:

```python
import bpy
from src.geometry.vents import set_vent_opening
from src.geometry.screens import set_screen_opening

set_vent_opening(bpy.data.objects["GH_VENT_S01_01"], 50)
set_screen_opening(bpy.data.objects["GH_SHADE_SCREEN"], 50)
set_screen_opening(bpy.data.objects["GH_DIFFUSE_SCREEN"], 0)
bpy.context.view_layer.update()
```

천창은 hinge에 놓인 pivot의 **로컬 X 회전**으로 움직인다. 20%·최대 90°이면 18°다. panel 자체 원점도 hinge에 있어 직접 로컬 회전할 수 있다. helper는 panel 또는 pivot을 받으며 누적 회전이 아닌 절대 각도를 설정한다.

스크린은 pivot의 `retract_axis` 로컬 scale을 바꾼다. 기본 config(`travel=across_span`)는 동마다 −Y 물받이 쪽 끝을 원점으로 삼아 **로컬 Y scale**로 폭 방향(좌우)으로 접히고, `along_length`에서는 X 음의 끝을 원점으로 **로컬 X scale**을 쓴다. helper는 전체 layer 그룹, 개별 pivot 또는 panel을 받는다. 100%에서 `1e-6` scale을 남겨 노드와 역변환을 유지하며, 완전히 펼칠 원본 mesh는 보존한다. 기본 산광은 100%라 거의 보이지 않는다. 확인하려면 0%로 펼친다. 생성 후 개폐를 바꾼 상태를 파일에 반영하려면 config를 바꿔 재생성한다.

외피 숨김은 Outliner의 **GH_ROOF_COVER Collection**에서 눈 아이콘을 사용한다. Empty 부모만 숨기는 동작은 자식 전체 숨김과 같지 않다.

Phase 1.5 제어 helper:

```python
from src.geometry.curtains import set_side_curtain_opening
from src.geometry.cover import set_cover_visibility

set_side_curtain_opening(bpy.data.objects["GH_SIDE_CURTAIN_LEFT"], 50)
set_cover_visibility("hidden")
set_cover_visibility("transparent", 0.15)
```

천창 motor는 panel/pivot에 붙여 움직이지 않는다. 기존 `GH_VENT_S01_01_PIVOT → GH_VENT_S01_01 → GH_VENT_S01_01_FRAME` 관계를 유지하고, 고정 `GH_VENT_S01_01_DRIVE`를 `GH_VENTS` 아래에 추가했다. `_PANEL`은 기존 panel mesh를 가리키는 picking anchor다. rack은 회전한 panel 끝점을 향해 이동·회전하고 pinion은 opening에 비례해 회전한다. 실제 기어비·회전수가 아닌 시각적 관계다. helper 실행 후에도 motor 위치는 고정된다.

스크린 drive는 수납 scale의 자식이 아니다. 기존 per-span pivot의 부모를 바꾸지 않고 DRIVE를 병렬로 추가했다. 따라서 drum/roller 크기는 유지된다. curtain은 상단 고정 원점에서 Z scale로 올라가며 bottom bar도 함께 움직인다.

GLB에는 hidden cover도 이름과 mesh를 유지해 포함된다. hidden 상태는 alpha 0과 `preview_hidden=true`, `cover_mode=hidden`으로 전달한다. glTF에는 Blender의 `hide_set`과 동일한 표준 가시성 속성이 없으므로, 다음 Three.js 구현에서 extras를 읽어 `.visible`을 설정해야 한다. 이 단계에서는 웹 코드를 만들지 않는다.

## Geometry와 성능

기본 아치는 `roof.profile=circular_pointed_arch`로, 반쪽마다 반경 `roof.arch_radius`의 원호가 `(-w/2,e)`와 `(0,r)`를 지나 용마루에서 만난다. `bezier_arch`를 지정하면 기존 2차 Bezier(제어점 `(-w/2,e)`, `(0,2r-e)`, `(w/2,e)`)를 사용한다. 기본 24 segment로 양 끝 처마와 중앙 용마루 높이를 만족한다. 외피와 천창은 같은 샘플 지붕 profile을 사용하고, 외피에는 천창 영역만큼 개구부를 둔다.

기둥·베드는 직육면체, 서까래·연결부재는 8각 단면이다. 반복 부재는 mesh를 공유한다. 기존 구조 수량은 주기둥 115개, 샛기둥 110개, 서까래 352개, 천창 4개, 차광/산광 각각 4개, 베드 20개로 유지된다. 전체 객체 수·unique mesh 수·plant instance 수·생성 시간·파일 크기는 `generation_report.json`의 `performance`, `output_bytes`에 실제 집계한다.

작물 한 개는 줄기·잎·유인줄·red/green 열매를 포함한 multi-material mesh다. 모든 `GH_PLANT_*`가 같은 mesh를 공유한다. `GH_PLANT_MASTER`는 공유 mesh 이름과 구성요소를 기록한 template anchor이며, 실제 plant는 각 crop row 아래의 linked mesh 객체다. tank는 body/cap/base/connector/label plate, pump는 motor/housing/in-out connector, control cabinet은 door/display/indicator 등으로 구분된다. 장비 전체를 한 mesh로 합치지 않는다.

마지막 main bay는 3m, secondary/rafter 마지막 구간은 0.75m다. spacing에 맞춰 전체 길이를 늘리지 않는다. 기둥 단면이나 파이프 반지름 때문에 외곽 mesh bounds는 기준 grid 치수보다 조금 클 수 있다. 보고서의 32×97.5m는 기준 footprint/grid 치수다.

## 검증

일반 Python이 있으면 순수 함수 테스트를 실행한다.

```sh
python -m unittest discover -s tests -v
```

시스템 Python 없이 Blender만으로도 실행할 수 있다. 프로젝트 루트에서:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background --python-exit-code 1 `
  --python-expr "import sys,unittest; sys.path.insert(0,'.'); r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests')); assert r.wasSuccessful()"
```

전체 acceptance 및 실제 GLB 재import:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background --python-exit-code 1 `
  --python scripts/validate_scene.py `
  -- --config config/greenhouse.json --output-dir dist --roundtrip --acceptance --render-previews
```

`validate_scene.py`는 **별도 headless 프로세스용**이다. 검사 중 scene을 교체하므로 편집 중인 GUI에서 실행하지 않는다. `--roundtrip` 없이도 저장된 BLEND를 열어 그룹·수량·이름·변환·개폐·GLB 노드·재질을 검사한다.

`--acceptance`는 기본 4연동 설정을 대상으로 기존 Phase 1의 3연동, 60m, 반대 방향 천창, optional geometry 비활성화, 0행 베드, cover/vent 독립 활성화, 재실행, 오류 입력과 사용자 객체 보존을 검사한다. 추가로 기존 Phase 1 JSON, hidden/opaque GLB, 저밀도·상한 작물, 운영 설비 비활성화, Cube 정리 예외를 검사한다. 원본 config와 `dist`는 바꾸지 않고 변형 결과를 `tmp/validation/cases/`에 만든다.

`--render-previews`는 `tmp/validation/previews/`에 기존 8장, Phase 1.6 정제 시점 9장, 전후면 검토 3장까지 총 20장을 생성한다. 기본 BLEND 카메라는 1600×900이며 검사용 렌더는 1280×800이다. crop 상세 이미지는 식별을 위해 구조 프레임을 임시 숨긴 cutaway이고, 생성 BLEND/GLB의 구조는 그대로다.

```text
exterior_perspective.png
interior_cover_hidden.png
interior_crop_view.png
fertigation_view.png
roof_vent_closed.png
roof_vent_open.png
screen_open.png
screen_closed.png
```

검사 결과는 `tmp/validation/acceptance_report.json`에 저장한다. `status: success`, 종료 코드 0, `[VALIDATION SUCCESS]`를 확인한다. 기본 생성 보고서와 이 검증 보고서는 역할이 다르다. 전자는 생성 시 검사, 후자는 재import와 변형 실행 결과다.

검증 기준:

| 명세 acceptance | 검사 |
|---|---|
| A. Config-driven | 3연동 폭 24m·천창 3개·베드 15개 |
| B. Length-driven | 60m 기준 grid와 베드 길이 52m |
| C. Interactive-ready | cover/vent/screen/bed/frame 객체 및 그룹 분리 |
| D. Vent pivot | 0/50/100% 각도·hinge 불변·직접 panel 회전·재import 후 제어 |
| E. Screen control | 고정 끝 불변·길이 감소·재import 후 다시 펼침 |
| F. GLB | 실제 재import하여 이름·계층·재질·월드 bounds/transform 비교 |
| G. Re-run | 두 번 실행 후 객체/mesh/재질 수 불변·사용자 객체 보존 |

Phase 1.5 추가 검사는 모든 bed의 crop 수와 공유 mesh, 필수 구동부, rack 연결점·pinion 회전·motor 고정, screen drum 회전, curtain 수납, 개별 양액 자산, bed별 공급/배액 연결, 센서 anchor와 `verified=false`, 기본 Cube 정책, preview 파일 생성이다. GLB 재import에서는 기존 이름·계층·재질 값·삼각형 수·bounds·custom properties를 비교하고 제어 helper를 다시 실행한다.

첫 결과 육안 확인: 4개 아치, 32×97.5m 비율, span당 베드 5개, 천창의 위쪽 개방, 스크린 층 구분, 외피 숨김 시 내부 식별을 확인한다. 스크린이 지붕과 충돌하면 입력 높이는 유지하고 시각 fabric만 샘플 지붕 내부로 clipping한다. 현재 기본 config에서는 충돌이 없어 clipping이 적용되지 않는다.

## 도면 해석상 잠정값과 한계

- 처마 5.0m는 도면 6~10쪽에 기입된 치수이고, 용마루 7.5m와 원호 반경 8.193m는 같은 단면의 벡터 좌표(1/150)에서 측정했다. 설계 도면 값이며 현장 실측이 아니므로 `verified=false`를 유지한다. 모델 원호는 처마 치수점 `(±4.0, 5.0)`을 지나므로 도면 곡선(물받이 끝 약 4.98m)보다 처마 부근에서 최대 약 0.1m 높다.
- 차광 4.8m·산광 4.55m는 처마 5.0m 아래, 트러스 구간(4.40~5.00m) 안에 있어 이전의 설치 높이 모순이 해소되었다. 스크린은 span 폭 8m 전체로 표시되며 `visible_width`는 계속 객체와 보고서에 남긴다.
- 도면 2/4쪽의 계단형 평면(S03–S04가 X3에서 시작)은 반영했다. 부분 screen/bed 배치(30쪽은 베드를 Y1–Y3 두 동에만 둔다), 양끝 1.5m 처마 돌출부와 중앙 통로는 동별 균등 반복으로 단순화했다.
- 천창은 span마다 용마루 좌우 2장(`_01`=+Y, `_02`=−Y)이며 폭 1.2m, 양끝 1m를 뺀 연속 길이다. 양랙·모터·기어는 low-poly 시각화이며 실제 제품/기어비/힌지 설계 복원이 아니다. panel 비율, 베드 세부 치수, 지붕 곡률과 부재 시각 단면은 실측 확정값이 아니다.
- 스크린은 scale 수납과 작은 retract bundle로 표현한다. 실제 천 주름/롤 역학이나 광학 모델은 없다. 투명 재질은 viewer에 따라 겹침 정렬 방식이 다를 수 있다.
- 기본 재질은 중립적인 시각화용이다. 프레임·외피·스크린은 별도 재질로 변경할 수 있다.
- Blender **5.2.2 LTS에서 실제 생성·재import·렌더 검증**했다. 4.x의 재질/export API 차이는 분리했지만 4.x 실행 자체는 이 PC에서 검증하지 않았다. Blender 파일은 만든 버전 또는 호환되는 버전으로 연다.
- 베드당 최대 45개 작물은 시각화 상한이다. 실제 생육 단계, 재배 주수, 수확량을 추정하지 않는다. 반복 mesh이므로 작물별 생장·모양 변화도 없다.
- 양액 설비는 종류만 도면 근거가 있고 정확 치수·좌표는 확정되지 않았다. 한쪽 end-service zoning은 동선 충돌을 피하는 provisional 배치이며 도면의 실제 설치 위치로 주장하지 않는다. 절대 좌표 모드에서는 사용자가 실제 동선과의 충돌을 검토해야 한다.
- 배관은 bed별 공급/배액 관계를 표현한다. 모든 tank 내부 연결이나 hydraulic network를 완성한 설계가 아니며, 압력·유량·밸브 제어를 시뮬레이션하지 않는다.
- Sensor, purifier, 계기류, control cabinet의 상세 형상/위치는 placeholder다. 실제 sensor 좌표와 PLC tag, 데이터는 없다.
- AI/PDF OCR, CAD/DXF/BIM 복원, 구조·열·유동 해석, Django, Three.js, 실제 센서/PLC 연결, MPC는 포함하지 않는다.

## 도면 근거와 불확실성

보고서의 `source_confidence`는 세 분류를 제공한다. 도면 근거는 장비의 **존재/종류**에 관한 것이며 정확 치수·좌표까지 확정한다는 뜻이 아니다.

| 분류 | 항목 |
|---|---|
| drawing_supported | 천창 shaft/rack/pinion/bearing/motor(6·40쪽), 차광·산광 및 curtain roller/drum(25~29쪽), 양액탱크·펌프·블로어·필터·계기·공급/배액(30~31쪽), span당 베드 5개(30쪽) |
| approximate | 장비 외형/크기, 작물 높이/잎/열매/visual spacing, 구동 연동량, 배관 경로·직경, 도면 측정 지붕 형상(현장 미실측) |
| placeholder | 실제 센서 위치, 임시 양액 장비 배치, purifier/control panel/계기 상세 형상, 미지정 PLC tag |

주요 신규 객체는 `existence_confidence`, `geometry_confidence`, `position_confidence`, `source_note`, `drawing_pages`를 함께 제공한다. Sensor는 `source_confidence=placeholder`, `verified_position=false`, `verified=false`다.

## 다음 Three.js 단계의 객체 계약

glTF custom properties는 노드의 `extras`이며 일반적인 loader에서는 `object.userData`로 접근할 수 있도록 export한다. 아래 이름은 고정 계약이다.

| 이름/패턴 | 역할 및 핵심 property |
|---|---|
| `GH_VENT_S01_01` / `_PIVOT` | 기존 panel/hinge; `asset_type=roof_vent/vent_pivot`, `span_index`, `controllable`, `control_variable=opening_percent`, `opening_percent`, `side`, `max_open_angle_deg` |
| `GH_VENT_S01_01_PANEL` | 기존 panel 이름을 유지하기 위한 picking anchor, `panel_object` |
| `GH_VENT_S01_01_DRIVE` | 고정 구동계, `control_owner`; pivot의 `drive_name`으로 연결 |
| `_SHAFT`, `_RACK_A/B`, `_PINION`, `_PINION_B`, `_BEARING`, `_MOTOR` | 천창 부품; rack의 `station_x`, `attach_y/z`, `pinion_y/z`, `rack_length`는 시각 연동용 |
| `GH_SHADE_SCREEN`, `GH_DIFFUSE_SCREEN` | 기존 layer root; 기존 `*_S01_PIVOT → *_S01` 관계 보존 |
| `GH_SHADE_SCREEN_DRIVE`, `GH_DIFFUSE_SCREEN_DRIVE` | 고정 drive 그룹; `GH_SHADE_DRUM_S01`, `GH_SHADE_SHAFT_S01`, `GH_SHADE_ROLLER_S01_01` 등 |
| `GH_SIDE_CURTAIN_LEFT/RIGHT` | `asset_type=side_curtain`, `opening_percent`, `full_height`, `panel_name`, `control_variable=opening_percent` |
| `GH_CROP_ROW_S01_R01` | bed별 crop row; `bed_name`, `span_index`, `row_index`, `visual_spacing` |
| `GH_PLANT_S01_R01_P001` | `asset_type=crop_plant`, `crop_type=cherry_tomato`, `plant_index`, `instance_mode=linked`, `master_name` |
| `GH_PLANT_MASTER` | `shared_mesh_name`, `components`를 갖는 template anchor |
| `GH_NUTRIENT_TANK_A/B/C`, `GH_WATER_TANK`, `GH_MIXING_TANK` | `asset_type=tank`, `tank_role`, `controllable=false` |
| `GH_FEED_PUMP`, `GH_RING_BLOWER` | `asset_type=pump/blower`, `controllable=true`, `control_variable=on_off`, `plc_tag_verified=false` |
| `GH_WATER_PURIFIER`, `GH_FILTER_01/02` | 별도 equipment root |
| `GH_CONTROL_PANEL`, `GH_DISPLAY` | cabinet/display; 실제 UI·PLC 데이터 없음 |
| `GH_PRESSURE_GAUGE`, `GH_PRESSURE_VALVE`, `GH_FLOW_METER` | 계기/valve; valve의 control property는 준비용, 실제 유량 제어 없음 |
| `GH_IRRIGATION_SUPPLY/DRAIN` | pipe 그룹; `GH_SUPPLY_S01_R01`, `GH_DRAIN_S01_R01`에 `bed_name`, `span_index`, `row_index` |
| `GH_SENSOR_T_RH_01_ANCHOR` → `GH_SENSOR_T_RH_01` | anchor world position을 label 위치로 사용; `sensor_id`, `sensor_type`, `live_data_ready=true`, `verified_position=false` |
| `GH_SENSOR_SOLAR_01_ANCHOR` → `GH_SENSOR_SOLAR_01` | 외부 일사량 sensor placeholder, 동일 property 계약 |
| `GH_ROOF_COVER` / `GH_ROOF_COVER_S01` | `cover_mode`, `preview_hidden`; root의 `transparent_opacity` |

`controllable`과 `live_data_ready`는 향후 연결을 위한 metadata다. 현재 PLC command나 live telemetry 구현을 의미하지 않는다. meter/Z-up 좌표가 glTF Y-up으로 변환되므로 웹에서 회전축은 import된 노드의 로컬 축을 기준으로 다뤄야 한다.

## 전체 소스 파일과 역할

```text
README.md                          실행·설정·검증·한계
.gitignore                         dist/tmp/캐시 제외
config/greenhouse.json              사람이 수정하는 입력
config/greenhouse.schema.json       입력 스키마와 보완 필드 기본값
src/__init__.py                     패키지
src/main.py                         생성 순서와 오류 처리
src/config_loader.py                JSON·스키마·의미 검증·경로 처리
src/geometry_math.py                Blender 없는 좌표·station·아치·제어 수학
src/scene_setup.py                  소유권 정리·Collection/Empty·단위·카메라·조명
src/materials.py                    7종 기본 재질
src/naming.py                       고정 이름 함수
src/validation.py                   scene·GLB·재import 공통 검사
src/report.py                       실제 수량·경고·생성 보고서
src/asset_metadata.py               존재/형상/위치 신뢰도와 unverified 표시
src/operational_validation.py       Phase 1.5 자산·개폐·Cube·외피 검증
src/preview.py                      기존 8개 + Phase 1.6/전후면 12개 preview 시점
src/geometry/__init__.py            geometry 패키지
src/geometry/primitives.py          공유 mesh·box·tube·surface
src/geometry/frame.py               기둥·단순 트러스/gutter·지면·ridge
src/geometry/roof.py                반복 아치 서까래
src/geometry/cover.py               천창 개구부를 가진 지붕 외피
src/geometry/vents.py               천창 mesh·hinge·개폐 helper
src/geometry/screens.py             차광/산광 panel·수납 helper
src/geometry/beds.py                균등 배치 베드
src/geometry/crops.py               공유 방울토마토 mesh와 bed별 linked instance
src/geometry/equipment_primitives.py 저폴리곤 부품·기어·multi-material mesh 조립
src/geometry/fertigation.py         양액 설비와 provisional 서비스 영역 배치
src/geometry/pipes.py               bed별 공급/배액 시각 연결
src/geometry/sensors.py             unverified sensor/anchor
src/geometry/curtains.py            측면 curtain·roller/drum·개폐
src/export/__init__.py              export 패키지
src/export/save_blend.py            BLEND 저장
src/export/export_glb.py            glTF 2.0 export 옵션·선택 복원
scripts/generate_greenhouse.py      CLI/GUI 공통 진입점
scripts/validate_scene.py           headless acceptance·렌더 검증
tests/test_config.py                config/오류 테스트
tests/test_geometry_math.py         수학·배치·제어 테스트
tests/test_naming.py                naming 테스트
tests/test_operational_config.py    신규 입력·센서·legacy default 검증
tests/fixtures/phase1.json           확장 이전 원본 Phase 1 입력
```

기존 `manage.py`, `markdown/`, `reference/`는 유지한다. 다음 단계에서 수정할 때는 치수·배치는 JSON, 아치 수학은 `geometry_math.py`, 천창/스크린 방식은 각 geometry 모듈, 시각 스타일은 `materials.py`, export 호환성은 `export/`에서 변경한다. 이후 단계의 런타임 기능은 이번 코드에 포함하지 않는다.

Phase 1.5 수정 파일: `README.md`, `config/greenhouse.json`, `config/greenhouse.schema.json`, `src/config_loader.py`, `src/scene_setup.py`, `src/materials.py`, `src/main.py`, `src/report.py`, `src/validation.py`, `src/geometry/cover.py`, `src/geometry/vents.py`, `src/geometry/screens.py`, `src/export/export_glb.py`, `scripts/validate_scene.py`.

Phase 1.5 추가 파일: `src/asset_metadata.py`, `src/operational_validation.py`, `src/preview.py`, `src/geometry/crops.py`, `src/geometry/equipment_primitives.py`, `src/geometry/fertigation.py`, `src/geometry/pipes.py`, `src/geometry/sensors.py`, `src/geometry/curtains.py`, `tests/test_operational_config.py`, `tests/fixtures/phase1.json`.


## Phase 1.6 시각 정제와 설정

`sidewalls.enabled=true`는 좌우 0.8m 하부 방풍벽과 전후면 아치 마감을 생성한다. 측면 curtain은 처마에서 하부 고정벽까지를 덮는다. 0%=닫힘, 50%=상부로 절반 수납, 100%=대부분 개방이다. roller/drum/shaft와 guide는 고정되고 bottom bar는 fabric 끝을 따른다. `GH_SIDE_CURTAIN_LEFT/RIGHT` 이름과 helper 인자는 그대로이며, 활성화 시 부모만 명세의 좌우 sidewall 노드로 연결한다. `GH_CURTAINS` Collection과 호환 그룹도 유지한다. 출입구 존재는 도면 근거가 있지만 `GH_FRONT_DOOR` 위치·크기는 placeholder/approximate다.

| 추가 설정 | 기본값·효과 |
|---|---|
| `sidewalls.fixed_lower_wall_height` | 0.8m, 시각화 잠정 하부 높이 |
| `sidewalls.material_opacity` | 0.28, 고정벽 반투명 재질 |
| `visual_refinement.clip_screens_to_interior` | true, 실제 polygon 지붕 아래 0.025m 여유를 둔 시각 폭 |
| `visual_refinement.compact_vent_mechanism` | true, 힌지 가까운 rack 연결점과 작은 모터 |
| `visual_refinement.service_zone_layout` | true, 한쪽 끝 tank / pump-filter-blower / controls 영역 |
| `crops.lod` | dashboard, 잎과 열매 감소; standard는 Phase 1.5 형상 |
| `preview.generate_refinement_views` | true, 검증 렌더에 정제 시점 9장 추가 |

기존 JSON에서 신규 항목을 생략하면 sidewalls와 refinement는 꺼지고 crop LOD는 standard다. `tests/fixtures/phase1.json`, `phase1_5.json`을 실제 생성·GLB 재import하는 regression에 포함한다. 기본 작물은 20×45=900개, 모두 하나의 multi-material mesh를 공유한다. 0.7m는 요청 간격이며 visual cap 때문에 실제 표시 간격은 더 넓어진다. 실제 재배 주수가 아니다.

차광 재질 alpha 0.72, 산광 0.42로 fabric을 구분한다. 수납 pivot은 `retract_axis` scale 계약을 따르며, `*_RETRACT_BUNDLE`은 pivot의 형제라 같이 사라지지 않는다. bundle의 같은 축 scale은 `0.15 + 0.85*opening/100`이다. `visual_clipping_applied`, `original_width`, `visible_width`, `original_height`를 GLB extras와 report에 남긴다. 입력 높이는 바꾸지 않는다.

천창 shaft는 길이방향 X축이다. 기존 `_RACK_A/B`는 힌지 가까운 panel 연결점을 따라 움직이고 `_MOTOR`는 고정이다. 실제 gear ratio/기계 설계 검증은 하지 않는다.

링블로어는 밀폐된 side-channel housing, motor, inlet/outlet, base로 구성한다. `GH_RING_BLOWER`에 `system=fertigation`, `is_circulation_fan=false`를 기록한다.

No circulation fan is generated in Phase 1.6. The drawing confirms a ring blower in the fertigation system, not greenhouse air-circulation fan placement.

양액 설비는 X 음의 끝 한쪽에 모으고, 기존 equipment root 이름/부모는 유지한다. `service_zone` property로 기능 그룹을 구분한다. A/B/C는 작은 mesh 글자, 원수는 큰 tank와 W 표시, 혼합은 M 표시와 상부 mixer로 구분한다. 정확한 장비 치수·좌표가 아니다. 공급/배액 header는 branch보다 굵고, branch에는 `line_role`, `connects_from`, `connects_to`, `bed_name`이 있다. 센서 anchor 좌표는 기존 config 그대로이며 `label_anchor=true`, `live_data_ready=true`, `verified_position=false`다.

## Visibility presets

Blender Console에서 프로젝트 import 경로를 설정한 뒤:

```python
from src.refinement import apply_view_preset
apply_view_preset('exterior')
apply_view_preset('interior')
apply_view_preset('equipment')
apply_view_preset('control_devices')
```

exterior는 외피·측벽과 작물을 표시한다. interior는 지붕을 숨기고 측벽을 더 투명하게 한다. equipment/control_devices는 여기에 작물 숨김을 적용한다. equipment는 구조 프레임·천창·스크린도 숨기고, control_devices는 양액 장비를 숨겨 구동부·센서에 집중한다. 객체를 삭제하거나 움직이는 pivot을 바꾸지 않는다. 노드별 `preset_hidden`과 root의 `view_preset`을 기록한다. Three.js에서는 필요에 따라 이 extras를 `.visible`로 연결해야 한다. Blender visibility는 glTF 표준 animation 기능이 아니다.

## Motion preview / smoke test

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background --python-exit-code 1 `
  --python scripts/create_motion_preview.py `
  -- --config config/greenhouse.json --output-dir tmp/motion_preview
```

`tmp/motion_preview/greenhouse_motion.blend`를 열고 Space로 재생한다. Frame 1=0%, 60=50%, 120=100%이며 천창·차광/산광·양쪽 curtain을 함께 구동한다. 각 frame의 helper 결과를 bake하여 rack 연결점이 단순 보간으로 벗어나지 않게 한다. 역순 scrubbing과 저장 후 재열기 검사를 거쳐 `motion_report.json`을 만든다. production `dist` 파일은 변경하지 않는다. **Blender transform smoke test이며 실제 웹 animation은 아니다.**

## 사람이 확인할 preview

기존 8장과 함께 `tmp/validation/previews/`에 다음 12장을 생성한다.

```text
sidewall_closed.png
sidewall_half_open.png
sidewall_open.png
screen_full_deployed.png
screen_retracted.png
vent_mechanism_closeup.png
ring_blower_closeup.png
fertigation_service_zone.png
sensor_placeholder_view.png
front_elevation.png
rear_elevation.png
front_door_closeup.png
```

우선 exterior_perspective, 측벽 3상태, interior_cover_hidden, screen deployed/retracted, vent closeup, service zone, blower closeup, interior_crop_view의 통로를 확인한다. Sensor closeup은 실제 설치 사진이 아닌 placeholder mesh 검토용이다. equipment closeup은 마감벽을 숨긴 cutaway다.

## Phase 1.6 파일 변경

추가: `src/geometry/sidewalls.py`, `src/refinement_math.py`, `src/refinement.py`, `src/refinement_validation.py`, `src/motion.py`, `src/orientation.py`, `scripts/create_motion_preview.py`, `tests/test_refinement.py`, `tests/test_orientation.py`, `tests/fixtures/phase1_5.json`.

수정: `README.md`, `config/greenhouse.json`, `config/greenhouse.schema.json`, `src/config_loader.py`, `src/scene_setup.py`, `src/main.py`, `src/materials.py`, `src/preview.py`, `src/report.py`, `src/validation.py`, `src/operational_validation.py`, `src/geometry/screens.py`, `src/geometry/curtains.py`, `src/geometry/vents.py`, `src/geometry/crops.py`, `src/geometry/equipment_primitives.py`, `src/geometry/fertigation.py`, `src/geometry/pipes.py`, `src/geometry/sensors.py`, `scripts/validate_scene.py`.

신규 모듈은 각각 마감 geometry, 순수 clipping 수학, visibility preset, refinement acceptance, motion keyframe 생성으로 역할을 나눈다. reference PDF/명세, 빈 manage.py는 변경하지 않는다.

## Phase 1.6 GLB moving-object 계약

| 노드 | 제어와 보존할 관계 |
|---|---|
| `GH_VENT_Sxx_01_PIVOT → GH_VENT_Sxx_01 → *_FRAME` | local X 회전; percent/100 × max angle, side 부호 적용 |
| `GH_VENT_Sxx_01_DRIVE → *_SHAFT, *_RACK_A/B, *_PINION, *_MOTOR` | 고정 drive; `control_owner`와 pivot `drive_name`으로 연결; motor는 회전 panel의 자식이 아님 |
| `GH_SHADE_SCREEN_Sxx_PIVOT → GH_SHADE_SCREEN_Sxx` | `retract_axis`(기본 `y`) local scale=`max(1-percent/100,1e-6)`; glTF에서 Blender Y는 local Z; diffuse도 동일 |
| `GH_SHADE_SCREEN_Sxx_RETRACT_BUNDLE` | layer root 아래 독립 노드, `control_owner`; fabric pivot과 함께 축소하지 않음 |
| `GH_SIDEWALL_LEFT/RIGHT → GH_SIDE_CURTAIN_LEFT/RIGHT → *_PANEL` | 상단 고정, panel scale Blender Z / glTF Y; bottom bar가 펼침 길이를 따름 |
| `GH_SENSOR_<ID>_ANCHOR → GH_SENSOR_<ID>` | world position을 label point로 사용, 실제 위치 미검증 |
| `GH_FRONT_WALL → GH_FRONT_DOOR → GH_FRONT_DOOR_PANEL` | X1/negative X 끝의 독립 end-wall assembly; 문은 벽 개구부와 같은 평면에 통합 |
| `GH_REAR_WALL → GH_REAR_WALL_SHELL` | X23/positive X 끝의 독립 마감면; frame-only 상태 금지 |

node extras에는 기존 `asset_type`, `span_index`, `row_index`, `controllable`, `control_variable`, `opening_percent`, `source_confidence`, `geometry_confidence`, `position_confidence`, `verified_position`, `plc_tag_verified`를 유지한다. 신규 `label_anchor`, `service_zone`, `is_circulation_fan`, `lod`, `visual_clipping_applied`, `original_height`, `original_width`, `visible_width`, `preset_hidden`, `view_preset`은 해당 역할의 객체에 존재한다.

glTF export는 `(x,y,z)Blender → (x,z,-y)glTF`의 Y-up 변환을 적용한다. **extras의 수치 자체는 좌표 변환하지 않는다.** 따라서 rack의 `attach_y/z`, `pinion_y/z`와 `config_json` 좌표는 Blender 기준임을 유지하고, 향후 웹 제어에서 명시적으로 변환해야 한다. GLB node transform·sensor anchor world position은 이미 glTF 좌표다. 이번 산출물에는 웹 runtime이나 GLB animation clip을 추가하지 않는다.

기본 service layout은 mesh 경계 사이 최소 `0.35 × visual_asset_scale`m를 검사한다. 기본 배율은 1이며 좁은 온실에서는 전체 service 자산을 축소한다. refinement 모드의 bed end margin은 최소 `3.0 × fertigation.asset_scale`m가 필요하다. 절대 좌표 배치에서 현장 동선 적합성은 별도 확인해야 한다.

## 도면 축과 Front/Rear 계약

도면 6쪽의 `정면도(X1)`를 Front, 10쪽의 `배면도(X23)`를 Rear로 사용한다. 온실 길이축은 Blender X축이다.

| 끝단 | 도면축 | Blender 위치 | 외부에서 보는 방향 |
|---|---|---|---|
| Front | X1 | `(-length/2, 0, 0)`, 기본 `(-48.75, 0, 0)` | +X |
| Rear | X23 | `(+length/2, 0, 0)`, 기본 `(+48.75, 0, 0)` | -X |

이 매핑은 카메라 이름이나 시점에 의존하지 않는다. `config.orientation`과 `GH_ROOT` extras의 `front_axis_reference`, `rear_axis_reference`, `front_end`, `rear_end`, `front_world_position`, `rear_world_position`으로 전달한다. `GH_FRONT_WALL`과 `GH_REAR_WALL`은 독립 노드다.

정면 출입구는 도면의 Y4-Y3 구간을 반영해 기본 `Y=total_width/6`에 두며, 해당 동의 정면(계단형 평면에서는 X3 면)에 붙는다. 문 폭 3.0m·높이 3.0m와 정확한 세부 위치는 판독 가능한 범위의 근사값이며 `verified=false`다. `GH_FRONT_DOOR`는 `GH_FRONT_WALL` 자식이고, 주변 cladding mesh에는 같은 크기의 실제 개구부가 있다. 배면은 panel/windbreak 재질, 마감기둥과 rail을 가진 연속 면이다.

양액 설비는 X1 쪽 end-service strip에 남아 있지만 이는 도면 30쪽의 정확 배치 복원이 아니다. 장비 root에는 `front_axis_reference=X1`, `equipment_access_facing=negative_x`, provisional 배치 설명을 기록했다.

## 검증 기록 (2026-09-24)

Blender 5.2.2 LTS에서 기본 검사 59개, acceptance 시나리오 24개, 순수 Python unittest 24개가 통과했다. acceptance에는 Phase 1/1.5 fixture, 재실행·사용자 객체 보존, 설정 변경, 개폐, GLB 재import와 네 preset export가 포함된다. 전후면 검사에서는 X1/X23 월드 위치, 독립 wall, 벽면에 통합된 door, rear surface를 검사하며, 축 반전·standalone door·투명 rear cladding을 의도적으로 만들어 모두 거부되는지도 확인한다.

`tmp/validation/acceptance_report.json`은 `status=success`, preview 20장과 GLB 재import 후 motion smoke 결과를 포함한다. `tmp/validation/end_wall_report.json`은 전후면 계약을 BLEND와 GLB 양쪽에서 확인한다. `tmp/motion_preview/motion_report.json`도 `status=success`다. Motion은 제어 노드 14개와 고정 anchor 17개를 검사하며 저장된 BLEND를 다시 열어 확인했다. Preview는 측벽 3상태, fabric 펼침/접힘, rack/pinion, 링블로어, service zoning, crop aisle, sensor와 정면·배면·문 상세를 직접 검토했다.

최종 기본 모델 수량과 파일 크기는 `dist/generation_report.json`에 기록한다. 재질 투명도와 LOD는 시각화용이며 현장의 실제 수량·치수·광학 성능을 증명하지 않는다.

## Phase 1.7 — Runnable Local LIVE Django + Three.js

Growlink `/api/live` 형식의 단일 fixture를 `live_data/fixtures/growlink_live_sample.json`에 두고, `live_data.adapter.normalize_growlink_live()`가 zone 1 / house 1을 영문 normalized DTO로 변환한다. 한글 source key는 adapter 밖에서 사용하지 않는다. `live_data.sources.get_live_snapshot()`은 `LIVE_DATA_SOURCE=mock_static|mock_dynamic`을 지원하며 기본값은 `mock_dynamic`이다. 이 모듈에는 네트워크 요청, credential, session, PLC 접근이 없다.

`manage.py`와 `greenhouse_web/`이 로컬 Django project shell을 구성한다. `/`는 실제 Three.js viewer를 렌더하고 `GET /api/digital-twin/live/`는 normalized DTO를 반환한다. DB, 인증, 제어 endpoint는 사용하지 않는다. Django 5.2는 `requirements.txt`와 프로젝트 내부 `.venv`로 관리한다.

브라우저 모듈은 `digital_twin/static/digital_twin/js/`에 있다. `viewer.mjs`가 Three.js, GLTFLoader, OrbitControls로 GLB를 로드하고 `Box3` bounds로 camera near/far, 위치, control target을 자동 설정한다. Three.js 0.180.0 runtime과 license는 `digital_twin/static/digital_twin/vendor/three/`에 포함해 외부 CDN 없이 실행한다. `live-config.mjs`가 2초 polling, 10초 stale 기준, 천창 최대각 90°(fallback)와 모든 GLB 이름을 한 곳에서 관리한다. `live-client.mjs`는 요청 완료 뒤 재귀 `setTimeout`을 예약해 요청 중첩을 방지한다. `live-state.mjs`는 실패 시 마지막 정상 값을 유지하며, `actuator-runtime.mjs`는 render loop에서 약 0.5–1초에 수렴하도록 값을 보간한다. object 누락은 한 번만 경고하고 다른 mapping을 계속 처리한다. `_live_panel.html`, `live-panel.mjs`, `live-panel.css`는 MOCK DATA, 환경값, actuator 값, live/stale/disconnected 상태를 표시한다.

`actuator-runtime.mjs`는 이름과 GLB `userData`를 함께 읽어 roof vent 8개, shade screen 4개, diffuse screen 4개, side curtain 2개의 registry를 만든다. 천창은 local X에 `percent/100 × max_open_angle_deg`를 적용하고 `side` metadata로 부호를 정한다. 두 screen channel의 percent는 Phase 1.6 `opening_percent` 의미를 유지해 `retract_axis`에 해당하는 local scale(`y`면 glTF local Z, 없거나 `x`면 local X)을 `max(1 - percent/100, 1e-6)`로 설정한다. Side curtain은 P2 registry까지만 포함하며 Phase 1.7 LIVE animation 대상은 아니다.

현재 GLB mapping은 다음과 같다.

| normalized channel | Phase 1.6 GLB node | 상태 |
|---|---|---|
| RoofVent_L | `GH_VENT_S01_01_PIVOT`, `GH_VENT_S02_01_PIVOT` | GLB에서 확인, span 분할은 provisional |
| RoofVent_R | `GH_VENT_S03_01_PIVOT`, `GH_VENT_S04_01_PIVOT` | GLB에서 확인, span 분할은 provisional |
| ShadeScreen_01 | `GH_SHADE_SCREEN_S01_PIVOT` … `S04` | GLB에서 확인 |
| ShadeScreen_02 | `GH_DIFFUSE_SCREEN_S01_PIVOT` … `S04` | GLB에서 확인, 두 번째 차광 계통으로 쓰는 의미는 provisional |

천창은 span마다 좌우 hinge pair다. `roof_vent_left_pct`는 모든 span의 `GH_VENT_Sxx_01_PIVOT`(+Y, X1에서 +X를 볼 때 왼쪽), `roof_vent_right_pct`는 `GH_VENT_Sxx_02_PIVOT`(−Y)에 연결한다. Growlink의 좌/우가 실제 어느 쪽인지는 현장 미확인이라 mapping은 provisional로 표시한다. 최대 개방각 90°는 운영자 제보값이다.

Blender → GLB → web 반영 순서는 다음과 같다.

1. `dist/greenhouse.blend`를 수정한다.
2. moving object 이름을 유지하거나 `live-config.mjs` mapping만 갱신한다.
3. 천창과 screen의 origin/pivot을 확인한다.
4. 기존 Blender 생성 명령으로 `dist/greenhouse.glb`를 다시 export한다.
5. `.\.venv\Scripts\python.exe scripts/sync_web_assets.py`로 web GLB asset을 동기화한다.
6. asset cache가 남으면 브라우저를 hard refresh한다.

검증 명령:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/frontend_phase17.test.mjs
.\.venv\Scripts\python.exe scripts/sync_web_assets.py --check
```

로컬 실행:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/sync_web_assets.py
python manage.py runserver 127.0.0.1:8010
```

브라우저에서 `http://127.0.0.1:8010/`을 연다. 수동 확인 항목은 온실 전체가 화면에 맞는지, orbit/zoom/pan이 동작하는지, `MOCK DATA`와 LIVE 값이 보이는지, `mock_dynamic`에서 천창과 두 screen layer가 부드럽게 움직이는지다. 8010은 향후 field PC의 8000번 Growlink endpoint와 혼동하지 않기 위한 개발 포트다. 현재 구현은 field PC, PLC, 실제 Growlink에 요청하지 않는다. Phase 1.8에서는 frontend와 adapter를 유지하고 `live_data.sources.load_raw_snapshot()`의 source 구현만 read-only bridge로 교체한다.

## Phase 1.8 — 3D Viewer & Dashboard UI/UX Refinement

Phase 1.8은 Phase 1.7의 normalized API, 2초 polling, stale/disconnected 상태, actuator 보간과 GLB motion contract를 변경하지 않고 로컬 viewer의 화면 구성과 탐색 기능을 개선한다. 화면 상단은 56px compact header이며 `MOCK DATA`, 연결 상태, 마지막 갱신 시간과 `LOCAL · NO FIELD CONTROL`을 항상 표시한다. LIVE panel은 Indoor, Outdoor, Actuators 카드로 구성되고 우측 화살표로 좁은 LIVE tab까지 접을 수 있다. API 실패와 stale 상태에서도 마지막 정상 값은 유지한다.

카메라는 GLB `Box3` 경계를 사용하며 1440×900 Overview에서 모델이 viewport 폭 약 60–75%, 높이 약 55–70%를 차지하도록 맞춘다. 다음 preset은 600ms 동안 위치와 OrbitControls target을 보간한다.

| View | 방향·초점 | visibility preset |
|---|---|---|
| Overview | 전체 모델 사선 상부 | `exterior` |
| Front | X1 / negative X에서 +X 방향 | `exterior` |
| Rear | X23 / positive X에서 -X 방향 | `exterior` |
| Roof | roof/vent 상부 사선 | `exterior` |
| Interior | 온실 내부 eye-level, crop row 방향 | `interior` |
| Equipment | `GH_FERTIGATION_UNIT` service zone | `equipment` |
| Control | vent, screen, curtain, sensor 범위 | `control_devices` |

`Cover`, `Crops`, `Equipment`, `Sensors`, `Controls` layer toggle은 로드 시 캐시한 root node를 사용한다. preset과 toggle은 매번 6,000개 이상의 node를 다시 순회하지 않는다. Reset은 Overview, GLB 기본 visibility와 선택 해제를 한 번에 복원한다. Fullscreen은 browser Fullscreen API를 사용한다.

roof vent, shade/diffuse screen, side curtain과 sensor는 캐시된 mesh만 raycast한다. hover tooltip과 click selection detail은 GLB extras에 실제로 존재하는 `asset_type`, `span_index`, `control_variable`, `verified`, `verified_position`, confidence와 현재 normalized actuator 값만 표시한다. 선택 highlight는 해당 mesh의 임시 material clone을 사용하고 해제할 때 원본을 복원한다.

평상시 화면에는 mapping/debug text를 표시하지 않는다. Developer drawer에서만 GLB load 상태, scene node 수, actuator registry, raycast target 수, source, connection, 현재 camera preset, 마지막 API 성공 시간과 provisional mapping을 확인한다. 현재 provisional 계약은 그대로다.

- `RoofVent_L`: `GH_VENT_S01_01_PIVOT`, `GH_VENT_S02_01_PIVOT`
- `RoofVent_R`: `GH_VENT_S03_01_PIVOT`, `GH_VENT_S04_01_PIVOT`
- `ShadeScreen_01`: 네 `GH_SHADE_SCREEN_Sxx_PIVOT`
- `ShadeScreen_02`: 네 `GH_DIFFUSE_SCREEN_Sxx_PIVOT`
- vent 최대 90°는 운영자 제보값이며, 개도율과 각도는 선형으로 가정한다.

desktop-first 검토 해상도는 1920×1080, 1440×900, 1366×768이다. 좁은 화면에서는 LIVE panel overlay와 하단 toolbar가 축소 또는 가로 스크롤되며 핵심 조작을 유지한다.

검증 명령:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/frontend_phase17.test.mjs tests/frontend_phase18.test.mjs
.\.venv\Scripts\python.exe scripts/sync_web_assets.py --check
```

실행 명령은 Phase 1.7과 같으며 `http://127.0.0.1:8010/`에서 확인한다. Blender 수정 후에는 `dist/greenhouse.glb`를 다시 export하고 `scripts/sync_web_assets.py`로 web asset을 동기화한다. 현재 source는 `mock_static` 또는 `mock_dynamic`뿐이며 실제 Growlink, PLC, credential, field control 연결은 포함하지 않는다.

## Phase 1.9 — Physics Data Contract

물리 데이터 경계는 [physics/README.md](physics/README.md)에 정의되어 있다.
`physics.builder.build_physics_input()`은 기존 normalized LIVE DTO를 받아
측정 상태·외기 disturbance·actuator·물리 파라미터를 분리한다. 기존 Django
API와 Phase 1.8.1 viewer는 변경하지 않는다. 물리 config는 `config/physics/`에
독립 보관하며, 시각용 opacity/roughness를 광학 투과율로 사용하지 않는다.

Physics는 Blender와 같은 meter/X-length/Y-width/Z-up 우수 좌표계이며,
Three.js world 변환은 `(x,y,z) → (x,z,-y)`다. +X는 X1 Front→X23 Rear이고
지리적 방위각은 북쪽 기준 시계방향이다. 위경도·고도·방위·광학계수는 제보·조회값을
unverified로 기록했고, 작물 기준 높이는 null이다. 천창은 0% 닫힘/100% 열림,
스크린은 0% 전개/100% 수납이며 물리 전개율은 `1 - opening_percent/100`이다.

Phase 2.0은 `PhysicsInput`, `SolarOutput`, `RadiationOutput`과 좌표 helper를
재사용할 수 있다. 현재는 입력 검증·품질 표시만 수행하며 ray/thermal/MPC
계산과 현장 연결은 없다. 테스트 및 mock-only 사용 예는 physics 문서에 있다.

> Phase 1.9 defines the physics interface but does not yet claim physically validated greenhouse radiation or thermal predictions.

## Phase 1.8.1 ? Interactive Spatial Navigation

The viewer now follows **Greenhouse ? Span ? Asset ? Context**. ALL/S1/S2/S3/S4 and direct roof-surface picking share one immutable selection state. Roof vents, shade/diffuse screens, side curtains, sensor assets and equipment groups can be selected in 3D. Equipment subparts resolve to their owning tank, pump, blower, filter or panel. Crop Zone supports focus and metadata only.

The right Context Panel contains LIVE, HISTORY and DETAILS tabs. Greenhouse shows a concise house overview; Span shows mapped actuators plus **House-level sensor ? Not span-specific** environment; Asset shows only supported channel data and existing metadata. Breadcrumbs return to the parent span or greenhouse. Sensor anchors have no verified LIVE ownership and receive no inferred environmental reading. Side curtains have no span mapping. History is an empty shell; alerts remain ?Not configured?.

Camera presets describe **how** to view the current selection; span buttons describe **where**. Fit Selected uses current mesh bounds and a 600ms camera transition. Reset Camera keeps selection; Back to Overview clears it. Front remains X1/negative X and Rear X23/positive X. Layers control Cover/Crops/Equipment/Sensors. Overlays independently control Control State emphasis and hover Labels; the selected label stays visible.

The slate background, directional roof lighting, neutral vent-panel contrast and restrained selected vent edges improve mechanical readability. Other spans are dimmed through cached material variants, without opacity changes. Control State mutes structure/crops. Shared originals and actuator transforms are preserved. Registries are built in one full scene traversal; pointer picking uses cached targets, and the render loop never searches the scene.

### sfes execution and validation

The specification's project-local activation command applies when that environment exists:

```powershell
.\sfes\Scripts\Activate.ps1
```

On this workstation the existing sfes environment is Conda-based at
`C:\Users\user\anaconda3\envs\sfes`, not a project-local directory.
Use `conda activate sfes` in an initialized Conda shell, or its Python executable directly. The environment was preserved and the missing Django requirement installed.

```powershell
python scripts/sync_web_assets.py
python manage.py check
python -m unittest discover -s tests -v
node --test tests/*.test.mjs
python scripts/sync_web_assets.py --check
python manage.py runserver 127.0.0.1:8010
```

Open http://127.0.0.1:8010/ and hard-refresh after changes. No field networking or write endpoint was added. Existing provisional L/R span split, diffuse-as-Screen-2 mapping and 35? visual angle remain unchanged.

Automated checks cover actual GLB raycasts, unified selection, honest context data, shared-material restoration, camera focus and moving bounds. Browser visual acceptance at 1440?900 remains pending because the available browser runtime reported no connected browser. In particular, roof opening readability, contextual label placement and the complete mouse navigation flow require rendered verification before declaring the phase fully accepted.

## LIVE mock VPD·이슬점 계산 (2026-09-30)

`mock_dynamic`은 실내온도와 내부습도만 변동시키고 VPD·이슬점은 fixture 고정값(0.005 kPa, 28.0℃)을 그대로 반환해 온습도와 불일치했다. 이제 `live_data/psychrometrics.py`의 `vpd_kpa()`, `dew_point_c()`가 같은 Tetens/Magnus 상수로 두 값을 온습도에서 계산하고, `build_dynamic_raw()`가 이를 mock override로 주입한다. `adapter.py`의 `_MOCK_ENVIRONMENT_PATHS`에는 `vpd_kpa → meas.VPD`, `dew_point_c → meas.이슬점`만 추가했다.

`normalize_growlink_live()`, `mock_static`, normalized DTO 형식과 frontend는 변경하지 않는다. 실제 Growlink source에서는 계속 센서가 보낸 VPD·이슬점을 사용한다. `mock_static` fixture의 이슬점(34.0℃/99.6%에서 28.0℃)은 온습도와 맞지 않지만 수집 샘플로 보고 유지한다. 수정 후 `manage.py check`, Python test 61개, Node test 21개가 통과했다.

## 지붕 형상 도면 측정값 반영 (2026-09-30)

도면 6~10쪽 단면의 벡터 좌표를 축척 1/150(1pt = 52.94mm, span 8,000과 측고 5,000 치수로 교차 확인)으로 측정했다. 모든 span에서 반쪽 아치는 오차 0mm의 원호이며 반경 약 8,193mm, 용마루는 G.L 기준 7,500mm다. `config/greenhouse.json`의 처마를 4.2→5.0m, 용마루를 5.0→7.5m로 바꾸고 `roof.profile=circular_pointed_arch`, `roof.arch_radius=8.193`을 추가했다.

`geometry_math.arch_height()`는 선택 인자 `radius`를 받아 원호를 계산하고, 없으면 기존 Bezier를 그대로 쓴다. 지붕 높이를 쓰는 cover·roof·sidewalls·vents·refinement_math는 `roof_arch_radius(g)`만 추가로 넘긴다. `config_loader`는 반경이 처마–용마루 현의 절반보다 작으면 거부한다. 원호는 처마 경사가 약 49°로 가팔라 끝벽 분할 방식에 따라 면적 비교 검사가 흔들리므로, 출입구 분할선을 정면뿐 아니라 배면에도 같이 넣는다. `tests/test_refinement.py`의 고정 높이(4.2/5.0)는 config 값으로 대체했다.

Blender 5.2.2에서 재생성 후 `validate_scene.py --roundtrip --acceptance --render-previews`가 acceptance 24개를 포함해 통과했고, `scripts/sync_web_assets.py --check`로 web GLB 동기화를 확인했다. Python test 61개, Node test 21개, `manage.py check`가 통과했다. 객체 수는 변하지 않았다.

## 천창 좌우 2장·현장 정보 반영 (2026-09-30)

도면 9쪽 용마루 단면은 힌지 하나에 좌우 2장이 각자의 랙으로 열리는 나비형이고, 4쪽 지붕평면도는 용마루마다 천창 띠 2줄과 모터 2개(X11–X12)를 보여 준다. 띠 폭은 한 장 1.21m, 긴 2동은 95.07m, 짧은 2동은 86.10m이며 모터 위치에서 끊기지 않는다. 운영자 제보(좌우 독립, 폭 1.2m, 양끝 1m 제외, 100% = 90°)와 일치해 `roof_vents`를 `mode=paired_ridge_vents`, `side=both`, `end_clearance=1.0`, `max_open_angle_deg=90`으로 바꿨다. 이후 계단형 평면 반영으로 짧은 2동의 천창은 동 길이 88.5m에서 양끝 1m를 뺀 86.5m가 되었다.

`vent_bounds(config, side)`와 `vent_sides()`로 좌우 범위를 따로 계산하고, cover 개구부·object count·acceptance 검사는 양쪽을 순회한다. 기존 `GH_VENT_Sxx_01` 이름은 +Y쪽에 유지하고 −Y쪽을 `_02`로 추가했다. web은 `천창 좌(L)`을 `_01`, `천창 우(R)`을 `_02`에 잠정 연결한다.

`config/physics/`에는 운영자 제보를 `source_type=operator_reported`, `verified=false`로 기록했다: 1중 PO 필름 투과율 0.85, 차광 스크린(알루미늄, 75% 차광, 보온 겸용) 0.25, 산란 스크린(20% 차광) 0.80, +X 방위 269°(X1 = 동쪽 가정, 서쪽이면 89°). 상부 보온커튼과 별도 보온 스크린은 없다. 스크린은 동별이 아니라 일괄 구동이며 100%가 열림이다. `차광커튼1/2`와 차광/산란 스크린의 대응, Growlink 좌/우의 방향, 89°가 진북 기준인지는 미확인이다. 일사 센서는 PAR이며 W 단위로 들어온다고 하나 외부 설치 여부와 PAR W/m²인지 전천일사인지는 확인이 필요하다. 위경도·고도는 다음 섹션에서 추가했다.

Blender 5.2.2에서 재생성(roof vent 8개) 후 `validate_scene.py --roundtrip --acceptance --render-previews`가 acceptance 24개와 motion smoke test를 포함해 통과했다. Python test 61개, Node test 21개가 통과했고 web GLB를 동기화했다. Node test의 L/R 이름·천창 수 기대값과 physics 기본 설정 test는 새 상태에 맞게 갱신했다.

## 계단형(L자) 평면과 위경도 반영 (2026-09-30)

도면 2·4·25·30쪽에서 Y1–Y3 두 동은 X1부터 97.5m, Y3–Y5 두 동은 X3부터 88.5m이고 앞쪽에 9m × 16m 빈 모서리가 있다. 출입구는 이 모서리 안쪽 X3 면의 Y3–Y4 사이에 있다. `greenhouse.span_start_offsets=[0,0,9,9]`로 동별 시작 위치를 지정하며, 값이 없으면 모두 0이라 기존·legacy config는 그대로 직사각형이다.

`geometry_math`의 `span_x_range`, `gridline_x_start`, `front_x_at`, `stations_from`으로 동·격자선별 범위를 계산한다. 기둥·트러스·서까래는 전체 격자 번호를 유지한 채 빈 모서리 위치만 건너뛰고(주기둥 115→111, 샛기둥 110→106, 서까래 352→336), 물받이·용마루재·외피·천창·스크린·베드·작물·측벽·측면 커튼은 동 또는 바깥 동 길이를 따른다. 정면 외피·기둥·가로재는 동별 정면(X1 또는 X3)에 두고, 두 정면 사이 y=0 격자선에 `GH_FRONT_STEP_WALL_Y03`(지면~처마)을 추가했다. 출입구는 X3 면으로 옮겼다. 급수 헤더는 모든 동이 존재하는 위치로 옮겨 건물 밖에 놓이지 않게 했다. 양액 설비는 긴 동(y<0) 안에 그대로 있다. 30쪽은 베드를 Y1–Y3 두 동에만 두지만, 베드는 4동 모두에 두고 동 길이에 맞춘다.

검증은 정면 외피가 각 동의 정면 평면 위에 있는지, 출입구가 해당 동 정면에 붙었는지, 외피 개구부가 동별 천창 범위와 겹치지 않는지 확인한다. 3연동 변형 시나리오는 offset 목록을 앞 3개로 자르고, 60m 변형의 베드 길이 검사는 S01 베드를 쓴다.

`config/physics/site.json`에 위도 35.8370, 경도 126.7090, 고도 3m를 사용자 제공 조회값(`operator_reported`, `verified=false`)으로 기록했다. 조회 방법은 기록되지 않았다.

Blender 5.2.2에서 재생성 후 `validate_scene.py --roundtrip --acceptance --render-previews`가 acceptance 24개와 motion smoke test를 포함해 통과했다. Python test 61개, Node test 21개가 통과했고 web GLB를 동기화했다. physics 기본 설정 test는 위경도가 채워진 상태에 맞게 출처 검사로 바꿨다.

## 스크린 좌우(폭 방향) 구동 (2026-09-30)

현장에서는 스크린이 동 길이 방향이 아니라 폭 방향(좌우)으로 움직인다. 도면 28쪽은 드럼 축(Ø48.1)이 측벽을 따라 X 방향으로 놓이고, 27쪽은 예인 와이어가 온실을 가로질러 스크린을 끌며 접힌 묶음이 X 방향으로 길게 놓인 구조를 보여 준다. `shade_screen`·`diffuse_screen`에 `travel=across_span`, `gather_side=negative_y`를 추가했다. 동마다 −Y 물받이 쪽에 pivot과 묶음을 두고 local Y scale로 접으며, 구동 축·드럼·롤러는 물받이를 따라 X 방향으로 둔다. 어느 쪽 물받이에 모이는지는 도면으로 확정되지 않아 잠정값이다. `travel`이 없는 legacy config는 기존 X 방향 수납을 그대로 쓴다.

pivot extras의 `retract_axis`(`x`/`y`)를 생성·검증·motion preview·web runtime이 공통으로 읽는다. glTF export에서 Blender local Y scale은 local Z로 바뀌므로 web은 `retract_axis=y`이면 `scale.z`를 조절하며, 실제 GLB에서 차광 30%가 `[1, 1, 0.7]`로 기록되는 것을 확인했다. Node test의 스크린 scale 기대값은 `scale.z`로 바꿨다.

## 온실 방위 측정값 반영 (2026-10-01)

현장 나침반 측정으로 용마루(장축) 방향이 진북 기준 104°이고 X1 출입구가 동쪽 끝임을 확인했다. physics +X(X1→X23, 동→서)의 방위를 104 + 180 = 284°로 `config/physics/site.json`에 기록했다(`source_type=measured`, `verified=false`). 이전 운영자 추정(약 89°, 정동서)과 15° 차이가 있다. 나침반 값이 자북 기준이라면 진북 방위는 약 8~9° 작고(+X 약 275~276°), 철골 구조 근처에서는 나침반이 틀어질 수 있으므로 위성사진으로 교차 확인이 필요하다. API에는 `차광커튼1/2`만 있고 산란 스크린 이름의 채널은 없어, `차광커튼1` → 차광, `차광커튼2` → 산란 대응은 잠정으로 유지한다.

## 3D 광 모델과 태양·그림자 시각화 (2026-10-01)

`physics/light_model.py`는 2D 샘플(`light_sample.py`)을 뷰어 GLB 형상으로 확장한 광 모델이다(검증 전 프레임워크). GLB에서 골조(서까래·트러스·기둥·물받이·용마루재·끝벽 기둥/가로재)와 샌드위치 판넬은 불투명, 피복·방풍벽·측벽·측면 커튼은 PO 필름(Fresnel 투과율, 수직 0.85로 보정)으로 읽고, 천창과 스크린은 GLB의 기본 자세 대신 LIVE 개도로 해석적으로 처리한다. 스크린은 Miguel et al.(1994)처럼 완전 확산층으로 보고, 산란광은 코사인 가중 하늘 방향 48개의 형상 경로를 한 번 추적해 `tmp/light_cache/`에 캐시한다. 직달광은 셀(1m)마다 3×3 광선으로 평균해 가는 부재의 줄 그림자를 다룬다. 출력은 작물 상단(3.0m) 평면의 전천일사·PAR 격자와 평균, 직달 받는 면적 비율이다. 반사, 외부 지면 반사, 작물 감쇠는 아직 없다.

의존성으로 `numpy`, `trimesh`, `rtree`, `embreex`를 `requirements.txt`에 추가했다. Embree가 없으면 순수 numpy 광선으로 수십 분 이상 걸리므로 사실상 필수다. 첫 계산은 약 1.5초, 이후 상태별 계산은 약 0.1초다.

`GET /api/digital-twin/solar/`는 태양 위치(physics/three.js 방향), 하루 태양 궤적, 외부 일사, 작물 상단 PAR 격자와 평균을 돌려준다. `time` 없이 호출하면 현재 시각과 LIVE 일사·구동기 값을 쓰고, `?time=2026-10-01T09:30`처럼 시각을 주면 외부 일사를 Zhang et al.(2020)의 맑은 날 모델(P=0.75)로 추정한다. 응답의 `provenance.validated`는 항상 false다.

뷰어 왼쪽 아래 패널에 Sun 줄(Sun & Shadow, Light Map)과 Time 줄(하루 시간 슬라이더, Now)을 추가했다. 태양은 실제 위경도·방위·시각 기준 위치에 표시되고 하루 궤적이 점선으로 보이며, 골조와 차광 스크린이 바닥·베드·작물에 그림자를 드리운다(필름 피복은 그림자를 만들지 않는다). Light Map은 모델이 계산한 작물 상단 PAR 분포를 색으로 겹쳐 보여 준다. 그림자는 시각화용이며 정량값은 Light Map과 API 값을 기준으로 한다. `?time=09:30&lightmap=1&view=interior`처럼 URL로 시각·표시·시점을 지정할 수 있다.

뷰어 페이지는 정적 파일이 바뀌면 달라지는 버전 토큰(`?v=`)을 CSS·GLB·JS 주소에 붙이고, JS 모듈 사이의 상대 경로와 `three` 지정자도 import map으로 같은 버전 주소에 연결한다. 페이지 자체는 `Cache-Control: no-cache`로 내보낸다. 개발 서버의 정적 파일 응답에는 캐시 헤더가 없어 브라우저가 예전 모듈을 재사용하던 문제를 막기 위한 것이다.

## 일사 모델 v1: 구현 명세 기반 재구성 (2026-10-01)

`physics/eqations/greenhouse_ray_tracing_implementation_spec.md`만을 근거로 새 모델 `physics/radiation_v1/`을 만들었다. 기존 `physics/light_sample.py`, `physics/light_model.py`, `/api/digital-twin/solar/`는 **참고 구현**으로 그대로 남기고, 새 모델은 그 식과 가정(Spencer 태양식, Erbs 분리, Fresnel 투과율, 맑은 날 모델, PAR=0.47, 천창 간극식, 셀 3×3 평균, 48방향 산란)을 쓰지 않는다.

구성: `config.py`(명세 15절 형식 `config/radiation_v1/site.json·optical.json·radiation.json`), `solar.py`(pvlib NREL SPA, 겉보기 고도), `geometry.py`(1m 작물 격자, GLB 의미 분류, 천창 판 회전), `screens.py`(개도 의미, 전개 영역), `raytrace.py`(r(λ)=p+λs), `radiation.py`(명세 8절 v1 식), `aggregation.py`(면적 가중 평균·min·max·p10/p50/p90·sunlit 비율), `adapters/live_to_physics.py`, `service.py`. 좌표 변환은 `physics/coordinates.py`의 `enu_from_altitude_azimuth`, `enu_to_greenhouse`로 모았다.

식: I_dir,j = DNI·max(0, n·s)·τ_cover·T_screen,j·S_j, I_diff,j = DHI·τ_cover,diff·T_screen,diff,j·F_sky(=1), I_total = I_dir + I_diff, I_eff = Σ I_j A_j / Σ A_j. 밤에는 직달 0, 불투명 차단(S_j=0)이면 직달 0이다. 골조와 정면 샌드위치 판넬은 불투명, 지붕 PO 필름과 천창 판은 피복, 끝벽 방풍벽·측벽·측면 커튼은 광학값이 없어 `UNKNOWN_OPTICS`로 두며 이를 지나는 셀의 직달은 None이다. 천창 판과 틀은 GLB의 저장 자세(±18°)에서 실제 개도 각도로 회전한다(개도와 각도의 관계는 기존 선형 계약, 미검증). 스크린은 개도에 따른 전개 영역을 광선이 지나면 τ_screen을 곱하고, 산란은 셀 바로 위 전개 여부로 정한다. 피복 산란 투과율·스크린 산란 투과율이 null이고 LIVE에는 GHI만 있어(`decompose_ghi`는 문헌 검토 전까지 NotImplementedError), 현재 상태는 `decomposition_required`이며 일사값은 None, 형상 기반 sunlit 지도만 계산된다. 값은 0으로 채우지 않는다.

`GET /api/digital-twin/radiation/v1/`는 명세 30절 형식(solar, radiation status·통계·격자, provenance)에 뷰어용 태양 궤적과 three.js 방향을 더해 돌려준다. `time`을 주면 측정 기상값이 없으므로 `missing_input`이다. 뷰어는 기본으로 v1을 쓰고, `?model=reference`로 참고 모델을 쓴다. v1의 Light Map은 모든 셀에 일사값이 생기기 전까지 sunlit/그늘 지도를 표시한다. 명세 25절 테스트(태양 위치, 정규화, 기둥 그림자 L=H/tanα, 오전 서쪽·오후 동쪽 그림자, 불투명 차단, 피복 감쇠, 스크린 전개, 단조성, 누락≠0)는 `tests/test_radiation_v1.py`에 있다. `pvlib`를 `requirements.txt`에 추가했다.


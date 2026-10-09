# 1단계 구현 명세 — 온실 구조 JSON → Blender 자동 생성 → GLB Export

> 목적: Codex가 이 문서만 읽고도 **현재 농가 도면을 기준으로 한 파라메트릭 3D 온실 생성기**를 구현할 수 있도록 한다.  
> 이번 단계에서는 **AI 도면 해석, Django, Three.js 대시보드, PLC, 센서 실시간 연동, MPC는 구현하지 않는다.**  
> 오직 `greenhouse.json → Blender scene → .blend + .glb` 파이프라인을 안정적으로 완성한다.

---

## 0. Codex에게 주는 최상위 지시

당신은 Blender Python 기반의 **파라메트릭 스마트온실 3D 모델 생성기**를 구현한다.

반드시 아래 원칙을 지킨다.

1. 소스 도면은 프로젝트 루트의 `reference/` 아래에 둔다.
2. 도면을 직접 OCR/AI 분석하는 기능은 이번 단계에서 구현하지 않는다.
3. 이번 단계의 입력은 사람이 확정한 `config/greenhouse.json`이다.
4. 모든 치수 단위는 **meter**로 통일한다.
5. Blender scene의 각 주요 설비는 **분리된 Object 또는 Collection**으로 생성한다.
6. 이후 Three.js에서 객체를 이름으로 찾고 애니메이션할 수 있도록 **안정적인 naming convention**을 사용한다.
7. 천창과 스크린은 향후 PLC/MPC 연동을 위해 반드시 **움직일 수 있는 독립 객체**로 만든다.
8. 실측 도면에 없는 치수는 임의로 "정답"처럼 확정하지 않는다.
9. 불확실한 값은 JSON에서 `verified: false` 또는 `assumption`으로 명시한다.
10. 구조적으로 중요한 파라미터를 코드에 하드코딩하지 않는다. 가능한 한 JSON에서 읽는다.
11. Blender GUI에서 실행할 수 있어야 하고, 가능하면 CLI/headless 실행도 지원한다.
12. 최종 산출물은 최소한 다음을 포함한다.
    - `dist/greenhouse.blend`
    - `dist/greenhouse.glb`
    - `dist/generation_report.json`
    - README 실행 방법
13. `.glb`는 Three.js에서 바로 사용할 수 있게 glTF 2.0 형식으로 export한다.
14. 웹 프론트엔드 코드는 이번 단계에서 만들지 않는다.
15. "예쁘기만 한 단일 mesh"가 아니라, 이후 실시간 상태 연동이 가능한 **구조화된 scene graph**를 만든다.

---

# 1. 프로젝트 목표

현재 보유한 스마트온실 시공 도면을 참고하여 아래 구조를 구현한다.

```text
config/greenhouse.json
        ↓
Blender Python Generator
        ↓
Structured Blender Scene
        ↓
greenhouse.blend
        ↓
GLB Export
        ↓
greenhouse.glb
```

이번 단계의 성공 조건은:

> `greenhouse.json`의 주요 파라미터를 변경하면 Blender에서 온실 폭, 길이, 연동 수, 지붕, 천창, 스크린, 내부 베드가 자동으로 다시 생성되어야 한다.

즉, **특정 온실 한 개를 손으로 모델링하는 프로젝트가 아니라, JSON 기반 파라메트릭 생성기를 만드는 것**이 핵심이다.

---

# 2. 현재 도면에서 확인 가능한 기준 정보

소스 PDF:

```text
MS80_김제 팜큐베이터_260921_204721.pdf
```

도면 전체는 40페이지이며, 이번 1단계에서 가장 중요한 페이지는 다음과 같다.

## 2.1 기본 모델

도면 표기:

```text
MS 8.0 Model
8m x 97.5m - 4연동
```

따라서 기본 구조:

```text
span_count = 4
span_width = 8.0 m
length = 97.5 m
total_width = 32.0 m
```

---

## 2.2 평면 구조

도면 평면도에서 다음 nominal spacing이 확인된다.

```text
주기둥: @4500 mm
샛기둥: @2250 mm
서까래: @1125 mm
```

따라서 config 기본값:

```text
main_column_spacing = 4.5 m
secondary_column_spacing = 2.25 m
rafter_spacing = 1.125 m
```

주의:

- 97.5 m 길이와 spacing이 정확히 정수배로 맞지 않을 수 있다.
- 마지막 bay는 자동 clipping 또는 별도 end offset 처리를 해야 한다.
- 생성기가 "길이를 spacing에 맞춰 임의 변경"하면 안 된다.
- **전체 길이 97.5 m를 우선 보존**하고 마지막 구간만 조정한다.

---

## 2.3 높이

정면도/단면도에서 다음 높이 표기가 확인된다.

```text
3.2 m
4.2 m
5.0 m
```

이번 1단계에서는 다음처럼 처리한다.

```text
eave_height = 4.2 m          # provisional
ridge_height = 5.0 m        # provisional
```

단, 도면의 모든 3.2/4.2/5.0 치수 의미를 완전히 구조해석한 것은 아니므로 JSON에 다음 metadata를 둔다.

```json
{
  "value": 4.2,
  "verified": false,
  "source": "front_elevation",
  "note": "Provisional interpretation for Phase 1"
}
```

**중요:** 코드에서 이 값을 "실측 확정값"이라고 표현하지 않는다.

---

## 2.4 지붕

온실은 4연동이며 각 span에 곡면형 지붕을 갖는다.

이번 단계에서는 구조해석용 CAD 수준의 정확한 곡률 대신 웹 시각화에 적합한 **parametric arch roof**를 만든다.

권장:

```text
roof_profile = bezier_arch 또는 circular_arc
span_width = 8.0
eave_height = 4.2
ridge_height = 5.0
```

지붕 외피와 프레임은 별도 객체로 구분한다.

---

## 2.5 천창

도면에서 다음이 확인된다.

```text
천창(양랙)
천창축
천창 프레임
피니언 기어
랙
천창 개폐 모터
```

따라서 이번 3D에서는 다음만 표현한다.

```text
RoofVent system exists
Vent panel is a separate movable object
Rack/pinion mechanism은 단순화된 visual geometry로 표현 가능
```

정밀 기계 CAD 모델은 필요 없다.

천창은 추후 다음 값을 입력받아 움직일 수 있어야 한다.

```text
opening = 0.0 ~ 1.0
```

또는

```text
opening_percent = 0 ~ 100
```

따라서 vent는 반드시 hinge/pivot를 가진 독립 Object로 생성한다.

예:

```text
GH_VENT_S01_01
GH_VENT_S02_01
GH_VENT_S03_01
GH_VENT_S04_01
```

---

## 2.6 차광 스크린

도면:

```text
차광 스크린(75%)
설치 높이 표기: 약 4.8 m
```

따라서:

```text
shade_screen.enabled = true
shade_screen.height = 4.8
shade_screen.transmittance_visual = 0.25
```

`transmittance_visual`은 시각 효과용 값이며 물리 모델 파라미터로 사용하지 않는다.

스크린은 추후 0~100% 개폐를 표현하기 위해 독립 객체로 만든다.

---

## 2.7 산광 스크린

도면:

```text
산광 스크린
높이 표기: 약 4.55 m
```

따라서:

```text
diffuse_screen.enabled = true
diffuse_screen.height = 4.55
```

이번 1단계에서는 산광 스크린을 하나의 반투명 horizontal layer로 단순화해도 된다.

---

## 2.8 토마토 베드

양액 배치도에서 다음이 확인된다.

```text
토마토베드: 동당 5줄
```

4연동이므로 기본 시각화 베드 개수는:

```text
5 beds/span × 4 spans = 20 beds
```

이번 단계에서는 작물 하나하나를 고폴리곤으로 생성하지 않는다.

베드는 긴 직육면체 또는 low-poly gutter/trough 형상으로 만든다.

필요하면 `show_plants` 옵션으로 매우 단순한 plant instance를 표시할 수 있게 설계하되 기본값은 false로 둔다.

---

# 3. 이번 단계의 명확한 범위

## 반드시 구현

```text
✅ JSON config parser
✅ Scene reset
✅ meter 기반 Blender unit 설정
✅ 바닥
✅ 4연동 온실 frame
✅ 주기둥
✅ 샛기둥
✅ 지붕/서까래의 시각적 표현
✅ 곡면 지붕
✅ 반투명 피복
✅ 천창
✅ 차광 스크린
✅ 산광 스크린
✅ 토마토 베드
✅ 기본 재질
✅ Collection 구조
✅ Object naming
✅ 카메라
✅ 기본 조명
✅ .blend 저장
✅ .glb export
✅ 생성 결과 report
✅ CLI 실행
✅ README
```

## 이번 단계에서 구현하지 않음

```text
❌ PDF AI 해석
❌ OCR
❌ CAD/DXF reconstruction
❌ BIM 수준 정확도
❌ 구조해석
❌ PLC 연결
❌ 센서 실시간 데이터
❌ Django
❌ Three.js dashboard
❌ WebSocket
❌ MPC
❌ 열수지 모델
❌ 물리 기반 스크린 광학 모델
❌ CFD
❌ 정밀 기계 rack/pinion CAD
```

---

# 4. 권장 폴더 구조

Codex는 다음 구조를 생성한다.

```text
greenhouse-3d-generator/
│
├─ README.md
├─ .gitignore
│
├─ reference/
│  └─ MS80_김제_팜큐베이터.pdf
│
├─ config/
│  ├─ greenhouse.json
│  └─ greenhouse.schema.json
│
├─ src/
│  ├─ __init__.py
│  ├─ main.py
│  │
│  ├─ config_loader.py
│  ├─ scene_setup.py
│  ├─ materials.py
│  ├─ naming.py
│  ├─ report.py
│  │
│  ├─ geometry/
│  │  ├─ __init__.py
│  │  ├─ primitives.py
│  │  ├─ frame.py
│  │  ├─ roof.py
│  │  ├─ cover.py
│  │  ├─ vents.py
│  │  ├─ screens.py
│  │  └─ beds.py
│  │
│  └─ export/
│     ├─ __init__.py
│     ├─ save_blend.py
│     └─ export_glb.py
│
├─ scripts/
│  ├─ generate_greenhouse.py
│  └─ validate_scene.py
│
├─ tests/
│  ├─ test_config.py
│  ├─ test_geometry_math.py
│  └─ test_naming.py
│
└─ dist/
   ├─ greenhouse.blend
   ├─ greenhouse.glb
   └─ generation_report.json
```

한 파일에 모든 기능을 몰아넣지 않는다.

---

# 5. 좌표계 규칙

반드시 아래 규칙을 통일해서 사용한다.

```text
X = 온실 길이 방향
Y = 온실 폭 방향
Z = 높이
```

원점:

```text
온실 전체 footprint의 중앙 바닥점 = (0, 0, 0)
```

따라서:

```text
X ∈ [-48.75, +48.75]
Y ∈ [-16.0, +16.0]
Z >= 0
```

4개 span의 중심 Y 좌표는 자동 계산한다.

예:

```text
span 1 center = -12
span 2 center = -4
span 3 center = +4
span 4 center = +12
```

span boundary:

```text
-16, -8, 0, +8, +16
```

코드에 숫자를 직접 하드코딩하지 말고 span_count와 span_width로 계산한다.

---

# 6. JSON 데이터 모델

`config/greenhouse.json` 기본값을 아래처럼 작성한다.

```json
{
  "metadata": {
    "project_name": "MS80_Gimje_Farmcubator",
    "source_drawing": "MS80_김제_팜큐베이터_260921_204721.pdf",
    "unit": "m",
    "phase": 1
  },

  "greenhouse": {
    "span_count": 4,
    "span_width": 8.0,
    "length": 97.5,

    "eave_height": {
      "value": 4.2,
      "verified": false,
      "note": "Phase 1 provisional interpretation"
    },

    "ridge_height": {
      "value": 5.0,
      "verified": false,
      "note": "Phase 1 provisional interpretation"
    },

    "roof": {
      "type": "arched_multi_span",
      "profile": "bezier_arch",
      "segments_per_span": 24
    }
  },

  "structure": {
    "main_column_spacing": 4.5,
    "secondary_column_spacing": 2.25,
    "rafter_spacing": 1.125,

    "main_column": {
      "width": 0.125,
      "depth": 0.075
    },

    "secondary_column": {
      "width": 0.125,
      "depth": 0.075
    },

    "visual_frame_radius": 0.035
  },

  "cover": {
    "enabled": true,
    "opacity": 0.22,
    "roughness": 0.32
  },

  "roof_vents": {
    "enabled": true,
    "mode": "one_visual_vent_per_span",
    "opening_percent": 20,
    "max_open_angle_deg": 35
  },

  "shade_screen": {
    "enabled": true,
    "height": 4.8,
    "opening_percent": 30,
    "visual_opacity": 0.36
  },

  "diffuse_screen": {
    "enabled": true,
    "height": 4.55,
    "opening_percent": 100,
    "visual_opacity": 0.16
  },

  "crop_beds": {
    "enabled": true,
    "rows_per_span": 5,
    "length_margin": 4.0,
    "width": 0.55,
    "height": 0.25,
    "z": 0.55,
    "show_plants": false
  },

  "ground": {
    "enabled": true,
    "margin": 5.0
  },

  "render": {
    "add_camera": true,
    "add_lights": true,
    "preview_resolution_x": 1600,
    "preview_resolution_y": 900
  },

  "export": {
    "blend_path": "dist/greenhouse.blend",
    "glb_path": "dist/greenhouse.glb",
    "report_path": "dist/generation_report.json",
    "apply_modifiers": true
  }
}
```

---

# 7. JSON Schema

`greenhouse.schema.json`을 작성해서 최소한 다음 validation을 한다.

```text
span_count >= 1
span_width > 0
length > 0
ridge_height > eave_height
spacing > 0
0 <= opacity <= 1
0 <= opening_percent <= 100
rows_per_span >= 0
max_open_angle_deg >= 0
```

Config 오류 발생 시:

```text
Traceback만 출력하지 말고,
어떤 필드가 왜 잘못되었는지 사용자 친화적 error message를 출력한다.
```

예:

```text
[CONFIG ERROR]
greenhouse.ridge_height.value must be greater than greenhouse.eave_height.value.
Received: ridge=4.0, eave=4.2
```

---

# 8. Blender Scene Collection 구조

최종 Blender scene은 최소 다음 구조를 갖는다.

```text
GH_ROOT
│
├─ GH_STRUCTURE
│  ├─ GH_COLUMNS_MAIN
│  ├─ GH_COLUMNS_SECONDARY
│  ├─ GH_RAFTERS
│  ├─ GH_TRUSSES
│  └─ GH_GUTTERS
│
├─ GH_ROOF
│  ├─ GH_ROOF_FRAME
│  └─ GH_ROOF_COVER
│
├─ GH_VENTS
│  ├─ GH_VENT_S01_01
│  ├─ GH_VENT_S02_01
│  ├─ GH_VENT_S03_01
│  └─ GH_VENT_S04_01
│
├─ GH_SCREENS
│  ├─ GH_SHADE_SCREEN
│  └─ GH_DIFFUSE_SCREEN
│
├─ GH_INTERIOR
│  └─ GH_BEDS
│
├─ GH_GROUND
│
└─ GH_SCENE
   ├─ Camera_Main
   ├─ Light_Key
   └─ Light_Fill
```

향후 Three.js에서는 이름으로 객체를 찾을 예정이므로 naming을 절대 임의 변경하지 않는다.

---

# 9. Object naming convention

## 주요 원칙

```text
GH_<CATEGORY>_<IDENTIFIER>
```

예:

```text
GH_COL_MAIN_X001_Y01
GH_COL_SECONDARY_X002_Y03
GH_RAFTER_X005_S02
GH_VENT_S01_01
GH_VENT_S02_01
GH_BED_S03_R04
```

규칙:

- S = span number
- R = row number
- X = longitudinal station
- Y = transverse grid
- zero-padding 사용

---

# 10. Geometry 구현 요구사항

## 10.1 Ground

크기:

```text
(length + 2 × margin)
×
(total_width + 2 × margin)
```

Z = 0

재질은 neutral dark/gray 또는 subdued ground material.

---

## 10.2 Main columns

main column station:

```python
x = -length/2
while x <= length/2:
    place_column(x)
    x += main_column_spacing
```

단 마지막 station이 끝점과 너무 멀면 반드시 끝단 column을 추가한다.

더 좋은 구현은 helper:

```python
make_stations(total_length, spacing, include_ends=True)
```

반드시 전체 길이 양 끝을 보존한다.

Y 위치는 span boundaries를 기준으로 한다.

```text
[-total_width/2, ..., +total_width/2]
```

즉 4연동이면 5개 transverse grid line이 생성된다.

---

## 10.3 Secondary columns

main column보다 더 촘촘하게 생성한다.

spacing:

```text
2.25 m
```

단 main column과 동일 위치인 경우 duplicate object를 만들지 않는다.

---

## 10.4 Roof arch

각 span별로 곡면 roof profile을 만든다.

필요 조건:

```text
start point = (-span_width/2, eave_height)
peak        = (0, ridge_height)
end point   = (+span_width/2, eave_height)
```

여기서 좌표는 span local Y-Z plane이다.

권장 방법:

1. Bezier curve
2. sampled parabola
3. circular arc

중 하나를 함수화한다.

예:

```python
generate_arch_points(
    span_width,
    eave_height,
    ridge_height,
    segments
)
```

이번 단계에서는 정밀 시공 곡률 복원이 아니라 **시각적으로 자연스러운 아치**가 목표다.

---

## 10.5 Rafters

지붕 arch profile을 X 방향으로 rafter_spacing마다 배치한다.

성능 문제를 방지하기 위해:

- 가능하면 mesh reuse / linked duplicate
- 지나치게 높은 segment 수 사용 금지
- GLB 용량을 관리

---

## 10.6 Roof cover

지붕 frame 위에 반투명 외피를 만든다.

요구:

```text
transparent
double sided 고려
metallic = 0
moderate roughness
alpha blend 사용
```

외피는 구조 frame과 별도 object.

Three.js에서 숨길 수 있도록:

```text
GH_ROOF_COVER
```

이름 고정.

---

# 11. 천창 구현

천창은 이번 단계에서 가장 중요한 interactive-ready object다.

## 요구

각 span마다 최소 1개의 대표 천창 object를 생성한다.

```text
GH_VENT_S01_01
GH_VENT_S02_01
GH_VENT_S03_01
GH_VENT_S04_01
```

천창 geometry:

- 지붕 상부 일부 panel
- 별도 mesh
- hinge point가 실제 회전축 역할
- local rotation으로 개폐

함수 예:

```python
set_vent_opening(obj, percent, max_angle_deg)
```

계산:

```python
angle = clamp(percent, 0, 100) / 100 * max_angle_deg
```

현재 config의:

```text
opening_percent = 20
```

이면 모델 생성 시 약 20% open 상태로 보이게 한다.

**중요:**

vent 위치와 축은 Geometry에 baked되지 않도록 해서 나중에 Three.js에서 회전 가능해야 한다.

가능하면 GLB hierarchy:

```text
GH_VENT_S01_01_PIVOT
└─ GH_VENT_S01_01
```

구조를 사용한다.

---

# 12. 차광 스크린 구현

스크린은 전체 온실 내부에 horizontal layer 형태로 표현한다.

높이:

```text
z = 4.8 m
```

하지만 단일 plane 하나로 끝내지 말고 향후 opening을 시각화할 수 있게 설계한다.

권장 구현:

```text
각 span별 screen panel
```

또는

```text
전체 screen width를 X축 또는 Y축으로 scale/clip 가능한 구조
```

Phase 1에서는 가장 단순하게:

```text
opening_percent가 커질수록 retract
```

되도록 geometry helper를 만든다.

예:

```python
set_screen_opening(screen_root, percent)
```

스크린 자체 material은 semi-transparent.

---

# 13. 산광 스크린 구현

기본 높이:

```text
4.55 m
```

차광스크린과 시각적으로 구분한다.

하지만 강한 색상 사용은 피한다.

차광과 산광은 material 이름도 구분:

```text
MAT_SCREEN_SHADE
MAT_SCREEN_DIFFUSE
```

---

# 14. 토마토 베드

각 span 안에 5개 베드를 균등 배치한다.

함수:

```python
bed_y_positions(
    span_center_y,
    span_width,
    rows_per_span,
    edge_margin
)
```

베드가 span boundary와 겹치지 않게 내부 margin을 둔다.

기본:

```text
rows_per_span = 5
total = 20
```

Object 이름:

```text
GH_BED_S01_R01
...
GH_BED_S04_R05
```

베드 길이:

```text
length - 2 * length_margin
```

---

# 15. Material 요구사항

최소 다음 material을 만든다.

```text
MAT_FRAME_METAL
MAT_COVER
MAT_VENT_FRAME
MAT_SCREEN_SHADE
MAT_SCREEN_DIFFUSE
MAT_BED
MAT_GROUND
```

목표 스타일:

```text
산업용 3D dashboard에 어울리는 neutral/clean visualization
```

화려한 게임 스타일이 아니다.

프레임:

```text
metallic 높음
roughness 중간
```

외피:

```text
semi-transparent
약한 roughness
```

스크린:

```text
semi-transparent
```

현재는 디자인보다 구조가 우선이므로 material system을 쉽게 변경 가능하게 분리한다.

---

# 16. Blender Unit 설정

반드시:

```python
scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'METERS'
scene.unit_settings.scale_length = 1.0
```

1 Blender Unit = 1 m.

---

# 17. Origin / Transform 규칙

GLB export 후 Three.js animation을 위해 중요하다.

모든 static object:

```text
scale 적용
rotation 적용 가능
transform 정리
```

단 movable object의 pivot은 유지한다.

천창:

```text
origin = hinge axis
```

스크린:

```text
origin = retract direction 기준점
```

GLB에서 hierarchy가 유지되도록 export한다.

---

# 18. Camera

기본 preview camera를 생성한다.

카메라는 온실 전체를 사선 위에서 볼 수 있는 위치.

예:

```text
X ≈ 70
Y ≈ -55
Z ≈ 35
```

단 절대값 하드코딩보다 bounding box에 따라 자동 계산하는 함수를 권장한다.

```python
fit_camera_to_bounds(...)
```

---

# 19. Lighting

최소:

```text
Sun 또는 Area key light
Fill area light
World ambient
```

목적:

- frame 식별 가능
- 투명 cover 내부 식별 가능
- bed가 묻히지 않음

포토리얼 렌더가 목적이 아니다.

---

# 20. Export 요구사항

`.glb` export:

```python
bpy.ops.export_scene.gltf(
    filepath=...,
    export_format='GLB',
    export_apply=True
)
```

실제 Blender 버전에 따라 인자를 검증해서 사용한다.

필수:

```text
object names 유지
collection/hierarchy 최대한 유지
materials 포함
animation 가능한 transforms 유지
```

GLB export 전에 모든 object naming collision 검사.

---

# 21. generation_report.json

생성 후 다음 report를 남긴다.

예:

```json
{
  "status": "success",
  "project": "MS80_Gimje_Farmcubator",
  "dimensions": {
    "length": 97.5,
    "width": 32.0,
    "span_count": 4
  },
  "objects": {
    "main_columns": 0,
    "secondary_columns": 0,
    "rafters": 0,
    "roof_vents": 4,
    "shade_screens": 4,
    "diffuse_screens": 4,
    "crop_beds": 20
  },
  "outputs": {
    "blend": "dist/greenhouse.blend",
    "glb": "dist/greenhouse.glb"
  },
  "warnings": [
    "Eave height is provisional",
    "Ridge height is provisional"
  ]
}
```

실제 count를 코드에서 계산해서 넣는다.

---

# 22. CLI 실행 인터페이스

목표:

```bash
blender --background \
  --python scripts/generate_greenhouse.py \
  -- \
  --config config/greenhouse.json \
  --output-dir dist
```

Windows PowerShell 예:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.x\blender.exe" `
  --background `
  --python scripts/generate_greenhouse.py `
  -- `
  --config config/greenhouse.json `
  --output-dir dist
```

Blender 경로는 사용자의 실제 설치경로에 맞게 수정한다.

---

# 23. Blender GUI 실행 방식

CLI가 어려운 사용자를 위해 README에 GUI 실행도 작성한다.

절차:

```text
1. Blender 실행
2. Scripting workspace
3. scripts/generate_greenhouse.py 열기
4. config 경로가 올바른지 확인
5. Run Script
6. Outliner에서 GH_ROOT 확인
7. File > Save
8. dist/greenhouse.glb 확인
```

가능하면 script 실행 시 config 기본 경로를 프로젝트 루트 기준으로 자동 탐색한다.

---

# 24. Python/Blender 구현 주의사항

Blender 내 Python은 일반 시스템 Python과 다를 수 있다.

따라서 이번 단계에서는 외부 dependency를 최대한 사용하지 않는다.

권장:

```text
stdlib
bpy
math
mathutils
json
pathlib
argparse
```

가능하면 numpy도 사용하지 않는다.

JSON schema validation은 외부 라이브러리가 필요한 경우:

1. 자체 lightweight validation
2. 또는 dependency 없이 기본 validation

을 우선한다.

---

# 25. 성능 요구사항

목표 PC에서 Blender viewport 조작이 지나치게 느려지지 않게 한다.

금지:

```text
모든 파이프를 초고폴리곤 cylinder로 생성
토마토 수천 개 고폴리곤 생성
불필요한 subdivision
투명 material 중첩 과다
```

권장:

```text
frame cylinder vertices: 8~12
arch segments: 16~32
repeated object는 shared mesh 활용
```

최종 GLB는 가능한 한 수십 MB 이하를 목표로 하되, 이번 단계에서는 정확한 크기 hard limit은 두지 않는다.

---

# 26. 재생성 안정성

스크립트를 두 번 실행해도 object가 누적되면 안 된다.

실행 시작 시:

```python
clear_previous_generated_scene()
```

를 호출해서 기존 `GH_` generated objects/collections을 정리한다.

사용자가 만든 다른 object를 무조건 삭제하지 않는다.

---

# 27. 테스트

## Unit test

Blender 없이 테스트 가능한 수학/설정 기능:

```text
config parsing
station generation
span center 계산
bed 위치 계산
arch point 생성
opening percent clamp
naming 규칙
```

---

## Blender validation

`validate_scene.py`는 다음을 검사한다.

```text
GH_ROOT exists
GH_STRUCTURE exists
GH_VENTS exists
GH_SCREENS exists
GH_INTERIOR exists

vent count >= span_count
bed count == span_count * rows_per_span

all required objects have unique names
no negative scale
GLB output exists
BLEND output exists
```

---

# 28. Acceptance Criteria

아래를 모두 만족해야 1단계 완료다.

### A. Config-driven

`span_count`를 4 → 3으로 바꾸고 다시 실행하면:

```text
폭 = 24 m
span = 3
vent representative count = 3
beds = 15
```

로 자동 변경되어야 한다.

### B. Length-driven

```text
length = 60
```

으로 변경하면 전체 frame/roof/bed 길이가 60 m 기준으로 재생성되어야 한다.

### C. Interactive-ready

Blender Outliner에서 다음을 개별 선택 가능해야 한다.

```text
roof cover
roof vent
shade screen
diffuse screen
crop bed
frame
```

### D. Vent pivot

천창 object를 선택하고 local rotation을 변경하면 hinge를 중심으로 자연스럽게 열리고 닫혀야 한다.

### E. Screen control

스크린 opening helper를 0, 50, 100으로 호출했을 때 시각적으로 다른 개폐 상태를 보여야 한다.

### F. GLB

`greenhouse.glb`를 Blender로 다시 import했을 때:

```text
geometry
materials
object names
hierarchy
```

가 유지되어야 한다.

### G. Re-run

동일 script를 두 번 실행해도 object duplication이 없어야 한다.

---

# 29. Codex 구현 순서

한 번에 모든 기능을 구현하지 말고 다음 순서로 commit 또는 작업 단계를 나눈다.

## Step 1 — Config

```text
greenhouse.json
config_loader.py
validation
```

검증 완료 후 다음 단계로 이동.

---

## Step 2 — Coordinate / math helpers

```text
span bounds
station generator
arch points
bed positions
```

unit test 작성.

---

## Step 3 — Basic shell

```text
ground
columns
arch roof frame
```

Blender에서 육안 검증.

---

## Step 4 — Cover

```text
transparent greenhouse cover
```

---

## Step 5 — Roof vent

```text
pivot hierarchy
opening_percent
```

가장 중요.

---

## Step 6 — Screens

```text
shade screen
diffuse screen
opening helper
```

---

## Step 7 — Interior

```text
20 tomato beds
```

---

## Step 8 — Materials / camera / lights

시각 품질 개선.

---

## Step 9 — Save / GLB export

```text
.blend
.glb
```

---

## Step 10 — Validation/report

```text
validate_scene.py
generation_report.json
```

---

# 30. 첫 실행 후 사람이 확인해야 할 항목

생성 결과가 나오면 다음을 사람이 도면과 비교한다.

```text
[ ] 4연동 구조인가
[ ] 전체 비율이 32 × 97.5 m에 맞는가
[ ] 각 연동 폭이 동일한가
[ ] 지붕 형상이 도면과 시각적으로 유사한가
[ ] eave/ridge 높이가 과도하게 이상하지 않은가
[ ] 천창 위치가 도면과 대략 맞는가
[ ] 천창 opening 방향이 올바른가
[ ] 차광 스크린 높이가 자연스러운가
[ ] 산광 스크린과 차광 스크린이 서로 구분되는가
[ ] 토마토 베드가 span당 5줄인가
[ ] 내부 통로가 시각적으로 확보되는가
[ ] cover를 숨겼을 때 내부가 잘 보이는가
```

첫 결과에서 도면과 다른 부분을 발견하면 JSON/geometry rule을 수정한다.

---

# 31. 절대 하지 말아야 할 것

```text
1. PDF를 자동 해석한다고 가정하고 임의 치수를 생성하지 말 것.
2. 도면에 없는 센서 위치를 임의 생성하지 말 것.
3. 모든 구조를 하나의 mesh로 합치지 말 것.
4. 천창을 static roof mesh에 합치지 말 것.
5. 스크린을 static roof/structure에 합치지 말 것.
6. width/length/span 값을 코드에 하드코딩하지 말 것.
7. 3D 모델을 photorealistic하게 만들기 위해 구조를 복잡하게 만들지 말 것.
8. MPC/PLC/Django/Three.js 코드를 이번 단계에 끼워 넣지 말 것.
9. BIM 정확도를 목표로 하지 말 것.
10. 확인되지 않은 도면 치수를 "확정"이라고 표현하지 말 것.
```

---

# 32. 향후 확장을 위해 준비만 해둘 것

이번 단계에서 구현하지는 않지만 구조적으로 다음 확장을 방해하지 않게 한다.

```text
Phase 2
PDF → AI drawing parser → greenhouse.json

Phase 3
GLB → Three.js viewer

Phase 4
Sensor positions + interactive object picking

Phase 5
PLC → WebSocket → 3D live state

Phase 6
MPC Preview

Phase 7
PLC write interface
```

따라서 현재 scene object에는 가능하면 custom properties를 넣는다.

예:

```python
obj["asset_type"] = "roof_vent"
obj["span_index"] = 1
obj["controllable"] = True
obj["control_variable"] = "opening_percent"
```

스크린:

```python
obj["asset_type"] = "shade_screen"
obj["controllable"] = True
obj["control_variable"] = "opening_percent"
```

베드:

```python
obj["asset_type"] = "crop_bed"
obj["span_index"] = 2
obj["row_index"] = 4
```

향후 exporter 또는 web app이 metadata를 사용할 수 있도록 한다.

---

# 33. Codex에게 요청하는 최종 산출물

작업을 완료한 뒤 아래 내용을 모두 제공한다.

```text
1. 생성한 전체 파일 목록
2. 각 주요 파일 역할
3. 실행 명령
4. Blender GUI 실행 방법
5. 성공 시 생성되는 파일
6. config 변경 방법
7. validation 실행 방법
8. 현재 알려진 한계
9. 도면 해석상 provisional인 값
10. 다음 단계에서 수정하기 쉬운 부분
```

코드만 던지고 끝내지 않는다.

---

# 34. 실제 사용자 실행 절차

사용자는 아래 순서만 수행하면 되게 만들어야 한다.

## 1) Blender 설치

Blender 4.x 계열 설치.

## 2) 저장소 열기

```bash
cd greenhouse-3d-generator
```

## 3) 도면 보관

소스 PDF를:

```text
reference/
```

에 넣는다.

PDF는 실행 시 직접 읽지 않아도 된다. 참고 원본이다.

## 4) config 확인

```text
config/greenhouse.json
```

확인.

## 5) Blender headless 실행

Windows 예:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.x\blender.exe" `
  --background `
  --python scripts/generate_greenhouse.py `
  -- `
  --config config/greenhouse.json `
  --output-dir dist
```

## 6) 결과 확인

```text
dist/greenhouse.blend
dist/greenhouse.glb
dist/generation_report.json
```

## 7) Blender에서 확인

```text
greenhouse.blend
```

열기.

## 8) 반드시 먼저 볼 것

Outliner에서:

```text
GH_ROOT
GH_VENTS
GH_SCREENS
GH_INTERIOR
```

가 분리되어 있는지 확인.

천창 object를 선택하고 회전시켜 실제로 개폐 가능한지 확인.

---

# 35. 이번 단계의 최종 정의

이 단계의 목적은:

> "도면 PDF를 자동으로 읽는 것"이 아니다.

정확히는:

> **"온실 구조를 JSON으로 표현하고, 그 JSON을 기반으로 재사용 가능한 Blender 3D 모델을 자동 생성하는 엔진을 만드는 것"**

이다.

따라서 첫 번째 완성품은 반드시:

```text
greenhouse.json
    ↓
generate_greenhouse.py
    ↓
greenhouse.blend
    ↓
greenhouse.glb
```

가 안정적으로 실행되는 상태여야 한다.

이 파이프라인이 성공한 뒤에만 다음 단계인:

```text
PDF
 ↓
AI
 ↓
greenhouse.json
```

자동 해석 기능을 추가한다.

---

# 36. Codex 작업 시작용 Prompt

아래 내용을 Codex에 그대로 전달해도 된다.

---

당신은 현재 저장소에서 Blender Python 기반 파라메트릭 스마트온실 3D 생성기를 구현해야 한다.

먼저 이 문서 전체를 읽고 작업 범위와 Acceptance Criteria를 파악하라.

이번 단계에서는 AI 도면 분석, PDF OCR, Django, Three.js, PLC, MPC를 구현하지 않는다.

입력은 `config/greenhouse.json`이며 출력은 `dist/greenhouse.blend`, `dist/greenhouse.glb`, `dist/generation_report.json`이다.

기준 온실은 MS 8.0 Model, 8 m × 97.5 m, 4연동 구조다. 총 폭은 32 m다. 평면도 기준 nominal spacing은 주기둥 4.5 m, 샛기둥 2.25 m, 서까래 1.125 m다. 높이는 Phase 1에서 eave 4.2 m, ridge 5.0 m를 provisional 값으로 사용하며, 확정값처럼 취급하지 않는다. 천창은 양랙 구조가 존재하며 향후 제어를 위해 별도 movable object와 pivot hierarchy를 가져야 한다. 차광 스크린은 약 4.8 m, 산광 스크린은 약 4.55 m 높이에 시각화한다. 토마토 베드는 span당 5줄, 총 20개를 기본으로 생성한다.

가장 중요한 요구사항은 "보기 좋은 단일 mesh"가 아니라 향후 Three.js/PLC/MPC 연결이 가능한 구조화된 scene graph다. Vent, screen, cover, frame, bed는 반드시 분리되어야 하며 안정적인 object name과 custom property를 가져야 한다.

작업은 다음 순서로 진행하라.

1. config 및 validation
2. coordinate/math helpers + unit tests
3. base structure
4. arched roof
5. transparent cover
6. movable roof vents
7. movable screens
8. crop beds
9. materials/camera/lights
10. save/export
11. validation/report
12. README

각 단계가 끝날 때 코드가 실행 가능한 상태를 유지한다.

도면에 없는 치수나 센서 위치를 임의로 추가하지 말고, 불확실한 값은 config metadata와 generation report에 warning으로 남겨라.

최종적으로 실행 명령, 파일 구조, config 변경법, validation 방법, known limitations까지 README에 작성하라.

---

**이 문서를 단일 source of truth로 사용하여 1단계 구현을 완료하라.**

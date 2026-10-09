# Phase 1.5 구현 명세 — 운영형 3D 온실 자산·작물·설비 고도화

> 목적: 기존 Phase 1의 `JSON → Blender → BLEND/GLB` 파이프라인을 유지하면서, 실제 도면에 근거한 설비와 내부 작물 표현을 추가하여 **운영 중인 스마트온실처럼 보이는 고품질 3D scene**으로 확장한다.  
> 이 단계는 AI 도면 자동해석, Django, Three.js, PLC, MPC를 구현하지 않는다.  
> 대신 이후 웹 실시간 시각화에 바로 연결할 수 있도록 **구동기·설비·센서 placeholder·방울토마토 작물·배관/양액 계통을 구조화된 object hierarchy로 구현**한다.

---

## 0. Codex 최상위 지시

이 문서를 **single source of truth**로 사용하여 기존 Phase 1 저장소를 수정하라.

기존 Phase 1의 다음 특성을 절대 깨뜨리지 않는다.

- `config/greenhouse.json` 기반 파라메트릭 생성
- Blender meter 단위
- `.blend` + `.glb` export
- stable object naming
- 재실행 시 생성 객체 중복 방지
- `GH_*` scene hierarchy
- vent/screen independent object
- GLB custom properties
- validation / generation report
- source drawing과 provisional 값의 구분

이번 단계에서는 다음을 추가한다.

1. 실제 도면에 근거한 양액/급수 설비
2. 실제 도면에 근거한 천창 구동 메커니즘의 시각적 표현
3. 실제 도면에 근거한 스크린/커튼 구동 메커니즘
4. 토마토 베드 위 방울토마토 작물 low-poly/instanced 표현
5. 센서 placeholder system
6. 주요 설비의 interactive-ready hierarchy
7. 기존 단순 박스/placeholder geometry의 품질 개선
8. 전체 scene material/lighting 개선
9. 내부를 보기 위한 cover visibility control
10. 향후 Three.js/PLC 연결을 위한 metadata

---

# 1. 작업 범위

## 반드시 구현

```text
✅ Phase 1 기존 구조 유지
✅ 토마토 작물 instance
✅ 베드별 crop row
✅ 천창 panel + 축 + rack/pinion + motor visual
✅ 차광 스크린 + drum/roller visual
✅ 산광 스크린
✅ 측면 커튼/roller visual
✅ 양액기
✅ 양액탱크 A/B/C
✅ 원수탱크
✅ 정수기 placeholder
✅ 급수펌프
✅ 링블로어
✅ 여과기
✅ 혼합탱크
✅ 공급 라인
✅ 배액 라인
✅ control panel placeholder
✅ flow/pressure instruments placeholder
✅ sensor placeholder system
✅ sensor position config
✅ equipment collection/hierarchy
✅ object naming
✅ custom properties
✅ 재질 개선
✅ 내부 확인용 preview
✅ acceptance validation
```

## 이번 단계에서 구현하지 않음

```text
❌ PDF AI 자동해석
❌ OCR
❌ 실제 PLC 연결
❌ 실제 sensor 데이터
❌ WebSocket
❌ Django
❌ Three.js
❌ MPC
❌ 열수지
❌ CFD
❌ BIM/CAD 정밀복원
❌ 실제 제조사 제품 mesh 다운로드
❌ 실제 전기 배선 시뮬레이션
❌ 실제 관수 hydraulic simulation
```

---

# 2. 도면에서 근거가 명확한 설비

이번 단계에서는 아래 설비를 **도면 근거 있음**으로 취급한다.

## 2.1 천창

도면에 다음 요소가 명시되어 있다.

```text
천창(양랙)
천창축
천창 프레임
천창 랙
피니언
축수베어링
천창개폐모터
랙/피니언 구조
```

따라서 Phase 1의 단순 vent panel을 아래처럼 확장한다.

```text
GH_VENT_S01_01_PIVOT
├─ GH_VENT_S01_01_PANEL
├─ GH_VENT_S01_01_FRAME
├─ GH_VENT_S01_01_SHAFT
├─ GH_VENT_S01_01_RACK_A
├─ GH_VENT_S01_01_RACK_B
├─ GH_VENT_S01_01_PINION
├─ GH_VENT_S01_01_BEARING
└─ GH_VENT_S01_01_MOTOR
```

정밀 기계 CAD가 목적은 아니다. rack/pinion/motor는 low-poly visual asset으로 만든다.

### 천창 control interface

기존:

```python
set_vent_opening(obj, percent)
```

를 유지한다.

개폐 시 실제로 움직여야 하는 것은 panel/frame/pivot이며 motor/rack/pinion은 최소한 시각적 연동이 가능하게 설계한다.

```text
vent opening ↑
rack translation ↑
pinion rotation ↑
```

정확한 gear ratio가 도면에 없는 경우 실제 회전수 계산은 하지 않고 visual relationship만 표현한다.

---

# 3. 스크린·커튼 계통

도면에 다음이 확인된다.

```text
차광 스크린(75%)
산광 스크린
드럼
예인크립
예인크립강선고리
예인로라(대)
예인로라(중)
커튼 롤러
드럼
축
```

따라서 단순 plane만 만들지 않는다.

## 3.1 차광 스크린

```text
GH_SHADE_SCREEN
├─ GH_SHADE_SCREEN_DRIVE
│  ├─ GH_SHADE_DRUM
│  ├─ GH_SHADE_SHAFT
│  └─ GH_SHADE_ROLLER_*
└─ GH_SHADE_SCREEN_PANELS
```

## 3.2 산광 스크린

```text
GH_DIFFUSE_SCREEN
├─ GH_DIFFUSE_SCREEN_DRIVE
└─ GH_DIFFUSE_SCREEN_PANELS
```

## 3.3 측면 커튼

도면에서 roller/drum 계통이 확인되므로 visual asset을 추가한다.

```text
GH_SIDE_CURTAIN_LEFT
GH_SIDE_CURTAIN_RIGHT
```

### 제어 interface

```python
set_screen_opening(obj, percent)
set_side_curtain_opening(obj, percent)
```

0 = 펼침/닫힘  
100 = 수납/개방

기존 semantics를 유지한다.

---

# 4. 양액 및 급수 계통

도면에 다음 요소가 명시되어 있으므로 실제 3D 설비로 구현한다.

```text
양액기
양액탱크 A
양액탱크 B
양액탱크 C
원수탱크
정수기
링블로어
급수펌프
여과기
혼합탱크
압력계
압력조절밸브
순간유량계
컨트롤 패널
디스플레이
공급 라인
배액 라인
```

또한 별도 상세도에 다음이 있다.

```text
MISO-7000
PVC pipe 32A
조임식엘보 40A
조임식티 40A
유니온볼밸브32A
PE 유니온볼밸브
```

정확한 vendor 제품 형상을 재현하지 않는다.

### 구현 수준

- tank: cylinder + cap + support
- pump: low-poly pump body
- filter: cylinder/canister
- blower: housing + motor
- control panel: industrial cabinet
- gauge: small dial-like object
- flow meter: inline box/cylinder
- pipe: curve/bevel 또는 cylinder path
- valve: simple T/lever asset

---

# 5. 양액 Collection 구조

```text
GH_FERTIGATION
├─ GH_FERTIGATION_UNIT
│  ├─ GH_CONTROL_PANEL
│  ├─ GH_DISPLAY
│  ├─ GH_MIXING_TANK
│  ├─ GH_WATER_TANK
│  ├─ GH_NUTRIENT_TANK_A
│  ├─ GH_NUTRIENT_TANK_B
│  ├─ GH_NUTRIENT_TANK_C
│  ├─ GH_WATER_PURIFIER
│  ├─ GH_FEED_PUMP
│  ├─ GH_RING_BLOWER
│  ├─ GH_FILTER_01
│  ├─ GH_FILTER_02
│  ├─ GH_PRESSURE_GAUGE
│  ├─ GH_PRESSURE_VALVE
│  └─ GH_FLOW_METER
│
├─ GH_IRRIGATION_SUPPLY
└─ GH_IRRIGATION_DRAIN
```

---

# 6. 양액 설비 위치 정책

도면의 양액 배치도와 설치 상세도를 참고한다.

단, 도면만으로 정확한 모든 좌표를 확정할 수 없는 경우 다음 정책을 사용한다.

```text
1. source drawing에서 위치를 명확히 판독 가능 → verified
2. 영역은 명확하지만 정확 좌표 불명 → approximate
3. 전혀 위치를 알 수 없음 → 생성 금지 또는 config provisional
```

절대 arbitrary 위치를 verified처럼 표현하지 않는다.

Config 예:

```json
"fertigation": {
  "enabled": true,
  "placement": {
    "x": -45.0,
    "y": -13.5,
    "z": 0.0,
    "verified": false,
    "note": "Approximate placement based on drawing area; verify visually"
  }
}
```

---

# 7. 토마토 작물

현재 베드는 있지만 식물이 없다. 이번 단계에서는 반드시 작물을 표현한다.

## 7.1 작물 종류

```text
cherry tomato / 방울토마토
```

정밀 botanical model이 아니라 greenhouse dashboard용 low-poly plant를 만든다.

## 7.2 작물 구성

한 개 대표 plant asset:

```text
GH_PLANT_MASTER
├─ stem
├─ leaves
├─ support_string
└─ tomato_clusters
```

### 최소 시각 요소

```text
줄기
녹색 잎
유인줄/지지선
작은 토마토 cluster
```

토마토 열매는 너무 많지 않게 한다.

### 성능

절대 plant마다 독립 mesh를 수백 개 만들지 않는다.

권장:

```text
linked instance
Geometry Nodes
shared mesh
collection instance
```

중 하나.

---

# 8. 작물 배치

각 bed를 따라 일정 간격으로 배치한다.

Config:

```json
"crops": {
  "enabled": true,
  "crop_type": "cherry_tomato",
  "plant_spacing": 0.45,
  "plant_height": 2.2,
  "instance_mode": "linked",
  "tomato_clusters": true,
  "detail_level": "medium"
}
```

베드 길이가 길기 때문에 성능을 위해 실제 plant instance 수에 상한을 둔다.

```text
max_visual_plants_per_bed = 80
```

필요한 경우 spacing을 visual spacing으로 자동 보정한다.

---

# 9. 센서

중요: 현재 도면에서 실제 환경센서 설치 위치는 확정되지 않았다. 따라서 센서는 반드시 **placeholder / unverified**로 구현한다.

## 9.1 Sensor types

```text
temperature_rh
solar_radiation
co2_optional
outside_weather_optional
```

이번 단계에서 기본으로 생성:

```text
Indoor T/RH sensor placeholder 2~4개
Outdoor solar radiation sensor placeholder 1개
```

단 실제 위치인 것처럼 표현하지 않는다.

Config:

```json
"sensors": {
  "enabled": true,
  "verified_positions": false,
  "items": [
    {
      "id": "T_RH_01",
      "type": "temperature_rh",
      "position": [0.0, -4.0, 2.0],
      "verified": false,
      "note": "Placeholder until farm sensor position is confirmed"
    }
  ]
}
```

---

# 10. Sensor 3D asset

센서는 저폴리곤 산업용 sensor enclosure 느낌으로 만든다.

```text
small body
probe or vented housing
mount
```

Object:

```text
GH_SENSOR_T_RH_01
GH_SENSOR_SOLAR_01
```

Custom property:

```python
obj["asset_type"] = "sensor"
obj["sensor_type"] = "temperature_rh"
obj["sensor_id"] = "T_RH_01"
obj["verified_position"] = False
obj["live_data_ready"] = True
```

---

# 11. 센서 표시 준비

Three.js 단계에서 센서를 클릭할 예정이므로:

```text
sensor mesh + sensor anchor empty
```

를 만든다.

```text
GH_SENSOR_T_RH_01_ANCHOR
└─ GH_SENSOR_T_RH_01
```

웹에서는 anchor world position을 label position으로 활용할 수 있어야 한다.

---

# 12. Scene hierarchy 최종 목표

```text
GH_ROOT
│
├─ GH_STRUCTURE
├─ GH_ROOF
├─ GH_VENTS
├─ GH_SCREENS
├─ GH_CURTAINS
├─ GH_INTERIOR
│  ├─ GH_BEDS
│  └─ GH_CROPS
├─ GH_FERTIGATION
├─ GH_SENSORS
├─ GH_GROUND
└─ GH_SCENE
```

---

# 13. Placeholder Cube 제거 정책

현재 scene에 Blender 기본 `Cube` 같은 사용자 object가 남아 있을 수 있다.

기존 Phase 1의 “사용자 객체 보존” 정책은 유지한다. 다만 generator가 만든 object가 아닌 다음 기본 objects는 config 옵션으로 제거 가능하게 한다.

```json
"scene_cleanup": {
  "remove_default_cube": true,
  "remove_default_camera": false,
  "remove_default_light": false
}
```

정확히 이름이 `Cube`이고 generator metadata가 없을 때만 삭제. 사용자 커스텀 object를 무작정 삭제하지 않는다.

---

# 14. Geometry 품질 목표

이번 단계는 단순 placeholder보다 한 단계 높은 퀄리티를 목표로 한다.

## Frame

현재 Phase 1 frame은 유지하되:

- 굵기 과장 최소화
- 연결부 지나친 중첩 최소화
- 내부 시야 확보

## Tanks

단순 cylinder여도 다음 정도는 추가한다.

```text
cap
base
pipe connector
label plate
```

## Pump

```text
motor cylinder
pump housing
in/out connector
```

## Control cabinet

```text
cabinet
door
display
indicator lights
```

## Vent motor

```text
motor housing
shaft
rack
pinion
bearing
```

## Crop

dashboard view에서 “토마토를 재배 중”임이 즉시 보여야 한다.

---

# 15. Material

기존 material system을 확장한다.

```text
MAT_PLANT_STEM
MAT_PLANT_LEAF
MAT_TOMATO_GREEN
MAT_TOMATO_RED
MAT_PIPE_SUPPLY
MAT_PIPE_DRAIN
MAT_TANK
MAT_PUMP
MAT_CONTROL_PANEL
MAT_SENSOR
MAT_MOTOR
MAT_CURTAIN
```

주의:

- 과한 saturated color 금지
- industrial dashboard visualization
- tomato/red 정도만 적절한 강조
- 전체 scene은 clean/neutral

---

# 16. Transparency / visibility

온실 외피 때문에 내부가 안 보이는 문제가 발생할 수 있다.

Config:

```json
"visualization": {
  "cover_mode": "transparent",
  "cover_opacity": 0.15,
  "interior_preview": true
}
```

추가 helper:

```python
set_cover_visibility(mode)
```

지원:

```text
opaque
transparent
hidden
```

---

# 17. Preview images

validation 과정에서 자동으로 다음 이미지를 렌더한다.

```text
tmp/validation/previews/
├─ exterior_perspective.png
├─ interior_cover_hidden.png
├─ interior_crop_view.png
├─ fertigation_view.png
├─ roof_vent_closed.png
├─ roof_vent_open.png
├─ screen_open.png
└─ screen_closed.png
```

---

# 18. Config 확장

`config/greenhouse.json`에 최소 다음을 추가한다.

```json
{
  "crops": {
    "enabled": true,
    "crop_type": "cherry_tomato",
    "plant_spacing": 0.45,
    "plant_height": 2.2,
    "max_visual_plants_per_bed": 80,
    "tomato_clusters": true,
    "detail_level": "medium"
  },

  "fertigation": {
    "enabled": true,
    "show_tanks": true,
    "show_pumps": true,
    "show_filters": true,
    "show_blower": true,
    "show_control_panel": true,
    "show_supply_lines": true,
    "show_drain_lines": true
  },

  "sensors": {
    "enabled": true,
    "verified_positions": false,
    "items": []
  },

  "side_curtains": {
    "enabled": true,
    "opening_percent": 20
  },

  "scene_cleanup": {
    "remove_default_cube": true
  },

  "visualization": {
    "cover_mode": "transparent",
    "cover_opacity": 0.15,
    "interior_preview": true
  }
}
```

---

# 19. 추천 신규 파일

기존 구조를 깨지 말고 다음 파일을 추가한다.

```text
src/geometry/
├─ crops.py
├─ fertigation.py
├─ pipes.py
├─ sensors.py
├─ curtains.py
└─ equipment_primitives.py
```

추가 가능한 helper:

```text
src/asset_metadata.py
src/preview.py
```

---

# 20. Asset metadata

모든 주요 object는 아래 custom property 규칙을 따른다.

## Vent

```python
asset_type = "roof_vent"
controllable = True
control_variable = "opening_percent"
```

## Screen

```python
asset_type = "shade_screen"
controllable = True
control_variable = "opening_percent"
```

## Pump

```python
asset_type = "pump"
controllable = True
control_variable = "on_off"
plc_tag_verified = False
```

## Sensor

```python
asset_type = "sensor"
live_data_ready = True
verified_position = False
```

## Tank

```python
asset_type = "tank"
controllable = False
```

---

# 21. 실제/추정 구분

`generation_report.json`에 반드시 다음 분류를 추가한다.

```json
"source_confidence": {
  "drawing_supported": [],
  "approximate": [],
  "placeholder": []
}
```

예:

```json
{
  "drawing_supported": [
    "roof vent system",
    "shade screen",
    "diffuse screen",
    "fertigation tanks",
    "feed pump",
    "ring blower",
    "filters",
    "supply/drain lines",
    "5 tomato beds per span"
  ],
  "approximate": [
    "exact fertigation equipment coordinates",
    "crop height"
  ],
  "placeholder": [
    "sensor positions"
  ]
}
```

---

# 22. 실행 명령

기존 Phase 1 CLI를 유지한다.

Windows PowerShell:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background `
  --python-exit-code 1 `
  --python scripts/generate_greenhouse.py `
  -- `
  --config config/greenhouse.json `
  --output-dir dist
```

생성 결과:

```text
dist/
├─ greenhouse.blend
├─ greenhouse.glb
└─ generation_report.json
```

---

# 23. Validation 실행 명령

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background `
  --python-exit-code 1 `
  --python scripts/validate_scene.py `
  -- `
  --config config/greenhouse.json `
  --output-dir dist `
  --roundtrip `
  --acceptance `
  --render-previews
```

---

# 24. Phase 1.5 Acceptance Criteria

## A. Crop

기본 config에서 20 beds 모두에 cherry tomato plant instance가 보여야 한다.

## B. Performance

Plant를 추가한 뒤에도 viewport 조작이 가능한 수준이어야 한다. 수천 개 unique mesh 생성 금지. 반드시 shared/instanced geometry.

## C. Vent mechanical visualization

각 span 천창에 다음이 시각적으로 구분되어야 한다.

```text
panel
shaft
motor
rack
pinion
bearing
```

## D. Vent control

```python
set_vent_opening(..., 0)
set_vent_opening(..., 50)
set_vent_opening(..., 100)
```

에서 panel과 관련 visual drive가 자연스럽게 변해야 한다.

## E. Screens

차광/산광 screen은 서로 분리된 object/hierarchy이며 0/50/100 상태를 시각적으로 확인 가능해야 한다.

## F. Curtain

측면 curtain object가 생성되고 opening_percent에 따라 변화해야 한다.

## G. Fertigation

최소 다음이 Blender Outliner에서 별도 object/group으로 보여야 한다.

```text
GH_NUTRIENT_TANK_A
GH_NUTRIENT_TANK_B
GH_NUTRIENT_TANK_C
GH_WATER_TANK
GH_FEED_PUMP
GH_RING_BLOWER
GH_FILTER_01
GH_MIXING_TANK
GH_CONTROL_PANEL
GH_IRRIGATION_SUPPLY
GH_IRRIGATION_DRAIN
```

## H. Sensors

Sensor placeholder가 생성되고 `verified_position = false` metadata를 가진다.

## I. Default Cube

`remove_default_cube = true`이면 Blender 기본 Cube가 scene에서 없어야 한다.

## J. GLB Roundtrip

재import 시 crop, vent, screen, fertigation, sensor major hierarchy 및 names 유지.

## K. Preview Render

최소 다음 4장은 정상 생성한다.

```text
exterior_perspective
interior_cover_hidden
interior_crop_view
fertigation_view
```

---

# 25. 시각 검수 기준

```text
[ ] 단순 철골 골격이 아니라 실제 재배 온실처럼 보임
[ ] 방울토마토 재배가 즉시 식별됨
[ ] 베드와 식물이 서로 겹치지 않음
[ ] crop height가 지붕/스크린을 과도하게 관통하지 않음
[ ] 천창 motor/rack/pinion이 시각적으로 식별됨
[ ] 천창 개방 방향 자연스러움
[ ] 스크린 층이 명확함
[ ] curtain이 frame과 충돌하지 않음
[ ] 양액 설비가 내부 동선과 심하게 충돌하지 않음
[ ] supply/drain pipe가 bed와 관계 있게 배치됨
[ ] 센서가 placeholder임이 report에 명시됨
[ ] cover 숨김 상태에서 내부 설비가 잘 보임
[ ] 전체 화면이 너무 복잡하거나 과도하게 고폴리곤이 아님
```

---

# 26. 절대 하지 말 것

```text
1. 도면에 없는 장비를 실제 장비처럼 확정해서 넣지 말 것
2. 실제 센서 위치를 임의 추정해서 verified 처리하지 말 것
3. 모든 plant를 unique mesh로 만들지 말 것
4. vendor 제품명을 임의로 추가하지 말 것
5. 실제 PLC tag를 추정하지 말 것
6. actual hydraulic function을 시뮬레이션하지 말 것
7. 모든 equipment를 하나의 mesh로 합치지 말 것
8. motor를 vent panel에 bake하지 말 것
9. screen/curtain을 static geometry로만 만들지 말 것
10. 기존 Phase 1 acceptance를 깨지 말 것
11. GLB export compatibility를 희생하지 말 것
12. 디자인을 위해 coordinate convention을 변경하지 말 것
```

---

# 27. Codex 작업 순서

## Step 1
기존 repository와 Phase 1 README/implementation spec을 읽는다.

## Step 2
현재 scene hierarchy와 generator architecture를 분석한다.

## Step 3
config/schema를 Phase 1.5로 확장한다.

## Step 4
default Cube cleanup 구현.

## Step 5
crop master + instancing 구현.

## Step 6
천창 mechanical visual 개선.

## Step 7
screen/curtain mechanical visual 구현.

## Step 8
fertigation equipment primitives 구현.

## Step 9
supply/drain piping 구현.

## Step 10
sensor placeholder 구현.

## Step 11
materials/lighting 개선.

## Step 12
preview rendering 구현.

## Step 13
GLB export / roundtrip validation.

## Step 14
README 업데이트.

---

# 28. Codex에게 바로 넣을 Goal Prompt

아래를 그대로 사용할 수 있다.

---

`Phase 1.5 구현 명세`를 single source of truth로 사용해서 기존 Phase 1 파라메트릭 온실 생성기를 운영형 3D 온실로 확장해.

기존 JSON → Blender → BLEND/GLB 파이프라인, naming, hierarchy, validation, 재실행 안정성은 절대 깨뜨리지 마.

이번 단계의 핵심은 다음이다.

1. 방울토마토 low-poly/instanced 작물을 모든 tomato bed에 생성
2. 천창을 panel만이 아니라 shaft, rack, pinion, bearing, motor가 보이는 구동 시스템으로 개선
3. 차광/산광 스크린에 drum/roller 계통 추가
4. 측면 curtain과 roller/drum 구현
5. 도면에 있는 양액기, nutrient tank A/B/C, water tank, purifier, feed pump, ring blower, filter, mixing tank, gauge, valve, flow meter, control panel을 low-poly industrial asset으로 구현
6. 공급/배액 라인을 구현
7. 실제 위치가 확인되지 않은 환경센서는 placeholder system으로 구현하고 반드시 verified=false 처리
8. default Blender Cube 제거 옵션 추가
9. 외피 transparent/hidden preview 지원
10. GLB에서 object names, hierarchy, metadata 유지
11. preview render 생성
12. 기존 Phase 1 acceptance + Phase 1.5 acceptance 모두 통과

도면에 없는 값은 임의로 사실처럼 확정하지 말고 approximate/placeholder로 분류해.

토마토는 unique mesh를 대량 생성하지 말고 shared mesh 또는 linked instance를 사용해 성능을 유지해.

작업을 완료하면 다음을 출력해.

- 수정/추가 파일 목록
- 실행 명령
- validation 명령
- preview 경로
- drawing-supported / approximate / placeholder 항목
- known limitations
- 다음 Three.js 단계에서 바로 사용할 object naming과 custom property 목록

Acceptance가 실패하면 성공할 때까지 수정해.

---

# 29. 이번 단계 완료 후 다음 단계

Phase 1.5 성공 후 다음은:

```text
Phase 2
PDF → AI → greenhouse.json 자동 추출

또는

Phase 2B
GLB → Three.js Viewer
```

현재 프로젝트 목적상 추천 순서:

```text
Phase 1.5
운영형 3D asset 완성

↓

Phase 2B
Three.js Viewer

↓

Phase 3
PLC live data

↓

Phase 4
AI drawing parser

↓

Phase 5
MPC Preview
```

즉 **3D를 충분히 완성한 뒤 웹으로 옮기는 것**이 현재 가장 안정적이다.

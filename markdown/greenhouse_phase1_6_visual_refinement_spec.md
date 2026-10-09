# Phase 1.6 구현 명세 — 3D 온실 시각 품질·측벽·설비 정제 및 Web-ready 구조 점검

> 목적: Phase 1.5에서 완성한 `JSON → Blender → BLEND/GLB` 파이프라인과 기존 object contract를 유지하면서,  
> 현재 모델에서 보이는 **측벽 누락/개방감, 스크린 가시성 부족, 천창 구동계의 과도한 기계 표현, 양액 설비의 임시 배치·generic 형상, 링블로어 오해 가능성, 과밀 작물, 내부 탐색성 저하**를 수정한다.
>
> 이번 단계의 목표는 “새 기능을 많이 추가하는 것”이 아니라,  
> **현재 3D 자산을 실제 운영형 스마트온실처럼 읽히도록 정제하고, 다음 Three.js 단계에서 그대로 사용할 수 있는 상태로 만드는 것**이다.
>
> AI 도면 자동해석, Django, PLC 실연동, MPC, WebSocket은 이번 단계에서 구현하지 않는다.

---

# 0. Codex 최상위 지시

현재 저장소의 `README.md`, Phase 1 명세, Phase 1.5 명세를 모두 읽고 기존 구조를 보존한 상태에서 아래 개선사항을 구현하라.

절대 깨뜨리면 안 되는 기존 기능:

```text
- config/greenhouse.json 기반 생성
- Blender meter 단위
- X=길이, Y=폭, Z=높이
- greenhouse.blend / greenhouse.glb / generation_report.json 생성
- GH_* object naming
- GLB custom properties
- vent/screen/curtain control helper
- rerun-safe generation
- Phase 1 acceptance
- Phase 1.5 acceptance
- GLB roundtrip validation
```

이번 단계에서는 기존 코드의 기능 확장보다 **형상·배치·가시성·실제성·웹 활용성**을 우선한다.

---

# 1. 현재 Phase 1.5에서 확인된 문제

## 1.1 측벽이 지나치게 개방되어 보임

현재 모델은 지붕 외피는 보이지만 좌우 측벽이 실제 온실 외피/커튼으로 충분히 읽히지 않는다.

도면에는 다음 근거가 있다.

```text
1중 방풍벽
마감기둥
측면 커텐
커튼 롤러
드럼
샌드위치 판넬마감 75T
출입구
```

따라서 현재처럼 frame만 보이는 상태는 불충분하다.

---

## 1.2 스크린 fabric 가시성이 낮음

현재 차광/산광 스크린은 hierarchy와 control helper는 존재하지만,
실제 viewport에서 fabric이 잘 보이지 않거나 구동축만 과도하게 보일 수 있다.

현재 semantics는 유지한다.

```text
0% = 펼침
100% = 수납
```

단, 0% 상태에서는 사용자가 즉시 “스크린이 펼쳐져 있다”고 인식할 수 있어야 한다.

---

## 1.3 천창 구동 메커니즘이 시각적으로 복잡함

현재 rack/pinion/shaft/motor visual은 기능 검증에는 충분하지만,
실제 viewport에서 frame/rafter와 겹쳐 긴 사선 구조처럼 보이며 해석이 어렵다.

목표:

```text
“기계가 많아 보임”
→
“이 모터/축/랙이 천창을 여는구나”가 읽히는 구조
```

---

## 1.4 링블로어 형상 오해 가능성

현재 `GH_RING_BLOWER`는 일반 순환팬/프로펠러팬처럼 보이면 안 된다.

링블로어는 양액/설비 계통의 장비이며,
온실 내부 공기 순환팬과 구분되어야 한다.

이번 단계에서 **실제 유동팬/순환팬을 새로 임의 추가하지 않는다.**

실제 농가의 유동팬 수량/위치가 별도 확인되기 전까지:

```text
GH_CIRCULATION_FAN_* 생성 금지
```

---

## 1.5 양액 설비가 임시 진열처럼 보임

현재 Phase 1.5는 `end_service_strip` provisional placement를 사용한다.

문제:

```text
- tank/pump/blower가 중앙 통로 가까이 보임
- equipment group 간 기능적 관계가 약함
- 실제 service zone처럼 읽히지 않음
- tank 역할 구분이 약함
```

---

## 1.6 작물 밀도가 높고 내부 탐색성이 떨어짐

현재 기본 scene은 bed 20개에 plant instance가 매우 많다.

dashboard 목적상:

```text
실제 주수 재현
보다
“방울토마토 재배 온실임이 명확하고 내부가 탐색 가능함”
```

이 더 중요하다.

---

## 1.7 Sensor는 placeholder인 상태가 맞음

센서 위치는 실제 확인되지 않았으므로:

```text
verified=false
```

를 유지한다.

다만 향후 Three.js에서 클릭 가능한 anchor라는 점이 더 잘 드러나도록 구조/표시를 개선한다.

---

## 1.8 높이/스크린 교차 문제

현재 README상:

```text
eave/ridge 높이 잠정
shade screen 4.8m
diffuse screen 4.55m
```

가 일부 지붕 형상과 교차할 수 있다.

이 단계에서는 자동으로 물리적으로 “맞춰버리지” 않는다.

대신:

```text
- 시각적 clipping
- visible zone 제한
- warning 유지
```

를 사용한다.

---

# 2. 이번 Phase 1.6의 최종 목표

최종 scene은 다음 인상을 줘야 한다.

```text
“철골 뼈대 + placeholder”
가 아니라

“실제 운영 중인 4연동 토마토 스마트온실의
 구조 / 외피 / 내부 스크린 / 천창 / 작물 / 양액설비가
 서로 구분되는 3D operational model”
```

---

# 3. 반드시 구현할 개선 항목

```text
✅ 좌우 측벽 외피
✅ 측면 커튼 fabric
✅ 측면 방풍벽 표현
✅ front/rear closure 개선
✅ 출입구 영역 시각 개선
✅ screen fabric 시인성 개선
✅ screen retract 표현 개선
✅ 천창 구동계 정리
✅ ring blower 재모델링
✅ tank/pump/filter/control panel 재정리
✅ fertigation service zone 개선
✅ supply/drain piping 정리
✅ crop density 최적화
✅ crop LOD/lightweight 개선
✅ sensor anchor 시각 개선
✅ cover/screen/crop visibility preset
✅ preview camera 개선
✅ web-ready transform 검증
✅ existing acceptance 유지
```

---

# 4. 측벽 구현

## 4.1 좌우 측벽 shell

새 hierarchy:

```text
GH_SIDEWALLS
├─ GH_SIDEWALL_LEFT
│  ├─ GH_SIDEWALL_LEFT_FIXED
│  └─ GH_SIDE_CURTAIN_LEFT
└─ GH_SIDEWALL_RIGHT
   ├─ GH_SIDEWALL_RIGHT_FIXED
   └─ GH_SIDE_CURTAIN_RIGHT
```

## 4.2 Fixed wall

도면의 방풍벽/마감기둥 근거를 반영하되 BIM 정밀복원은 하지 않는다.

구성:

```text
lower fixed wall / windbreak zone
upper movable curtain zone
```

Material:

```text
MAT_SIDEWALL_FIXED
```

외피와 동일한 완전 투명 재질이 아니라, 경계가 읽히도록 약간 더 불투명하게 한다.

## 4.3 Side curtain

현재 `GH_SIDE_CURTAIN_LEFT/RIGHT` helper를 유지한다.

개선 목표:

```text
0%:
측벽이 실제 막으로 닫혀 보임

50%:
상부 또는 설정된 방향으로 절반 수납

100%:
대부분 개방
```

현재 scale-only 방식이 시각적으로 너무 단순하면
`panel + bottom bar + roll/drum` 구조로 개선한다.

## 4.4 Roller / Drum

측벽 상부에 다음을 표현한다.

```text
curtain shaft
roller
drum
bottom bar
guide line
```

정밀 기계부품은 필요 없다.

---

# 5. Front / Rear 면 개선

현재 모델에서 전후면이 frame만 보이면 보완한다.

최소:

```text
GH_FRONT_WALL
GH_REAR_WALL
GH_FRONT_DOOR
```

도면에서 출입구가 존재하므로 door placeholder는 drawing-supported로 분류 가능하다.

단 정확 door size가 불명확한 경우:

```text
geometry_confidence = approximate
```

---

# 6. 스크린 개선

## 6.1 목표

0% 펼침 상태에서:

```text
온실 상부에 넓은 screen fabric layer가 분명히 보여야 함
```

현재처럼 drive shaft/roller만 강조되어서는 안 된다.

## 6.2 차광/산광 시각 차이

차광:

```text
조금 더 진한 neutral fabric
opacity higher
```

산광:

```text
조금 더 밝고 diffuse
opacity lower
```

둘은 material과 위치로 구분 가능해야 한다.

## 6.3 Retracted state

100% 수납 시 screen panel을 단순히 `scale=1e-6`만 하는 것보다,
가능하면 retract edge에:

```text
small folded/rolled bundle
```

을 보여준다.

이 bundle은 static visual이어도 된다.

## 6.4 Screen clipping

screen height가 roof lower area를 침범하는 문제는
전체 폭을 무조건 유지하지 말고 시각 layer만 roof interior envelope 안에서 clip 가능하게 한다.

단 config의 original height value는 변경하지 않는다.

report에:

```text
visual_clipping_applied = true
```

를 기록한다.

---

# 7. 천창 구동계 개선

## 7.1 현재 contract 유지

다음 이름은 유지:

```text
GH_VENT_S01_01
GH_VENT_S01_01_PIVOT
GH_VENT_S01_01_DRIVE
GH_VENT_S01_01_SHAFT
GH_VENT_S01_01_RACK_A
GH_VENT_S01_01_RACK_B
GH_VENT_S01_01_PINION
GH_VENT_S01_01_MOTOR
```

## 7.2 시각 개선

다음 원칙을 적용한다.

```text
- motor는 compact
- shaft는 roof longitudinal axis와 정렬
- rack은 vent panel과 drive를 잇는 짧은 요소
- pinion은 rack 근처
- bearing은 shaft support로 보이게
- frame/rafter와 불필요한 교차 최소화
```

## 7.3 과도한 diagonal 제거

viewport에서 길게 대각선으로 보이는 bar/link가 실제 rack 표현 목적 이상으로 길면 축소한다.

목표:

```text
mechanism readable
not visually dominant
```

---

# 8. 링블로어 재모델링

## 8.1 금지

다음처럼 보이면 안 된다.

```text
일반 원형 프로펠러팬
온실 순환팬
벽걸이 fan
```

## 8.2 권장 low-poly 형태

```text
motor cylinder
+
ring/side-channel blower housing
+
inlet port
+
outlet port
+
base
```

Object:

```text
GH_RING_BLOWER
├─ MOTOR
├─ HOUSING
├─ INLET
├─ OUTLET
└─ BASE
```

metadata:

```python
asset_type = "blower"
system = "fertigation"
is_circulation_fan = False
```

---

# 9. 순환팬 정책

이번 단계에서 실제 농가 순환팬 위치/수량이 확인되지 않았으므로 생성하지 않는다.

README에 명시:

```text
No circulation fan is generated in Phase 1.6.
The drawing confirms a ring blower in the fertigation system,
not greenhouse air-circulation fan placement.
```

향후 농가 확인 후:

```text
GH_CIRCULATION_FAN_S01_01
```

등으로 별도 추가.

---

# 10. Fertigation service zone 개선

## 10.1 목표

장비가 중앙 aisle에 전시된 것처럼 보이지 않고
한쪽 서비스 영역에 모여 있어야 한다.

## 10.2 배치

기본:

```text
end_service_strip
```

유지하되 내부에서 다시 zoning한다.

예:

```text
Zone A — tanks
Zone B — pump/filter/blower
Zone C — control cabinet/instruments
Zone D — pipe manifold
```

## 10.3 equipment spacing

장비 간 최소 간격:

```text
0.35 ~ 0.6m visual clearance
```

작업 동선이 전혀 없어 보이지 않게 한다.

---

# 11. Tank 개선

각 tank를 동일 cylinder로만 두지 않는다.

## Nutrient tanks A/B/C

```text
similar size
distinct label plate
individual inlet/outlet
```

## Water tank

```text
slightly larger
```

## Mixing tank

```text
smaller or intermediate
mixing top detail
```

label text를 실제 geometry text로 넣어도 좋다.

예:

```text
A
B
C
WATER
MIX
```

너무 큰 글자는 금지.

---

# 12. Pump / Filter / Panel 개선

## Feed pump

```text
motor
pump body
inlet
outlet
base
```

## Filter

```text
vertical or inline canister
pipe connector
```

## Control panel

```text
cabinet body
door
small display
indicator elements
```

## Gauge / Flow meter

너무 작아서 viewport에서 안 보이면
실제보다 약간 크게 시각화해도 된다.

단 report:

```text
visual_scale_exaggerated = true
```

---

# 13. Pipe routing 개선

현재 bed supply/drain relation은 유지.

하지만 파이프가 무작위 선처럼 보이지 않도록:

```text
main supply manifold
→ branch
→ bed

bed
→ drain branch
→ main drain
```

구조를 시각적으로 표현한다.

색상은 과도하게 밝지 않게 구분한다.

---

# 14. 작물 밀도 개선

현재 visual plants가 너무 조밀할 수 있다.

기본값 변경 제안:

```json
"crops": {
  "plant_spacing": 0.7,
  "max_visual_plants_per_bed": 45
}
```

정확한 재배 주수가 아니라 visualization density다.

## 14.1 Crop LOD

추가 config:

```json
"crops": {
  "lod": "dashboard"
}
```

`dashboard` mode:

```text
leaf count reduced
tomato cluster limited
stem visible
walkway visibility preserved
```

## 14.2 Crop row spacing

bed center를 따라 완전 정렬만 하지 말고
약간의 deterministic offset variation을 줄 수 있다.

단 randomness seed 고정.

목표:

```text
copy-paste wall 느낌 완화
```

---

# 15. 센서 시각 개선

실제 위치는 그대로 unverified.

구조:

```text
GH_SENSOR_T_RH_01_ANCHOR
└─ GH_SENSOR_T_RH_01
```

mesh는 작게 유지한다.

Anchor는 Blender viewport에서 확인 가능하되
GLB에서는 Three.js label anchor로 쓸 수 있어야 한다.

custom property:

```text
live_data_ready=true
verified_position=false
```

---

# 16. Visibility Preset

새 helper:

```python
apply_view_preset(name)
```

지원:

```text
exterior
interior
equipment
control_devices
```

## exterior

```text
cover visible
sidewall visible
crop normal
equipment normal
```

## interior

```text
roof cover hidden
sidewall transparency increased
screen visible
crop visible
```

## equipment

```text
cover hidden
crop partly hidden or faded
fertigation emphasized
```

## control_devices

```text
cover hidden
crop reduced visibility
vent/screen/curtain/sensor emphasized
```

---

# 17. Material 정제

전체 색상 정책:

```text
frame = neutral metallic gray
cover = subtle transparent
sidewall = slightly visible translucent
screen shade = darker neutral
screen diffuse = lighter neutral
crop = muted natural green
tomato = restrained red
equipment = industrial neutral
pipes = muted categorical distinction
sensor = small accent
```

과한 saturated neon 금지.

---

# 18. Preview rendering 개선

기존 preview에 다음을 추가한다.

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
```

---

# 19. Web-ready animation preparedness

실제 Three.js animation은 다음 단계에서 한다.

하지만 Phase 1.6에서 반드시 검증:

```text
vent pivot transform
screen scale/retract origin
curtain retract origin
sensor anchor position
```

GLB 재import 후에도 동작해야 한다.

---

# 20. Blender animation smoke test

실제 웹 animation은 아니지만
Blender 내부 smoke test를 추가한다.

새 script:

```text
scripts/create_motion_preview.py
```

timeline:

```text
Frame 1:
vent 0
shade 0
curtain 0

Frame 60:
vent 50
shade 50
curtain 50

Frame 120:
vent 100
shade 100
curtain 100
```

실제 scene contract가 animation 가능한지 검증 목적.

---

# 21. Config 추가/수정

예:

```json
{
  "sidewalls": {
    "enabled": true,
    "fixed_lower_wall_height": 0.8,
    "material_opacity": 0.28
  },

  "visual_refinement": {
    "clip_screens_to_interior": true,
    "compact_vent_mechanism": true,
    "service_zone_layout": true
  },

  "crops": {
    "plant_spacing": 0.7,
    "max_visual_plants_per_bed": 45,
    "lod": "dashboard"
  },

  "preview": {
    "generate_refinement_views": true
  }
}
```

기존 config와 backward compatibility 유지.

---

# 22. 신규/수정 파일 권장

신규:

```text
src/geometry/sidewalls.py
src/refinement.py
scripts/create_motion_preview.py
tests/test_refinement.py
```

기존 수정:

```text
src/main.py
src/materials.py
src/preview.py
src/report.py
src/operational_validation.py
src/geometry/screens.py
src/geometry/vents.py
src/geometry/fertigation.py
src/geometry/equipment_primitives.py
src/geometry/crops.py
src/geometry/curtains.py
src/geometry/pipes.py
config/greenhouse.json
config/greenhouse.schema.json
README.md
```

---

# 23. Phase 1.6 Acceptance Criteria

## A. Sidewall

0% curtain 상태에서 좌우 측벽이 뻥 뚫려 보이지 않아야 한다.

## B. Curtain motion

0/50/100 상태가 육안으로 명확히 구분되어야 한다.

## C. Screen visibility

차광/산광 screen 0% 상태에서 fabric이 명확히 보여야 한다.

## D. Screen retract

100% 상태에서 screen이 수납된 위치가 이해 가능해야 한다.

## E. Vent mechanism

motor/shaft/rack/pinion이 서로 관계 있게 보이되
frame보다 더 눈에 띄지 않아야 한다.

## F. Ring blower

일반 circulation fan처럼 보이지 않아야 한다.

metadata:

```text
is_circulation_fan=false
```

## G. Fertigation zoning

tank/pump/filter/blower/panel이 service zone으로 읽혀야 한다.

## H. Crop

dashboard 시점에서 aisle이 식별 가능해야 한다.

## I. Sensor

sensor anchor가 존재하고 `verified_position=false`.

## J. Preview

새 refinement preview가 모두 생성되어야 한다.

## K. Existing regression

Phase 1/1.5 acceptance 모두 통과.

## L. GLB

재import 후:

```text
sidewall
curtain
screen
vent
fertigation
sensor
```

major object names/hierarchy 유지.

---

# 24. 실행 명령

## 생성

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background `
  --python-exit-code 1 `
  --python scripts/generate_greenhouse.py `
  -- `
  --config config/greenhouse.json `
  --output-dir dist
```

## 전체 validation

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

## Motion preview 생성

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background `
  --python-exit-code 1 `
  --python scripts/create_motion_preview.py `
  -- `
  --config config/greenhouse.json `
  --output-dir tmp/motion_preview
```

---

# 25. 사람이 반드시 확인할 화면

```text
1. exterior perspective
2. sidewall closed
3. sidewall half open
4. interior cover hidden
5. screen deployed
6. screen retracted
7. vent mechanism closeup
8. fertigation service zone
9. ring blower closeup
10. crop aisle view
```

---

# 26. README에 반드시 추가할 내용

```text
- sidewall model 설명
- curtain semantics
- screen visibility/retract 방식
- ring blower ≠ circulation fan 명시
- circulation fan 미구현 이유
- fertigation placement provisional 설명
- crop visual density는 실제 주수 아님
- sensor 위치 미검증
- screen clipping은 시각화용 처리
- Three.js에서 사용할 moving object contract
- Blender motion preview는 웹 animation이 아님
```

---

# 27. Codex용 Goal Prompt

아래를 그대로 사용하라.

---

현재 저장소의 README.md와 Phase 1/1.5 구현 명세를 모두 읽은 뒤, 이 Phase 1.6 명세를 single source of truth로 사용해서 기존 3D 온실 생성기를 시각적으로 정제해.

기존 JSON → Blender → BLEND/GLB 파이프라인, object naming, control helper, custom properties, roundtrip validation, Phase 1/1.5 acceptance는 절대 깨뜨리지 마.

이번 작업의 핵심은 새 기능 추가가 아니라 아래 시각적/구조적 문제를 수정하는 것이다.

1. 측벽이 뻥 뚫려 보이는 문제 수정
   - 도면 근거가 있는 1중 방풍벽, 측면 커튼, roller/drum, fixed lower wall을 반영
   - 좌우 sidewall hierarchy를 별도 구성
   - curtain 0/50/100 상태가 시각적으로 명확해야 함

2. front/rear closure 개선
   - 외피/마감 영역과 출입구 placeholder 표현

3. 차광/산광 스크린 시각 개선
   - 0% 상태에서 fabric이 명확히 보여야 함
   - 100% 상태에서 retract bundle이 이해 가능해야 함
   - drive shaft보다 screen fabric이 시각적으로 우선되게
   - roof와 교차하는 영역은 config 값을 바꾸지 말고 visual clipping으로 처리하고 report에 기록

4. 천창 구동계 정리
   - motor compact
   - shaft 방향 정리
   - rack/pinion을 짧고 명확하게
   - frame과 불필요하게 겹치는 긴 diagonal linkage 제거
   - 기존 object names/control contract 유지

5. `GH_RING_BLOWER` 재모델링
   - 일반 온실 순환팬처럼 보이지 않게
   - motor + ring/side-channel blower housing + inlet/outlet + base로 구성
   - `is_circulation_fan=false`
   - 실제 circulation fan은 별도 현장 정보가 없으므로 생성하지 말 것

6. 양액 service zone 개선
   - tank / pump / filter / blower / control panel / instruments를 기능적으로 묶어 배치
   - 중앙 통로에 장비를 진열한 것처럼 보이지 않게
   - tank A/B/C, water, mixing 역할이 시각적으로 구분되게
   - supply/drain은 main manifold → branch → bed 관계가 읽히게

7. 작물 density 조정
   - dashboard용으로 aisle visibility를 확보
   - 기본 max_visual_plants_per_bed를 45 수준으로 낮추고 lightweight LOD 제공
   - 실제 재배 주수로 주장하지 말 것

8. sensor는 위치 미확인 placeholder를 유지
   - verified_position=false
   - anchor를 Three.js label point로 사용할 수 있게 유지

9. visibility preset 추가
   - exterior
   - interior
   - equipment
   - control_devices

10. preview render 확대
   - sidewall closed/half/open
   - screen deployed/retracted
   - vent mechanism closeup
   - ring blower closeup
   - fertigation service zone
   - sensor placeholder

11. Blender motion smoke test 추가
   - vent/screen/curtain 0→50→100
   - 실제 web animation 구현이 아니라 pivot/transform 검증 목적

12. 기존 Phase 1/1.5 acceptance와 GLB roundtrip을 모두 유지하고 Phase 1.6 acceptance까지 통과할 것

도면에서 확인되지 않은 실제 circulation fan, 센서 위치, PLC tag, 장비 정확 치수/좌표는 임의 생성하거나 verified 처리하지 마.

작업 완료 후 반드시 다음을 출력해.

- 수정/추가 파일 목록
- 실행 명령
- validation 결과
- motion preview 실행법
- drawing-supported / approximate / placeholder 항목
- GLB object contract
- known limitations
- 사람이 확인해야 할 preview 목록

Acceptance 실패가 있으면 통과할 때까지 수정해.

---

# 28. 권장 다음 단계

Phase 1.6 완료 후 더 이상 Blender asset에 큰 문제가 없다면:

```text
Phase 2B — Three.js Interactive Viewer
```

로 넘어간다.

그 단계에서:

```text
GLB load
camera/orbit
object picking
sensor labels
vent/screen/curtain animation
mock PLC state
```

를 구현한다.

실제 PLC 연결과 MPC는 그 이후 단계에서 진행한다.

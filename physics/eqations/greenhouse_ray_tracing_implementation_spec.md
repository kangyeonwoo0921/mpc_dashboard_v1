# Greenhouse Ray-Tracing Radiation Model — Implementation Specification

> 목적: Codex / Claude Code가 이 문서를 단독으로 읽고, 기존 3D 온실 대시보드에 **태양 위치 + 3D ray tracing + 작물영역 일사량 계산**을 단계적으로 구현할 수 있도록 하는 실행 명세서.
>
> 기준 논문: Zhang et al. (2020), *Solar Radiation Allocation and Spatial Distribution in Chinese Solar Greenhouses: Model Development and Application*, Energies 13, 1108.
>
> 중요: 원 논문은 **Chinese Solar Greenhouse(CSG)** 를 대상으로 한다. 본 프로젝트는 **4연동 투광형 온실 + 천창 + 스크린**이므로 CSG 전용 지오메트리 식은 그대로 사용하지 않고, 복사 전달 구조만 3D mesh 기반으로 일반화한다.

---

# 0. 최종 목표

```text
datetime + site position + greenhouse orientation
                  ↓
          solar position
                  ↓
          sun direction vector
                  ↓
      greenhouse 3D mesh / GLB
                  ↓
             ray tracing
                  ↓
 direct shadow / cover crossing / screen crossing
                  ↓
 measured or decomposed DNI + DHI
                  ↓
 crop-zone spatial irradiance map
                  ↓
 effective greenhouse irradiance
                  ↓
 thermal model / MPC input
```

핵심 원칙:
- 같은 `sun direction`을 Three.js 태양 표시와 Python 물리 계산에 같이 사용한다.
- visualization과 physics는 동일한 좌표계/상태를 공유한다.
- 초기 버전은 **direct + diffuse**까지만 구현한다.
- multi-reflection, CFD, leaf-level optics는 초기 범위에서 제외한다.
- PLC write/자동제어는 하지 않는다.

---

# 1. 구현 단계

## Phase A — Geometry + Solar Position
현장 광학 스펙 없이 가능.

1. 물리 좌표계 확정
2. site config 구조
3. greenhouse orientation 정의
4. solar altitude / azimuth 계산
5. solar direction vector 계산
6. Three.js Sun visualization
7. CropZone 1 m grid 생성
8. binary shadow ray casting

## Phase B — Radiation
현장 일사/피복/스크린 스펙 필요.

1. GHI/DNI/DHI 입력 구조
2. cover transmittance
3. screen transmittance
4. direct irradiance
5. diffuse irradiance
6. spatial irradiance map
7. area-weighted mean irradiance

## Phase C — Refinement
필요할 때만.

1. incidence-angle-dependent cover transmittance
2. sky-view factor
3. partial screen geometry refinement
4. reflected radiation / radiosity
5. PAR / PPFD / DLI conversion
6. thermal model coupling
7. MPC coupling

---

# 2. Equation Mapping

| Eq. | 원 논문 역할 | 본 프로젝트 판단 | 구현 방침 |
|---|---|---|---|
| 1–4 | CSG 이중 원호 지붕 형상 | 제외 | GLB triangle mesh 사용 |
| 5 | roof slope β | 변형 | mesh face normal 사용 |
| 6 | 입사각 | 핵심 변형 | `cosθ = n·s` |
| 7 | beam on surface | 핵심 변형 | `DNI * max(0,n·s)` |
| 8 | isotropic diffuse | 변형 | 초기 `DHI * τ * F_sky` |
| 9 | 외부 지면 반사 | 후속 | v1에서는 0 |
| 10–13 | clear/cloud sky 외부일사 생성 | 대체 | 실측 GHI/DNI/DHI 또는 decomposition |
| 14 | 일 누적 외부입사 | 선택 | 제어 핵심 아님 |
| 15–18 | Fresnel/Snell 투과율 | 후속 | v1 constant τ, 이후 angle-dependent |
| 19–21 | entering direct+diffuse | 핵심 | 구조 유지 |
| 22 | 일 누적 entering radiation | 선택 | DLI/일적산용 |
| 23 | sunray path | 핵심 변형 | 3D `r=p+λs` |
| 24 | 내부 receiving point beam | 변형 | receiver normal 기반 |
| 25–27 | diffuse angular distribution | 후속 | v1 단순화 |
| 28–29 | multi-reflection | 초기 제외 | Phase C radiosity |
| 30 | 내부 총 일사 | 핵심 | `I=Idir+Idiff(+Irefl)` |
| 31 | 내부면 흡수에너지 | 선택/제외 | 북벽 열저장용 |
| 32 | W/m²→lux | 제외 | 추후 PAR/PPFD/DLI |
| 33–34 | 북벽/전체 solar availability | 제외 | CSG 전용 |

---

# 3. 완전 제외할 식

## Eq. 1–4
- CSG의 남측 이중 원호 지붕 반경/중심/곡선식.
- 본 프로젝트는 이미 Blender/GLB geometry가 있으므로 재구성하지 않는다.

대체:
```text
analytical roof equation
→ GLB triangle mesh
```

## Eq. 10–13
- clear-sky/cloud-cover 모델로 외부 beam/diffuse를 생성.
- 실시간 운영은 현장 solar sensor 또는 공공 기상자료를 사용.

대체:
```text
measured GHI
→ DNI/DHI decomposition
```

## Eq. 31, 33, 34
- CSG의 north wall / north roof / ground heat-storage 평가용.
- 대상 온실과 목적이 다르므로 제외.

## Eq. 32
- W/m² → lux 경험식.
- 작물 제어에는 lux보다 PAR/PPFD/DLI가 적합하므로 제외 권장.

---

# 4. 변형하여 사용할 식

## Eq. 5 — roof slope
논문은 roof curve를 미분해 slope β를 구하지만, 본 프로젝트는 mesh normal을 쓴다.

```python
surface_normal = triangle.face_normal
```

## Eq. 6 — incidence angle

3D 일반화:

```math
cos(theta_i) = n_i · s
```

구현:

```python
cos_theta = clamp(dot(normal, sun_dir), -1.0, 1.0)
theta = acos(cos_theta)
```

주의:
- normal 방향 일관성 유지
- 앞면 입사만 사용할 경우 `max(0, dot(...))`

## Eq. 7 — beam radiation on surface

권장:

```math
I_beam_surface = DNI * max(0, n · s)
```

주의:
- DNI와 GHI를 혼동하지 말 것.
- GHI만 있으면 DNI/DHI decomposition 필요.

## Eq. 8 — diffuse radiation

v1:

```math
I_diff,j = DHI * tau_cover_diff * T_screen_diff,j * F_sky,j
```

초기:

```math
F_sky,j = 1
```

## Eq. 9 — outside ground reflection

초기:

```python
ground_reflected = 0.0
```

후속:

```math
I_ground_reflected = GHI * albedo * view_factor
```

---

# 5. 피복 투과율 — Eq. 15–18

논문은 Fresnel + Snell 법칙으로 angle-dependent transmittance를 계산한다.

v1:
```python
tau_cover_direct = config.cover.direct_transmittance
tau_cover_diffuse = config.cover.diffuse_transmittance
```

Phase C:
```text
theta_i
→ Fresnel/Snell
→ tau_cover(theta_i)
```

절대 규칙:
- 논문 PO film의 `refractive index = 1.535`를 실제 온실에 그대로 쓰지 말 것.
- 실제 피복재 스펙이 들어오면 그때 적용.

---

# 6. 핵심 식

## Eq. 19–21 — direct + diffuse decomposition

본 프로젝트 일반화:

```math
I_j = I_dir,j + I_diff,j
```

direct:
```math
I_dir,j =
DNI
* cos(theta_crop,j)
* tau_cover_dir(theta_cover)
* T_screen_dir,j
* S_j
```

diffuse:
```math
I_diff,j =
DHI
* tau_cover_diff
* T_screen_diff,j
* F_sky,j
```

## Eq. 23 — ray path

3D 일반화:

```math
r(lambda) = p + lambda * s
```

where:
- `p`: CropZone grid point
- `s`: sun direction
- `lambda >= 0`

구현 개념:

```python
ray_origin = crop_point
ray_direction = sun_dir
hits = intersect_scene(ray_origin, ray_direction)
```

판정:
```text
opaque object hit
→ blocked / shadow

transparent cover hit
→ attenuation

screen hit
→ additional attenuation

no opaque blocker
→ sunlit
```

## Eq. 24 — receiving point beam

원 논문의 2D north-wall 식은 사용 금지.

수평 crop reference plane:

```math
cos(theta_crop) = sin(solar_altitude)
```

따라서:

```math
I_dir,j =
DNI
* sin(h)
* tau_cover_dir
* T_screen_dir,j
* S_j
```

3D crop surface를 쓰면:

```math
cos(theta_crop,j) = max(0, n_crop,j · s)
```

중요:
- cover incidence cosine과 crop-plane cosine을 중복해서 곱하지 말 것.
- cover incidence는 투과율 계산용.
- crop incidence는 receiving flux projection용.

## Eq. 30 — total inside radiation

v1:
```math
I_crop,j = I_dir,j + I_diff,j
```

Phase C:
```math
I_crop,j = I_dir,j + I_diff,j + I_reflected,j
```

---

# 7. 초기 제외하지만 보존할 식

## Eq. 25–27
- diffuse angular distribution / view factor.
- 3D multispan에서는 그대로 쓰지 않는다.
- v1은 `F_sky=1`, 이후 3D sky-view factor로 고도화.

## Eq. 28–29
- multi-reflection.
- 초기 제외.
- Phase C에서 radiosity 또는 iterative surface exchange로 구현 가능.

---

# 8. 최종 v1 물리식

```math
cos(theta_i) = n_i · s
```

```math
r(lambda) = p + lambda s
```

```math
S_j =
0, if opaque geometry blocks ray
1, otherwise
```

```math
I_dir,j =
DNI
* max(0, n_crop,j · s)
* tau_cover
* T_screen,j
* S_j
```

```math
I_diff,j =
DHI
* tau_cover,diff
* T_screen,diff,j
* F_sky,j
```

```math
I_total,j = I_dir,j + I_diff,j
```

```math
I_eff =
sum(I_total,j * A_j)
/
sum(A_j)
```

`I_eff`를 이후 thermal model / MPC의 radiation input으로 사용한다.

---

# 9. Solar Position Contract

입력:
```text
timestamp
latitude
longitude
timezone
greenhouse_long_axis_azimuth_deg
```

출력:
```text
solar_altitude_deg
solar_azimuth_deg
sun_direction_world
sun_direction_greenhouse
```

권장:
- `pvlib`
- `astral`
- 검증된 SPA 구현

가능하면 직접 천문식을 새로 구현하지 않는다.

---

# 10. Coordinate Convention

권장 물리 좌표계:

```text
+Z = Up
+X = greenhouse longitudinal axis
+Y = greenhouse lateral axis
```

지리 좌표:
```text
azimuth 0°   = North
azimuth 90°  = East
azimuth 180° = South
azimuth 270° = West
```

필수 변환:
```text
geographic ENU sun vector
→ greenhouse local XYZ
```

`greenhouse_long_axis_azimuth_deg`는 **true north 기준 clockwise**.

---

# 11. CropZone Grid

초기:
```text
resolution = 1 m × 1 m
```

각 cell:

```python
@dataclass(frozen=True)
class CropCell:
    cell_id: str
    center_xyz: tuple[float, float, float]
    normal_xyz: tuple[float, float, float]
    area_m2: float
```

수평 reference plane이면:
```python
normal_xyz = (0.0, 0.0, 1.0)
```

출력:
```text
sunlit
direct_W_m2
diffuse_W_m2
total_W_m2
```

---

# 12. Shadow Factor

```math
S_j =
0 if opaque geometry blocks sun ray
1 otherwise
```

physics semantic:
```text
OPAQUE_STRUCTURE
→ blocks direct ray

TRANSPARENT_COVER
→ does not block; applies tau_cover

SHADE_SCREEN
→ attenuation, not binary blocker

DIFFUSE_SCREEN
→ attenuation, not binary blocker

ROOF_VENT
→ geometry changes with actuator state

DECORATIVE
→ ignored by physics
```

---

# 13. Screen Semantics

현재 runtime 의미:

```text
opening_percent = 100
→ fully retracted / fully open

opening_percent = 0
→ fully deployed
```

physics:

```math
deployment_fraction = 1 - opening_percent/100
```

## 권장 방식
screen mesh가 실제 전개상태를 반영하면:

```text
ray crosses deployed screen
→ T_screen = tau_screen

ray does not cross screen
→ T_screen = 1
```

## fallback
geometry가 불완전한 경우에만:

```math
tau_screen_eff =
(1 - f_deploy) + f_deploy * tau_screen
```

이 fallback은 공간효과를 잃으므로 우선순위가 낮다.

---

# 14. 실시간 데이터 계약

```json
{
  "timestamp": "...",
  "site": {
    "latitude_deg": null,
    "longitude_deg": null,
    "elevation_m": null,
    "timezone": "Asia/Seoul",
    "greenhouse_long_axis_azimuth_deg": null
  },
  "weather": {
    "ghi_W_m2": null,
    "dni_W_m2": null,
    "dhi_W_m2": null
  },
  "actuators": {
    "roof_vent_left_percent": null,
    "roof_vent_right_percent": null,
    "shade_screen_1_opening_percent": null,
    "shade_screen_2_opening_percent": null
  }
}
```

절대 규칙:

```text
missing != 0
```

예:

```python
dni = None
```

를 자동으로 `0`으로 바꾸지 말 것.

상태 예:

```json
{
  "radiation_status": "decomposition_required"
}
```

---

# 15. Config

```text
config/
  site.json
  optical.json
  radiation.json
```

## site.json

```json
{
  "latitude_deg": null,
  "longitude_deg": null,
  "elevation_m": null,
  "timezone": "Asia/Seoul",
  "greenhouse_long_axis_azimuth_deg": null,
  "source": "unknown",
  "verified": false
}
```

## optical.json

```json
{
  "cover": {
    "material": null,
    "direct_transmittance": null,
    "diffuse_transmittance": null,
    "refractive_index": null,
    "source": "unknown",
    "verified": false
  },
  "shade_screen_1": {
    "direct_transmittance": null,
    "diffuse_transmittance": null,
    "reflectance": null,
    "absorptance": null,
    "source": "unknown",
    "verified": false
  },
  "shade_screen_2": {
    "direct_transmittance": null,
    "diffuse_transmittance": null,
    "reflectance": null,
    "absorptance": null,
    "source": "unknown",
    "verified": false
  }
}
```

## radiation.json

```json
{
  "grid_resolution_m": 1.0,
  "direct_model": "ray_cast",
  "diffuse_model": "isotropic",
  "sky_view_factor_mode": "unity",
  "ground_reflection": false,
  "multi_reflection": false,
  "canopy_attenuation": false
}
```

---

# 16. Provenance

허용:
```text
measured
manufacturer_spec
drawing
paper
estimated
temporary_test_fixture
unknown
```

예:

```json
{
  "value": 0.72,
  "provenance": "manufacturer_spec",
  "verified": true
}
```

테스트값:

```json
{
  "value": 0.70,
  "provenance": "temporary_test_fixture",
  "verified": false
}
```

실제값처럼 표시하지 않는다.

---

# 17. 권장 파일 구조

```text
greenhouse_web/
  physics/
    __init__.py
    contracts.py
    coordinates.py
    solar.py
    geometry.py
    raytrace.py
    radiation.py
    screens.py
    aggregation.py
    validation.py

    adapters/
      live_to_physics.py

    tests/
      test_coordinates.py
      test_solar.py
      test_raytrace.py
      test_radiation.py
      test_screen_semantics.py
      test_missing_data.py
```

---

# 18. 주요 데이터 클래스

```python
@dataclass(frozen=True)
class SiteConfig:
    latitude_deg: float | None
    longitude_deg: float | None
    elevation_m: float | None
    timezone: str
    greenhouse_long_axis_azimuth_deg: float | None
```

```python
@dataclass(frozen=True)
class SolarState:
    altitude_deg: float
    azimuth_deg: float
    sun_direction_world: tuple[float, float, float]
    sun_direction_greenhouse: tuple[float, float, float]
```

```python
@dataclass(frozen=True)
class OpticalProperties:
    tau_direct: float | None
    tau_diffuse: float | None
```

```python
@dataclass(frozen=True)
class RadiationCellResult:
    cell_id: str
    sunlit: bool
    direct_W_m2: float | None
    diffuse_W_m2: float | None
    total_W_m2: float | None
```

---

# 19. API Signatures

## Solar

```python
def calculate_solar_state(
    timestamp,
    site_config: SiteConfig
) -> SolarState:
    ...
```

Acceptance:
- altitude/azimuth 반환
- ENU → greenhouse local transform
- normalized vector
- timezone-aware datetime 필수
- nighttime 처리

## Raytrace

```python
def trace_direct_ray(
    origin_xyz,
    sun_direction_xyz,
    scene
) -> RayTraceResult:
    ...
```

```python
@dataclass(frozen=True)
class RayTraceResult:
    blocked: bool
    opaque_hits: tuple
    cover_hits: tuple
    screen_hits: tuple
```

---

# 20. Direct Radiation Algorithm

```python
for cell in crop_grid:

    if solar.altitude_deg <= 0:
        direct = 0.0
        continue

    ray = trace_direct_ray(
        origin_xyz=cell.center_xyz,
        sun_direction_xyz=solar.sun_direction_greenhouse,
        scene=scene,
    )

    S = 0 if ray.blocked else 1

    tau_cover = calculate_cover_transmission(ray, optics)

    tau_screen = calculate_screen_transmission(
        ray,
        optics,
        actuator_state,
    )

    cos_crop = max(
        0.0,
        dot(
            cell.normal_xyz,
            solar.sun_direction_greenhouse,
        ),
    )

    direct = (
        DNI
        * cos_crop
        * tau_cover
        * tau_screen
        * S
    )
```

---

# 21. Diffuse Radiation Algorithm v1

```python
for cell in crop_grid:

    F_sky = 1.0

    tau_cover = cover.diffuse_transmittance
    tau_screen = screen_diffuse_transmission(...)

    diffuse = (
        DHI
        * tau_cover
        * tau_screen
        * F_sky
    )
```

---

# 22. Aggregation

```math
I_eff =
sum(I_j * A_j)
/
sum(A_j)
```

권장 출력:

```text
mean_W_m2
min_W_m2
max_W_m2
sunlit_fraction
p10_W_m2
p50_W_m2
p90_W_m2
```

---

# 23. GHI-only 처리

규칙:

```text
GHI exists
DNI missing
DHI missing
→ status = decomposition_required
```

interface:

```python
def decompose_ghi(
    ghi_W_m2,
    solar_state,
    weather_context,
) -> tuple[float, float]:
    raise NotImplementedError
```

후보:
- Erbs
- Reindl
- DIRINT

알고리즘은 별도 문헌검토 후 확정.

---

# 24. Visualization Coupling

Single source of truth:

```text
backend physics solar calculation
→ frontend visualization
```

backend response 예:

```json
{
  "solar": {
    "altitude_deg": 42.7,
    "azimuth_deg": 181.3,
    "direction": [0.02, -0.73, 0.68]
  }
}
```

frontend:
```text
same direction
→ Sun object position
→ shadow visualization
```

frontend에서 별도의 태양계산 로직을 중복 구현하지 않는다.

---

# 25. 테스트

## Solar position
- 알려진 날짜/시간에서 고도/방위 합리적 범위
- 일출 전 altitude < 0
- 정오 부근 altitude 증가

## Vector normalization

```python
assert abs(norm(sun_dir) - 1.0) < 1e-9
```

## Analytical shadow test

높이 `H` 수직 기둥:

```math
L = H / tan(alpha)
```

ray-traced shadow 길이와 비교.

## Direction test

```text
morning → shadow westward
afternoon → shadow eastward
```

좌표계 정의에 맞게 검증.

## Opaque blocker

```text
opaque mesh between cell and sun
→ sunlit = false
```

## Transparent cover

```text
cover hit only
→ sunlit = true
→ irradiance attenuated
```

## Screen

```text
fully retracted
→ no screen attenuation

fully deployed
→ tau_screen applied
```

## Monotonicity

```text
screen deployment 증가
→ effective direct irradiance가 증가하면 안 됨
```

## Missing data

```text
tau_cover = None
→ silently 0으로 바꾸지 않음
→ incomplete/invalid status
```

---

# 26. Acceptance Criteria — Phase A

- [ ] `site.json` 존재
- [ ] solar position module 구현
- [ ] timezone-aware timestamp 처리
- [ ] geographic → greenhouse coordinate transform 구현
- [ ] Three.js Sun이 backend solar state 사용
- [ ] CropZone 1m grid 생성
- [ ] binary shadow ray casting 구현
- [ ] analytical shadow test 통과
- [ ] 오전/정오/오후 shadow 이동 정상
- [ ] 실제 현장값 없으면 `verified:false`

---

# 27. Acceptance Criteria — Phase B

- [ ] GHI/DNI/DHI data contract
- [ ] cover direct/diffuse transmittance
- [ ] screen direct/diffuse transmittance
- [ ] direct map
- [ ] diffuse map
- [ ] total radiation map
- [ ] area-weighted mean
- [ ] sunlit fraction
- [ ] missing != zero
- [ ] provenance/status 제공

---

# 28. Non-goals

초기 구현에서 하지 말 것:

```text
X CFD
X leaf-level ray tracing
X Monte Carlo photon transport
X spectral radiation
X detailed BSDF
X full radiosity
X multiple reflection
X canopy Beer-Lambert attenuation
X cloud geometry reconstruction
X PLC write
X automatic actuator control
```

---

# 29. 현장정보가 들어오면 교체할 값

필수:

```text
latitude
longitude
greenhouse azimuth
cover material
cover tau_direct
cover tau_diffuse
screen material
screen tau_direct
screen tau_diffuse
screen opening% ↔ deployment state
roof vent % ↔ actual angle
solar sensor type / units / installation
```

가능하면:

```text
DNI/DHI availability
screen reflectance
screen absorptance
cover refractive index
wind speed
wind direction
```

---

# 30. 모델 결과 API

```json
{
  "timestamp": "...",
  "solar": {
    "altitude_deg": 0,
    "azimuth_deg": 0,
    "direction_greenhouse": [0, 0, 1]
  },
  "radiation": {
    "status": "ok",
    "mean_W_m2": 0,
    "min_W_m2": 0,
    "max_W_m2": 0,
    "sunlit_fraction": 0,
    "grid": []
  },
  "provenance": {
    "site": "estimated",
    "cover": "unknown",
    "screen": "unknown"
  }
}
```

---

# 31. Coding Rules for Codex / Claude Code

1. 기존 기능을 깨지 말 것.
2. Three.js viewer와 physics engine 분리 유지.
3. physics code를 Django view에 직접 섞지 말 것.
4. network I/O와 pure physics function 분리.
5. 함수는 deterministic하게 작성.
6. unknown parameter를 임의 추정하지 말 것.
7. test fixture와 production config 분리.
8. `None`을 0으로 자동 변환하지 말 것.
9. 좌표계 변환을 단일 module로 중앙화.
10. sun direction 계산을 frontend/backend에서 중복 구현하지 말 것.
11. initial physics model은 단순하게 유지.
12. correctness 검증 후 optimization.
13. equation implementation에는 provenance 주석 남길 것.

예:

```python
# Adapted conceptually from Zhang et al. (2020), Eq. 6.
# Generalized from 2D roof-slope geometry to 3D mesh surface normals.
```

---

# 32. 코드 에이전트 실행 순서

```text
STEP 1
현재 repo 구조 분석

STEP 2
physics package 재사용 또는 생성

STEP 3
coordinate convention 문서화

STEP 4
SiteConfig / SolarState contracts 생성

STEP 5
solar position 구현 + tests

STEP 6
greenhouse azimuth transform 구현 + tests

STEP 7
backend solar API 생성

STEP 8
Three.js Sun visualization을 backend 값에 연결

STEP 9
CropZone 1m grid 생성

STEP 10
binary opaque ray casting 구현

STEP 11
analytical shadow test

STEP 12
screen/cover semantic mesh classification

STEP 13
radiation calculation skeleton 추가

STEP 14
optical 실측값이 없으면 null + incomplete status 유지
```

---

# 33. 완료 보고 형식

```markdown
## Implemented
- ...

## Files changed
- ...

## Tests
- ...

## Verified behavior
- ...

## Remaining unknown parameters
- ...

## Known limitations
- ...

## Next recommended step
- ...
```

---

# 34. 핵심 요약

Zhang et al.의 34개 식을 그대로 복제하지 않는다.

실제로 가져갈 핵심:

```text
Eq. 6
→ incidence geometry

Eq. 7
→ direct beam projection

Eq. 19–21
→ direct + diffuse decomposition

Eq. 23
→ ray path / shadow concept

Eq. 30
→ total inside radiation structure
```

이를 3D mesh 기반으로 일반화한다.

최종 control-oriented output:

```math
I_eff =
sum(I_total,j * A_j)
/
sum(A_j)
```

이 값이 이후 thermal model 및 MPC의 solar disturbance/input이 된다.

---

# 35. Source Note

Zhang, X. et al. (2020). *Solar Radiation Allocation and Spatial Distribution in Chinese Solar Greenhouses: Model Development and Application*. Energies, 13, 1108.

Scope distinction:
- Source greenhouse: CSG, 2D analytical curved south roof, opaque north wall/roof
- Target greenhouse: 4-span transparent greenhouse, GLB/Blender geometry, roof vents, shade screens
- Geometry-specific equations are not directly transferable.
- Radiation transport concepts are adapted into a 3D mesh-based model.

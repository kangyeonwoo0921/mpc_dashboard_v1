# Frontend API · 3D Model Contract

대상: 대시보드 프론트엔드 개발자. 백엔드(Django) 내부 구현을 몰라도 화면을 만들 수 있도록
**API 응답 형식, 3D 모델(GLB) 객체 규칙, 채널 매핑, 값의 의미**를 정리한다.
기준 시점 2026-10-09. 형식이 바뀌면 이 문서와 `schema_version`을 함께 바꾼다.

---

## 0. 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py runserver 8010
```

- 뷰어: `http://127.0.0.1:8010/` (Django 템플릿 + Three.js, 참고 구현)
- 모든 API는 같은 서버(same origin)에서 제공된다. 별도 dev 서버(Vite 등)에서 호출하려면
  프록시 설정이 필요하다(현재 CORS 미설정).
- 3D 모델을 다시 만들 필요는 없다. 생성 결과가 `digital_twin/static/digital_twin/models/greenhouse.glb`에 들어 있다.

## 1. 공통 규칙

| 규칙 | 내용 |
|---|---|
| 시간 | ISO 8601, 한국 표준시(`+09:00`) |
| **결측** | 값이 없으면 `null`. **`null`을 0으로 바꾸지 말 것**(0 %, 0 W/m²와 의미가 다름) |
| 캐시 | 모든 API 응답 `Cache-Control: no-store` |
| 메서드 | 모두 `GET`. 다른 메서드는 405 |
| 천창 % | 0 = 닫힘, 100 = 최대 개방 |
| **스크린 %** | **열림 %**: 100 = 완전히 걷힘(빛 통과), 0 = 완전히 침(전개). 전개율 = 1 − %/100 |
| 데이터 출처 | `source`: `mock_dynamic`(기본, 사인파 가짜 데이터) / `mock_static` / `field_collector`(현장 수집기의 실제 값, 약 1분 갱신). `mock`으로 시작하면 가짜 데이터 |
| 잠정값 | `verified: false`, `provenance: "estimated"`는 확정값이 아님. 화면에 "잠정" 표시 권장 |

## 2. 채널 매핑 (현장 ↔ API ↔ 3D)

| 현장 채널 | 실시간 API 키 | MPC 추천 키 | 물리 장치 | GLB pivot |
|---|---|---|---|---|
| 천창 좌(L) | `roof_vent_left_pct` | `roof_vent_percent` (좌우 공통) | 용마루 천창 +Y 쪽 판 | `GH_VENT_S01..S04_01_PIVOT` |
| 천창 우(R) | `roof_vent_right_pct` | `roof_vent_percent` (좌우 공통) | 용마루 천창 −Y 쪽 판 | `GH_VENT_S01..S04_02_PIVOT` |
| 차광커튼1 | `shade_screen_1_pct` | `diffuse_screen_open_percent` | 10 % '울트라' 산광 스크린, 높이 4.55 m | `GH_DIFFUSE_SCREEN_S01..S04_{N,P}_PIVOT` |
| 차광커튼2 | `shade_screen_2_pct` | `shade_screen_open_percent` | 70 % 알루미늄 차광 스크린(야간 보온), 높이 4.8 m | `GH_SHADE_SCREEN_S01..S04_{N,P}_PIVOT` |

- 천창 L/R의 좌우 기준(+Y = 좌)은 현장 확인 전 **잠정**.
- 이 매핑의 코드 기준은 `digital_twin/static/digital_twin/js/live-config.mjs`의 `OBJECT_MAP`.

## 3. API

### 3.1 `GET /api/digital-twin/live/` — 실시간 스냅샷

주기: 뷰어는 2초마다 호출(`LIVE_CONFIG.pollIntervalMs`), 10초 이상 갱신 없으면 stale.

```json
{
  "timestamp": "2026-10-09T23:36:40.320490+09:00",
  "source": "mock_dynamic",
  "connected": true,
  "environment": {
    "indoor_temperature_c": 30.72, "indoor_rh_pct": 65.13, "vpd_kpa": 1.542,
    "co2_ppm": 393.0, "dew_point_c": 23.4, "setpoint_temperature_c": 23.6,
    "outdoor_temperature_c": 27.4, "solar_w_m2": 527.3,
    "wind_speed_m_s": 1.0, "wind_direction_text": "45° 북동", "accumulated_solar": 1270.0
  },
  "actuators": {
    "roof_vent_left_pct": 46.41, "roof_vent_right_pct": 76.81,
    "side_vent_front_pct": 45.0, "side_vent_rear_pct": 30.0, "side_vent_left_pct": 30.0, "side_vent_right_pct": 30.0,
    "vertical_curtain_front_pct": 50.0, "vertical_curtain_rear_pct": 70.0,
    "vertical_curtain_left_pct": 70.0, "vertical_curtain_right_pct": 70.0,
    "shade_screen_1_pct": 1.04, "shade_screen_2_pct": 2.2,
    "boiler_on": false, "circulation_fan_on": true, "exhaust_fan_on": false
  }
}
```

- `solar_w_m2`: 피복 위(외부) 전천일사 센서.
- `source: "field_collector"`일 때 `timestamp`는 현장 수집 시각이다. 수집이 3분 넘게 끊기면 모든 값이 `null`, `connected: false`가 된다.
- 외부 상대습도·대기압은 현장 센서가 없어 응답에 없다.
- `wind_direction_text`는 현장 원문 문자열(각도+방위).

### 3.2 `GET /api/digital-twin/radiation/v1/` — 태양·일조·일사 (레이트레이싱)

파라미터: `time`(선택, ISO, 예 `2026-10-09T12:30`). 없으면 현재 시각 + 실시간 값.
`time`을 주면 형상(태양·그림자)만 계산하고 일사량은 `null`.

| 필드 | 의미 |
|---|---|
| `solar.altitude_deg`, `solar.azimuth_deg` | 태양 고도·방위(진북 시계방향) |
| `solar.direction_threejs` | 태양 방향 단위벡터(Three.js 좌표) |
| `solar.path_threejs` | 그날 태양 궤적(20분 간격, 지평선 위) |
| `inputs.weather`, `inputs.actuators` | 계산에 쓴 입력 |
| `radiation.status` | `ok` / `decomposition_required` / `missing_input` (아래) |
| `radiation.statuses` | 모든 상태 플래그(예 `parameter_missing:cover.diffuse_transmittance`) |
| `radiation.sunlit_fraction` | 작물면 칸 중 직달광이 닿는 비율(0–1) |
| `radiation.mean_W_m2` 등 | 작물면 일사 통계. 현재는 `null`(분해 모델 미정) |
| `radiation.grid` | 작물면 격자(아래) |
| `provenance` | 입력값 출처·검증 여부 |

`radiation.status`:
- `ok`: 직달·산란 일사가 있어 W/m² 계산 가능
- `decomposition_required`: 전천일사만 있음 → **현재 상태**. W/m²는 `null`, `sunlit`만 유효
- `missing_input`: 일사 입력 없음(`time` 지정 시)

격자(`radiation.grid`):
- `rows × cols` 칸, `cell_size_m` 간격, 높이 `height_m`(작물면, 잠정 3.0 m)
- 배열 인덱스 = `row * cols + col`. `row`는 물리 +Y 방향, `col`은 +X 방향, 시작점 `origin_xy_m`
- 배열: `sunlit`(true/false/null), `direct_W_m2`, `diffuse_W_m2`, `total_W_m2`
- `null` 칸은 온실 밖(파인 부분 등) 또는 값 없음 → **투명하게 표시**

### 3.3 `GET /api/digital-twin/solar/` — 레퍼런스 일사 모델

초기 비교용 모델. 새 화면은 3.2를 쓸 것. 응답: `sun`, `sun_path_threejs`, `mean`, `grid`(`par_w_m2`, `sunlit`), `provenance`.

### 3.4 `GET /api/mpc/recommendation/` — MPC 추천 (**MOCK**)

**실제 제어기는 아직 없다.** 응답은 합의된 형식의 가짜 값이며 `is_mock: true`로 표시된다.
실제 MPC가 붙어도 형식은 유지한다(`schema_version`이 바뀌면 이 문서도 갱신).

파라미터: `scenario` = `ok`(기본) | `degraded` | `unavailable` — 각 상태 화면 개발용.

```json
{
  "schema_version": "mpc-recommendation/0.1",
  "is_mock": true,
  "timestamp": "2026-10-09T12:00:00+09:00",
  "mode": "recommendation_only",
  "sampling_minutes": 5, "prediction_horizon_minutes": 60, "control_horizon_minutes": 20,
  "field_channels": { "...": "2절 매핑과 동일" },
  "current":        { "roof_vent_percent": 50.0, "diffuse_screen_open_percent": 100, "shade_screen_open_percent": 100 },
  "status": "ok",
  "reasons": [],
  "recommendation": { "roof_vent_percent": 59.6, "shade_screen_open_percent": 100.0, "diffuse_screen_open_percent": 100.0 },
  "trajectory": { "times": ["12:00", "12:05", "… 12개"], "roof_vent_percent": ["…12개"], "shade_screen_open_percent": ["…"], "diffuse_screen_open_percent": ["…"] },
  "predicted":  { "times": ["12:00", "… 13개(t0 포함)"], "T_air_C": [], "RH_air_percent": [], "VPD_air_kPa": [],
                  "radiation_crop_W_m2": [], "Q_vent_W_m2": [] },
  "diagnostics": { "objective_total": 1.0, "objective_temperature": 0.4, "objective_humidity": 0.3,
                   "objective_light": 0.15, "objective_heat_loss": 0.1, "objective_movement": 0.05 },
  "supervisor": { "day_phase_state": "DAY_VENTILATION", "active_constraints": [], "overrides_applied": [] },
  "source_status": { "model": "mock", "weights": "unknown", "radiation": "mock" },
  "confidence": "mock"
}
```

| 필드 | 의미 |
|---|---|
| `mode` | 항상 `recommendation_only`. **장치를 직접 제어하지 않음**(추천만) |
| `status` | `ok` / `degraded`(일부 값 부족, 추천은 있음) / `recommendation_unavailable` |
| `reasons` | `degraded`·`unavailable`의 사유 코드 목록 |
| `current` | 지금 현장 개도(실시간 API에서 변환, 천창은 좌우 평균). 없으면 `null` |
| `recommendation` | 지금 적용할 추천값(%) — `unavailable`이면 `null` |
| `trajectory` | 향후 60분 추천 개도(5분 × 12). 20분(4스텝) 이후는 마지막 값 유지 |
| `predicted` | 추천대로 했을 때 예측: 온도 °C, 상대습도 %, VPD kPa, 작물면 일사 W/m², 환기 열손실 W/m²(바닥면적당). `times`는 13개(현재 포함) |
| `diagnostics` | 목적함수 항목별 값(상대값, 단위 없음) |
| `supervisor.day_phase_state` | `NIGHT_INSULATION`, `DAWN_HUMIDITY_RELIEF`, `MORNING_SOLAR_GAIN`, `DAY_VENTILATION`, `DAY_SHADE_ASSIST`, `EVENING_TRANSITION`, `SAFETY_OVERRIDE` |
| `supervisor.active_constraints`, `overrides_applied` | 적용된 제약·안전 규칙(문자열 목록) |
| `confidence` | 현재 `mock`/`low`. 실제 의미는 MPC 단계에서 정의 |

`unavailable`이면 `recommendation`, `trajectory`, `predicted`, `diagnostics`가 모두 `null`이다.

## 4. 3D 모델 (GLB)

- 파일: `digital_twin/static/digital_twin/models/greenhouse.glb` (glTF 2.0, Y-up, 1 unit = 1 m)
- 물리 좌표 → Three.js: `[x, y, z]_physics → [x, z, -y]_three`. 물리 X = 길이(X1 정면 −48.75 → X23 후면 +48.75), Y = 폭(−16 ~ +16), Z = 높이.
- 4연동(S01–S04, 동당 8 m). **S01–S02는 정면에서 9 m 들어가 있음**(현장 정정). S01 = 정면에서 볼 때 오른쪽 끝 동.
- 각 객체의 `userData`(glTF extras): `asset_type`, `span_index`, `controllable`, `control_variable`, `opening_percent` 등.

움직이는 객체:

| 객체 | 이름 | 움직임 |
|---|---|---|
| 천창 판 | `GH_VENT_S{01-04}_{01,02}_PIVOT` | local X축 회전. 각도 = 방향 × %/100 × `userData.max_open_angle_deg`(현재 ≈ 40.5°). `userData.side`: `positive_y`(+1) / `negative_y`(−1) |
| 차광·산광 스크린 | `GH_{SHADE,DIFFUSE}_SCREEN_S{01-04}_{N,P}_PIVOT` | 동마다 양쪽 물받이(N = −Y, P = +Y)에서 한 장씩 나와 가운데서 만남. local **Z** 스케일 = 1 − %/100(최소 1e-6) |
| 측창 커튼 | `asset_type: side_curtain` | 참고 구현 `actuator-runtime.mjs` 참고 |
| 센서 | `GH_SENSOR_*_ANCHOR` | 위치 표시용. 일사센서 `SOLAR_01`은 S01 뒤끝 피복 위(위치 잠정) |

참고 구현: `digital_twin/static/digital_twin/js/`의 `actuator-runtime.mjs`(개도 적용), `scene-registry.mjs`(객체 탐색), `solar-runtime.mjs`(태양·그림자·일조 지도).

## 5. 아직 확정되지 않은 것 (화면에 "잠정" 표시 권장)

| 항목 | 상태 |
|---|---|
| 실시간 데이터 | mock. 현장 Growlink 연결 예정 |
| MPC 추천 | mock. 형식만 확정 |
| 작물면 일사 W/m² | 직달·산란 분해 모델 미정 → `null` |
| 스크린·피복 광학값 | 현장 제보 기반 잠정값 |
| 천창 % ↔ 각도 | 선형 가정, 최대각(기둥 기준 110°) 잠정 |
| 천창 좌/우 기준, 센서 위치, 작물면 높이 | 잠정 |

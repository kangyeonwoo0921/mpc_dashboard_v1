# 프론트엔드 작업 안내

대상: 대시보드 프론트엔드 담당자. 이 저장소에서 **어디를 작업하고 어디를 건드리지 않는지**, 시작 방법과
협업 규칙을 정리한다. API 응답 형식과 3D 모델 규칙의 상세는 [frontend_api_contract.md](frontend_api_contract.md)를 본다.
기준 시점 2026-10-10.

---

## 1. 시작하기

저장소: https://github.com/kangyeonwoo0921/mpc_dashboard_v1 (`main` 브랜치)

```powershell
git clone https://github.com/kangyeonwoo0921/mpc_dashboard_v1.git
cd mpc_dashboard_v1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py runserver 8010
```

- 브라우저에서 `http://127.0.0.1:8010/`을 열면 참고용 3D 뷰어가 뜬다.
- 3D 모델을 다시 만들 필요는 없다(Blender 불필요). 완성된 `greenhouse.glb`가 들어 있다.

읽는 순서:

1. 이 문서: 작업 범위와 규칙
2. [frontend_api_contract.md](frontend_api_contract.md): API, 채널 매핑, 3D 객체 이름, 값의 의미
3. `digital_twin/static/digital_twin/js/`: 참고 구현

## 2. 작업 범위 (폴더 기준)

```
mpc_dashboard_v1/
├─ digital_twin/
│  ├─ templates/digital_twin/      ✅ 작업 (화면 HTML)
│  ├─ static/digital_twin/
│  │  ├─ js/                       ✅ 작업 (화면 로직)
│  │  ├─ css/                      ✅ 작업 (스타일)
│  │  ├─ models/greenhouse.glb     👀 사용만 (수정 금지)
│  │  └─ vendor/three/             👀 사용만 (라이브러리 원본)
│  ├─ views.py, urls.py, mpc_mock.py   ✋ 요청으로 변경 (API)
├─ greenhouse_web/                 ✋ 요청으로 변경 (Django 설정)
├─ live_data/                      ✋ 요청으로 변경 (실시간 데이터 연결)
├─ markdown/frontend_*.md          👀 읽기 (변경은 요청)
├─ tests/frontend_*.test.mjs       ✅ 작업 (JS 테스트)
├─ tests/test_*.py                 ⛔ 백엔드·물리 테스트
├─ mpc_lab/                        ⛔ MPC·일사 예측 연구 코드
├─ physics/                        ⛔ 일사·레이트레이싱 계산
├─ src/, scripts/, config/         ⛔ 3D 온실 생성기(Blender)와 형상 설정
└─ (새 폴더) frontend/              ✅ 별도 프론트엔드 앱을 만들 경우
```

### ✅ 직접 작업하는 곳

| 위치 | 내용 |
|---|---|
| `digital_twin/templates/digital_twin/` | 화면 HTML (`viewer.html`, `_live_panel.html`) |
| `digital_twin/static/digital_twin/js/` | 3D 뷰어, 개도 반영, 실시간 패널, 태양·그림자 표시. 지금 코드는 참고 구현이라 고쳐도 되고 새로 만들어도 된다 |
| `digital_twin/static/digital_twin/css/` | 스타일 |
| `tests/frontend_*.test.mjs` | 위 JS의 테스트. JS를 고치면 함께 고친다 (`node --test tests/*.test.mjs`) |
| 새 폴더(예: `frontend/`) | React·Vite 등 별도 앱으로 만들 경우. API는 프록시로 Django(8010)에 연결 (CORS 미설정) |

### 👀 사용만 하는 곳

| 위치 | 이유 |
|---|---|
| `digital_twin/static/digital_twin/models/greenhouse.glb` | Blender 생성기로 만든 결과물. 직접 고치면 다음 생성 때 덮어써진다. 모델 변경이 필요하면 요청 |
| `digital_twin/static/digital_twin/vendor/three/` | Three.js 원본 |
| `markdown/frontend_api_contract.md`, 이 문서 | 계약 문서. 내용이 틀리거나 부족하면 알려 주면 갱신한다 |

### ✋ 요청을 통해서만 바꾸는 곳 (백엔드)

| 위치 | 내용 |
|---|---|
| `digital_twin/views.py`, `urls.py`, `mpc_mock.py` | API 응답. 필드 추가·형식 변경이 필요하면 요청 |
| `greenhouse_web/` | Django 설정. CORS·정적 파일 설정이 필요하면 협의 |
| `live_data/` | 실시간 데이터 연결부. 현재 mock, 나중에 현장 Growlink 연결 |

### ⛔ 건드리지 않는 곳

| 위치 | 내용 |
|---|---|
| `mpc_lab/` | MPC 제어·일사 예측 연구 코드 (별도 Python 환경) |
| `physics/` | 일사·레이트레이싱 계산 |
| `src/`, `scripts/`, `config/` | 3D 온실 생성기와 형상·광학 설정 |
| `tests/test_*.py` | 백엔드·물리 테스트 |

## 3. 사용할 API (모두 GET, same origin)

| API | 내용 | 현재 상태 |
|---|---|---|
| `/api/digital-twin/live/` | 실시간 환경값·장치 개도 | **mock** (`source: "mock_dynamic"`) |
| `/api/digital-twin/radiation/v1/` | 태양 위치·궤적, 작물면 일조 격자 | 작동. 작물면 W/m²는 `null` |
| `/api/digital-twin/solar/` | 초기 레퍼런스 모델 | 비교용. 새 화면은 radiation/v1 사용 |
| `/api/mpc/recommendation/` | MPC 추천값·예측 궤적 | **mock** (`is_mock: true`). `?scenario=ok\|degraded\|unavailable` |

필드별 의미와 예시 응답은 [frontend_api_contract.md](frontend_api_contract.md) 3절.

## 4. 꼭 지킬 규칙

| 규칙 | 내용 |
|---|---|
| `null` | **0으로 바꾸지 말고 "값 없음"으로 표시**. 0 %, 0 W/m²와 의미가 다르다 |
| 스크린 % | **열림 %**: 100 = 완전히 걷힘, 0 = 완전히 침 |
| 천창 % | 0 = 닫힘, 100 = 최대 개방 |
| 잠정값 | `verified: false`, `provenance: "estimated"`는 확정값이 아니다. 화면에 "잠정" 표시 |
| mock 표시 | `source: "mock_dynamic"`, `is_mock: true`인 동안 화면에 "가짜 데이터" 표시 |
| MPC 모드 | `mode: "recommendation_only"`: 추천만 하고 장치를 직접 제어하지 않는다 |
| 시간 | ISO 8601, 한국 표준시(`+09:00`) |
| 채널 이름 | 차광커튼1 = 산광 스크린(`diffuse`), 차광커튼2 = 차광 스크린(`shade`). 매핑 기준은 `live-config.mjs`의 `OBJECT_MAP` |

## 5. 협업 방식

- `main`에 직접 올리지 말고 **작업 브랜치**(예: `frontend/dashboard-v1`)에서 작업한 뒤 **PR**로 올린다.
- PR 전에 `node --test tests/*.test.mjs`가 통과하는지 확인한다.
- API에 필드가 더 필요하거나 형식을 바꿔야 하면 코드를 고치지 말고 요청한다. 반영 후 계약 문서와
  `schema_version`이 함께 바뀐다.
- `.venv/`, `node_modules/`, 빌드 결과물은 커밋하지 않는다.

## 6. 앞으로 바뀌는 것

| 항목 | 현재 | 예정 |
|---|---|---|
| 실시간 데이터 | mock | 현장 Growlink 연결. **응답 형식 유지** |
| MPC 추천 | mock (형식 확정) | 실제 제어기 연결. 형식 유지, 바뀌면 `schema_version` 변경 |
| 작물면 일사 W/m² | `null` | 직달·산란 분해 모델 결정 후 값 제공 |
| 일사 예측(5–60분) | API 없음 | 연구 단계. 대시보드에 표시하게 되면 API·계약 문서에 추가 |
| 천창 좌우 기준, 센서 위치, 광학값, 작물면 높이 | 잠정 | 현장 확인 후 확정 |

## 7. 문의

API·데이터·3D 모델 관련 요청은 저장소 관리자(kangyeonwoo0921)에게 한다.

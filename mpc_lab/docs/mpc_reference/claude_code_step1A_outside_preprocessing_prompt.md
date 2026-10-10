# Claude Code 작업 프롬프트 — Step 1A: Outside 데이터 전처리 파이프라인 구축

## 작업 목적

현재 스마트팜 프로젝트에서 향후 다음 흐름을 구현할 예정이다.

```text
실시간/누적 outside 데이터
→ 데이터 품질관리 및 표준화
→ 5분 canonical 시계열
→ 태양위치/clear-sky 계산
→ XGBoost 기반 5~60분 GHI 예측
→ GHI→DNI/DHI 분해
→ Radiance ray tracing
→ 온실 내부 유효 일사
→ Vanthoor 기반 온실 동역학
→ MPC 추천제어
```

이번 작업 범위는 **위 전체 흐름 중 Step 1A, 즉 outside 데이터의 수집·정제·표준화 파이프라인만 구축하는 것**이다.

중요한 점은 이 작업을 단발성 CSV cleaning으로 만들지 않는 것이다. 현장 데이터는 **2026-07-28부터 계속 누적되고 있으며**, 앞으로도 계속 추가된다. 현재 확보한 export 파일은 용량 제한 때문에 여러 구간으로 나뉠 수 있다.

따라서 이번 단계의 목표는 다음과 같다.

> 새 outside CSV가 계속 추가되어도 동일한 규칙으로 처리할 수 있고, 이후 XGBoost 실시간 추론 및 주기적 adaptive retraining과 자연스럽게 연결되는 preprocessing/ingestion layer를 구축한다.

---

## 0. 코드를 쓰기 전에 먼저 할 일

현재 repository 전체 구조를 먼저 읽어라.

특히 다음을 확인한다.

- 프로젝트 root 구조
- 기존 `mpc_lab`, Django, greenhouse 관련 package/module 구조
- config 파일
- data/model/schema 관련 코드
- 테스트 구조
- dependency 관리 방식
- naming convention
- logging/error handling 방식
- 이미 존재하는 preprocessing 또는 ingestion 코드
- architecture/model assumption 문서

**중복되는 새 구조를 임의로 만들지 말고, 현재 repository의 구조와 conventions에 맞는 위치를 우선 선택하라.**

기존 3D dashboard, Three.js/Django visualization, PLC read-only 연결 등 이번 작업과 직접 관련 없는 코드는 수정하지 않는다.

아래에서 예시 구조를 제시하지만, 현재 repository를 직접 읽어 더 적절한 구조가 있다고 판단되면 그쪽을 선택해도 된다. 다만 아래의 **기능 요구사항과 data contract는 유지**해야 한다.

코드를 작성하기 전에 짧게 다음을 정리한 뒤 진행하라.

1. 이 기능을 어느 package/module에 배치할지
2. 기존 코드 중 재사용 가능한 부분
3. 새로 추가할 주요 파일과 역할
4. 기존 파일을 수정해야 한다면 그 이유

불필요한 대규모 refactor는 하지 않는다.

---

## 1. 입력 데이터

현재 outside CSV 예시는 다음과 같다.

```text
/mnt/data/outside_2026-06-01_2026-10-09.csv
/mnt/data/outside_2026-10-07_2026-10-09.csv
```

첫 번째 파일처럼 export filename과 실제 포함 범위가 일치하지 않을 수 있다. 현장 데이터 자체는 2026-07-28부터 지속적으로 누적되고 있고, CSV export 용량 제한 때문에 파일이 중간에서 잘릴 수 있다.

따라서:

- filename의 날짜를 실제 data range라고 신뢰하지 말 것
- CSV 내부 timestamp로 실제 범위를 판단할 것
- 여러 export 파일이 서로 overlap될 수 있음을 전제로 할 것
- 같은 timestamp가 여러 파일에 중복 존재할 수 있음을 전제로 할 것

---

## 2. 지금까지 확인된 raw data 특성

실제 파일을 다시 직접 검사해서 확인하되, 아래 이슈가 이미 관찰되었다.

### 2.1 약 1분 간격

대부분 약 60초 간격으로 기록되지만 timestamp가 정각은 아닐 수 있다.

예:

```text
00:00:45
00:01:45
...
```

따라서 5분 데이터 생성 시 단순히 5행씩 묶지 말고 반드시 timestamp 기반 resampling을 사용한다.

### 2.2 schema drift 가능성

과거 export 일부에서 컬럼 수/순서가 중간에 달라진 사례가 있었다.

예를 들어 초기 구간에는:

```text
timestamp
누적일사량
외부습도
외부온도
외부풍속
외부풍향
일사센서
```

형태였으나, 이후 구간에서는 외부습도 열이 빠진 것으로 보이는 6열 데이터가 같은 header 아래 이어지는 사례가 있었다.

또 일부 최신 행에서는 header보다 추가 값이 하나 더 존재하는 export anomaly가 관찰되었다.

따라서:

- 단순 `read_csv()` 결과를 그대로 신뢰하지 말 것
- row field count/schema consistency를 검사할 것
- 가능한 경우 schema drift를 탐지할 것
- 자동 복원이 명확히 가능한 경우 근거를 남기고 복원할 것
- 확신할 수 없는 경우 임의로 열을 맞추지 말고 invalid/review 상태로 남길 것
- schema correction 결과를 summary/log에 남길 것

### 2.3 overlapping export / duplicate timestamp

같은 기간을 여러 번 export할 수 있어 duplicate가 생길 수 있다.

따라서 deduplication 정책이 필요하다.

- 동일 timestamp + 동일 값인 duplicate와
- 동일 timestamp + 다른 값인 conflicting duplicate

를 구분한다.

어떤 row를 최종 채택할지는 실제 데이터와 현재 코드베이스를 보고 합리적으로 판단하되, 조용히 임의 삭제하지 말고 정책을 코드/문서에 명시한다.

### 2.4 sensor freeze 의심

과거 일사센서에서 동일값이 비정상적으로 긴 시간 지속되는 구간이 관찰되었다.

예시로 약 `564 W/m²`가 장시간 고정된 구간이 있었다.

따라서 freeze detection을 포함하되:

- 짧은 고정구간을 무조건 오류로 처리하지 말 것
- rule은 configurable하게 만들 것
- 동일값 지속시간과 daylight 여부 등을 고려할 것
- 최초 버전은 값 수정보다 flagging 중심으로 구현할 것
- freeze 구간을 자동 보간해서 덮어쓰지 말 것

### 2.5 비정상적인 0 값

한낮에 외기온도와 일사센서가 동시에 0으로 떨어지는 시점이 일부 관찰되었다.

하지만 야간 GHI=0은 정상이다.

따라서:

- `GHI == 0`만으로 invalid 처리하지 말 것
- daylight 여부를 고려할 것
- 다른 센서의 동시 이상 여부도 참고할 수 있게 할 것
- 우선 QC flag를 남기고 raw value는 추적 가능하게 유지할 것

---

## 3. 핵심 데이터 원칙

### 3.1 Raw는 immutable

원본 CSV는 절대 덮어쓰지 않는다.

논리 흐름은 다음처럼 분리한다.

```text
raw
→ parsed
→ quality controlled
→ canonical 1-min
→ canonical 5-min
```

실제 저장 파일 수와 세부 구조는 repository에 맞게 판단해도 된다.

### 3.2 Canonical naming

향후 전체 시스템에서 동일한 의미를 유지해야 한다.

최소 outside canonical 변수는 다음 의미를 가진다.

```text
timestamp
ghi
t_out
rh_out
wind_speed
wind_dir
```

raw에 누적일사값이 있으면 순간일사 GHI와 분리해서 별도 이름으로 보존한다.

예:

```text
solar_energy_cumulative
```

실제 의미/단위는 파일을 직접 확인한 뒤 확정한다.

**누적일사량과 순간 일사량을 절대 동일 변수로 취급하지 않는다.**

기존 repository naming convention이 더 적절하면 그 convention을 따라도 된다.

### 3.3 단위

최소 기대 단위:

```text
ghi        : W/m²
t_out      : °C
rh_out     : %
wind_speed : raw 확인 후 명시
wind_dir   : degree
timestamp  : Asia/Seoul
```

확인되지 않은 단위는 추정하지 않는다. metadata에서 unresolved로 남긴다.

### 3.4 Timezone

현장 timestamp는 한국 현지시간으로 취급한다.

코드 내부에서는 timezone-aware datetime을 사용하고 `Asia/Seoul`을 명시한다.

---

## 4. QC 규칙

이상값을 발견했다고 즉시 삭제/보간하지 말고 먼저 quality flag를 남긴다.

최소한 다음 상태를 표현할 수 있어야 한다.

```text
valid
missing
duplicate
conflicting_duplicate
schema_anomaly
sensor_freeze
out_of_range
suspected_communication_error
interpolated
```

구현 방식은 enum, boolean columns, bitmask, 별도 quality table 등 현재 코드베이스에 가장 적합한 방법을 선택해도 된다.

가능하면 변수별 quality 상태를 추적할 수 있도록 설계한다.

---

## 5. 물리적 범위 검사

공격적인 threshold를 임의 설정하지 않는다.

- 명백히 불가능한 값 또는 확실한 sentinel만 invalid 처리
- 애매한 값은 flag
- 제조사 스펙/현장 정보가 없으면 보수적으로 처리
- threshold는 config로 관리 가능하게 할 것
- 근거 없는 magic number를 코드 곳곳에 넣지 말 것
- 후속 모델을 위해 값을 임의 생성하지 말 것

---

## 6. Daylight / solar sanity check

향후 clear-sky index, XGBoost, DNI/DHI decomposition으로 이어질 수 있게 daylight 판단 기반을 마련한다.

먼저 repository/config에서 현장 위치가 이미 정의되어 있는지 확인한다.

- 있으면 재사용
- 없으면 임의 좌표를 생성하지 말 것

정확한 위치가 없으면 daylight 계산을 optional/unresolved 상태로 두고 필요한 config를 명시한다.

위치가 있으면 향후 `pvlib`과 재사용 가능한 형태로 `sun_above_horizon` 또는 equivalent flag를 계산할 수 있게 한다.

이번 단계에서는 clear-sky irradiance나 DNI/DHI는 아직 계산하지 않는다.

---

## 7. Missing / interpolation

결측을 무조건 보간하지 않는다.

특히 GHI는 cloud ramp가 있으므로 보수적으로 처리한다.

최소한 다음 상태를 구분한다.

```text
observed
interpolated
missing
invalid
```

짧은 gap interpolation 여부와 최대 허용 길이는 config로 분리한다.

근거가 부족하면 자동 interpolation default OFF도 허용한다.

향후 ML에서 실측값과 보간값을 구분할 수 있어야 한다.

---

## 8. Canonical 1-minute dataset

먼저 1분 canonical dataset을 만든다.

목표:

- 정렬된 시간축
- 동일 schema
- 중복 처리
- QC 정보
- raw→canonical mapping 추적 가능
- 이후 추가 export와 안전하게 merge 가능

빈 1분 timestamp를 전체 생성할지 여부는 실제 데이터 특성과 downstream 요구를 보고 결정하되 이유를 문서화한다.

---

## 9. Canonical 5-minute dataset

후속 XGBoost와 MPC는 우선 5분 간격 사용을 계획한다.

따라서 1분 canonical data에서 timestamp 기반 5분 resampling을 수행한다.

예상 aggregation 원칙:

```text
ghi        → mean
t_out      → mean
rh_out     → mean
wind_speed → mean
wind_dir   → circular mean
```

단 실제 raw 변수 의미/단위를 직접 확인한 뒤 확정한다.

누적값은 단순 평균하지 않는다.

5분 interval 내 valid observation coverage가 너무 낮은 경우 quality가 낮다는 정보를 남긴다.

최소 sample/coverage threshold는 config화하거나 근거가 없으면 provisional/unresolved로 명시한다.

---

## 10. Adaptive forecasting을 고려한 구조

향후 일사예측은 XGBoost를 기본 production candidate로 사용하고, 새 outside 데이터가 계속 쌓이면 **주기적 재학습(periodic retraining)** 하도록 설계할 예정이다.

실시간 예측 루프:

```text
새 outside 데이터
→ 동일 preprocessing
→ 최신 feature
→ current XGBoost
→ GHI t+5 ... t+60
```

adaptive retraining 루프:

```text
누적 outside 데이터
→ 동일 preprocessing
→ training dataset
→ candidate XGBoost 재학습
→ 기존 모델과 validation 비교
→ 개선 시 model promotion
```

따라서 이번 preprocessing은:

- 단발성 CSV cleaner가 아니어야 함
- 새 file/new rows를 반복 처리 가능해야 함
- deterministic/idempotent해야 함
- overlapping exports에 안전해야 함
- inference와 retraining에서 동일한 preprocessing logic을 공유할 수 있어야 함

실시간 streaming infrastructure 자체는 이번 단계에서 만들 필요 없다.

---

## 11. 저장 형식

현재 repository와 downstream Python workflow를 보고 적절한 방식을 선택한다.

가능 후보:

- CSV
- Parquet
- 둘 다

대용량 누적 데이터에는 Parquet이 적합할 수 있지만, 사용자가 쉽게 검토할 수 있는 CSV snapshot/report를 추가해도 된다.

저장 위치 역시 현재 repository 구조를 우선한다.

---

## 12. Metadata / data contract

가능하면 schema/config에 다음 정보를 관리한다.

```text
canonical_name
raw_name
unit
dtype
category
aggregation_5min
validity_rule
missing_policy
source
```

outside 변수는 향후 MPC 관점에서 기본적으로 `disturbance` category에 속한다.

포맷은 YAML/TOML/JSON/Python schema 중 현재 repository에 가장 자연스러운 방식을 선택한다.

---

## 13. 진단 summary

실행 후 최소한 다음을 보여준다.

```text
actual start timestamp
actual end timestamp
raw row count
parsed row count
duplicate count
conflicting duplicate count
schema anomaly count
missing count per variable
invalid count per variable
freeze-flagged count
suspected communication error count
1-min output row count
5-min output row count
5-min coverage
```

가능하면 날짜별 QC summary도 제공한다.

그리고:

- 자동 수정
- flag only
- unresolved

를 구분해서 보고한다.

---

## 14. 테스트

최소 테스트 범위:

1. timestamp parsing / timezone
2. overlapping export merge
3. exact duplicate 처리
4. conflicting duplicate 처리
5. schema drift handling
6. nighttime GHI=0 정상 처리
7. daylight suspicious zero flagging
8. sensor freeze detection
9. missing preservation
10. 5분 resampling
11. wind-direction circular mean
12. idempotency
13. malformed row handling
14. canonical schema validation

가능하면 edge case를 재현한 작은 fixture를 우선 사용하고, 실제 CSV는 integration/smoke test에 활용한다.

---

## 15. 이번 단계에서 하지 않을 것

다음은 아직 구현하지 않는다.

```text
XGBoost training
smart persistence
clear-sky irradiance prediction
GHI forecasting
DNI/DHI decomposition
Radiance
ray tracing
Vanthoor dynamics modification
MPC optimizer
inside/zone1 preprocessing
PLC write
```

다만 후속단계를 고려한 interface/data contract는 반영한다.

inside 전처리는 추후 Step 1B에서 별도 구현한다.

---

## 16. 코드 구조에 대한 자유도

예시:

```text
src/
  preprocessing/
    outside.py
    qc.py
    schema.py
    resample.py

config/
  outside_schema.yaml
  qc_rules.yaml

data/
  raw/
  processed/
```

이 구조를 그대로 따를 필요는 없다.

현재 repository를 직접 읽고 더 자연스러운 구조가 있으면 그 구조를 선택하라.

중요한 것은 다음이다.

- 역할 분리
- testability
- reuse
- adaptive retraining과 실시간 inference 양쪽에서 동일 preprocessing 사용
- 기존 프로젝트 구조와 일관성

---

## 17. 절대 하지 말 것

- raw CSV 덮어쓰기
- 행 번호 기반 5분 aggregation
- 모든 missing 자동 interpolation
- 모든 GHI=0을 오류 처리
- 풍향 arithmetic mean
- filename의 날짜를 실제 data range라고 신뢰
- 불명확한 schema를 조용히 임의 변환
- 근거 없는 물리 threshold 생성
- downstream 편의를 위해 값을 임의 생성
- 기존 dashboard/PLC 관련 코드의 불필요한 수정

---

## 18. 완료 기준

작업 완료 후 다음을 보고한다.

### A. Repository 분석

- 선택한 구현 위치
- 기존 코드 재사용 여부
- 실제 outside CSV schema
- 발견된 schema anomalies
- 실제 데이터 기간

### B. 구현

- 추가/수정 파일 목록
- 각 파일 역할
- canonical schema
- QC 규칙
- resampling 규칙
- adaptive/retraining-ready 구조

### C. 실행 결과

현재 확보한 outside CSV를 실제로 파이프라인에 통과시켜:

```text
raw → clean 1-min → clean 5-min
```

결과를 생성하고 summary를 보여준다.

### D. 테스트

- 전체 테스트 결과
- 새 테스트 수
- 실패/skip 여부

### E. unresolved

아직 확정할 수 없는 항목을 별도로 정리한다.

예:

```text
wind speed unit
weather station exact coordinates
sensor manufacturer range
freeze threshold
interpolation threshold
5-min minimum coverage
```

이 항목들은 임의값으로 채우지 않는다.

---

## 19. 최종 설계 의도

이번 Step 1A의 성공 기준은 단순히 현재 CSV가 깨끗하게 읽히는 것이 아니다.

최종적으로 다음이 가능해야 한다.

```text
새로운 outside export 추가
        ↓
같은 preprocessing pipeline 실행
        ↓
기존 canonical dataset과 안전하게 merge
        ↓
QC 적용
        ↓
새 5분 canonical data 생성
        ↓
향후 XGBoost inference / retraining에서 그대로 사용
```

즉 Step 1A를 **지속적으로 누적되는 실제 현장 데이터의 표준 입구**로 설계하라.

현재 repository를 충분히 읽고, 위 요구사항을 만족하는 범위 안에서 세부 구현 방식은 가장 적절하다고 판단되는 방법을 선택해서 진행하라.

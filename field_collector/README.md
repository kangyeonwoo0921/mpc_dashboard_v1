# 현장 PC 데이터 수집기 (읽기 전용)

현장 대시보드의 `GET http://127.0.0.1:8000/api/live`를 1분마다 읽어 파일로 쌓는다.
1순위 용도는 3D 디지털 트윈의 mock 데이터를 실제 값으로 바꾸는 것(`latest.json`)이고, 그다음이 일사 예측·MPC용 기록이다.

현장 PC는 우리 PC가 아니므로 다음을 지킨다.

- PLC에 접속하지 않는다. 기존 대시보드의 파일·데이터·설정을 읽거나 바꾸지 않는다.
- 요청은 GET 한 종류(브라우저가 대시보드를 볼 때와 같은 요청)뿐이며 쿠키·로그인 정보를 보내지 않는다. 주소는 127.0.0.1/localhost만 허용한다.
- 아무것도 설치하지 않는다(Python 표준 라이브러리만, 3.9 이상). 쓰는 곳은 `output_dir` 하나뿐이다.
- 안전장치: 한 번에 하나만 실행(잠금 파일), 낮은 CPU 우선순위, 읽기 실패 후 `retry_wait_s`(5분) 대기,
  디스크 여유가 `min_free_disk_gb`(5 GB) 미만이면 쓰기 중지, 주기는 10초 미만 불가.
- 되돌리기: 실행 창을 닫거나 작업을 멈추고 `C:\GreenhouseCollector\` 폴더를 지우면 끝(작업 스케줄러를 등록했다면 4절의 제거 명령도).
- **현장 담당자의 허락을 받고, 처음 실행하는 시각을 알려 둔다.**

## 1. 복사

현장 PC에 `C:\GreenhouseCollector\` 폴더를 만들고 이 폴더의 세 파일을 복사한다.

```
C:\GreenhouseCollector\
├─ collector.py
├─ config.json
└─ README.md
```

`config.json`:

| 키 | 기본값 | 의미 |
|---|---|---|
| `url` | `http://127.0.0.1:8000/api/live` | 현장 대시보드 API. 127.0.0.1/localhost만 허용 |
| `interval_s` | 60 | 읽기 주기(초) |
| `second_offset` | 5 | 매분 몇 초에 읽을지 |
| `timeout_s` | 10 | 응답 대기 시간(초) |
| `retry_wait_s` | 300 | 읽기 실패 후 다시 시도하기 전 대기(초) |
| `min_free_disk_gb` | 5 | 디스크 여유가 이보다 적으면 쓰기 중지 |
| `output_dir` | `C:\GreenhouseCollector\data` | 저장 폴더. 공유 동기화 폴더(`GreenhouseFieldData`)로 바꾸면 연구실 PC·노트북으로 자동 전달 |

## 2. 확인 (아무 파일도 쓰지 않음)

PowerShell:

```powershell
cd C:\GreenhouseCollector
python --version
python collector.py --once
```

- `python`이 없다는 오류가 나면 `py --version`, `py collector.py --once`로 해 본다.
- 현장 대시보드가 쓰는 Python(3.11.9)을 그대로 써도 된다. 표준 라이브러리만 쓰므로 그 환경을 바꾸지 않는다.
- 외기·실내 측정값, 개도, 운전 상태와 "outside CSV row"가 출력되면 정상이다.

## 3. 실행

```powershell
python collector.py
```

매분 5초에 한 번 읽는다. 창을 닫으면 멈춘다. 결과(`output_dir` 아래):

| 파일 | 내용 |
|---|---|
| `latest.json` | 마지막 응답 |
| `raw\live_YYYY-MM-DD.jsonl` | 매 읽기의 수집 시각 + 응답(라벨 등 고정 부분 제외). 약 5 MB/일 |
| `outside\outside_YYYY-MM-DD.csv` | 기존 외기 내보내기와 같은 열(시각,누적일사량,외부온도,외부풍속,외부풍향,일사센서) |
| `collector.log` | 시작, 실패, 복구 기록 |

읽기에 실패하면 로그에 남기고 계속 돈다. 실패한 분은 기록하지 않는다(빈 구간으로 남는다).

## 4. 자동 실행 (작업 스케줄러)

확인이 끝난 뒤 한 번만 실행한다. 로그인할 때 창 없이 시작하고, 이미 실행 중이면 새로 띄우지 않는다.

```powershell
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument '"C:\GreenhouseCollector\collector.py"' -WorkingDirectory "C:\GreenhouseCollector"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "GreenhouseCollector" -Action $action -Trigger $trigger -Settings $settings
Start-ScheduledTask -TaskName "GreenhouseCollector"
```

관리:

```powershell
Get-ScheduledTask -TaskName "GreenhouseCollector" | Get-ScheduledTaskInfo   # 상태
Stop-ScheduledTask -TaskName "GreenhouseCollector"                          # 멈춤
Unregister-ScheduledTask -TaskName "GreenhouseCollector" -Confirm:$false    # 제거
```

## 5. 연구실 PC·노트북에서 쓰기

`output_dir`이 공유 폴더(Google Drive `내 드라이브\GreenhouseFieldData`)이면:

- 연구실 PC(운영): `mpc_lab\scripts\run_live_operation.ps1` — 5분마다 일사 예측, `latest_forecast.json`을 같은 폴더에 씀
- 어느 PC든(시연 포함): `scripts\run_dashboard_live.ps1` — 3D 디지털 트윈이 실제 값과 예측을 표시
- 마지막 수집이 3분 넘게 끊기면 실시간 값은 모두 `null`, `connected: false`로 나온다(오래된 값을 현재 값처럼 보여주지 않음).
- 스크립트 없이 실행하면 대시보드는 지금처럼 mock 데이터다.

자세한 내용: `mpc_lab/docs/LIVE_OPERATION.md`.

## 6. 확인할 점

- 현장 PC 시계가 정확해야 한다(수집 시각 = 현장 PC 시각). `farm.time`(대시보드 시각)도 raw 기록에 함께 남는다.
- 외기 CSV의 `일사센서` 열에는 `farm.outside.일사량`을 쓴다. 응답의 `sens.ext.일사`(예: 171)와 값이 조금 다를 수 있어,
  며칠 뒤 대시보드의 외기 내보내기 파일과 비교해 같은 값인지 확인한다. 두 값은 raw 기록에 모두 남는다.
- 실내습도 99.9 %, 이슬점 = 실내온도인 값이 보이면 습도 센서 상태를 현장에 확인한다.

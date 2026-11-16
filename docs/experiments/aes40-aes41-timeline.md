# AES-40 → AES-41 실험·운영 타임라인

기록 범위: 2026-11-10 ~ 2026-11-13. 시각은 **UTC** 기준이며 KST는 +9시간이다.
실험 manifest, 결과 JSON, 평가 보고서, RPC 로그 및 작업 중 확인한 운영 기록을 바탕으로 정리했다.
정확한 실행 시각이 확인되지 않은 작업은 날짜/순서만 기록했다. 이 문서는 이후 진행을 자동 반영하지 않는다.

## 1. 공통 조건과 결과 해석

- 태스크: 동일한 SWE-bench Verified 500개. 평가에는 공식 메타데이터 사용.
- Generation task 파일 SHA-256: `c2a66a2d75b03724204c2ec69d77a697eaede254fb6f7f9c00db7a131060ea76`.
- 기본 user simulator: `centinels/gpt-6.1-sol`.
- Generation timeout: 600초. 평가 timeout: 1,800초.
- Generation 이미지: `wasabi-pi:1.4.0-wasabi-614a531`.
- Baseline은 같은 이미지에서 Wasabi entrypoint를 우회하고 Pi를 직접 실행한다. Wasabi extension은 비활성화한다.
- 정상 generation은 패치 수집까지 정상 종료했다는 뜻이다. 빈 패치가 가능하며 테스트 통과를 뜻하지 않는다.
- Resolve rate 분모는 빈 패치·generation 오류를 포함해 반복당 500개로 유지한다.
- API 오류, 질문 프로토콜 오류, evaluation 실행 오류, 테스트 실패는 구분한다.
- 실패 재시도는 별도 폴더에 보존했다. 재시도 반영 결과는 원래 1회 시도만의 성능과 다르다.
- 상위 manifest의 `evaluation: not launched`나 `BLOCKED`는 최초 실행 시점 상태일 수 있다. 후속 retry/continuation/evaluation 파일이 최신 사실의 근거다.

## 2. 타임라인

### 2026-11-10 ~ 11: 최초 Luna 5.6 비교 실험

| 작업 | 간략 기록 |
|---|---|
| 최초 generation | `gpt-5.6-luna`로 Baseline / Wasabi 각각 500개 × 3회, 총 3,000건 실행. 조건별 worker 20개, 총 40개. |
| 상호작용 조건 | Baseline 코딩 중 질문 응답 상한 5회. 기존 Wasabi는 clarification 응답 상한 5회, coding-agent return 질문 지원 0회. |
| Wasabi 모델 | `openrouter/qwen/qwen3.8-flash` 사용. |
| 최초 종료 확인 | 정상 완료 2,983건, 오류 17건. `.git` 임시 디렉터리 정리 오류 13건, timeout 4건. |
| Generation 복구 | 정리 오류 태스크의 패치를 재수집하고 timeout 태스크를 재실행. 15건 복구, Baseline rep-1의 2건은 추가 시도 후에도 실패. |
| Git cleanup 수정 | 임시 Git 명령에 `gc.auto=0`, `maintenance.auto=false`를 설정해 백그라운드 maintenance와 디렉터리 삭제의 경합을 방지. |
| 평가 준비 | `swebench==4.1.0` 별도 환경 구성. 로컬 변환 데이터의 버전 문자열 오류를 발견해 공식 평가 데이터로 교체; 500개 ID와 base commit 일치 확인. |
| 환경 사전 점검 | 12개 프로젝트 대표 및 기존 skip 관련 태스크 등 16개에 공식 정답 패치 적용. 16/16 resolved, 필수 FAIL_TO_PASS/PASS_TO_PASS 성공 확인. |
| Optional skip 검토 | pandas/scipy/jplephem/bs4/bleach 등 관련 skip 기록. 공식 이미지는 변경하지 않음. 대표 16개 검증이지 전체 500개 환경 보증은 아님. |
| 최초 본 평가 | 최대 worker 100으로 실행. 이미지 준비 실패가 대량 발생해 정상 보고서가 없는 태스크를 재평가 대상으로 분리. |
| 복구 실행 | 이미지 pull 동시 5개 + 평가 worker 20개로 분리. 요청에 따라 pull 10개, 평가 worker 80개로 확대. |
| 이미지 다운로드 지연 | Matplotlib 대형 이미지 pull 일부가 장시간 대기. 일부 완료·다음 이미지 진행도 확인했으므로 전체 정지로 단정하지 않음. |
| 디스크 보호 중단 | 시스템 SSD 여유가 120 GiB 미만으로 떨어져 자동 중단. 확인 당시 약 103 GiB 남음. |
| 이미지 사용량 조사 | SWE-bench 이미지 305개. Docker 표시 크기 기준 5 GB 초과 42개, 그중 10 GB 초과 27개. 공유 레이어를 포함하므로 단순 합산 불가. |
| 임시 task-major 정책 | 같은 태스크의 6개 조건·반복을 평가한 뒤 10 GB 초과 이미지를 삭제하는 실행기를 작성·실행. 최대 78개(13×6) 평가. |
| 이미지 메타데이터 | 500개 태스크의 이미지 참조·로컬 크기·보유 여부·정책을 `image-metadata.json`에 기록. 미다운로드 크기는 null. |
| 정책 철회 | NVMe 증설 결정으로 task-major 실행기·테스트·문서 변경을 revert. 자동 삭제 supervisor 중단, 이미 실행 중인 평가만 마무리. 기존 결과·메타데이터 보존. |
| 종료 준비 | 평가·다운로드와 컨테이너가 종료된 것을 확인하고 디스크 sync. 재부팅/장착 준비. |

### 2026-11-11: 저장소 증설·Docker 이전·PR

| 작업 | 간략 기록 |
|---|---|
| SSD 인식 | 기존 980 PRO 1TB 외에 970 PRO 1TB, 970 EVO 250GB 확인. 추가 SSD 모두 기존 파일시스템이 있어 삭제 승인 후 진행. |
| 포맷·마운트 | 추가 1TB → `/mnt/data`, 250GB → `/mnt/scratch`, ext4. UUID 기반 fstab 설정. 기존 OS SSD는 유지. |
| Docker 이전 | Docker/containerd 중지 후 `/var/lib/docker`, `/var/lib/containerd`를 새 SSD에 rsync. 내용 체크섬 검증 후 bind mount로 원래 경로 유지. |
| 복사·검증 | 진행률 없는 rsync라 장시간 무출력. 복사 후 전체 체크섬 검증 단계임을 프로세스로 구분. |
| 서비스 확인 | Docker/containerd active 및 새 SSD 마운트 확인. 기존 Python 이미지의 실행·쓰기·읽기와 SWE-bench 이미지의 testbed Python 실행 성공. |
| 재부팅 검증 | 새 SSD 자동 마운트와 Docker 실행 재확인. |
| 원본 정리 | 사용자 터미널에서 기존 `.pre-migration-20261111-112422` 두 디렉터리 삭제. OS SSD 여유 약 198 → 490 GiB. |
| 저장소 구조 | `/mnt/data/{docker,containerd,experiments,cache}`는 같은 파일시스템 공간 공유. `/mnt/scratch`는 별도 보조 공간. |
| PR | [PR #1](https://github.com/kc-ml2/Wasabi-benchmark/pull/1): simulator reply limit 설정 및 임시 Git cleanup 개선. 실험 원본·로컬 인프라 스크립트 제외. |

장치 이름(`nvme0n1` 등)은 재부팅/장착으로 바뀌었다. 장치 번호가 아니라 모델·시리얼·UUID로 구분한다.

### 2026-11-12: GPT-6.1 Sol baseline generation

| 작업 | 간략 기록 |
|---|---|
| 04:45 시작 | Coding agent만 `centinels/gpt-6.1-sol`로 변경. 500개 × 3회, simulator Sol / 응답 상한 5회 유지. 새 SSD에 별도 결과 저장. |
| Smoke | 1건 정상 완료 후 본 실험 시작. |
| 1회차 worker 128 | 368건 정상, 132건 오류. upstream HTTP 403 및 timeout 발생. 오류 50건 초과로 이후 반복 자동 중단. |
| 05:26 재시도 | 실패 132건만 같은 worker 128 설정으로 재실행: 74 성공 / 58 실패. 과부하·idle capacity 부족 48건, 403 10건. |
| 05:48 재시도 | 남은 58건, worker 상한 64(실제 최대 58): 54 성공 / 4 실패. 남은 4건은 inflight session capacity 오류. |
| 06:32 재시도 | 남은 4건을 worker 4로 실행해 모두 정상 완료. 1회차 누적 500/500 정상 generation. |
| 2·3회차 | worker 64로 순차 실행. 2회차 498 정상 / 2 오류, 3회차 496 정상 / 4 오류. |

### 2026-11-13: Sol 복구·평가·모델 비교

| 작업 | 간략 기록 |
|---|---|
| 02:41 재시도 | 2회차 2건 + 3회차 4건, 최대 6개 동시 실행. 5건 복구, 1건 API model access 검증 오류 잔존. |
| Sol generation 정리 | 반복별 정상 완료 500 / 500 / 499. 최종 누락은 3회차 `pydata__xarray-4094`. |
| Evaluation 준비 | 성공한 retry prediction을 우선 반영. nonempty 1,485 / empty 14 / generation 누락 1. |
| 이미지 재확보 | 500개 중 473개 보유, 대형 이미지 27개 누락. 동시 10개로 재다운로드 후 모두 보존. |
| Evaluation | 각 반복 순차 실행, 최대 worker 80. 3회 모두 종료, 평가 실행 오류 0. |
| 모델 비교 | 이전 Luna 결과와 동일 ID/base commit 확인. 전체 분모 기준 Sol 평균 81.27%, Luna baseline 55.20%, Luna+Wasabi 63.13%. |

### 2026-11-13: GPT-6 Luna generation·질문 파서 진단

| 작업 | 간략 기록 |
|---|---|
| 모델명 확인 | `gpt-6.1-luna` smoke는 Invalid model name으로 실패. `/v1/models` 확인 후 사용자 승인으로 `gpt-6-luna` 사용. |
| 07:38 시작 | `centinels/gpt-6-luna`, worker 64, 500개 × 3회 계획. Simulator Sol, 응답 상한 5회, timeout 600초 유지. |
| 1회차 | 439 정상 / 61 오류. nonempty 410. 질문 envelope 오류 57건, API content-policy 거부 4건. 이후 반복 자동 중단. |
| 10:06 재시도 | 61건을 설정 변경 없이 재시도. 33 정상 / 28 오류; 성공 중 nonempty 23. 잔존 오류는 envelope 27건 + timeout 1건. |
| 원인 확인 | 일부 출력이 `질문 설명 + <user_question>질문</user_question>` 형태. strict whole-message 파서가 simulator 호출 전에 거부. 확인한 사례의 simulator_turns는 0. |
| 파서 수정 | 유효한 단일 질문 블록은 주변 텍스트를 무시하고 질문만 전달. 원문·제외 텍스트 로그 보존. 중복/중첩/불완전/빈 태그는 거부. 모든 baseline 모델 공통 적용. |
| 버전 기록 | 새 manifest에 `question_parser_version: single-envelope-v2`. 기존 strict 결과와 구분. 당시 전체 테스트 35개, 실패 0 / skip 3. |
| 11:26 v2 진단 | 남은 28건만 새 파서로 실행: 25 정상 / 3 envelope 오류, nonempty 20. 선택된 실패 subset 진단이므로 strict 결과와 합쳐 새 모델 점수로 취급하지 않음. |

v2 진단에서 남은 오류: `django__django-15022`, `django__django-15280`, `sympy__sympy-24562`.
GPT-6 Luna 2·3회차와 evaluation은 이 기록 범위에서 미실행이다.

### 2026-11-13: AES-41 상호작용 확장·worktree 이동

| 작업 | 간략 기록 |
|---|---|
| 기존 경로 확인 | Baseline은 coding-agent 텍스트의 질문 태그, Wasabi는 `extension_ui_request` 기반 사전 clarification. 기존 Wasabi runner는 coding-time return을 처리하지 않았음. |
| 새 정책 합의 | 사용자 → Wasabi → coding agent → 사용자 답변 → Wasabi → coding agent. Wasabi clarification 응답은 무제한, coding-agent 질문 응답만 최대 3회. |
| CLI 추가 | `--coding-question-limit 3`. 양수일 때 Wasabi simulator 제한을 해제하고 별도 coding reply counter 사용. 기본값 0은 기존 initial-only 동작 보존. |
| 기록·테스트 | `wasabi-return-v1`과 parser 버전을 manifest에 기록. 양쪽 응답 수 분리. 모의 RPC에서 반복 재진입·독립 예산 확인. 전체 테스트 36개, 실패 0 / skip 3. |
| 14:45 live smoke | 실제 Pi/Wasabi 이미지에서 coding 질문 1회 → Sol 답변 → Wasabi Checking request 재실행 → `SMOKE_COMPLETE` 종료 확인. |
| Smoke 범위 | OpenRouter 키 부재로 checker는 Centinels Sol, coding agent는 Luna 5.6. 실제 clarification 질문은 0회. 재진입은 검증했지만 실제 clarification 다회/3회 상한은 모의 테스트 범위. |
| 코드 이동 | 미커밋 7개 파일(+209/-21)을 AES-41 worktree로 이동하고 byte 일치 확인. AES-40의 해당 코드 변경은 복원. 로그·진단 결과는 원위치 보존. |

새 worktree: `/home/uiseop/orca/workspaces/wasabi-benchmark/aes-41-experiment-on-coding-agent-return-three-t`.
이동 시 최신 `origin/main`과 AES-40 HEAD는 커밋 해시는 달랐지만 커밋된 파일 내용은 같았다.

## 3. 평가 결과 스냅샷

전체 500개를 분모로 한 **해결 확인 건수**. 미보고/실행 오류를 실제 테스트 실패와 혼동하지 않는다.

| 조건 | Rep 1 | Rep 2 | Rep 3 | 평균 resolve rate |
|---|---:|---:|---:|---:|
| GPT-5.6 Luna baseline | 278/500 | 273/500 | 277/500 | 55.20% |
| GPT-5.6 Luna + Wasabi (기존 initial-only) | 315/500 | 320/500 | 312/500 | 63.13% |
| GPT-6.1 Sol baseline | 401/500 | 409/500 | 409/500 | 81.27% |
| GPT-6 Luna baseline | 미평가 | 미실행 | 미실행 | — |

- Luna baseline rep-1 `django__django-15022`, Luna+Wasabi rep-3 `sphinx-doc__sphinx-7590`는 비교 시점에 보고서가 없었음. 그 외 empty/missing과 별도 구분.
- Sol 평가: 보고서 492/498/495개, unresolved 91/89/86개, empty 8/2/4개, generation missing 0/0/1개, 평가 실행 오류 모두 0.
- 태스크별 3회 해결 횟수 비교: Sol 개선 196 / 동일 290 / 감소 14개.
- Luna 0/3 → Sol 3/3: 83개. Luna 3/3 → Sol 0/3: 3개.
- 후자의 3개: `django__django-10097`, `django__django-12193`, `pytest-dev__pytest-7205`.
- Worker·재시도 이력이 달라 모델 외 모든 조건이 통제된 비교는 아니다. 새 파서/새 Wasabi return 조건은 이 표에 포함하지 않는다.

## 4. 원본 기록 위치

**삭제 기록:** 사용자 요청으로 AES-40의 GPT-6 Luna baseline 1회차·재시도·v2 진단
원본과 전용 `.sandbox` 실행/상태 파일을 삭제했다(약 26 GiB). 잘못된 모델명
`gpt-6.1-luna` smoke 경로도 확인했으며 정리 시 이미 존재하지 않았다.
아래 Luna 6 경로 및 관련 상태 파일은 역사적 참조이며 더 이상 존재하지 않는다.
본문의 당시 집계는 이력으로 보존하되 재검증 가능한 원본 데이터로 취급하지 않는다.
Baseline은 AES-41에서 새로 실행할 예정이다. GPT-5.6 Luna, GPT-6.1 Sol,
Wasabi return smoke, 공용 Docker 이미지 및 AES-41 코드는 삭제하지 않았다.


아래 경로는 이 서버의 위치이며 Git에는 대용량 원본을 포함하지 않는다.

| 기록 | 경로 |
|---|---|
| 최초 Luna 5.6 실험 | AES-40 worktree의 `runs/aes40-three-repetitions/` |
| 최초 evaluation·image metadata | 위 경로의 `evaluation/` |
| Sol 실험 | `/mnt/data/experiments/aes40-baseline-gpt61sol-20261112-044503/` |
| Sol 모델 비교 | 위 경로의 `evaluation/model-comparison.json` |
| Luna 6 실험 | `/mnt/data/experiments/aes40-baseline-gpt6luna-20261113-073856/` |
| Luna 6 v2 진단 | 위 경로의 `parser-v2-diagnostic-20261113-112655/` |
| Wasabi return live smoke | AES-40 worktree의 `runs/wasabi-return-smoke-20261113-144519/` |
| 실행/모니터링 스크립트 | AES-40 worktree의 `.sandbox/` (Git 제외) |
| 운영 시점 상태 요약 | `.sandbox/aes40-status.md`, `sol-baseline-status.md`, `sol-evaluation-status.md`, `luna6-baseline-status.md` 등 |

원본 결과 해석 우선순위: 개별 `results.json`/평가 `report.json` → 해당 실행 `exit.json` 및 command/manifest → 상위 요약 → 당시 채팅 관측.
프로세스 종료 후 상태 문서는 자동 갱신되지 않을 수 있다. PID는 재부팅 후 재사용될 수 있으므로 실행 증거로 단독 사용하지 않는다.

## 5. Luna 6 zero-reply baseline (2026-11-13)
Recorded: 2026-11-13T18:29:27.807543+00:00 (UTC).
- Coding agent: `centinels/gpt-6-luna`; Wasabi disabled; simulator replies: 0.
- Unchanged baseline prompt; first question receives a fixed limit notice, another question fails.
- Planned: 500 tasks × 3 repetitions; generation/evaluation workers: 64; timeouts: 600/1800 seconds.
- Parser: `single-envelope-v2`. Every tenth task retains full generation artifacts; other tasks retain predictions and summaries.
- Each generation repetition is followed immediately by evaluation. No automatic retries.
- Final supervisor state: `{'phase': 'finished', 'repetitions': 3}`. Process exit alone does not imply successful completion.
- Artifacts: `/home/uiseop/orca/workspaces/wasabi-benchmark/aes-41-experiment-on-coding-agent-return-three-t/.sandbox/luna6-zero-20261113-155517`.

| Repetition | Generation finished | Completed | Errors | Nonempty patches | Evaluation exit |
|---|---:|---:|---:|---:|---|
| 1 | 500/500 | 494 | 6 | 458 | 0 |

Rep 1 evaluation summary (`luna6-zero.luna6-zero-20261113-155517-rep-1.json`):
```json
{
  "total_instances": 500,
  "submitted_instances": 500,
  "completed_instances": 458,
  "resolved_instances": 226,
  "unresolved_instances": 232,
  "empty_patch_instances": 42,
  "error_instances": 0,
  "schema_version": 2
}
```
| 2 | 500/500 | 492 | 8 | 455 | 0 |

Rep 2 evaluation summary (`luna6-zero.luna6-zero-20261113-155517-rep-2.json`):
```json
{
  "total_instances": 500,
  "submitted_instances": 500,
  "completed_instances": 455,
  "resolved_instances": 229,
  "unresolved_instances": 226,
  "empty_patch_instances": 45,
  "error_instances": 0,
  "schema_version": 2
}
```
| 3 | 500/500 | 489 | 11 | 452 | 0 |

Rep 3 evaluation summary (`luna6-zero.luna6-zero-20261113-155517-rep-3.json`):
```json
{
  "total_instances": 500,
  "submitted_instances": 500,
  "completed_instances": 451,
  "resolved_instances": 227,
  "unresolved_instances": 224,
  "empty_patch_instances": 48,
  "error_instances": 1,
  "schema_version": 2
}
```

### Zero-reply 결과 해석 (재시도 전 기준)

- GPT-6 Luna, simulator 답변 0회: 226/500, 229/500, 227/500, 평균 **45.47%**.
- 기존 GPT-5.6 Luna baseline, simulator 답변 상한 5회: 평균 **55.20%**. 이번 zero-reply 조건이 **9.73%p 낮았다**.
- 특징적 관찰: 최신 Luna 모델의 zero-reply 조건이 이전 Luna 모델의 질문 허용 baseline보다 낮은 해결률을 보였다.
- 단, 모델·질문 파서·재시도 이력이 다르므로 이 차이를 interaction 제한의 인과 효과로 단정하지 않는다. 기존 상한 5회는 실제 5회 답변 사용을 의미하지 않는다. 동일 GPT-6 Luna/parser-v2에서 답변 0회 vs 5회를 비교해야 효과를 분리할 수 있다.
- Luna 5.6 baseline 최초 실행의 실제 simulator 답변 횟수를 원본 `baseline-rep-{1,2,3}/results.json`에서 집계했다(재시도 제외):
  - Rep 1: 0회 498건, 1회 2건, 2회 이상 0건.
  - Rep 2: 0회 496건, 1회 4건, 2회 이상 0건.
  - Rep 3: 0회 499건, 1회 1건, 2회 이상 0건.
  - 총 1,500회 실행 중 1,493회(99.53%)는 simulator 답변 0회였고, 7회만 답변 1회를 사용했다. 여러 번 답변한 실행은 없었다.
  - 근거: `/mnt/data/wasabi-benchmark/aes40-three-repetitions/`.
- 따라서 비교의 핵심은 **Luna 6 zero-reply 조건(45.47%)이 실제로도 거의 추가 답변 없이 수행된 Luna 5.6 baseline(55.20%)보다 낮았다**는 관찰이다. 이를 interaction 제한 때문이라고 설명할 근거는 부족하다. 모델의 작업 방식, 질문·패치 생성 경향 및 실행 조건 차이를 함께 검토해야 한다. 답변 횟수 집계는 최초 실행 기준이고 기존 해결률은 복구 이력이 있는 결과라는 범위 차이도 유의한다.
- 이번 초기 프롬프트는 질문을 허용하는 기존 PROTOCOL 그대로다. 답변 예산만 0이며, 첫 유효 질문에 고정 계속 작업 안내를 보낸다. 처음부터 질문 금지를 명시한 조건과는 다르다.
- 최초 generation 오류 25건: envelope 12, API capacity 5, policy rejection 4, 600초 timeout 3, WebSocket 연결 실패 1. 평가 오류 1건은 rep-3 `sphinx-doc__sphinx-7985`의 1,800초 timeout.
- 오류 재시도는 별도 디렉터리에 보존하며, 완료 후 원본 점수와 재시도 반영 점수를 구분해 해석한다.

### Zero-reply baseline error retry (2026-11-14T02:18:53.481255+00:00)

- Artifacts: `/home/uiseop/orca/workspaces/wasabi-benchmark/aes-41-experiment-on-coding-agent-return-three-t/.sandbox/luna6-zero-20261113-155517/retry-20261114-014045`. Original results preserved; one retry, unchanged model/budget/timeouts.
- Rep 1: generation retries 6, completed 6.
  - Retry evaluation only: {"total_instances": 500, "submitted_instances": 6, "completed_instances": 4, "resolved_instances": 2, "unresolved_instances": 2, "empty_patch_instances": 2, "error_instances": 0, "schema_version": 2}
- Rep 2: generation retries 8, completed 8.
  - Retry evaluation only: {"total_instances": 500, "submitted_instances": 8, "completed_instances": 8, "resolved_instances": 5, "unresolved_instances": 3, "empty_patch_instances": 0, "error_instances": 0, "schema_version": 2}
- Rep 3: generation retries 11, completed 11.
  - Retry evaluation only: {"total_instances": 500, "submitted_instances": 12, "completed_instances": 7, "resolved_instances": 3, "unresolved_instances": 4, "empty_patch_instances": 4, "error_instances": 1, "schema_version": 2}

### Luna 6 baseline, five replies (2026-11-14T10:51:06.140684+00:00)

- 500 tasks × 1; workers 32; simulator Sol 6.1; parser-v2; no automatic retries.
- Artifacts: `/home/uiseop/orca/workspaces/wasabi-benchmark/aes-41-experiment-on-coding-agent-return-three-t/.sandbox/luna6-five-20261114-094654`. Detailed generation logs disabled; workspaces removed; evaluation logs removed after evaluation, reports retained.
- Generation completed: 492/500; simulator replies: 47; evaluation exit: 0.
- Evaluation: {"total_instances": 500, "submitted_instances": 500, "completed_instances": 454, "resolved_instances": 244, "unresolved_instances": 210, "empty_patch_instances": 46, "error_instances": 0, "schema_version": 2}

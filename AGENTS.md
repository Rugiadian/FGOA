# FGOA Project Rules for AI Assistants

## 1. 버전 관리 규칙 (Version Management Rule)
- **코드 업데이트 시 버전 갱신**: 코드를 수정하거나 기능을 추가/업데이트할 때마다 `core/version.py`의 `__version__`을 반드시 현재 업데이트 날짜 및 시간(`yymmdd.hhmm`, 예: `260924.1256`)으로 갱신합니다. (초는 포함하지 않음)
- **단순화된 날짜시간 형식**: 다른 연산(SemVer 메이저/마이너/패치 판단, 커밋 해시 계산 등) 없이 오직 업데이트 시점의 날짜시간(`yymmdd.hhmm`)을 버전 숫자로 지정합니다.
- **프로그램 창 제목 표시**: 메인 윈도우 제목(Window Title)에 항상 현재 앱 버전(`FGOA v{__version__}`)이 표기되어야 합니다.

## 2. 작업 내역 개별 txt 파일 기록 규칙 (Work History Logging Rule)
- **개별 txt 로그 파일 생성**: 사용자의 요청을 처리할 때마다 요청 내용, 처리 결과 요약, 작업 일시(시기) 등을 기록한 개별 `.txt` 파일을 `history/` 폴더에 생성합니다. (하나의 파일에 이어 쓰지 말고 건마다 개별 파일 생성)
- **파일명 형식**: `history/YYYY-MM-DD_HHMMSS_요약.txt` (예: `history/2026-09-24_003524_요청_로그_개별_txt_기록_규칙_수립.txt`)
- **로그 내용 필수 항목**:
  1. [일시 / Timestamp]: 요청 및 완료 시각
  2. [요청 내용 / User Request]: 사용자가 요청한 원문 또는 핵심 내용
  3. [결과 요약 / Summary of Results]: 수행한 작업 및 변경 사항 요약
  4. [영향 파일 목록 / Affected Files]: 생성되거나 수정된 파일 경로
- **히스토리 파일 열람 제한 (Write-Only Archive)**: `history/` 폴더는 사용자를 위한 작업 기록 보관용 아카이브입니다. 사용자가 이전 작업 내역 확인을 명시적으로 요구하지 않는 한, 일반적인 코드 탐색·분석·수정 시 `history/` 폴더 내 과거 로그 파일을 임의로 읽거나 전역 검색하지 않습니다.

## 3. 토큰 최적화 규칙 (Token Optimization Rule)
- **무관한 파일/캐시 접근 금지**: `.geminiignore` 및 `.gitignore`에 등록된 항목(`history/`, `__pycache__/`, `*.log`, 대용량 JSON 등)을 불필요하게 AI 컨텍스트에 주입하거나 전역 검색하지 않습니다.
- **최소 범위 파일 조회**: 대형 소스 코드(800줄 초과) 탐색 시 파일 전체를 반복 로드하지 않고, `StartLine`/`EndLine`을 지정하거나 검색 도구를 활용해 필요한 영역만 집중 조회합니다.


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
- **무관한 파일/캐시 접근 금지**: `.geminiignore` 및 `.gitignore`에 등록된 항목(`history/`, `references/`, `__pycache__/`, `*.log`, 대용량 JSON, 이미지 파일, `.git/` 등)을 불필요하게 AI 컨텍스트에 주입하거나 전역 검색하지 않습니다.
- **최소 범위 파일 조회 및 편집 (Surgical Slice Inspection)**: 대형 소스 코드(특히 2,000줄을 초과하는 `ui/main_window.py`, `ui/inspector_widget.py`) 탐색 시 파일 전체(`view_file` 시작/끝 라인 생략)를 로드하는 것을 엄격히 금지합니다. 반드시 `Select-String`이나 `findstr` 등의 검색 명령어로 수정 대상 라인을 먼저 특정한 뒤, `StartLine`/`EndLine`을 30~60줄 이내로 최소화하여 조회 및 수정합니다.
- **터미널 명령어 출력 필터링 및 페이징 방지 (CLI Output Limiting)**: 파일 목록이나 검색 명령 실행 시 무제한 출력을 피하고 파이프라인(`| Select-Object -First 20`, `Select-String` 타깃팅 등)을 통해 AI 컨텍스트로 반환되는 텍스트 양을 철저히 제한합니다.
- **테스트 실행 시 표준 출력 버퍼링 필수 (`-b`)**: 전체 테스트 스위트 실행 시 반드시 `python -m unittest discover -b -s tests`를 사용하여 통과된 테스트의 불필요한 표준 출력(stdout/print문)이 AI 컨텍스트에 대량 누적되는 것을 방지합니다. 단위 테스트 내에 불필요한 콘솔 `print()` 구문을 작성하지 않습니다.
- **콘솔 잡음/경고 원천 차단 (Suppress Console Warnings)**: Qt null pixmap 경고(`QPixmap::scaled: Pixmap is a null pixmap`) 등 C++ 레벨 stderr 잡음이 발생하지 않도록 `pix.isNull()` 방어 코드를 철저히 적용합니다.
- **답변 생성 시 불필요한 코드 전문 재출력 지양 (Diff/Summary-Focused Response)**: 사용자가 전체 소스 출력을 명시적으로 요구하지 않는 한, 수백 줄의 기존 소스 코드를 답변에 통째로 복사-출력하지 않고, 변경된 핵심 함수나 변경점(Diff/요약) 위주로 간결하게 답변하여 출력 토큰 낭비를 최소화합니다.
- **신규 기능 모듈 분리 원칙 (Modularization Principle)**: 대형 파일(`ui/main_window.py`, `ui/inspector_widget.py`)에 거대한 로직을 직접 누적하지 않고, 다이얼로그·컴포넌트·유틸리티 단위로 별도 모듈 분리를 지향하여 AI가 향후 특정 기능을 탐색·수정할 때 필요한 컨텍스트 크기를 작게 유지합니다.
- **작업 완료 후 세션 분리 권장**: 대형 기능 추가나 구조 변경이 완료된 후에는 새로운 독립적인 요청 시 새로운 대화 세션(New Chat)을 시작하여, 이전 작업의 수십만 토큰에 달하는 누적 히스토리가 매 턴마다 재주입되는 것을 방지하도록 사용자에게 안내합니다.


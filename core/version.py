"""
FGOA Version Definition
규칙: Git 커밋 기록으로부터 최신 커밋 날짜시간(yymmdd.hhmm)을 동적으로 자동 추출합니다.
Git이 없는 환경이나 패키징 환경을 위해 기본 폴백 버전을 지원합니다.
"""
import glob
import os
import re
import shutil
import subprocess

_FALLBACK_VERSION = "261009.1640"


def _find_git_executable() -> str:
    """시스템 환경 또는 GitHub Desktop 설치 경로에서 git 실행 파일을 탐색합니다."""
    exe = shutil.which("git")
    if exe:
        return exe
    candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        gh_gits = glob.glob(
            os.path.join(
                local_app, "GitHubDesktop", "app-*", "resources", "app", "git", "cmd", "git.exe"
            )
        )
        if gh_gits:
            return gh_gits[0]
    return "git"


def get_version() -> str:
    """최신 Git 커밋 날짜시간을 yymmdd.hhmm 형식으로 동적 반환합니다."""
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git_exe = _find_git_executable()
    try:
        out = subprocess.check_output(
            [git_exe, "log", "-1", "--format=%cd", "--date=format:%y%m%d.%H%M"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).strip()
        if re.match(r"^\d{6}\.\d{4}$", out):
            return out
    except Exception:
        pass
    return _FALLBACK_VERSION


__version__ = get_version()

"""
Log & Trace Manager Mixin for MainWindow.
Handles real-time logging, HTML formatting, clickable screenshot preview,
mismatch breakdown accordion, and robust trace screenshot cleanups.
"""
import os
import re
import html
from typing import Dict, Any, Optional

from PyQt5.QtWidgets import QMessageBox
from ui.theme import get_theme_colors
from core.path_utils import to_trace_absolute_path, get_trace_dir
from core.trace_logger import TraceLogger


class MainWindowLogMixin:
    """Mixin providing real-time logging and trace log capabilities to MainWindow."""

    def _clear_logs(self):
        self.txt_log.clear()
        if hasattr(self, "_log_records"):
            self._log_records.clear()
        self._next_log_id = 0

    def _append_log(self, level: str, msg: str):
        if not hasattr(self, "_log_records"):
            self._log_records = []
        if not hasattr(self, "_next_log_id"):
            self._next_log_id = 0

        pal = get_theme_colors(getattr(self, "current_theme", "light"))
        color_map = {
            "INFO": pal["log_info"],
            "ACTION": pal["log_action"],
            "SUCCESS": pal["log_success"],
            "WARN": pal["log_warn"],
            "ERROR": pal["log_error"],
            "USER": pal["log_user"]
        }
        color = color_map.get(level, pal["text_primary"])
        prefix_color = "#64748b" if pal["is_light"] else "#8da4c4"

        # Check for [TRACE_SHOT:path(|NUM:0001)] tag
        shot_path = ""
        shot_num = ""
        m_shot = re.search(r"\[TRACE_SHOT:(.*?)\]", msg)
        if m_shot:
            raw_shot_info = m_shot.group(1).strip()
            if "|NUM:" in raw_shot_info:
                shot_path, shot_num = raw_shot_info.split("|NUM:", 1)
                shot_path = shot_path.strip()
                shot_num = shot_num.strip()
            elif "|" in raw_shot_info:
                shot_path, shot_num = raw_shot_info.split("|", 1)
                shot_path = shot_path.strip()
                shot_num = shot_num.strip().lstrip("#")
            else:
                shot_path = raw_shot_info
                m_num = re.search(r'shot_(\d+)', os.path.basename(shot_path))
                shot_num = m_num.group(1) if m_num else ""

            msg = (msg[:m_shot.start()] + msg[m_shot.end():]).strip()

        log_id = self._next_log_id
        self._next_log_id += 1

        record = {
            "id": log_id,
            "level": level,
            "raw_msg": msg,
            "expanded": False,
            "has_mismatch": False,
            "screenshot_path": shot_path,
            "screenshot_number": shot_num
        }

        # Check for explicit [MISMATCH:count]detail[/MISMATCH] tags
        m_tag = re.search(r'\[MISMATCH(?::(\d+))?\](.*?)\[/MISMATCH\]', msg, re.DOTALL)
        if m_tag:
            count = m_tag.group(1) or ""
            detail = m_tag.group(2).strip()
            record["has_mismatch"] = True
            record["prefix_text"] = msg[:m_tag.start()].strip()
            record["suffix_text"] = msg[m_tag.end():].strip()
            record["mismatch_detail"] = detail
            record["fail_count"] = count
        elif "\n     └ 불일치: " in msg or "\n  └ 불일치: " in msg:
            sep = "\n     └ 불일치: " if "\n     └ 불일치: " in msg else "\n  └ 불일치: "
            parts = msg.split(sep, 1)
            record["has_mismatch"] = True
            record["prefix_text"] = parts[0].strip()
            record["suffix_text"] = ""
            record["mismatch_detail"] = parts[1].strip()
            record["fail_count"] = ""

        self._log_records.append(record)

        # Cap in-memory log records to prevent memory leak on long-running macro sessions
        MAX_LOG_RECORDS = 1000
        if len(self._log_records) > MAX_LOG_RECORDS:
            del self._log_records[:len(self._log_records) - MAX_LOG_RECORDS]

        # Append newly formatted HTML
        html_content = self._format_log_record_html(record, pal, color, prefix_color)
        self.txt_log.append(html_content)

        if hasattr(self, "chk_autoscroll") and self.chk_autoscroll and self.chk_autoscroll.isChecked():
            sb = self.txt_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _format_log_record_html(self, record: dict, pal: dict, color: str, prefix_color: str) -> str:
        log_id = record["id"]
        level = record["level"]

        shot_p = record.get("screenshot_path", "")
        shot_num = record.get("screenshot_number", "")
        shot_badge = ""
        if shot_p:
            shot_abs = to_trace_absolute_path(shot_p)
            if shot_abs and os.path.isfile(shot_abs):
                num_tag = f" #{shot_num}" if shot_num else ""
                shot_badge = f" <a href='view-screenshot:{log_id}' style='color: #38bdf8; text-decoration: none; font-weight: bold;'>[📸{num_tag} 화면]</a>"

        # Equalize word width for log levels (INFO, SUCCESS, ACTION, WARN, ERROR)
        # Pad to 7 characters (length of 'SUCCESS') with non-breaking spaces for alignment
        padded_level = level.ljust(7)
        level_html = padded_level.replace(" ", "&nbsp;")
        tag_prefix = f"<span style='color: {prefix_color}; font-family: Consolas, monospace;'>[{level_html}]</span>"

        if record.get("has_mismatch"):
            prefix_t = record.get("prefix_text", "")
            suffix_t = record.get("suffix_text", "")
            suffix_part = f" {suffix_t}" if suffix_t else ""
            detail_t = record.get("mismatch_detail", "")
            cnt_str = f"불일치 {record['fail_count']}건" if record.get("fail_count") else "불일치"

            if not record.get("expanded", False):
                # Collapsed: Show clickable badge link to expand
                btn_link = f"<a href='toggle-mismatch:{log_id}' style='color: #38bdf8; text-decoration: none; font-weight: bold;'>[▶ {cnt_str} 세부내역 열기]</a>"
                return f"<div id='mismatch_{log_id}' style='margin: 1px 0;'>{tag_prefix} <span style='color: {color};'>{prefix_t} {btn_link}{suffix_part}</span>{shot_badge}</div>"
            else:
                # Expanded: Show clickable badge link to collapse, and formatted details indented per-point
                is_partial_success = (level == "SUCCESS")
                btn_close_color = "#eab308" if is_partial_success else "#f87171"
                btn_link = f"<a href='toggle-mismatch:{log_id}' style='color: {btn_close_color}; text-decoration: none; font-weight: bold;'>[▼ {cnt_str} 세부내역 닫기]</a>"
                header_line = f"{tag_prefix} <span style='color: {color};'>{prefix_t} {btn_link}{suffix_part}</span>{shot_badge}"

                # Format per-point detail lines
                detail_lines = [l.strip() for l in detail_t.split("\n") if l.strip()]
                formatted_items = []
                for line in detail_lines:
                    clean_l = line.lstrip("•").strip()
                    escaped_l = html.escape(clean_l)
                    escaped_l = escaped_l.replace("[일치]", "<span style='color: #22c55e; font-weight: bold;'>[일치]</span>")
                    escaped_l = escaped_l.replace("[불일치]", "<span style='color: #ef4444; font-weight: bold;'>[불일치]</span>")
                    formatted_items.append(f"<div style='margin: 2px 0;'>&bull; {escaped_l}</div>")
                inner_details = "".join(formatted_items)

                box_bg = ("rgba(245, 158, 11, 0.12)" if is_partial_success else "rgba(239, 68, 68, 0.12)") if not pal["is_light"] else ("#fef3c7" if is_partial_success else "#fee2e2")
                box_border = "#f59e0b" if is_partial_success else "#ef4444"
                text_detail_color = ("#fde68a" if is_partial_success else "#fca5a5") if not pal["is_light"] else ("#92400e" if is_partial_success else "#991b1b")
                header_title = "🔍 세부 포인트 판정 내역 (OR 일부 일치):" if is_partial_success else "🔍 불일치 세부 포인트 목록:"

                detail_box = (
                    f"<div style='margin-left: 18px; margin-top: 3px; margin-bottom: 4px; padding: 6px 10px; "
                    f"background-color: {box_bg}; border-left: 3px solid {box_border}; border-radius: 4px; "
                    f"font-family: Consolas, monospace; font-size: 8.5pt; color: {text_detail_color}; line-height: 1.45;'>"
                    f"<div style='font-weight: bold; margin-bottom: 3px; color: {box_border};'>{header_title}</div>"
                    f"{inner_details}"
                    f"</div>"
                )
                return f"<div id='mismatch_{log_id}' style='margin: 1px 0;'>{header_line}{detail_box}</div>"

        elif "루프 시작" in record['raw_msg']:
            badge = "<span style='background: #2563eb; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 8.5pt;'>🔄 루프 시작</span>"
            border_c = "#3b82f6"
            bg_c = "rgba(59, 130, 246, 0.12)" if not pal["is_light"] else "#eff6ff"
            return f"<div style='margin: 3px 0; padding: 3px 6px; background-color: {bg_c}; border-left: 3px solid {border_c}; border-radius: 4px;'>{tag_prefix} {badge} <span style='color: {color}; font-weight: bold;'>{html.escape(record['raw_msg'])}</span>{shot_badge}</div>"

        elif "루프 탈출" in record['raw_msg'] or "루프 종료" in record['raw_msg']:
            badge = "<span style='background: #d97706; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 8.5pt;'>⚡ 루프 탈출</span>"
            border_c = "#f59e0b"
            bg_c = "rgba(245, 158, 11, 0.12)" if not pal["is_light"] else "#fffbeb"
            return f"<div style='margin: 3px 0; padding: 3px 6px; background-color: {bg_c}; border-left: 3px solid {border_c}; border-radius: 4px;'>{tag_prefix} {badge} <span style='color: {color}; font-weight: bold;'>{html.escape(record['raw_msg'])}</span>{shot_badge}</div>"

        elif level == "USER":
            prefix_html = f"<span style='color: {color}; font-weight: bold;'>[사용자 로그]</span>"
            msg_html = f"<span style='color: {color}; font-weight: bold;'>{html.escape(record['raw_msg'])}</span>"
            return f"{prefix_html} {msg_html}{shot_badge}"
        else:
            return f"{tag_prefix} <span style='color: {color};'>{record['raw_msg']}</span>{shot_badge}"

    def _on_log_anchor_clicked(self, url):
        if hasattr(url, "toString"):
            url_str = url.toString() or url.path() or ""
        else:
            url_str = str(url)

        if "view-screenshot:" in url_str:
            try:
                param = url_str.split("view-screenshot:", 1)[1].strip()
                shot_path = ""
                shot_num = ""

                # 1. Try resolving by log_id integer (avoids URL encoding issues on foreign PCs)
                if param.isdigit() and hasattr(self, "_log_records"):
                    target_id = int(param)
                    target_rec = next((r for r in self._log_records if r.get("id") == target_id), None)
                    if target_rec:
                        shot_path = target_rec.get("screenshot_path", "")
                        shot_num = target_rec.get("screenshot_number", "")

                # 2. Fallback to direct path string if not integer
                if not shot_path:
                    shot_path = param

                resolved_abs = to_trace_absolute_path(shot_path)

                if resolved_abs and os.path.isfile(resolved_abs):
                    from ui.image_preview_dialog import show_image_preview
                    num_prefix = f"[#{shot_num}] " if shot_num else ""
                    show_image_preview(resolved_abs, title=f"📸 추적 스크린샷 {num_prefix}- {os.path.basename(resolved_abs)}", parent=self)
                else:
                    QMessageBox.warning(
                        self,
                        "스크린샷 파일 없음",
                        f"스크린샷 파일을 찾을 수 없습니다.\n\n"
                        f"기록된 경로: {shot_path}\n"
                        f"탐색된 로컬 경로: {resolved_abs or '없음'}\n\n"
                        f"다른 컴퓨터에서 복사한 경우 trace_logs 폴더가 함께 복사되었는지 확인해 주세요."
                    )
            except Exception as e:
                QMessageBox.warning(self, "오류", f"스크린샷을 여는 중 오류가 발생했습니다:\n{e}")
            return

        if "toggle-mismatch:" in url_str or "toggle_mismatch:" in url_str:
            try:
                for prefix in ("toggle-mismatch:", "toggle_mismatch:"):
                    if prefix in url_str:
                        log_id = int(url_str.split(prefix)[1].strip("/"))
                        break
                if hasattr(self, "_log_records"):
                    target_rec = next((r for r in self._log_records if r.get("id") == log_id), None)
                    if target_rec:
                        target_rec["expanded"] = not target_rec.get("expanded", False)
                        self._rerender_all_logs()
            except Exception:
                pass

    def _rerender_all_logs(self):
        if not hasattr(self, "_log_records") or not self._log_records:
            return

        sb = self.txt_log.verticalScrollBar()
        val = sb.value()
        was_at_bottom = (val >= sb.maximum() - 20)

        pal = get_theme_colors(getattr(self, "current_theme", "light"))
        color_map = {
            "INFO": pal["log_info"],
            "ACTION": pal["log_action"],
            "SUCCESS": pal["log_success"],
            "WARN": pal["log_warn"],
            "ERROR": pal["log_error"],
            "USER": pal["log_user"]
        }
        prefix_color = "#64748b" if pal["is_light"] else "#8da4c4"

        html_blocks = []
        for rec in self._log_records:
            color = color_map.get(rec["level"], pal["text_primary"])
            html_blocks.append(self._format_log_record_html(rec, pal, color, prefix_color))

        self.txt_log.setHtml("<br>".join(html_blocks))

        if was_at_bottom and hasattr(self, "chk_autoscroll") and self.chk_autoscroll and self.chk_autoscroll.isChecked():
            sb.setValue(sb.maximum())
        else:
            sb.setValue(val)

    def _on_robust_trace_toggled(self, checked: bool):
        if hasattr(self, "_save_app_config"):
            self._save_app_config()
        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            self.runner.set_robust_trace_enabled(checked)
        self._append_log("INFO", f"⚙️ [설정] 강력 로그추적 모드가 {'활성화' if checked else '비활성화'}되었습니다.")

    def _on_delete_trace_logs(self):
        target_dir = get_trace_dir()
        reply = QMessageBox.question(
            self,
            "추적 폴더 일괄 삭제",
            f"강력 로그추적을 통해 저장된 모든 스크린샷과 루프 하위 폴더를 일괄 삭제하시겠습니까?\n\n대상 경로: {target_dir}\n(삭제 후 복구할 수 없습니다.)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            res = TraceLogger.clean_all_trace_logs(target_dir)
            freed_mb = res["freed_bytes"] / (1024 * 1024)
            msg = f"강력 로그추적 폴더 정리 완료:\n폴더 {res['deleted_dirs']}개, 파일 {res['deleted_files']}개 삭제 (총 {freed_mb:.2f} MB 확보)"
            self._append_log("INFO", f"🗑️ [추적 로그 정리] 폴더 {res['deleted_dirs']}개, 파일 {res['deleted_files']}개 ({freed_mb:.2f} MB) 일괄 삭제 완료.")
            QMessageBox.information(self, "삭제 완료", msg)

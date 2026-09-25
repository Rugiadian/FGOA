"""
Reference Image Gallery Dialog for FGOA.
Manages captured and imported reference images, tracking usage across
cognition conditions (Eye) and action coordinates (Hand).
"""
import os
import glob
from typing import List, Dict, Any, Optional
from PIL import Image
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QFrame, QFileDialog, QMessageBox, QComboBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon, QColor, QFont

from core.models import Project, Scenario
from core.screen_capture import ScreenCapture
from core.window_manager import WindowManager
from core.path_utils import get_references_dir, to_relative_path, to_absolute_path
from ui.coordinate_picker_dialog import CoordinatePickerDialog
from ui.qt_image_utils import pil_to_qpixmap


REFS_DIR = get_references_dir()


class ReferenceGalleryDialog(QDialog):
    """
    Dialog for browsing, importing, capturing, and managing reference images,
    clearly indicating which scenarios (Eye conditions / Hand actions) use each image.
    """

    def __init__(self, project: Project, target_hwnd: int = 0, picker_mode: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🖼️ 레퍼런스 갤러리 (이미지 선택)" if picker_mode else "🖼️ 레퍼런스 갤러리 (참조 이미지 및 사용처 관리)")
        self.resize(1080, 720)

        self.project = project
        self.target_hwnd = target_hwnd
        self.picker_mode = picker_mode
        self.selected_path: Optional[str] = None
        self.image_entries: List[Dict[str, Any]] = []

        os.makedirs(REFS_DIR, exist_ok=True)

        self._init_ui()
        self.refresh_gallery()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Top Control Bar
        top_bar = QFrame()
        top_bar.setObjectName("card_frame")
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(10, 6, 10, 6)

        btn_capture = QPushButton("📸 현재 게임창 캡처 추가")
        btn_capture.setObjectName("btn_primary")
        btn_capture.clicked.connect(self._on_capture_current_window)
        tb_layout.addWidget(btn_capture)

        btn_import = QPushButton("📂 외부 이미지 파일 가져오기...")
        btn_import.clicked.connect(self._on_import_image)
        tb_layout.addWidget(btn_import)

        btn_refresh = QPushButton("🔄 새로고침")
        btn_refresh.clicked.connect(self.refresh_gallery)
        tb_layout.addWidget(btn_refresh)

        tb_layout.addSpacing(16)

        tb_layout.addWidget(QLabel("사용 구분:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItem("모든 이미지", "all")
        self.combo_filter.addItem("🟢 사용 중인 이미지만", "used")
        self.combo_filter.addItem("⚪ 미사용 이미지만", "unused")
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        tb_layout.addWidget(self.combo_filter)

        tb_layout.addSpacing(12)

        tb_layout.addWidget(QLabel("📐 해상도별 분류:"))
        self.combo_resolution = QComboBox()
        self.combo_resolution.addItem("전체 해상도 보기", "all")
        self.combo_resolution.currentIndexChanged.connect(self._apply_filter)
        tb_layout.addWidget(self.combo_resolution)

        tb_layout.addStretch()

        self.lbl_stats = QLabel("총 0개 이미지 (0개 사용 중)")
        self.lbl_stats.setStyleSheet("font-weight: bold; color: #475569;")
        tb_layout.addWidget(self.lbl_stats)

        main_layout.addWidget(top_bar)

        # Center Horizontal Splitter: [Left: Image List | Right: Preview & Usages]
        splitter = QSplitter(Qt.Horizontal)

        # Left List Container
        left_container = QFrame()
        left_container.setObjectName("card_frame")
        l_layout = QVBoxLayout(left_container)
        l_layout.setContentsMargins(6, 6, 6, 6)
        l_layout.setSpacing(6)

        self.lbl_res_banner = QLabel("📐 전체 해상도")
        self.lbl_res_banner.setStyleSheet(
            "background-color: #f1f5f9; color: #475569; font-weight: bold; font-size: 8.5pt; "
            "padding: 4px 8px; border-radius: 4px; border: 1px solid #cbd5e1;"
        )
        l_layout.addWidget(self.lbl_res_banner)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(72, 48))
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        l_layout.addWidget(self.list_widget)
        splitter.addWidget(left_container)

        # Right Detail Container
        right_container = QFrame()
        right_container.setObjectName("card_frame")
        r_layout = QVBoxLayout(right_container)
        r_layout.setContentsMargins(10, 10, 10, 10)
        r_layout.setSpacing(8)

        # 1. Image Preview Box
        self.lbl_preview = QLabel("이미지를 선택하세요")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet(
            "background-color: #0f172a; color: #94a3b8; border-radius: 6px; min-height: 260px;"
        )
        r_layout.addWidget(self.lbl_preview, 1)

        # 2. Image Info (Path, Size, Resolution)
        self.lbl_info = QLabel("선택된 이미지 정보")
        self.lbl_info.setStyleSheet("font-size: 8.5pt; color: #64748b;")
        r_layout.addWidget(self.lbl_info)

        # 3. Usage Table
        lbl_usage_title = QLabel("📌 사용 현황 (어느 조건 및 액션에 사용 중인지)")
        lbl_usage_title.setStyleSheet("font-weight: bold; font-size: 9.5pt; color: #1e293b;")
        r_layout.addWidget(lbl_usage_title)

        self.tbl_usages = QTableWidget()
        self.tbl_usages.setColumnCount(3)
        self.tbl_usages.setHorizontalHeaderLabels(["시나리오", "구분 (Eye/Hand)", "상세 사용 내용"])
        self.tbl_usages.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_usages.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_usages.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_usages.setFixedHeight(140)
        r_layout.addWidget(self.tbl_usages)

        # 4. Action buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_select_this = QPushButton("✅ 이 이미지 선택")
        self.btn_select_this.setObjectName("btn_primary")
        self.btn_select_this.clicked.connect(self._on_select_current_image)
        btn_box.addWidget(self.btn_select_this)

        self.btn_pick_from_img = QPushButton("🎯 이 이미지에서 좌표 찍기...")
        self.btn_pick_from_img.clicked.connect(self._on_open_coord_picker)
        btn_box.addWidget(self.btn_pick_from_img)

        self.btn_delete_img = QPushButton("🗑️ 이미지 삭제")
        self.btn_delete_img.setStyleSheet("color: #ef4444;")
        self.btn_delete_img.clicked.connect(self._on_delete_image)
        btn_box.addWidget(self.btn_delete_img)

        btn_box.addStretch()

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        r_layout.addLayout(btn_box)
        splitter.addWidget(right_container)

        splitter.setStretchFactor(0, 38)
        splitter.setStretchFactor(1, 62)
        splitter.setSizes([380, 620])

        main_layout.addWidget(splitter, 1)

    @classmethod
    def get_all_gallery_entries(cls, project: Project) -> List[Dict[str, Any]]:
        """Collect all reference images and compute usage across scenarios and modules."""
        paths = set()
        if os.path.isdir(REFS_DIR):
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
                for p in glob.glob(os.path.join(REFS_DIR, ext)):
                    paths.add(os.path.normpath(os.path.abspath(p)))

        # Also check project conditions
        for cond in getattr(project, "conditions", []):
            if cond.reference_image_path:
                abs_p = to_absolute_path(cond.reference_image_path)
                if abs_p and os.path.exists(abs_p):
                    paths.add(os.path.normpath(abs_p))

        # Check project action sequences
        for seq in getattr(project, "action_sequences", []):
            if seq.last_action_image_path:
                abs_p = to_absolute_path(seq.last_action_image_path)
                if abs_p and os.path.exists(abs_p):
                    paths.add(os.path.normpath(abs_p))

        # Check scenarios
        for scen in project.scenarios:
            if scen.condition and scen.condition.reference_image_path:
                abs_p = to_absolute_path(scen.condition.reference_image_path)
                if abs_p and os.path.exists(abs_p):
                    paths.add(os.path.normpath(abs_p))
            if getattr(scen, "last_action_image_path", None):
                abs_p = to_absolute_path(scen.last_action_image_path)
                if abs_p and os.path.exists(abs_p):
                    paths.add(os.path.normpath(abs_p))

        entries = []
        for p in sorted(paths):
            usages = cls.compute_image_usages(p, project)
            try:
                stat = os.stat(p)
                size_kb = stat.st_size / 1024
                with Image.open(p) as img:
                    w, h = img.size
            except Exception:
                w, h = 0, 0
                size_kb = 0

            entries.append({
                "path": p,
                "filename": os.path.basename(p),
                "width": w,
                "height": h,
                "size_kb": size_kb,
                "usages": usages,
                "is_used": len(usages) > 0
            })
        return entries

    @classmethod
    def compute_image_usages(cls, image_path: str, project: Project) -> List[Dict[str, str]]:
        """Computes list of scenario and module usages for this image."""
        usages = []
        norm_target = os.path.normpath(os.path.abspath(image_path))
        target_fname = os.path.basename(norm_target)

        # 1. Check Condition Modules
        for cond in getattr(project, "conditions", []):
            if cond.reference_image_path:
                cond_abs = to_absolute_path(cond.reference_image_path)
                if (cond_abs and os.path.normpath(cond_abs) == norm_target) or os.path.basename(cond.reference_image_path) == target_fname:
                    c_num = getattr(cond, "condition_number", 1)
                    usages.append({
                        "scenario_name": f"모듈 [C{c_num}] {cond.name}",
                        "type": "👁️ Eye 인식조건",
                        "detail": f"기준 레퍼런스 (포인트 {len(cond.points)}개 판정)"
                    })

        # 2. Check Action Sequence Modules
        for seq in getattr(project, "action_sequences", []):
            if seq.last_action_image_path:
                seq_abs = to_absolute_path(seq.last_action_image_path)
                if (seq_abs and os.path.normpath(seq_abs) == norm_target) or os.path.basename(seq.last_action_image_path) == target_fname:
                    s_num = getattr(seq, "sequence_number", 1)
                    usages.append({
                        "scenario_name": f"모듈 [A{s_num}] {seq.name}",
                        "type": "✋ Hand 액션시퀀스",
                        "detail": f"좌표 지정 기준 이미지 ({len(seq.actions)}개 액션)"
                    })

        # 3. Check Scenarios
        for scen in project.scenarios:
            eff_cond = scen.get_effective_condition(project) if hasattr(scen, "get_effective_condition") else scen.condition
            if eff_cond and eff_cond.reference_image_path:
                cond_abs = to_absolute_path(eff_cond.reference_image_path)
                if (cond_abs and os.path.normpath(cond_abs) == norm_target) or os.path.basename(eff_cond.reference_image_path) == target_fname:
                    usages.append({
                        "scenario_name": f"고유 s{scen.scenario_number} (실행 #{scen.step_number}) {scen.name}",
                        "type": "👁️ Eye 색상 조건",
                        "detail": f"시나리오 연결 조건 ({len(eff_cond.points)}개 포인트)"
                    })

            # Check scenario hand actions
            act_img = getattr(scen, "last_action_image_path", None)
            if not act_img and scen.actions:
                for act in scen.actions:
                    if getattr(act, "reference_image_path", None):
                        act_img = act.reference_image_path
                        break
            if act_img:
                act_abs = to_absolute_path(act_img)
                if (act_abs and os.path.normpath(act_abs) == norm_target) or os.path.basename(act_img) == target_fname:
                    usages.append({
                        "scenario_name": f"고유 s{scen.scenario_number} (실행 #{scen.step_number}) {scen.name}",
                        "type": "✋ Hand 액션",
                        "detail": f"시나리오 액션 좌표 지정 이미지"
                    })

        return usages

    def refresh_gallery(self, select_path: Optional[str] = None):
        self.image_entries = self.get_all_gallery_entries(self.project)

        # If a specific image was captured or imported, reset filters to show it
        if select_path and isinstance(select_path, str):
            if hasattr(self, "combo_filter"):
                self.combo_filter.blockSignals(True)
                self.combo_filter.setCurrentIndex(0)  # "all"
                self.combo_filter.blockSignals(False)
            if hasattr(self, "combo_resolution"):
                self.combo_resolution.blockSignals(True)
                self.combo_resolution.setCurrentIndex(0)  # "all"
                self.combo_resolution.blockSignals(False)

        # Update resolution classification options
        if hasattr(self, "combo_resolution"):
            cur_res = self.combo_resolution.currentData() or "all"
            self.combo_resolution.blockSignals(True)
            self.combo_resolution.clear()
            self.combo_resolution.addItem("📐 전체 해상도 보기", "all")

            res_counts = {}
            for e in self.image_entries:
                key = f"{e['width']}×{e['height']}"
                res_counts[key] = res_counts.get(key, 0) + 1

            target_win = WindowManager.get_window_info(self.target_hwnd) if self.target_hwnd else None
            target_res_key = f"{target_win.client_width}×{target_win.client_height}" if target_win and target_win.client_width > 0 else ""

            # Sort resolutions: target resolution first, then by count descending, then key
            sorted_keys = sorted(
                res_counts.keys(),
                key=lambda k: (k != target_res_key, -res_counts[k], k)
            )

            for res_key in sorted_keys:
                cnt = res_counts[res_key]
                target_tag = " [현재 타겟]" if res_key == target_res_key else ""
                self.combo_resolution.addItem(f"📐 {res_key}{target_tag} ({cnt}개)", res_key)

            idx = self.combo_resolution.findData(cur_res)
            if idx >= 0:
                self.combo_resolution.setCurrentIndex(idx)
            else:
                self.combo_resolution.setCurrentIndex(0)
            self.combo_resolution.blockSignals(False)

        self._apply_filter(select_path=select_path)

    def _apply_filter(self, select_path: Optional[str] = None):
        filter_mode = self.combo_filter.currentData() if hasattr(self, "combo_filter") and hasattr(self.combo_filter, "currentData") else "all"
        if not filter_mode:
            filter_mode = "all"

        res_mode = self.combo_resolution.currentData() if hasattr(self, "combo_resolution") and hasattr(self.combo_resolution, "currentData") else "all"
        if not res_mode:
            res_mode = "all"

        self.list_widget.clear()

        # Update header banner
        if hasattr(self, "lbl_res_banner"):
            target_win = WindowManager.get_window_info(self.target_hwnd) if self.target_hwnd else None
            target_res_key = f"{target_win.client_width}×{target_win.client_height}" if target_win and target_win.client_width > 0 else ""
            if res_mode == "all":
                self.lbl_res_banner.setText("📐 전체 해상도 이미지")
                self.lbl_res_banner.setStyleSheet("background-color: #f1f5f9; color: #475569; font-weight: bold; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px; border: 1px solid #cbd5e1;")
            else:
                is_target = (res_mode == target_res_key)
                tag = " (현재 타겟 창 해상도와 일치 ✅)" if is_target else ""
                self.lbl_res_banner.setText(f"📐 {res_mode} 분류{tag}")
                if is_target:
                    self.lbl_res_banner.setStyleSheet("background-color: #f0fdf4; color: #166534; font-weight: bold; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px; border: 1px solid #86efac;")
                else:
                    self.lbl_res_banner.setStyleSheet("background-color: #eff6ff; color: #1e40af; font-weight: bold; font-size: 8.5pt; padding: 4px 8px; border-radius: 4px; border: 1px solid #bfdbfe;")

        used_count = sum(1 for e in self.image_entries if e["is_used"])
        res_types_count = len({f"{e['width']}×{e['height']}" for e in self.image_entries})
        self.lbl_stats.setText(f"총 {len(self.image_entries)}개 이미지 ({used_count}개 사용 중, 해상도 {res_types_count}종류)")

        for entry in self.image_entries:
            if filter_mode == "used" and not entry["is_used"]:
                continue
            if filter_mode == "unused" and entry["is_used"]:
                continue

            entry_res = f"{entry['width']}×{entry['height']}"
            if res_mode != "all" and entry_res != res_mode:
                continue

            # Create Item with distinct resolution tag
            item = QListWidgetItem()
            status_tag = "🟢 사용 중" if entry["is_used"] else "⚪ 미사용"
            item.setText(
                f"[{entry['width']}×{entry['height']}] {entry['filename']}\n{status_tag} | {entry['size_kb']:.1f} KB"
            )
            item.setData(Qt.UserRole, entry)
            item.setToolTip(
                f"파일명: {entry['filename']}\n"
                f"디바이스 해상도: {entry['width']}×{entry['height']}\n"
                f"용량: {entry['size_kb']:.1f} KB\n"
                f"사용 현황: {'사용 중 (' + str(len(entry['usages'])) + '곳)' if entry['is_used'] else '미사용'}\n"
                f"경로: {entry['path']}"
            )

            # Thumbnail Icon
            try:
                with Image.open(entry["path"]) as im:
                    thumb = im.copy()
                    thumb.thumbnail((72, 48))
                    pix = pil_to_qpixmap(thumb)
                    item.setIcon(QIcon(pix))
            except Exception:
                pass

            self.list_widget.addItem(item)

        target_row = 0
        if select_path and isinstance(select_path, str):
            norm_target = os.path.normpath(os.path.abspath(select_path))
            for r in range(self.list_widget.count()):
                ent = self.list_widget.item(r).data(Qt.UserRole)
                if ent and os.path.normpath(os.path.abspath(ent["path"])) == norm_target:
                    target_row = r
                    break

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(target_row)
            item_to_scroll = self.list_widget.item(target_row)
            if item_to_scroll:
                self.list_widget.scrollToItem(item_to_scroll)
        else:
            self._clear_detail_view()

    def _on_item_selected(self, current: Optional[QListWidgetItem], previous=None):
        if not current:
            self._clear_detail_view()
            return
        entry = current.data(Qt.UserRole)
        if not entry:
            return

        # 1. Preview
        try:
            pix = QPixmap(entry["path"])
            scaled = pix.scaled(580, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_preview.setPixmap(scaled)
        except Exception:
            self.lbl_preview.setText("이미지를 미리볼 수 없습니다.")

        # 2. Metadata info with target resolution comparison
        status_str = f"🟢 사용 중 ({len(entry['usages'])}곳)" if entry["is_used"] else "⚪ 미사용"
        target_win = WindowManager.get_window_info(self.target_hwnd) if self.target_hwnd else None
        target_match_str = ""
        if target_win and target_win.client_width > 0:
            if entry["width"] == target_win.client_width and entry["height"] == target_win.client_height:
                target_match_str = " (현재 타겟 해상도와 일치 ✅)"
            else:
                target_match_str = f" (현재 타겟: {target_win.client_width}×{target_win.client_height} ⚠️ 해상도 다름)"

        self.lbl_info.setText(
            f"파일: {entry['filename']}\n"
            f"상태: {status_str} | 디바이스 해상도: {entry['width']} × {entry['height']}{target_match_str} | 용량: {entry['size_kb']:.1f} KB\n"
            f"경로: {entry['path']}"
        )

        # 3. Usages Table
        usages = entry["usages"]
        self.tbl_usages.setRowCount(len(usages))
        for r, u in enumerate(usages):
            it_scen = QTableWidgetItem(u["scenario_name"])
            it_type = QTableWidgetItem(u["type"])
            it_detail = QTableWidgetItem(u["detail"])
            self.tbl_usages.setItem(r, 0, it_scen)
            self.tbl_usages.setItem(r, 1, it_type)
            self.tbl_usages.setItem(r, 2, it_detail)

    def _clear_detail_view(self):
        self.lbl_preview.setPixmap(QPixmap())
        self.lbl_preview.setText("선택된 이미지가 없습니다.")
        self.lbl_info.setText("")
        self.tbl_usages.setRowCount(0)

    def _on_capture_current_window(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 없음", "타겟 게임 창이 선택되어 있지 않습니다.")
            return
        img = ScreenCapture.capture_client_area(self.target_hwnd)
        if not img:
            QMessageBox.warning(self, "캡처 실패", "타겟 창을 캡처할 수 없습니다.")
            return

        import datetime
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"capture_{now_str}.png"
        save_path = os.path.join(REFS_DIR, fname)
        if os.path.exists(save_path):
            idx = 1
            while os.path.exists(os.path.join(REFS_DIR, f"capture_{now_str}_{idx}.png")):
                idx += 1
            fname = f"capture_{now_str}_{idx}.png"
            save_path = os.path.join(REFS_DIR, fname)
        img.save(save_path, "PNG")
        self.refresh_gallery(select_path=save_path)
        QMessageBox.information(self, "캡처 완료", f"현재 게임창이 갤러리에 추가되었습니다:\n{fname}")

    def _on_import_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "레퍼런스 이미지 가져오기", "", "이미지 파일 (*.png *.jpg *.jpeg *.bmp)"
        )
        if path and os.path.exists(path):
            import shutil
            fname = os.path.basename(path)
            dest = os.path.join(REFS_DIR, fname)
            try:
                shutil.copyfile(path, dest)
                self.refresh_gallery(select_path=dest)
                QMessageBox.information(self, "가져오기 완료", f"이미지가 갤러리에 추가되었습니다:\n{fname}")
            except Exception as ex:
                QMessageBox.critical(self, "가져오기 오류", f"파일 복사 중 오류: {ex}")

    def _on_open_coord_picker(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        entry = item.data(Qt.UserRole)
        dlg = CoordinatePickerDialog(
            image_path=entry["path"],
            target_hwnd=self.target_hwnd,
            parent=self
        )
        dlg.exec_()

    def _on_delete_image(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        entry = item.data(Qt.UserRole)
        if entry["is_used"]:
            res = QMessageBox.warning(
                self, "사용 중인 이미지",
                f"'{entry['filename']}' 파일은 현재 {len(entry['usages'])}곳의 시나리오에서 사용 중입니다!\n"
                "정말로 삭제하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return
        else:
            res = QMessageBox.question(
                self, "삭제 확인",
                f"'{entry['filename']}' 이미지를 갤러리에서 삭제하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return

        try:
            if os.path.exists(entry["path"]):
                os.remove(entry["path"])
            self.refresh_gallery()
        except Exception as ex:
            QMessageBox.critical(self, "삭제 실패", f"파일 삭제 오류: {ex}")

    def _on_select_current_image(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "선택 필요", "선택된 이미지가 없습니다.")
            return
        entry = item.data(Qt.UserRole)
        if entry and os.path.exists(entry["path"]):
            self.selected_path = entry["path"]
            self.accept()

    def _on_item_double_clicked(self, item: QListWidgetItem):
        if not item:
            return
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        if self.picker_mode:
            self._on_select_current_image()
        else:
            self._on_open_coord_picker()

    def get_selected_image_path(self) -> Optional[str]:
        return self.selected_path


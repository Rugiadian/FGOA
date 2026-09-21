"""
Reference Image Gallery Dialog for FGOA.
Manages captured and imported reference images, tracking usage across
cognition conditions (Eye) and action coordinates (Hand).
"""
import os
import glob
from typing import List, Dict, Any, Optional
from PIL import Image, ImageQt
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
from ui.coordinate_picker_dialog import CoordinatePickerDialog


REFS_DIR = os.path.expanduser("~/.fgoa_refs")


class ReferenceGalleryDialog(QDialog):
    """
    Dialog for browsing, importing, capturing, and managing reference images,
    clearly indicating which scenarios (Eye conditions / Hand actions) use each image.
    """

    def __init__(self, project: Project, target_hwnd: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🖼️ 레퍼런스 갤러리 (참조 이미지 및 사용처 관리)")
        self.resize(1080, 720)

        self.project = project
        self.target_hwnd = target_hwnd
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

        tb_layout.addWidget(QLabel("필터:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItem("모든 이미지 보기", "all")
        self.combo_filter.addItem("🟢 사용 중인 이미지만", "used")
        self.combo_filter.addItem("⚪ 미사용 이미지만", "unused")
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        tb_layout.addWidget(self.combo_filter)

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

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(72, 48))
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
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
        """Collect all reference images and compute usage across scenarios."""
        paths = set()
        if os.path.isdir(REFS_DIR):
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
                for p in glob.glob(os.path.join(REFS_DIR, ext)):
                    paths.add(os.path.normpath(os.path.abspath(p)))

        for scen in project.scenarios:
            if scen.condition and scen.condition.reference_image_path:
                p = scen.condition.reference_image_path
                if os.path.exists(p):
                    paths.add(os.path.normpath(os.path.abspath(p)))

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
        """Computes list of scenario usages for this image."""
        usages = []
        norm_target = os.path.normpath(os.path.abspath(image_path))

        for scen in project.scenarios:
            # 1. Eye Condition Check
            if scen.condition and scen.condition.reference_image_path:
                cond_norm = os.path.normpath(os.path.abspath(scen.condition.reference_image_path))
                if cond_norm == norm_target:
                    pt_count = len(scen.condition.points)
                    usages.append({
                        "scenario_name": f"고유 #{scen.scenario_number} (실행 #{scen.step_number}) {scen.name}",
                        "type": "👁️ Eye 색상 조건",
                        "detail": f"기준 레퍼런스 (포인트 {pt_count}개 판정)"
                    })

            # 2. Hand Action Check (if scenario is bound to this reference)
            if scen.condition and scen.condition.reference_image_path:
                cond_norm = os.path.normpath(os.path.abspath(scen.condition.reference_image_path))
                if cond_norm == norm_target and scen.actions:
                    usages.append({
                        "scenario_name": f"고유 #{scen.scenario_number} (실행 #{scen.step_number}) {scen.name}",
                        "type": "✋ Hand 액션",
                        "detail": f"액션 좌표 기준 이미지 ({len(scen.actions)}개 액션)"
                    })

        return usages

    def refresh_gallery(self):
        self.image_entries = self.get_all_gallery_entries(self.project)
        self._apply_filter()

    def _apply_filter(self):
        filter_mode = self.combo_filter.currentData() if hasattr(self.combo_filter, "currentData") else "all"
        if not filter_mode:
            filter_mode = "all"

        self.list_widget.clear()

        used_count = sum(1 for e in self.image_entries if e["is_used"])
        self.lbl_stats.setText(f"총 {len(self.image_entries)}개 이미지 ({used_count}개 사용 중)")

        for entry in self.image_entries:
            if filter_mode == "used" and not entry["is_used"]:
                continue
            if filter_mode == "unused" and entry["is_used"]:
                continue

            # Create Item
            item = QListWidgetItem()
            status_tag = "🟢 사용 중" if entry["is_used"] else "⚪ 미사용"
            item.setText(
                f"{entry['filename']}\n{status_tag} | {entry['width']}×{entry['height']} ({entry['size_kb']:.1f} KB)"
            )
            item.setData(Qt.UserRole, entry)

            # Thumbnail Icon
            try:
                with Image.open(entry["path"]) as im:
                    thumb = im.copy()
                    thumb.thumbnail((72, 48))
                    qim = ImageQt.ImageQt(thumb)
                    pix = QPixmap.fromImage(qim)
                    item.setIcon(QIcon(pix))
            except Exception:
                pass

            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
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

        # 2. Metadata info
        status_str = f"🟢 사용 중 ({len(entry['usages'])}곳)" if entry["is_used"] else "⚪ 미사용"
        self.lbl_info.setText(
            f"파일: {entry['filename']}\n"
            f"상태: {status_str} | 해상도: {entry['width']} × {entry['height']} | 용량: {entry['size_kb']:.1f} KB\n"
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

        import uuid
        fname = f"capture_{uuid.uuid4().hex[:8]}.png"
        save_path = os.path.join(REFS_DIR, fname)
        img.save(save_path, "PNG")
        self.refresh_gallery()
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
                self.refresh_gallery()
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

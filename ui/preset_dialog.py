"""
Dialogs for Scenario Preset management:
1. SavePresetDialog: Saves selected scenarios as a new preset.
2. PresetManagerDialog: Browse, preview, search, import/export, and load presets into scenario sequence.
"""
import os
import shutil
from typing import List, Dict, Any, Optional
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QRadioButton, QButtonGroup, QMessageBox, QFileDialog,
    QSplitter, QFrame, QCheckBox, QAbstractItemView, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from core.models import Scenario
from core.preset_manager import PresetManager


class SavePresetDialog(QDialog):
    """
    Dialog to save selected scenarios as a new preset.
    """
    def __init__(self, selected_scenarios: List[Scenario], parent=None):
        super().__init__(parent)
        self.setWindowTitle("💾 시나리오 프리셋 저장")
        self.resize(560, 480)
        self.selected_scenarios = selected_scenarios
        self.saved_filepath: Optional[str] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Title
        lbl_title = QLabel("📦 선택한 시나리오를 프리셋으로 저장")
        lbl_title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #2563eb;")
        layout.addWidget(lbl_title)

        # Form: Name
        layout.addWidget(QLabel("프리셋 이름 *:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("예: 3턴 연속 스킬 및 보구 발동 루프")
        layout.addWidget(self.txt_name)

        # Form: Description
        layout.addWidget(QLabel("프리셋 설명 (선택 사항):"))
        self.txt_desc = QTextEdit()
        self.txt_desc.setMaximumHeight(60)
        self.txt_desc.setPlaceholderText("이 프리셋의 용도, 시작 조건, 필요 레퍼런스 등을 기록하세요.")
        layout.addWidget(self.txt_desc)

        # Included Scenarios Preview Table
        layout.addWidget(QLabel(f"포함될 시나리오 목록 ({len(self.selected_scenarios)}건 선택됨):"))
        self.tbl_scenarios = QTableWidget()
        self.tbl_scenarios.setColumnCount(4)
        self.tbl_scenarios.setHorizontalHeaderLabels(["선택", "순서", "시나리오 이름", "액션 수"])
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_scenarios.resizeSection(0, 45)
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tbl_scenarios.resizeSection(1, 45)
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.tbl_scenarios.resizeSection(3, 70)
        self.tbl_scenarios.verticalHeader().setDefaultSectionSize(26)
        self.tbl_scenarios.setSelectionBehavior(QAbstractItemView.SelectRows)

        self._populate_table()
        layout.addWidget(self.tbl_scenarios, 1)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 프리셋 저장")
        btn_save.setObjectName("btn_primary")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

        # Default focus
        self.txt_name.setFocus()

    def _populate_table(self):
        self.tbl_scenarios.setRowCount(len(self.selected_scenarios))
        self.checkboxes: List[QCheckBox] = []
        for r, scen in enumerate(self.selected_scenarios):
            chk = QCheckBox()
            chk.setChecked(True)
            self.checkboxes.append(chk)
            # Center checkbox in cell
            cell_widget = QWidget()
            w_layout = QHBoxLayout(cell_widget)
            w_layout.addWidget(chk)
            w_layout.setAlignment(Qt.AlignCenter)
            w_layout.setContentsMargins(0, 0, 0, 0)
            self.tbl_scenarios.setCellWidget(r, 0, cell_widget)

            it_order = QTableWidgetItem(str(r + 1))
            it_order.setTextAlignment(Qt.AlignCenter)
            self.tbl_scenarios.setItem(r, 1, it_order)

            it_name = QTableWidgetItem(scen.name)
            self.tbl_scenarios.setItem(r, 2, it_name)

            act_cnt = len(scen.actions) if scen.actions else 0
            it_act = QTableWidgetItem(f"{act_cnt}개")
            it_act.setTextAlignment(Qt.AlignCenter)
            self.tbl_scenarios.setItem(r, 3, it_act)

    def _on_save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "입력 오류", "프리셋 이름을 입력해주세요.")
            self.txt_name.setFocus()
            return

        # Filter checked scenarios
        scenarios_to_save = [
            scen for i, scen in enumerate(self.selected_scenarios)
            if i < len(self.checkboxes) and self.checkboxes[i].isChecked()
        ]

        if not scenarios_to_save:
            QMessageBox.warning(self, "선택 오류", "프리셋에 포함할 시나리오를 1개 이상 선택해주세요.")
            return

        desc = self.txt_desc.toPlainText().strip()
        try:
            self.saved_filepath = PresetManager.save_preset(name, scenarios_to_save, desc)
            QMessageBox.information(
                self, "저장 완료",
                f"프리셋 '{name}'이(가) 성공적으로 저장되었습니다!\n(시나리오 {len(scenarios_to_save)}건 포함)"
            )
            self.accept()
        except Exception as ex:
            QMessageBox.critical(self, "저장 실패", f"프리셋 저장 중 오류 발생:\n{ex}")


class PresetManagerDialog(QDialog):
    """
    Dialog for browsing, previewing, managing, and loading scenario presets into project.
    """
    sig_scenarios_imported = pyqtSignal(list, str)  # (List[Scenario], insertion_mode: "after_selected" / "append" / "replace")

    def __init__(self, current_selection_index: int = -1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 시나리오 프리셋 보관함 및 불러오기")
        self.resize(920, 620)
        self.current_selection_index = current_selection_index
        self.loaded_scenarios: List[Scenario] = []
        self.insertion_mode: str = "after_selected" if current_selection_index >= 0 else "append"
        self.preset_list: List[Dict[str, Any]] = []
        self.current_preset_data: Optional[Dict[str, Any]] = None

        self._init_ui()
        self._load_presets()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Top Header Bar
        top_bar = QHBoxLayout()
        lbl_head = QLabel("📦 시나리오 프리셋 라이브러리")
        lbl_head.setStyleSheet("font-size: 11pt; font-weight: bold; color: #2563eb;")
        top_bar.addWidget(lbl_head)
        top_bar.addStretch()

        btn_import_file = QPushButton("📂 외부 프리셋 파일 열기...")
        btn_import_file.setToolTip("컴퓨터에 저장된 .json 프리셋 파일을 보관함에 추가합니다.")
        btn_import_file.clicked.connect(self._on_import_external_file)
        top_bar.addWidget(btn_import_file)

        main_layout.addLayout(top_bar)

        # 2-Pane Splitter (Left: Preset List | Right: Preset Details & Scenarios Preview)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("preset_splitter")

        # ==========================================
        # Left Pane: Preset List with Search
        # ==========================================
        left_frame = QFrame()
        left_frame.setObjectName("card_frame")
        l_layout = QVBoxLayout(left_frame)
        l_layout.setContentsMargins(8, 8, 8, 8)
        l_layout.setSpacing(6)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 프리셋 검색...")
        self.txt_search.textChanged.connect(self._filter_presets)
        l_layout.addWidget(self.txt_search)

        self.list_presets = QListWidget()
        self.list_presets.setAlternatingRowColors(True)
        self.list_presets.currentItemChanged.connect(self._on_preset_selected)
        l_layout.addWidget(self.list_presets, 1)

        # Left bottom buttons
        l_btns = QHBoxLayout()
        btn_export = QPushButton("📤 파일로 내보내기")
        btn_export.clicked.connect(self._on_export_preset)
        l_btns.addWidget(btn_export)

        btn_delete = QPushButton("🗑️ 삭제")
        btn_delete.clicked.connect(self._on_delete_preset)
        l_btns.addWidget(btn_delete)
        l_layout.addLayout(l_btns)

        splitter.addWidget(left_frame)

        # ==========================================
        # Right Pane: Preset Details, Scenario Checklist & Load Options
        # ==========================================
        right_frame = QFrame()
        right_frame.setObjectName("card_frame")
        r_layout = QVBoxLayout(right_frame)
        r_layout.setContentsMargins(10, 10, 10, 10)
        r_layout.setSpacing(8)

        # Metadata info box
        self.lbl_preset_title = QLabel("프리셋을 선택하세요")
        self.lbl_preset_title.setStyleSheet("font-size: 11pt; font-weight: bold;")
        r_layout.addWidget(self.lbl_preset_title)

        self.lbl_preset_desc = QLabel("")
        self.lbl_preset_desc.setStyleSheet("color: #64748b; font-size: 9pt;")
        self.lbl_preset_desc.setWordWrap(True)
        r_layout.addWidget(self.lbl_preset_desc)

        # Table of scenarios inside the preset
        table_hdr = QHBoxLayout()
        table_hdr.addWidget(QLabel("포함된 시나리오 목록:"))
        table_hdr.addStretch()

        btn_select_all = QPushButton("전체 선택")
        btn_select_all.setFixedHeight(22)
        btn_select_all.clicked.connect(lambda: self._set_all_checkboxes(True))
        table_hdr.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("전체 해제")
        btn_deselect_all.setFixedHeight(22)
        btn_deselect_all.clicked.connect(lambda: self._set_all_checkboxes(False))
        table_hdr.addWidget(btn_deselect_all)
        r_layout.addLayout(table_hdr)

        self.tbl_preview = QTableWidget()
        self.tbl_preview.setColumnCount(5)
        self.tbl_preview.setHorizontalHeaderLabels(["선택", "순서", "시나리오 명", "인식 조건", "액션"])
        p_hdr = self.tbl_preview.horizontalHeader()
        p_hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        p_hdr.resizeSection(0, 42)
        p_hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        p_hdr.resizeSection(1, 42)
        p_hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        p_hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        p_hdr.resizeSection(3, 140)
        p_hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        p_hdr.resizeSection(4, 110)
        self.tbl_preview.verticalHeader().setDefaultSectionSize(26)
        self.tbl_preview.setSelectionBehavior(QAbstractItemView.SelectRows)
        r_layout.addWidget(self.tbl_preview, 1)

        # Import Mode Frame
        mode_box = QFrame()
        mode_box.setStyleSheet("background-color: rgba(37, 99, 235, 0.05); border-radius: 6px; padding: 4px;")
        m_layout = QHBoxLayout(mode_box)
        m_layout.setContentsMargins(6, 4, 6, 4)
        m_layout.addWidget(QLabel("<b>불러오기 위치:</b>"))

        self.radio_group = QButtonGroup(self)
        self.rb_after_selected = QRadioButton("현재 선택 항목 뒤에 삽입")
        self.rb_append = QRadioButton("목록 맨 끝에 추가")
        self.rb_replace = QRadioButton("기존 시나리오 전체 교체")

        self.radio_group.addButton(self.rb_after_selected, 0)
        self.radio_group.addButton(self.rb_append, 1)
        self.radio_group.addButton(self.rb_replace, 2)

        if self.current_selection_index >= 0:
            self.rb_after_selected.setChecked(True)
        else:
            self.rb_append.setChecked(True)
            self.rb_after_selected.setEnabled(False)

        m_layout.addWidget(self.rb_after_selected)
        m_layout.addWidget(self.rb_append)
        m_layout.addWidget(self.rb_replace)
        m_layout.addStretch()
        r_layout.addWidget(mode_box)

        # Action Buttons
        act_layout = QHBoxLayout()
        act_layout.addStretch()

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.reject)
        act_layout.addWidget(btn_close)

        self.btn_load = QPushButton("📥 시나리오에 불러오기")
        self.btn_load.setObjectName("btn_primary")
        self.btn_load.setEnabled(False)
        self.btn_load.clicked.connect(self._on_load_preset)
        act_layout.addWidget(self.btn_load)

        r_layout.addLayout(act_layout)

        splitter.addWidget(right_frame)
        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 65)
        splitter.setSizes([310, 580])

        main_layout.addWidget(splitter, 1)

    def _load_presets(self):
        self.preset_list = PresetManager.list_presets()
        self._filter_presets()
        if self.list_presets.count() > 0:
            self.list_presets.setCurrentRow(0)

    def _filter_presets(self):
        query = self.txt_search.text().strip().lower()
        self.list_presets.clear()

        for p in self.preset_list:
            name = p.get("name", "이름 없음")
            desc = p.get("description", "")
            if query and (query not in name.lower() and query not in desc.lower()):
                continue

            item = QListWidgetItem()
            count = p.get("scenario_count", len(p.get("scenarios", [])))
            builtin_badge = " [기본]" if p.get("is_builtin", False) else ""
            item.setText(f"{name}{builtin_badge} ({count}개)")
            item.setData(Qt.UserRole, p)
            self.list_presets.addItem(item)

    def _on_preset_selected(self, current: Optional[QListWidgetItem], previous=None):
        if not current:
            self.current_preset_data = None
            self.lbl_preset_title.setText("프리셋을 선택하세요")
            self.lbl_preset_desc.setText("")
            self.tbl_preview.setRowCount(0)
            self.btn_load.setEnabled(False)
            return

        p = current.data(Qt.UserRole)
        self.current_preset_data = p
        self.btn_load.setEnabled(True)

        name = p.get("name", "")
        desc = p.get("description", "")
        created = p.get("created_at", "")
        count = p.get("scenario_count", len(p.get("scenarios", [])))

        self.lbl_preset_title.setText(f"📦 {name} (총 {count}개 시나리오)")
        self.lbl_preset_desc.setText(f"설명: {desc or '(설명 없음)'} | 생성: {created}")

        # Populate preview table
        scenarios_dict = p.get("scenarios", [])
        self.tbl_preview.setRowCount(len(scenarios_dict))
        self.preview_checkboxes: List[QCheckBox] = []

        for r, s_dict in enumerate(scenarios_dict):
            chk = QCheckBox()
            chk.setChecked(True)
            self.preview_checkboxes.append(chk)

            cw = QWidget()
            cw_l = QHBoxLayout(cw)
            cw_l.addWidget(chk)
            cw_l.setAlignment(Qt.AlignCenter)
            cw_l.setContentsMargins(0, 0, 0, 0)
            self.tbl_preview.setCellWidget(r, 0, cw)

            it_idx = QTableWidgetItem(str(r + 1))
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.tbl_preview.setItem(r, 1, it_idx)

            it_name = QTableWidgetItem(s_dict.get("name", "시나리오"))
            self.tbl_preview.setItem(r, 2, it_name)

            # Condition summary
            cond = s_dict.get("condition")
            if cond and cond.get("points"):
                cond_text = f"포인트 {len(cond['points'])}개 ({cond.get('logic_operator', 'AND')})"
            elif s_dict.get("node_type") == "loop_start":
                cond_text = f"루프 시작 ({s_dict.get('loop_count', 5)}회)"
            elif s_dict.get("node_type") == "loop_end":
                cond_text = "루프 종료"
            else:
                cond_text = "무조건 실행"
            it_cond = QTableWidgetItem(cond_text)
            self.tbl_preview.setItem(r, 3, it_cond)

            # Actions summary
            acts = s_dict.get("actions", [])
            act_text = f"{len(acts)}개 액션" if acts else "(없음)"
            it_act = QTableWidgetItem(act_text)
            self.tbl_preview.setItem(r, 4, it_act)

    def _set_all_checkboxes(self, checked: bool):
        if hasattr(self, "preview_checkboxes"):
            for chk in self.preview_checkboxes:
                chk.setChecked(checked)

    def _on_load_preset(self):
        if not self.current_preset_data:
            return

        selected_indices = [
            i for i, chk in enumerate(self.preview_checkboxes)
            if chk.isChecked()
        ]

        if not selected_indices:
            QMessageBox.warning(self, "선택 오류", "불러올 시나리오를 1개 이상 체크해주세요.")
            return

        # Instantiate scenarios with unique IDs and remapped targets
        scenarios = PresetManager.instantiate_preset_scenarios(
            self.current_preset_data,
            selected_indices=selected_indices
        )

        if not scenarios:
            QMessageBox.warning(self, "오류", "선택된 시나리오를 인스턴스화할 수 없습니다.")
            return

        # Determine insertion mode
        if self.rb_replace.isChecked():
            mode = "replace"
        elif self.rb_after_selected.isChecked():
            mode = "after_selected"
        else:
            mode = "append"

        self.loaded_scenarios = scenarios
        self.insertion_mode = mode
        self.sig_scenarios_imported.emit(scenarios, mode)
        self.accept()

    def _on_export_preset(self):
        if not self.current_preset_data:
            QMessageBox.warning(self, "선택 필요", "내보낼 프리셋을 먼저 목록에서 선택해주세요.")
            return

        src_path = self.current_preset_data.get("filepath")
        if not src_path or not os.path.exists(src_path):
            QMessageBox.warning(self, "오류", "프리셋 원본 파일을 찾을 수 없습니다.")
            return

        def_name = f"{self.current_preset_data.get('name', 'preset')}.json"
        dst_path, _ = QFileDialog.getSaveFileName(
            self, "프리셋 파일로 내보내기", def_name, "JSON Files (*.json)"
        )
        if dst_path:
            try:
                shutil.copyfile(src_path, dst_path)
                QMessageBox.information(self, "내보내기 완료", f"프리셋이 내보내졌습니다:\n{dst_path}")
            except Exception as ex:
                QMessageBox.critical(self, "내보내기 실패", f"오류 발생: {ex}")

    def _on_import_external_file(self):
        src_path, _ = QFileDialog.getOpenFileName(
            self, "외부 프리셋 파일 가져오기", "", "JSON Files (*.json)"
        )
        if not src_path:
            return

        try:
            data = PresetManager.load_preset_file(src_path)
            if "scenarios" not in data:
                QMessageBox.warning(self, "형식 오류", "유효한 FGOA 프리셋 파일이 아닙니다 ('scenarios' 항목 누락).")
                return

            # Save into presets directory
            name = data.get("name", os.path.splitext(os.path.basename(src_path))[0])
            desc = data.get("description", "")
            scenarios = [Scenario.from_dict(s) for s in data.get("scenarios", [])]
            PresetManager.save_preset(name, scenarios, desc)

            self._load_presets()
            QMessageBox.information(self, "가져오기 완료", f"프리셋 '{name}'이(가) 보관함에 추가되었습니다.")
        except Exception as ex:
            QMessageBox.critical(self, "가져오기 실패", f"파일을 불러오는 중 오류 발생:\n{ex}")

    def _on_delete_preset(self):
        if not self.current_preset_data:
            QMessageBox.warning(self, "선택 필요", "삭제할 프리셋을 선택해주세요.")
            return

        if self.current_preset_data.get("is_builtin", False):
            QMessageBox.warning(self, "삭제 불가", "기본 제공 프리셋은 삭제할 수 없습니다.")
            return

        name = self.current_preset_data.get("name", "")
        filepath = self.current_preset_data.get("filepath", "")

        res = QMessageBox.question(
            self, "프리셋 삭제",
            f"프리셋 '{name}'을(를) 보관함에서 영구 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            try:
                PresetManager.delete_preset(filepath)
                self._load_presets()
                QMessageBox.information(self, "삭제 완료", f"프리셋 '{name}'이(가) 삭제되었습니다.")
            except Exception as ex:
                QMessageBox.critical(self, "삭제 실패", f"삭제 오류: {ex}")

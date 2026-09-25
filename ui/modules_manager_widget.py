"""
Modules Manager Widget for FGOA.
Displays and manages all registered Condition modules and ActionSequence modules
in a dedicated tab next to the scenario flow list.
"""
import copy
from typing import Optional, List, Dict, Any
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QMessageBox, QInputDialog, QFrame, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from core.models import Project, Condition, ActionSequence
from core.path_utils import to_absolute_path


class ModulesManagerWidget(QWidget):
    """
    Manages modular Condition and ActionSequence building blocks.
    Allows creating, cloning, editing, and deleting modules,
    and shows which scenarios each module is assembled into.
    """
    sig_module_changed = pyqtSignal()
    sig_log = pyqtSignal(str, str)

    def __init__(self, project: Project, target_hwnd: int = 0, parent=None):
        super().__init__(parent)
        self.project = project
        self.target_hwnd = target_hwnd
        self._init_ui()
        self.refresh_modules()

    def set_project(self, project: Project, target_hwnd: int = 0):
        self.project = project
        self.target_hwnd = target_hwnd
        self.refresh_modules()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)

        # -------------------------------------------------------------
        # Upper Section: Condition Modules (인식조건 모듈)
        # -------------------------------------------------------------
        cond_frame = QFrame()
        cond_frame.setObjectName("card_frame")
        cf_layout = QVBoxLayout(cond_frame)
        cf_layout.setContentsMargins(6, 6, 6, 6)
        cf_layout.setSpacing(4)

        cond_header = QHBoxLayout()
        lbl_cond_title = QLabel("👁️ 인식조건 모듈 목록 (Conditions)")
        lbl_cond_title.setStyleSheet("font-weight: bold; font-size: 9pt; color: #2563eb;")
        cond_header.addWidget(lbl_cond_title)
        cond_header.addStretch()

        btn_add_cond = QPushButton("➕ 새 조건")
        btn_add_cond.clicked.connect(self._on_add_condition)
        cond_header.addWidget(btn_add_cond)

        btn_dup_cond = QPushButton("📋 복제")
        btn_dup_cond.clicked.connect(self._on_duplicate_condition)
        cond_header.addWidget(btn_dup_cond)

        btn_edit_cond = QPushButton("🎯 편집")
        btn_edit_cond.clicked.connect(self._on_edit_condition)
        cond_header.addWidget(btn_edit_cond)

        btn_del_cond = QPushButton("🗑️ 삭제")
        btn_del_cond.setStyleSheet("color: #ef4444;")
        btn_del_cond.clicked.connect(self._on_delete_condition)
        cond_header.addWidget(btn_del_cond)

        cf_layout.addLayout(cond_header)

        self.tbl_conditions = QTableWidget()
        self.tbl_conditions.setColumnCount(6)
        self.tbl_conditions.setHorizontalHeaderLabels([
            "번호", "이름", "포인트", "로직", "기본 액션 연결", "사용 시나리오"
        ])
        hdr_c = self.tbl_conditions.horizontalHeader()
        hdr_c.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_conditions.setColumnWidth(0, 42)
        hdr_c.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr_c.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr_c.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr_c.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr_c.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.tbl_conditions.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_conditions.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_conditions.itemDoubleClicked.connect(self._on_edit_condition)
        cf_layout.addWidget(self.tbl_conditions)

        splitter.addWidget(cond_frame)

        # -------------------------------------------------------------
        # Lower Section: Action Sequence Modules (액션시퀀스 모듈)
        # -------------------------------------------------------------
        seq_frame = QFrame()
        seq_frame.setObjectName("card_frame")
        sf_layout = QVBoxLayout(seq_frame)
        sf_layout.setContentsMargins(6, 6, 6, 6)
        sf_layout.setSpacing(4)

        seq_header = QHBoxLayout()
        lbl_seq_title = QLabel("✋ 액션시퀀스 모듈 목록 (Action Sequences)")
        lbl_seq_title.setStyleSheet("font-weight: bold; font-size: 9pt; color: #16a34a;")
        seq_header.addWidget(lbl_seq_title)
        seq_header.addStretch()

        btn_add_seq = QPushButton("➕ 새 시퀀스")
        btn_add_seq.clicked.connect(self._on_add_sequence)
        seq_header.addWidget(btn_add_seq)

        btn_dup_seq = QPushButton("📋 복제")
        btn_dup_seq.clicked.connect(self._on_duplicate_sequence)
        seq_header.addWidget(btn_dup_seq)

        btn_edit_seq = QPushButton("🎯 편집")
        btn_edit_seq.clicked.connect(self._on_edit_sequence)
        seq_header.addWidget(btn_edit_seq)

        btn_del_seq = QPushButton("🗑️ 삭제")
        btn_del_seq.setStyleSheet("color: #ef4444;")
        btn_del_seq.clicked.connect(self._on_delete_sequence)
        seq_header.addWidget(btn_del_seq)

        sf_layout.addLayout(seq_header)

        self.tbl_sequences = QTableWidget()
        self.tbl_sequences.setColumnCount(5)
        self.tbl_sequences.setHorizontalHeaderLabels([
            "번호", "제목", "액션 수", "동작 요약", "사용 시나리오"
        ])
        hdr_s = self.tbl_sequences.horizontalHeader()
        hdr_s.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_sequences.setColumnWidth(0, 42)
        hdr_s.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr_s.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr_s.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr_s.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tbl_sequences.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_sequences.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_sequences.itemDoubleClicked.connect(self._on_edit_sequence)
        sf_layout.addWidget(self.tbl_sequences)

        self.table_conditions = self.tbl_conditions
        self.table_sequences = self.tbl_sequences

        splitter.addWidget(seq_frame)
        splitter.setSizes([300, 300])

        main_layout.addWidget(splitter)

    def refresh(self):
        """Alias for refresh_modules."""
        self.refresh_modules()

    def refresh_modules(self):
        """Refreshes both Condition and ActionSequence tables."""
        if not self.project:
            return

        # 1. Populate Conditions Table
        conds = getattr(self.project, "conditions", [])
        self.tbl_conditions.setRowCount(len(conds))

        for row, cond in enumerate(conds):
            c_num = getattr(cond, "condition_number", row + 1)
            it_num = QTableWidgetItem(f"C{c_num}")
            it_num.setTextAlignment(Qt.AlignCenter)
            it_num.setForeground(QColor("#2563eb"))
            f = it_num.font()
            f.setBold(True)
            it_num.setFont(f)
            self.tbl_conditions.setItem(row, 0, it_num)

            it_name = QTableWidgetItem(cond.name)
            self.tbl_conditions.setItem(row, 1, it_name)

            it_pts = QTableWidgetItem(f"{len(cond.points)}개")
            it_pts.setTextAlignment(Qt.AlignCenter)
            self.tbl_conditions.setItem(row, 2, it_pts)

            it_logic = QTableWidgetItem(cond.logic_operator)
            it_logic.setTextAlignment(Qt.AlignCenter)
            self.tbl_conditions.setItem(row, 3, it_logic)

            # Connected action sequence
            seq_target = self.project.find_action_sequence(cond.action_sequence_id) if cond.action_sequence_id else None
            if seq_target:
                s_num = getattr(seq_target, "sequence_number", "")
                seq_str = f"🔗 [A{s_num}] {seq_target.name}"
            else:
                seq_str = "-"
            it_seq = QTableWidgetItem(seq_str)
            it_seq.setTextAlignment(Qt.AlignCenter)
            self.tbl_conditions.setItem(row, 4, it_seq)

            # Scenarios using this condition
            used_scens = [s for s in self.project.scenarios if s.condition_id == cond.id]
            used_str = f"{len(used_scens)}곳" if used_scens else "미사용"
            it_used = QTableWidgetItem(used_str)
            it_used.setTextAlignment(Qt.AlignCenter)
            if used_scens:
                scen_names = ", ".join([f"s{s.scenario_number} [{s.name}]" for s in used_scens])
                it_used.setToolTip(f"사용처: {scen_names}")
                it_used.setForeground(QColor("#16a34a"))
            else:
                it_used.setForeground(QColor("#94a3b8"))
            self.tbl_conditions.setItem(row, 5, it_used)

        # 2. Populate Action Sequences Table
        seqs = getattr(self.project, "action_sequences", [])
        self.tbl_sequences.setRowCount(len(seqs))

        for row, seq in enumerate(seqs):
            s_num = getattr(seq, "sequence_number", row + 1)
            it_num = QTableWidgetItem(f"A{s_num}")
            it_num.setTextAlignment(Qt.AlignCenter)
            it_num.setForeground(QColor("#16a34a"))
            f = it_num.font()
            f.setBold(True)
            it_num.setFont(f)
            self.tbl_sequences.setItem(row, 0, it_num)

            it_name = QTableWidgetItem(seq.name)
            self.tbl_sequences.setItem(row, 1, it_name)

            it_cnt = QTableWidgetItem(f"{len(seq.actions)}개")
            it_cnt.setTextAlignment(Qt.AlignCenter)
            self.tbl_sequences.setItem(row, 2, it_cnt)

            it_sum = QTableWidgetItem(seq.get_summary())
            self.tbl_sequences.setItem(row, 3, it_sum)

            used_scens = [s for s in self.project.scenarios if s.sequence_id == seq.id]
            used_str = f"{len(used_scens)}곳" if used_scens else "미사용"
            it_used = QTableWidgetItem(used_str)
            it_used.setTextAlignment(Qt.AlignCenter)
            if used_scens:
                scen_names = ", ".join([f"s{s.scenario_number} [{s.name}]" for s in used_scens])
                it_used.setToolTip(f"사용처: {scen_names}")
                it_used.setForeground(QColor("#16a34a"))
            else:
                it_used.setForeground(QColor("#94a3b8"))
            self.tbl_sequences.setItem(row, 4, it_used)

    # -------------------------------------------------------------
    # Condition Operations
    # -------------------------------------------------------------
    def _on_add_condition(self):
        c_num = self.project.get_next_condition_number()
        name, ok = QInputDialog.getText(self, "새 인식조건 모듈", "인식조건 이름:", text=f"인식조건 {c_num}")
        if ok and name.strip():
            cond = Condition(
                condition_number=c_num,
                name=name.strip()
            )
            self.project.add_condition(cond)
            self.refresh_modules()
            self.sig_module_changed.emit()
            self.sig_log.emit("INFO", f"👁️ 새 인식조건 모듈 [C{c_num}] '{cond.name}'이(가) 등록되었습니다.")

    def _on_duplicate_condition(self):
        row = self.tbl_conditions.currentRow()
        conds = getattr(self.project, "conditions", [])
        if not (0 <= row < len(conds)):
            return
        orig = conds[row]
        cloned = copy.deepcopy(orig)
        import uuid
        cloned.id = f"cond_{uuid.uuid4().hex[:6]}"
        cloned.condition_number = self.project.get_next_condition_number()
        cloned.name = f"{cloned.name} (복제)"
        self.project.add_condition(cloned)
        self.refresh_modules()
        self.sig_module_changed.emit()
        self.sig_log.emit("INFO", f"📋 인식조건 모듈 [C{orig.condition_number}] ➔ [C{cloned.condition_number}] 복제 완료")

    def _on_edit_condition(self):
        row = self.tbl_conditions.currentRow()
        conds = getattr(self.project, "conditions", [])
        if not (0 <= row < len(conds)):
            return
        cond = conds[row]
        from ui.condition_editor_dialog import ConditionEditorDialog
        dlg = ConditionEditorDialog(
            condition=cond,
            project=self.project,
            target_hwnd=self.target_hwnd,
            parent=self
        )
        if dlg.exec_() == ConditionEditorDialog.Accepted:
            updated = dlg.get_condition()
            cond.points = updated.points
            cond.logic_operator = updated.logic_operator
            cond.reference_image_path = updated.reference_image_path
            self.refresh_modules()
            self.sig_module_changed.emit()

    def _on_delete_condition(self):
        row = self.tbl_conditions.currentRow()
        conds = getattr(self.project, "conditions", [])
        if not (0 <= row < len(conds)):
            return
        cond = conds[row]
        used = [s for s in self.project.scenarios if s.condition_id == cond.id]
        msg = f"인식조건 모듈 [C{cond.condition_number}] '{cond.name}'을(를) 삭제하시겠습니까?"
        if used:
            msg += f"\n(현재 {len(used)}곳의 시나리오에서 사용 중입니다. 연결이 안전하게 해제됩니다.)"
        res = QMessageBox.question(self, "조건 삭제", msg, QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.project.delete_condition(cond.id)
            self.refresh_modules()
            self.sig_module_changed.emit()
            self.sig_log.emit("WARN", f"🗑️ 인식조건 모듈 [C{cond.condition_number}] '{cond.name}' 삭제 완료")

    # -------------------------------------------------------------
    # Action Sequence Operations
    # -------------------------------------------------------------
    def _on_add_sequence(self):
        s_num = self.project.get_next_sequence_number()
        name, ok = QInputDialog.getText(self, "새 액션시퀀스 모듈", "액션시퀀스 제목:", text=f"시퀀스 {s_num}")
        if ok and name.strip():
            seq = ActionSequence(
                sequence_number=s_num,
                name=name.strip()
            )
            self.project.add_action_sequence(seq)
            self.refresh_modules()
            self.sig_module_changed.emit()
            self.sig_log.emit("INFO", f"✋ 새 액션시퀀스 모듈 [A{s_num}] '{seq.name}'이(가) 등록되었습니다.")

    def _on_duplicate_sequence(self):
        row = self.tbl_sequences.currentRow()
        seqs = getattr(self.project, "action_sequences", [])
        if not (0 <= row < len(seqs)):
            return
        orig = seqs[row]
        cloned = copy.deepcopy(orig)
        import uuid
        cloned.id = f"seq_{uuid.uuid4().hex[:6]}"
        cloned.sequence_number = self.project.get_next_sequence_number()
        cloned.name = f"{cloned.name} (복제)"
        self.project.add_action_sequence(cloned)
        self.refresh_modules()
        self.sig_module_changed.emit()
        self.sig_log.emit("INFO", f"📋 액션시퀀스 모듈 [A{orig.sequence_number}] ➔ [A{cloned.sequence_number}] 복제 완료")

    def _on_edit_sequence(self):
        row = self.tbl_sequences.currentRow()
        seqs = getattr(self.project, "action_sequences", [])
        if not (0 <= row < len(seqs)):
            return
        seq = seqs[row]
        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        ref_path = to_absolute_path(seq.last_action_image_path) if seq.last_action_image_path else None
        dlg = CoordinatePickerDialog(
            image_path=ref_path,
            target_hwnd=self.target_hwnd,
            actions=seq.actions,
            project=self.project,
            parent=self
        )
        if dlg.exec_() == CoordinatePickerDialog.Accepted:
            seq.actions = dlg.get_actions()
            if dlg.current_image_path:
                seq.last_action_image_path = dlg.current_image_path
            self.refresh_modules()
            self.sig_module_changed.emit()

    def _on_delete_sequence(self):
        row = self.tbl_sequences.currentRow()
        seqs = getattr(self.project, "action_sequences", [])
        if not (0 <= row < len(seqs)):
            return
        seq = seqs[row]
        used = [s for s in self.project.scenarios if s.sequence_id == seq.id]
        msg = f"액션시퀀스 모듈 [A{seq.sequence_number}] '{seq.name}'을(를) 삭제하시겠습니까?"
        if used:
            msg += f"\n(현재 {len(used)}곳의 시나리오에서 사용 중입니다. 연결이 안전하게 해제됩니다.)"
        res = QMessageBox.question(self, "시퀀스 삭제", msg, QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.project.delete_action_sequence(seq.id)
            self.refresh_modules()
            self.sig_module_changed.emit()
            self.sig_log.emit("WARN", f"🗑️ 액션시퀀스 모듈 [A{seq.sequence_number}] '{seq.name}' 삭제 완료")

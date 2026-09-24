"""
Action Sequence Manager Dialog for FGOA.
Allows managing registered ActionSequence modules (Create, Rename, Duplicate, Delete, Inspect).
"""
import copy
from typing import Optional, List
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QInputDialog, QAbstractItemView, QWidget
)
from PyQt5.QtCore import Qt
from core.models import Project, ActionSequence


class ActionSequenceManagerDialog(QDialog):
    """Dialog for managing reusable ActionSequence modules."""

    def __init__(self, project: Project, current_sequence_id: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.current_sequence_id = current_sequence_id
        self.selected_sequence_id: Optional[str] = current_sequence_id

        self.setWindowTitle("⚙️ 액션 시퀀스 모듈 관리 (Action Sequence Manager)")
        self.resize(750, 480)
        self.setMinimumSize(600, 360)

        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header Info
        lbl_info = QLabel(
            "<b>액션 시퀀스 모듈:</b> 자주 사용하는 액션들의 묶음을 모듈화하여 여러 시나리오에서 재사용할 수 있습니다.<br>"
            "<span style='color: #64748b; font-size: 8.5pt;'>"
            "• 액션: 클릭, 드래그, 키 입력 등 개별 조작 단위<br>"
            "• 액션 시퀀스: 여러 액션을 순서대로 모아둔 재사용 가능 묶음 (모듈)</span>"
        )
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        # Table of sequences
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "시퀀스 이름", "액션 수", "액션 요약", "연결된 시나리오"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(4, 130)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(lambda item: self._on_rename_sequence())
        layout.addWidget(self.table, 1)

        # Action Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_new = QPushButton("➕ 새 시퀀스 생성")
        self.btn_new.clicked.connect(self._on_new_sequence)
        btn_layout.addWidget(self.btn_new)

        self.btn_rename = QPushButton("✏️ 이름 변경")
        self.btn_rename.clicked.connect(self._on_rename_sequence)
        self.btn_rename.setEnabled(False)
        btn_layout.addWidget(self.btn_rename)

        self.btn_duplicate = QPushButton("📋 복제")
        self.btn_duplicate.clicked.connect(self._on_duplicate_sequence)
        self.btn_duplicate.setEnabled(False)
        btn_layout.addWidget(self.btn_duplicate)

        self.btn_delete = QPushButton("🗑️ 삭제")
        self.btn_delete.setStyleSheet("color: #dc2626;")
        self.btn_delete.clicked.connect(self._on_delete_sequence)
        self.btn_delete.setEnabled(False)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_select = QPushButton("🔗 이 시퀀스 선택")
        self.btn_select.setStyleSheet("font-weight: bold; color: #2563eb;")
        self.btn_select.clicked.connect(self._on_select_and_close)
        self.btn_select.setEnabled(False)
        btn_layout.addWidget(self.btn_select)

        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _get_selected_sequence(self) -> Optional[ActionSequence]:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.project.action_sequences):
            return None
        return self.project.action_sequences[row]

    def _on_selection_changed(self):
        seq = self._get_selected_sequence()
        has_sel = seq is not None
        self.btn_rename.setEnabled(has_sel)
        self.btn_duplicate.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_select.setEnabled(has_sel)
        if seq:
            self.selected_sequence_id = seq.id

    def _refresh_table(self):
        self.table.setRowCount(len(self.project.action_sequences))
        select_row = -1

        for row, seq in enumerate(self.project.action_sequences):
            if seq.id == self.current_sequence_id or seq.id == self.selected_sequence_id:
                select_row = row

            it_id = QTableWidgetItem(seq.id)
            it_id.setTextAlignment(Qt.AlignCenter)
            it_id.setFlags(it_id.flags() & ~Qt.ItemIsEditable)

            it_name = QTableWidgetItem(seq.name)
            it_name.setFlags(it_name.flags() & ~Qt.ItemIsEditable)

            it_cnt = QTableWidgetItem(f"{len(seq.actions)}개")
            it_cnt.setTextAlignment(Qt.AlignCenter)
            it_cnt.setFlags(it_cnt.flags() & ~Qt.ItemIsEditable)

            it_summary = QTableWidgetItem(seq.get_summary())
            it_summary.setFlags(it_summary.flags() & ~Qt.ItemIsEditable)

            # Find linked scenarios
            linked = [f"s{s.scenario_number}" for s in self.project.scenarios if getattr(s, "sequence_id", None) == seq.id]
            linked_str = ", ".join(linked) if linked else "-"
            it_linked = QTableWidgetItem(linked_str)
            it_linked.setTextAlignment(Qt.AlignCenter)
            it_linked.setFlags(it_linked.flags() & ~Qt.ItemIsEditable)

            self.table.setItem(row, 0, it_id)
            self.table.setItem(row, 1, it_name)
            self.table.setItem(row, 2, it_cnt)
            self.table.setItem(row, 3, it_summary)
            self.table.setItem(row, 4, it_linked)

        if select_row >= 0:
            self.table.selectRow(select_row)
        elif self.project.action_sequences:
            self.table.selectRow(0)

    def _on_new_sequence(self):
        name, ok = QInputDialog.getText(self, "새 액션 시퀀스 생성", "시퀀스 이름:", text="새 액션 시퀀스")
        if ok and name.strip():
            new_seq = ActionSequence(name=name.strip())
            self.project.add_action_sequence(new_seq)
            self.selected_sequence_id = new_seq.id
            self._refresh_table()

    def _on_rename_sequence(self):
        seq = self._get_selected_sequence()
        if not seq:
            return
        name, ok = QInputDialog.getText(self, "시퀀스 이름 변경", "새 시퀀스 이름:", text=seq.name)
        if ok and name.strip():
            seq.name = name.strip()
            self._refresh_table()

    def _on_duplicate_sequence(self):
        seq = self._get_selected_sequence()
        if not seq:
            return
        dup = copy.deepcopy(seq)
        import uuid
        dup.id = f"seq_{uuid.uuid4().hex[:6]}"
        dup.name = f"{seq.name} (복사본)"
        self.project.add_action_sequence(dup)
        self.selected_sequence_id = dup.id
        self._refresh_table()

    def _on_delete_sequence(self):
        seq = self._get_selected_sequence()
        if not seq:
            return
        linked = [s.name for s in self.project.scenarios if getattr(s, "sequence_id", None) == seq.id]
        warn_msg = f"'{seq.name}' 시퀀스를 정말 삭제하시겠습니까?"
        if linked:
            warn_msg += f"\n\n⚠️ 경고: 현재 {len(linked)}개 시나리오({', '.join(linked[:3])})에서 이 시퀀스를 사용 중입니다!\n삭제 시 해당 시나리오들의 시퀀스 연결이 해제됩니다."

        if QMessageBox.question(self, "시퀀스 삭제 확인", warn_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.project.delete_action_sequence(seq.id)
            self.selected_sequence_id = None
            self._refresh_table()

    def _on_select_and_close(self):
        seq = self._get_selected_sequence()
        if seq:
            self.selected_sequence_id = seq.id
            self.accept()

"""
Draggable Actions Table Widget and Action Column Delegate for FGOA Inspector.
(인스펙터 액션 목록 드래그 앤 드롭 테이블 및 인라인 컬럼 편집 델리게이트)
"""
from typing import Any, Optional

from PyQt5.QtWidgets import (
    QTableWidget, QStyledItemDelegate, QAbstractItemView,
    QApplication, QComboBox, QDoubleSpinBox, QLineEdit, QAbstractSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData
from PyQt5.QtGui import QDrag


class DraggableActionsTableWidget(QTableWidget):
    """QTableWidget supporting safe mouse drag-and-drop row reordering without item loss."""
    sig_row_reordered = pyqtSignal(int, int)  # (from_row, to_row)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self._drag_start_pos = None
        self._drag_start_row = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_row = self.rowAt(event.pos().y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            (event.buttons() & Qt.LeftButton)
            and self._drag_start_pos is not None
            and self._drag_start_row >= 0
        ):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData("application/x-fgoa-action-row", str(self._drag_start_row).encode("utf-8"))
                drag.setMimeData(mime)
                self._drag_start_pos = None
                drag.exec_(Qt.MoveAction)
                self._drag_start_row = -1
                return
            super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-action-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-action-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-action-row"):
            data_bytes = event.mimeData().data("application/x-fgoa-action-row").data()
            try:
                from_row = int(data_bytes.decode("utf-8"))
            except Exception:
                from_row = -1
            to_row = self.rowAt(event.pos().y())
            if to_row < 0:
                to_row = self.rowCount() - 1
            if to_row < 0:
                to_row = 0
            event.acceptProposedAction()
            if from_row != to_row and from_row >= 0 and to_row >= 0:
                self.sig_row_reordered.emit(from_row, to_row)
        else:
            event.ignore()


class ActionColumnDelegate(QStyledItemDelegate):
    """
    Delegate for Offset (Col 3), Delay (Col 4), and Log (Col 5) columns.
    Normally displays clean text (like Action Type column).
    Switches to inline editor on click, and reverts to clean text after editing.
    """
    def __init__(self, inspector: Any, parent=None):
        super().__init__(parent)
        self.inspector = inspector

    def createEditor(self, parent, option, index):
        col = index.column()
        row = index.row()
        act = self.inspector._get_action_at(row)
        if not act:
            return super().createEditor(parent, option, index)

        if col == 3:  # 오프셋
            if act.action_type in ("mouse_click", "mouse_drag"):
                combo = QComboBox(parent)
                combo.addItem("약", "weak")
                combo.addItem("강", "strong")
                combo.addItem("해제", "none")
                combo.setStyleSheet("font-size: 8.5pt;")
                return combo
            return None  # 비마우스 액션은 편집 불가

        elif col == 4:  # 대기 시간: 화살표 숨김 (NoButtons)
            spin = QDoubleSpinBox(parent)
            spin.setRange(0.0, 3600.0)
            spin.setDecimals(1)
            spin.setSingleStep(0.1)
            spin.setSuffix("s")
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setAlignment(Qt.AlignCenter)
            spin.setStyleSheet("font-size: 8.5pt;")
            return spin

        elif col == 5:  # 로그
            edit = QLineEdit(parent)
            edit.setPlaceholderText("로그 문구 (비워두면 꺼짐)")
            edit.setStyleSheet("font-size: 8.5pt; padding: 1px 3px;")
            return edit

        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        col = index.column()
        row = index.row()
        act = self.inspector._get_action_at(row)
        if not act:
            return

        if col == 3 and isinstance(editor, QComboBox):
            cur = getattr(act, "coord_anti_ban", "weak")
            idx = editor.findData(cur)
            editor.setCurrentIndex(idx if idx >= 0 else 0)

        elif col == 4 and isinstance(editor, QDoubleSpinBox):
            editor.setValue(act.delay_seconds)
            editor.selectAll()

        elif col == 5 and isinstance(editor, QLineEdit):
            cur_log = getattr(act, "custom_log", "")
            if not cur_log and act.action_type == "log_message":
                cur_log = getattr(act, "log_text", "")
            editor.setText(cur_log)
            editor.selectAll()

    def setModelData(self, editor, model, index):
        col = index.column()
        row = index.row()
        act = self.inspector._get_action_at(row)
        if not act:
            return

        if col == 3 and isinstance(editor, QComboBox):
            new_mode = editor.currentData()
            self.inspector._on_inline_offset_changed(act, new_mode)
            offset_map = {"weak": "약", "strong": "강", "none": "해제"}
            model.setData(index, offset_map.get(new_mode, "약"), Qt.DisplayRole)

        elif col == 4 and isinstance(editor, QDoubleSpinBox):
            new_delay = editor.value()
            self.inspector._on_inline_delay_changed(act, new_delay)
            model.setData(index, f"{new_delay:.1f}s" if new_delay > 0 else "-", Qt.DisplayRole)

        elif col == 5 and isinstance(editor, QLineEdit):
            new_log = editor.text().strip()
            self.inspector._on_inline_log_changed(act, new_log)
            model.setData(index, new_log if new_log else "-", Qt.DisplayRole)

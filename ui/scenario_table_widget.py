"""
Scenario Table Widget and Custom Vertical Header for FGOA.
(시나리오 목록 드래그 앤 드롭 테이블 및 실행 하이라이트 헤더)
"""
from PyQt5.QtWidgets import (
    QTableWidget, QHeaderView, QAbstractItemView, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData
from PyQt5.QtGui import QColor, QDrag


class ScenarioVerticalHeader(QHeaderView):
    """Custom vertical header that highlights the currently executing scenario row with distinct cell color."""

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.highlight_row: int = -1

    def set_highlight_row(self, row: int):
        if self.highlight_row != row:
            self.highlight_row = row
            self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex == self.highlight_row:
            painter.save()
            # Vivid emerald green background for currently running scenario node
            painter.fillRect(rect, QColor("#16a34a"))
            painter.setPen(QColor("#15803d"))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            # Bold white text
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            text = self.model().headerData(logicalIndex, Qt.Vertical, Qt.DisplayRole) if self.model() else ""
            if not text:
                text = str(logicalIndex + 1)
            painter.drawText(rect, Qt.AlignCenter, str(text))
            painter.restore()
        else:
            super().paintSection(painter, rect, logicalIndex)


class DraggableScenarioTableWidget(QTableWidget):
    """QTableWidget supporting safe mouse drag-and-drop scenario row reordering without item loss."""
    sig_row_reordered = pyqtSignal(int, int)  # (from_row, to_row)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._custom_v_header = ScenarioVerticalHeader(self)
        self.setVerticalHeader(self._custom_v_header)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.horizontalHeader().setMinimumSectionSize(20)
        self._drag_start_pos = None
        self._drag_start_row = -1

    def set_highlight_row(self, row: int):
        """Highlights the specified row in the vertical header."""
        self._custom_v_header.set_highlight_row(row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_column_widths()

    def adjust_column_widths(self):
        """Dynamically adjusts column widths in proportion to the table viewport width."""
        w = self.viewport().width()
        if w <= 0:
            return

        # Fixed-width compact columns:
        # 0: 스냅샷 (48px), 1: 고유 ID (s1, s2...) (48px), 2: 활성 (38px)
        fixed_sum = 48 + 48 + 38
        rem = max(320, w - fixed_sum)

        # Distribute remaining width proportionally:
        # 3: 시나리오 이름 (28%), 4: 인식조건 모듈 (26%), 5: 액션시퀀스 모듈 (26%), 6: 분기 (20%)
        w_name = max(80, int(rem * 0.28))
        w_cond = max(85, int(rem * 0.26))
        w_act = max(85, int(rem * 0.26))
        w_branch = max(65, rem - w_name - w_cond - w_act)

        header = self.horizontalHeader()
        header.resizeSection(0, 48)
        header.resizeSection(1, 48)
        header.resizeSection(2, 38)
        header.resizeSection(3, w_name)
        header.resizeSection(4, w_cond)
        header.resizeSection(5, w_act)
        header.resizeSection(6, w_branch)

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
                mime.setData("application/x-fgoa-scen-row", str(self._drag_start_row).encode("utf-8"))
                drag.setMimeData(mime)
                self._drag_start_pos = None
                drag.exec_(Qt.MoveAction)
                self._drag_start_row = -1
                return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-scen-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-scen-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-scen-row"):
            data_bytes = event.mimeData().data("application/x-fgoa-scen-row").data()
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

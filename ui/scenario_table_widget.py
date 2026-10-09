"""
Scenario Table Widget and Custom Vertical Header for FGOA.
(시나리오 목록 드래그 앤 드롭 테이블 및 실행 하이라이트 헤더)
"""
from PyQt5.QtWidgets import (
    QTableWidget, QHeaderView, QAbstractItemView, QApplication,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData
from PyQt5.QtGui import QColor, QDrag, QPainter


# Column index constants
COL_SNAPSHOT = 0
COL_ID = 1
COL_ENABLED = 2
COL_NAME = 3
COL_CONDITION = 4
COL_ACTION = 5
COL_BRANCH = 6

# Columns that can be toggled by the user: (col_index, display_label)
TOGGLEABLE_COLUMNS = [
    (COL_CONDITION, "인식조건 모듈"),
    (COL_ACTION, "액션시퀀스 모듈"),
    (COL_BRANCH, "분기"),
]


class ScenarioVerticalHeader(QHeaderView):
    """Custom vertical header that highlights the currently executing scenario row with distinct cell color."""

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.highlight_row: int = -1
        self.paused_row: int = -1

    def set_highlight_row(self, row: int):
        if self.highlight_row != row:
            self.highlight_row = row
            self.viewport().update()

    def set_paused_row(self, row: int):
        if self.paused_row != row:
            self.paused_row = row
            self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex == self.paused_row:
            painter.save()
            # Vibrant amber/orange background for paused scenario node
            painter.fillRect(rect, QColor("#ea580c"))
            painter.setPen(QColor("#c2410c"))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            # Bold white text with pause icon
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            text = self.model().headerData(logicalIndex, Qt.Vertical, Qt.DisplayRole) if self.model() else ""
            if not text:
                text = str(logicalIndex + 1)
            painter.drawText(rect, Qt.AlignCenter, f"⏸ {text}")
            painter.restore()
        elif logicalIndex == self.highlight_row:
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


class ScenarioItemDelegate(QStyledItemDelegate):
    """Custom item delegate to maintain visible disabled gray text even when a row is selected."""

    def __init__(self, table):
        super().__init__(table)
        self.table = table

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()

        is_disabled = index.data(Qt.UserRole + 99)
        if is_disabled and (opt.state & QStyle.State_Selected):
            # 1. Draw base selection background without text
            text = opt.text
            opt.text = ''
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
            opt.text = text

            # 2. Draw text with clear gray contrast over selection color:
            # - Light theme selection (#dbeafe): #64748b (Slate-500: strong contrast, clearly gray)
            # - Dark theme selection (#294066): #94a3b8 (Slate-400: clear visible muted gray)
            theme = getattr(self.table, "current_theme", "light")
            disabled_sel_color = QColor("#64748b" if theme == "light" else "#94a3b8")

            painter.save()
            painter.setFont(opt.font)
            painter.setPen(disabled_sel_color)
            rect = option.rect.adjusted(4, 0, -4, 0)
            painter.drawText(rect, int(opt.displayAlignment | Qt.AlignVCenter), opt.text)
            painter.restore()
        else:
            super().paint(painter, option, index)


class DraggableScenarioTableWidget(QTableWidget):
    """QTableWidget supporting safe mouse drag-and-drop scenario row reordering without item loss."""
    sig_row_reordered = pyqtSignal(int, int)  # (from_row, to_row)
    sig_delete_requested = pyqtSignal()
    sig_column_visibility_changed = pyqtSignal(int, bool)  # (col_idx, is_visible)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_theme = "light"
        self._custom_v_header = ScenarioVerticalHeader(self)
        self.setVerticalHeader(self._custom_v_header)
        self.setItemDelegate(ScenarioItemDelegate(self))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.horizontalHeader().setMinimumSectionSize(20)
        self._drag_start_pos = None
        self._drag_start_row = -1
        self._user_column_widths = {}
        self._is_adjusting_widths = False
        self.horizontalHeader().sectionResized.connect(self._on_section_resized)

        # Horizontal header context menu for column visibility
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)

    def _on_section_resized(self, logicalIndex: int, oldSize: int, newSize: int):
        if not self._is_adjusting_widths:
            self._user_column_widths[logicalIndex] = newSize

    def _on_header_context_menu(self, pos):
        """Shows column visibility context menu when right-clicking the horizontal header."""
        menu = self.create_column_visibility_menu(self)
        menu.exec_(self.horizontalHeader().viewport().mapToGlobal(pos))

    def create_column_visibility_menu(self, parent=None, title: str = "👁️ 열 표시 / 숨기기") -> QMenu:
        """Creates a QMenu with checkable actions to toggle scenario table columns."""
        menu = QMenu(title, parent or self)
        actions_by_col = {}

        for col_idx, col_name in TOGGLEABLE_COLUMNS:
            action = QAction(col_name, menu)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(col_idx))
            action.setData(col_idx)
            action.toggled.connect(lambda checked, c=col_idx: self.set_column_visible(c, checked))
            menu.addAction(action)
            actions_by_col[col_idx] = action

        menu.addSeparator()
        act_show_all = QAction("👁️ 모든 열 표시", menu)
        act_show_all.triggered.connect(self.show_all_columns)
        menu.addAction(act_show_all)

        def sync_checked():
            for c_idx, act in actions_by_col.items():
                act.blockSignals(True)
                act.setChecked(not self.isColumnHidden(c_idx))
                act.blockSignals(False)

        menu.aboutToShow.connect(sync_checked)
        return menu

    def set_column_visible(self, col: int, visible: bool):
        """Sets visibility for the specified column and recalculates table widths."""
        self.setColumnHidden(col, not visible)
        self.adjust_column_widths()
        self.sig_column_visibility_changed.emit(col, visible)

    def is_column_visible(self, col: int) -> bool:
        """Returns True if the specified column is currently visible."""
        return not self.isColumnHidden(col)

    def show_all_columns(self):
        """Shows all toggleable columns and recalculates widths."""
        for col_idx, _ in TOGGLEABLE_COLUMNS:
            self.setColumnHidden(col_idx, False)
            self.sig_column_visibility_changed.emit(col_idx, True)
        self.adjust_column_widths()

    def get_column_visibility_state(self) -> dict:
        """Returns a dict mapping col index and friendly name -> visibility for persistence."""
        name_map = {
            COL_CONDITION: "condition",
            COL_ACTION: "action",
            COL_BRANCH: "branch",
        }
        res = {}
        for col_idx, _ in TOGGLEABLE_COLUMNS:
            is_vis = not self.isColumnHidden(col_idx)
            res[str(col_idx)] = is_vis
            name = name_map.get(col_idx)
            if name:
                res[name] = is_vis
        return res

    def set_column_visibility_state(self, state: dict):
        """Restores column visibility from a saved state dict."""
        if not isinstance(state, dict):
            return
        name_map = {
            "condition": COL_CONDITION,
            "action": COL_ACTION,
            "branch": COL_BRANCH,
        }
        for col_idx, _ in TOGGLEABLE_COLUMNS:
            is_vis = None
            if str(col_idx) in state:
                is_vis = bool(state[str(col_idx)])
            else:
                for name, c in name_map.items():
                    if c == col_idx and name in state:
                        is_vis = bool(state[name])
                        break
            if is_vis is not None:
                self.setColumnHidden(col_idx, not is_vis)
        self.adjust_column_widths()

    def set_highlight_row(self, row: int):
        """Highlights the specified row in the vertical header."""
        self._custom_v_header.set_highlight_row(row)

    def set_paused_row(self, row: int):
        """Marks the specified row as paused in the vertical header."""
        self._custom_v_header.set_paused_row(row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_column_widths()

    def adjust_column_widths(self):
        """Dynamically adjusts column widths in proportion to table viewport, preserving user-resized widths."""
        w = self.viewport().width()
        if w <= 0:
            return

        self._is_adjusting_widths = True
        try:
            header = self.horizontalHeader()
            # Fixed-width compact columns:
            # 0: 스냅샷 (48px), 1: 고유 ID (48px), 2: 활성 (38px)
            w0 = self._user_column_widths.get(0, 48) if not self.isColumnHidden(0) else 0
            w1 = self._user_column_widths.get(1, 48) if not self.isColumnHidden(1) else 0
            w2 = self._user_column_widths.get(2, 38) if not self.isColumnHidden(2) else 0

            if not self.isColumnHidden(0):
                header.resizeSection(0, w0)
            if not self.isColumnHidden(1):
                header.resizeSection(1, w1)
            if not self.isColumnHidden(2):
                header.resizeSection(2, w2)

            fixed_sum = w0 + w1 + w2
            rem = max(100, w - fixed_sum)

            # Dynamic columns: 3: name, 4: cond, 5: act, 6: branch
            base_weights = {
                3: 0.32,
                4: 0.26,
                5: 0.26,
                6: 0.16,
            }
            min_widths = {3: 80, 4: 75, 5: 75, 6: 55}

            vis_dyn_cols = [c for c in [3, 4, 5, 6] if not self.isColumnHidden(c)]
            if not vis_dyn_cols:
                return

            if len(vis_dyn_cols) == 1:
                header.resizeSection(vis_dyn_cols[0], max(min_widths.get(vis_dyn_cols[0], 80), rem))
                return

            # Check for user-customized widths among currently visible dynamic columns
            user_assigned = {c: self._user_column_widths[c] for c in vis_dyn_cols if c in self._user_column_widths}
            unassigned_cols = [c for c in vis_dyn_cols if c not in self._user_column_widths]

            if not unassigned_cols:
                # All visible columns were manually resized by user
                for c in vis_dyn_cols:
                    header.resizeSection(c, max(min_widths.get(c, 50), user_assigned[c]))
            elif user_assigned:
                # Some columns resized by user; distribute remaining width to unassigned ones
                used_by_user = sum(user_assigned.values())
                unassigned_rem = max(len(unassigned_cols) * 60, rem - used_by_user)
                weight_sum = sum(base_weights[c] for c in unassigned_cols)
                allocated_total = 0
                for i, c in enumerate(unassigned_cols):
                    if i == len(unassigned_cols) - 1:
                        c_w = max(min_widths.get(c, 50), unassigned_rem - allocated_total)
                    else:
                        c_w = max(min_widths.get(c, 50), int(unassigned_rem * (base_weights[c] / weight_sum)))
                        allocated_total += c_w
                    header.resizeSection(c, c_w)
                for c, u_w in user_assigned.items():
                    header.resizeSection(c, max(min_widths.get(c, 50), u_w))
            else:
                # No user resizing; proportionally distribute rem among all visible dynamic columns
                weight_sum = sum(base_weights[c] for c in vis_dyn_cols)
                allocated_total = 0
                for i, c in enumerate(vis_dyn_cols):
                    if i == len(vis_dyn_cols) - 1:
                        c_w = max(min_widths.get(c, 50), rem - allocated_total)
                    else:
                        c_w = max(min_widths.get(c, 50), int(rem * (base_weights[c] / weight_sum)))
                        allocated_total += c_w
                    header.resizeSection(c, c_w)
        finally:
            self._is_adjusting_widths = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.sig_delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

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

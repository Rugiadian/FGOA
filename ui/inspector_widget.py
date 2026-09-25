"""
Inspector Widget for FGOA.
Unity Inspector-style always-open scenario and properties editor.
Divided vertically into:
  - Upper Pane: Color Detection & Branching Rules (Eye & Brain)
  - Lower Pane: Action Sequences (Hand)
Supports independent condition/action combining and compact high-density layout.
"""
import os
from typing import Optional, List, Dict, Any
import copy
import time
import random
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QScrollArea, QFrame, QMessageBox, QStackedWidget, QSplitter,
    QMenu, QApplication, QShortcut, QAbstractItemView,
    QStyledItemDelegate, QAbstractSpinBox, QInputDialog, QSizePolicy
)
from PyQt5.QtGui import QColor, QFont, QPixmap, QKeySequence, QDrag
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData, QPoint

from core.models import Scenario, Project, Condition, ColorPoint, Action, ActionSequence
from core.path_utils import to_absolute_path, to_relative_path
from core.screen_capture import ScreenCapture
from core.input_controller import InputController
from core.evaluator import ConditionEvaluator
from ui.widgets.color_badge import ColorChipWidget
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.action_editor_dialog import SingleActionDialog


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


class ClickableThumbnailLabel(QLabel):
    """
    Compact clickable 50px thumbnail widget for reference images.
    Preserves aspect ratio and scales smoothly to width 50px.
    """
    clicked = pyqtSignal()

    def __init__(self, border_color: str = "#3b82f6", tooltip: str = "", parent=None):
        super().__init__(parent)
        self.border_color = border_color
        self.setFixedWidth(50)
        self.setFixedHeight(30)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet(
            f"QLabel {{ border: 1.5px solid {self.border_color}; border-radius: 4px; background-color: #0f172a; }} "
            f"QLabel:hover {{ border: 2px solid #60a5fa; background-color: #1e293b; }}"
        )
        self.image_path: Optional[str] = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_image(self, path: Optional[str], hide_on_empty: bool = True, max_w: Optional[int] = None, max_h: Optional[int] = None) -> bool:
        """Sets and scales reference image. If hide_on_empty is False, displays a clean placeholder when empty."""
        self.image_path = path
        target_w = max_w if max_w else (self.width() if self.width() > 0 else 50)
        target_h = max_h if max_h else (self.height() if self.height() > 0 else 30)

        if path and os.path.isfile(path):
            pix = QPixmap(path)
            if not pix.isNull():
                scaled = pix.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.setPixmap(scaled)
                self.setStyleSheet(
                    f"QLabel {{ border: 1.5px solid {self.border_color}; border-radius: 4px; background-color: #0f172a; }} "
                    f"QLabel:hover {{ border: 2px solid #60a5fa; background-color: #1e293b; }}"
                )
                self.show()
                return True

        self.clear()
        if hide_on_empty:
            self.hide()
            return False
        else:
            self.setStyleSheet(
                f"QLabel {{ border: 1.5px dashed #475569; border-radius: 4px; background-color: #0f172a; color: #64748b; font-size: 8pt; }} "
                f"QLabel:hover {{ border: 1.5px dashed #94a3b8; background-color: #1e293b; color: #94a3b8; }}"
            )
            self.setText("빈칸")
            self.show()
            return False


class InspectorWidget(QWidget):
    """
    Always-open Unity Inspector-like panel for viewing and editing
    the currently selected scenario.
    """
    sig_scenario_saved = pyqtSignal(Scenario)
    sig_scenario_changed = pyqtSignal(Scenario)
    sig_modules_manager_requested = pyqtSignal()
    sig_log = pyqtSignal(str, str)  # level, msg

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_scenario: Optional[Scenario] = None
        self.current_scenario: Optional[Scenario] = None  # Working draft
        self.project: Optional[Project] = None
        self.target_hwnd: int = 0
        self._is_loading = False
        self._is_undoing_redoing = False
        self.is_dirty = False
        self.inspector_undo_stack: List[Dict[str, Any]] = []
        self.inspector_redo_stack: List[Dict[str, Any]] = []

        self._init_ui()
        self._init_shortcuts()

    def set_project(self, project: Project):
        self.project = project

    def _init_shortcuts(self):
        """Register keyboard shortcuts for inspector actions."""
        self.sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.sc_undo.activated.connect(self._on_undo_inspector)
        self.sc_redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.sc_redo_y.activated.connect(self._on_redo_inspector)
        self.sc_redo_shift_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.sc_redo_shift_z.activated.connect(self._on_redo_inspector)
        self.sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.sc_save.activated.connect(self._on_save_inspector)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==========================================
        # 0. Condition & Branching Panel (Eye & Brain)
        # ==========================================
        self.condition_panel = QWidget()
        self.condition_panel.setObjectName("condition_panel")
        cp_layout = QVBoxLayout(self.condition_panel)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(0)

        self.condition_stack = QStackedWidget()
        cp_layout.addWidget(self.condition_stack)

        self.empty_condition_widget = self._create_empty_condition_widget()
        self.condition_stack.addWidget(self.empty_condition_widget)

        self.condition_content_widget = QWidget()
        cc_layout = QVBoxLayout(self.condition_content_widget)
        cc_layout.setContentsMargins(4, 4, 4, 4)
        cc_layout.setSpacing(4)

        # 1.0 Pane Title Header Bar with Save, Cancel, Undo, Redo controls
        self.pane_header = QFrame()
        self.pane_header.setObjectName("card_frame")
        ph_layout = QHBoxLayout(self.pane_header)
        ph_layout.setContentsMargins(8, 4, 8, 4)
        ph_layout.setSpacing(6)

        lbl_inspector_title = QLabel("👁️ 인식 조건 및 분기")
        lbl_inspector_title.setStyleSheet("font-weight: bold; font-size: 9.5pt;")
        ph_layout.addWidget(lbl_inspector_title)

        self.lbl_dirty_indicator = QLabel("✓ 저장됨")
        self.lbl_dirty_indicator.setStyleSheet("font-size: 8pt; color: #16a34a; font-weight: bold;")
        ph_layout.addWidget(self.lbl_dirty_indicator)

        ph_layout.addStretch()

        # Undo Button
        self.btn_undo_inspector = QPushButton("◀")
        self.btn_undo_inspector.setFixedWidth(28)
        self.btn_undo_inspector.setToolTip("인스펙터 실행 취소 (Undo - Ctrl+Z)")
        self.btn_undo_inspector.clicked.connect(self._on_undo_inspector)
        self.btn_undo_inspector.setEnabled(False)
        ph_layout.addWidget(self.btn_undo_inspector)

        # Redo Button
        self.btn_redo_inspector = QPushButton("▶")
        self.btn_redo_inspector.setFixedWidth(28)
        self.btn_redo_inspector.setToolTip("인스펙터 다시 실행 (Redo - Ctrl+Y / Ctrl+Shift+Z)")
        self.btn_redo_inspector.clicked.connect(self._on_redo_inspector)
        self.btn_redo_inspector.setEnabled(False)
        ph_layout.addWidget(self.btn_redo_inspector)

        # Cancel Button
        self.btn_cancel_inspector = QPushButton("↩️ 취소")
        self.btn_cancel_inspector.setToolTip("수정한 내용을 모두 버리고 원래 상태로 되돌립니다.")
        self.btn_cancel_inspector.clicked.connect(self._on_cancel_inspector)
        self.btn_cancel_inspector.setEnabled(False)
        ph_layout.addWidget(self.btn_cancel_inspector)

        # Save Button
        self.btn_save_inspector = QPushButton("💾 저장")
        self.btn_save_inspector.setObjectName("btn_primary")
        self.btn_save_inspector.setStyleSheet("font-weight: bold; padding: 2px 10px;")
        self.btn_save_inspector.setToolTip("인스펙터 변경사항을 시나리오에 적용 및 저장합니다. (Ctrl+S)")
        self.btn_save_inspector.clicked.connect(self._on_save_inspector)
        self.btn_save_inspector.setEnabled(False)
        ph_layout.addWidget(self.btn_save_inspector)

        self.lbl_inspector_status = QLabel("시나리오 설정")
        self.lbl_inspector_status.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        ph_layout.addWidget(self.lbl_inspector_status)
        cc_layout.addWidget(self.pane_header)

        # 1.1 Header Card (Compact: 실행 순서, 고유 번호, 활성, 이름)
        self.header_card = self._create_header_card()
        cc_layout.addWidget(self.header_card)

        # Condition & Branch cards in scroll area
        upper_scroll = QScrollArea()
        upper_scroll.setWidgetResizable(True)
        upper_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        upper_container = QWidget()
        upper_layout = QVBoxLayout(upper_container)
        upper_layout.setContentsMargins(4, 4, 4, 4)
        upper_layout.setSpacing(6)

        self.condition_card = self._create_condition_card()
        upper_layout.addWidget(self.condition_card)

        self.branch_card = self._create_branch_card()
        upper_layout.addWidget(self.branch_card)

        upper_layout.addStretch()
        upper_scroll.setWidget(upper_container)
        cc_layout.addWidget(upper_scroll, 1)

        self.condition_stack.addWidget(self.condition_content_widget)
        self.condition_stack.setCurrentIndex(0)

        # ==========================================
        # 1. Action Sequence Panel (Hand)
        # ==========================================
        self.action_panel = QWidget()
        self.action_panel.setObjectName("action_panel")
        ap_layout = QVBoxLayout(self.action_panel)
        ap_layout.setContentsMargins(0, 0, 0, 0)
        ap_layout.setSpacing(0)

        self.action_stack = QStackedWidget()
        ap_layout.addWidget(self.action_stack)

        self.empty_action_widget = self._create_empty_action_widget()
        self.action_stack.addWidget(self.empty_action_widget)

        self.action_content_widget = QWidget()
        ac_layout = QVBoxLayout(self.action_content_widget)
        ac_layout.setContentsMargins(4, 4, 4, 4)
        ac_layout.setSpacing(4)

        # Action Pane Header Bar
        self.action_pane_header = QFrame()
        self.action_pane_header.setObjectName("card_frame")
        aph_layout = QHBoxLayout(self.action_pane_header)
        aph_layout.setContentsMargins(8, 4, 8, 4)
        aph_layout.setSpacing(6)

        lbl_action_title = QLabel("✋ 액션 시퀀스 (Hand)")
        lbl_action_title.setStyleSheet("font-weight: bold; font-size: 9.5pt;")
        aph_layout.addWidget(lbl_action_title)

        self.lbl_action_status = QLabel("")
        self.lbl_action_status.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        aph_layout.addWidget(self.lbl_action_status)

        aph_layout.addStretch()

        self.btn_cancel_action = QPushButton("↩️ 취소")
        self.btn_cancel_action.setToolTip("수정한 내용을 원래 상태로 되돌립니다.")
        self.btn_cancel_action.clicked.connect(self._on_cancel_inspector)
        self.btn_cancel_action.setEnabled(False)
        aph_layout.addWidget(self.btn_cancel_action)

        self.btn_save_action = QPushButton("💾 저장")
        self.btn_save_action.setObjectName("btn_primary")
        self.btn_save_action.setStyleSheet("font-weight: bold; padding: 2px 10px;")
        self.btn_save_action.setToolTip("액션 시퀀스 변경사항을 저장합니다. (Ctrl+S)")
        self.btn_save_action.clicked.connect(self._on_save_inspector)
        self.btn_save_action.setEnabled(False)
        aph_layout.addWidget(self.btn_save_action)

        ac_layout.addWidget(self.action_pane_header)

        # Action card in scroll area
        lower_scroll = QScrollArea()
        lower_scroll.setWidgetResizable(True)
        lower_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lower_container = QWidget()
        lower_layout = QVBoxLayout(lower_container)
        lower_layout.setContentsMargins(4, 4, 4, 4)
        lower_layout.setSpacing(6)

        self.action_card = self._create_action_card()
        lower_layout.addWidget(self.action_card)

        lower_layout.addStretch()
        lower_scroll.setWidget(lower_container)
        ac_layout.addWidget(lower_scroll, 1)

        self.action_stack.addWidget(self.action_content_widget)
        self.action_stack.setCurrentIndex(0)

        # Vertical Splitter for default container or standalone fallback:
        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.setObjectName("inspector_v_splitter")
        self.v_splitter.addWidget(self.condition_panel)
        self.v_splitter.addWidget(self.action_panel)
        self.v_splitter.setStretchFactor(0, 54)
        self.v_splitter.setStretchFactor(1, 46)
        self.v_splitter.setSizes([340, 290])

        main_layout.addWidget(self.v_splitter)

        # Backwards compatibility aliases
        self.stack = self.condition_stack
        self.empty_widget = self.empty_condition_widget

    def _create_empty_condition_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        icon_lbl = QLabel("👁️")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 36pt;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("인식 조건 및 분기 (Eye & Brain)")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #334155;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("왼쪽 시나리오 목록에서 항목을 클릭하면\n화면 인식 색상 조건 및 분기 규칙 편집기가 표시됩니다.")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setStyleSheet("color: #64748b; font-size: 9pt; line-height: 140%;")
        layout.addWidget(desc_lbl)

        return w

    def _create_empty_action_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        icon_lbl = QLabel("✋")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 36pt;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("액션 시퀀스 (Hand)")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #334155;")
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("왼쪽 시나리오 목록에서 항목을 클릭하면\n마우스 클릭, 드래그, 키 입력 등 동작 시퀀스 편집기가 표시됩니다.")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setStyleSheet("color: #64748b; font-size: 9pt; line-height: 140%;")
        layout.addWidget(desc_lbl)

        return w

    def _create_empty_widget(self) -> QWidget:
        return self._create_empty_condition_widget()

    # ==========================================
    # Header Card (Identity)
    # ==========================================
    def _create_header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("inspector_card")
        main_card_layout = QHBoxLayout(card)
        main_card_layout.setContentsMargins(6, 6, 6, 6)
        main_card_layout.setSpacing(8)

        # Left Info Layout: Identity, Name, and Node Type
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        # Top Row: [실행 #1] [고유 #101] [v] 시나리오 활성화 | UUID
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.lbl_step_badge = QLabel("실행 #1")
        self.lbl_step_badge.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; "
            "padding: 2px 6px; border-radius: 4px; font-size: 8.5pt;"
        )
        self.lbl_step_badge.setToolTip("시나리오 실행 순서 번호 (목록 순서 변경 시 자동 재계산)")
        top_row.addWidget(self.lbl_step_badge)

        lbl_uid_title = QLabel("고유 ID:")
        lbl_uid_title.setStyleSheet("font-weight: bold; font-size: 8.5pt; color: #7c3aed;")
        top_row.addWidget(lbl_uid_title)

        self.spin_scen_num = QSpinBox()
        self.spin_scen_num.setRange(1, 99999)
        self.spin_scen_num.setPrefix("s")
        self.spin_scen_num.setValue(1)
        self.spin_scen_num.setFixedWidth(65)
        self.spin_scen_num.setStyleSheet("font-weight: bold; color: #7c3aed;")
        self.spin_scen_num.setToolTip("시나리오 고유 ID (순서가 바뀌어도 유지되는 고유 식별 번호)")
        self.spin_scen_num.valueChanged.connect(self._on_scenario_number_changed)
        top_row.addWidget(self.spin_scen_num)

        top_row.addSpacing(6)

        self.chk_enabled = QCheckBox("시나리오 활성화")
        self.chk_enabled.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        self.chk_enabled.stateChanged.connect(self._on_field_changed)
        top_row.addWidget(self.chk_enabled)

        top_row.addStretch()

        self.lbl_id = QLabel("ID: scen_...")
        self.lbl_id.setStyleSheet("color: #64748b; font-family: monospace; font-size: 8pt;")
        top_row.addWidget(self.lbl_id)
        info_layout.addLayout(top_row)

        # Name Row: 이름 [ QLineEdit ]
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        lbl_n = QLabel("이름:")
        lbl_n.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        name_row.addWidget(lbl_n)
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("시나리오 설명 또는 목적 입력...")
        self.txt_name.textChanged.connect(self._on_field_changed)
        name_row.addWidget(self.txt_name, 1)
        info_layout.addLayout(name_row)

        # Node Type & Loop Control Row
        node_row = QHBoxLayout()
        node_row.setSpacing(6)
        lbl_nt = QLabel("노드 유형:")
        lbl_nt.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        node_row.addWidget(lbl_nt)

        self.combo_node_type = QComboBox()
        self.combo_node_type.addItem("📄 일반 시나리오 (조건/액션)", "normal")
        self.combo_node_type.addItem("🔁 루프 시작 노드 (Loop Start)", "loop_start")
        self.combo_node_type.addItem("🔁 루프 종료 노드 (Loop End)", "loop_end")
        self.combo_node_type.currentIndexChanged.connect(self._on_node_type_changed)
        node_row.addWidget(self.combo_node_type)

        # Loop Controls Sub-widget
        self.loop_container = QWidget()
        l_sub = QHBoxLayout(self.loop_container)
        l_sub.setContentsMargins(0, 0, 0, 0)
        l_sub.setSpacing(6)

        l_sub.addWidget(QLabel("루프 제어:"))
        self.combo_loop_mode = QComboBox()
        self.combo_loop_mode.addItem("지정 횟수 반복 (Count)", "count")
        self.combo_loop_mode.addItem("조건 일치 시 탈출 (Break Until Match)", "until_match")
        self.combo_loop_mode.addItem("조건 일치 동안 반복 (While Match)", "while_match")
        self.combo_loop_mode.addItem("무한 반복 (Infinite)", "infinite")
        self.combo_loop_mode.currentIndexChanged.connect(self._on_loop_mode_changed)
        l_sub.addWidget(self.combo_loop_mode)

        self.lbl_loop_cnt = QLabel("반복:")
        l_sub.addWidget(self.lbl_loop_cnt)
        self.spin_loop_cnt = QSpinBox()
        self.spin_loop_cnt.setRange(1, 99999)
        self.spin_loop_cnt.setValue(5)
        self.spin_loop_cnt.setSuffix(" 회")
        self.spin_loop_cnt.valueChanged.connect(self._on_field_changed)
        l_sub.addWidget(self.spin_loop_cnt)

        node_row.addWidget(self.loop_container)

        self.lbl_loop_end_info = QLabel("🔁 대응되는 루프 시작점으로 복귀하여 다음 회차를 실행합니다.")
        self.lbl_loop_end_info.setStyleSheet("color: #7c3aed; font-weight: bold; font-size: 8.5pt;")
        self.lbl_loop_end_info.setVisible(False)
        node_row.addWidget(self.lbl_loop_end_info)

        node_row.addStretch()
        info_layout.addLayout(node_row)
        main_card_layout.addLayout(info_layout, 1)

        # Right Column: Scenario Node Reference Snapshot Display
        snap_box = QWidget()
        snap_box_layout = QVBoxLayout(snap_box)
        snap_box_layout.setContentsMargins(2, 0, 2, 0)
        snap_box_layout.setSpacing(2)
        snap_box_layout.setAlignment(Qt.AlignCenter)

        self.lbl_node_snapshot = ClickableThumbnailLabel(
            border_color="#3b82f6",
            tooltip="📸 시나리오 노드 레퍼런스 이미지 스냅샷\n(인식 조건 이미지를 기본값으로 불러오며, 지정되지 않으면 빈칸으로 둡니다)"
        )
        self.lbl_node_snapshot.setFixedSize(76, 52)
        self.lbl_node_snapshot.clicked.connect(self._on_node_snapshot_clicked)

        lbl_snap_sub = QLabel("📸 노드 스냅샷")
        lbl_snap_sub.setStyleSheet("font-size: 7.5pt; color: #64748b; font-weight: bold;")
        lbl_snap_sub.setAlignment(Qt.AlignCenter)

        snap_box_layout.addWidget(self.lbl_node_snapshot)
        snap_box_layout.addWidget(lbl_snap_sub)
        main_card_layout.addWidget(snap_box, 0, Qt.AlignVCenter | Qt.AlignRight)

        return card

    # ==========================================
    # Upper Section: 1. Condition & Eye Card
    # ==========================================
    def _create_condition_card(self) -> QGroupBox:
        grp = QGroupBox("👁️ 색상 인식 조건 (Eye)")
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)

        # Condition Module Selection / Link Bar (인식조건 모듈화 연결)
        cond_bar = QHBoxLayout()
        cond_bar.setSpacing(4)
        lbl_cond = QLabel("🔗 연결 조건:")
        lbl_cond.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        cond_bar.addWidget(lbl_cond)

        self.combo_condition = QComboBox()
        self.combo_condition.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_condition.currentIndexChanged.connect(self._on_condition_combo_changed)
        cond_bar.addWidget(self.combo_condition, 1)

        self.btn_save_as_cond = QPushButton("💾 조건으로 등록...")
        self.btn_save_as_cond.setToolTip("현재 시나리오의 인식 조건을 재사용 가능한 '인식조건 모듈'로 등록하고 연결합니다.")
        self.btn_save_as_cond.clicked.connect(self._on_save_as_new_condition)
        cond_bar.addWidget(self.btn_save_as_cond)

        self.btn_unlink_cond = QPushButton("🔓 연결 해제")
        self.btn_unlink_cond.setToolTip("연결된 공용 인식조건 모듈을 해제하고 인스턴트 인식 조건으로 복제합니다.")
        self.btn_unlink_cond.clicked.connect(self._on_unlink_condition)
        cond_bar.addWidget(self.btn_unlink_cond)

        self.btn_manage_cond = QPushButton("⚙️ 모듈 관리...")
        self.btn_manage_cond.setToolTip("등록된 모듈(인식조건, 액션시퀀스) 관리 탭으로 이동")
        self.btn_manage_cond.clicked.connect(self._on_manage_conditions)
        cond_bar.addWidget(self.btn_manage_cond)

        layout.addLayout(cond_bar)

        self.lbl_cond_mod_status = QLabel("")
        self.lbl_cond_mod_status.setStyleSheet("color: #64748b; font-size: 8pt; padding: 1px 2px;")
        layout.addWidget(self.lbl_cond_mod_status)

        # Top row: [v] 조건 감지 활성화 | 일치 규칙: [AND/OR] | [📋 조건 가져오기...]
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.chk_has_condition = QCheckBox("조건 감지 활성화")
        self.chk_has_condition.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        self.chk_has_condition.setToolTip("체크 해제 시 조건 없이 무조건 액션을 실행합니다.")
        self.chk_has_condition.stateChanged.connect(self._on_has_condition_toggled)
        top_row.addWidget(self.chk_has_condition)

        top_row.addStretch()

        lbl_rule = QLabel("일치 규칙:")
        lbl_rule.setStyleSheet("font-size: 8.5pt;")
        top_row.addWidget(lbl_rule)

        self.combo_cond_logic = QComboBox()
        self.combo_cond_logic.addItem("모든 포인트 일치 (AND)", "AND")
        self.combo_cond_logic.addItem("하나라도 일치 (OR)", "OR")
        self.combo_cond_logic.currentIndexChanged.connect(self._on_field_changed)
        top_row.addWidget(self.combo_cond_logic)

        self.btn_copy_cond = QPushButton("📋 조건 가져오기...")
        self.btn_copy_cond.setToolTip("다른 시나리오의 색상 인식 조건을 복사해와서 조합합니다.")
        self.btn_copy_cond.clicked.connect(self._on_copy_condition_from_other)
        top_row.addWidget(self.btn_copy_cond)

        # 50px Reference Thumbnail for Condition (Eye)
        self.lbl_thumb_cond = ClickableThumbnailLabel(
            border_color="#3b82f6",
            tooltip="👁️ 인식 조건 레퍼런스 이미지 (가로 50px)\n클릭 시 조건/색상 편집기 열기"
        )
        self.lbl_thumb_cond.clicked.connect(self._on_open_canvas_editor)
        self.lbl_thumb_cond.hide()
        top_row.addWidget(self.lbl_thumb_cond)

        layout.addLayout(top_row)

        # Points Table
        self.tbl_points = QTableWidget()
        self.tbl_points.setColumnCount(6)
        self.tbl_points.setHorizontalHeaderLabels(["ID", "상대 좌표 (X, Y)", "목표 색상", "허용 오차", "판정 모드", "삭제"])
        hdr_pts = self.tbl_points.horizontalHeader()
        hdr_pts.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr_pts.resizeSection(0, 32)
        hdr_pts.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr_pts.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr_pts.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr_pts.resizeSection(3, 70)
        hdr_pts.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr_pts.setSectionResizeMode(5, QHeaderView.Fixed)
        hdr_pts.resizeSection(5, 38)
        self.tbl_points.verticalHeader().setDefaultSectionSize(24)
        self.tbl_points.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_points.setMinimumHeight(80)
        self.tbl_points.setMaximumHeight(150)
        layout.addWidget(self.tbl_points)

        # Points Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_open_canvas = QPushButton("🎯 이미지에서 좌표 지정")
        btn_open_canvas.setObjectName("btn_primary")
        btn_open_canvas.setToolTip("레퍼런스 이미지 또는 게임 화면을 열어 색상 인식 포인트 좌표를 시각적으로 지정합니다.")
        btn_open_canvas.clicked.connect(self._on_open_canvas_editor)
        btn_row.addWidget(btn_open_canvas)

        btn_add_pt = QPushButton("➕ 포인트 추가")
        btn_add_pt.clicked.connect(self._on_add_point)
        btn_row.addWidget(btn_add_pt)

        btn_del_pt = QPushButton("🗑️ 선택 삭제")
        btn_del_pt.clicked.connect(self._on_delete_point)
        btn_row.addWidget(btn_del_pt)

        btn_test_cond = QPushButton("⚡ 판정 테스트")
        btn_test_cond.setStyleSheet("color: #16a34a; font-weight: bold;")
        btn_test_cond.clicked.connect(self._on_test_condition_now)
        btn_row.addWidget(btn_test_cond)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Live Test Result Label
        self.lbl_cond_test_result = QLabel("")
        self.lbl_cond_test_result.setStyleSheet("font-size: 8.5pt; font-weight: bold;")
        self.lbl_cond_test_result.setVisible(False)
        layout.addWidget(self.lbl_cond_test_result)

        return grp

    # ==========================================
    # Upper Section: 2. Branching Card (Brain)
    # ==========================================
    def _create_branch_card(self) -> QGroupBox:
        grp = QGroupBox("🧠 실행 분기 및 판단 규칙 (Brain)")
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)

        # On Match
        m_layout = QHBoxLayout()
        m_layout.setSpacing(6)
        lbl_match = QLabel("만약 [조건 일치] ➔")
        lbl_match.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 8.5pt;")
        lbl_match.setFixedWidth(120)
        m_layout.addWidget(lbl_match)

        self.combo_on_match = QComboBox()
        self.combo_on_match.addItem("액션 실행 후 다음 단계", "execute")
        self.combo_on_match.addItem("다른 시나리오로 점프 (Jump)", "jump")
        self.combo_on_match.addItem("오토 즉시 정지 (Stop)", "stop")
        self.combo_on_match.currentIndexChanged.connect(self._on_match_branch_changed)
        m_layout.addWidget(self.combo_on_match, 1)

        self.combo_jump_match = QComboBox()
        self.combo_jump_match.currentIndexChanged.connect(self._on_field_changed)
        m_layout.addWidget(self.combo_jump_match, 1)
        layout.addLayout(m_layout)

        # On Mismatch
        mm_layout = QHBoxLayout()
        mm_layout.setSpacing(6)
        lbl_mismatch = QLabel("만약 [조건 불일치] ➔")
        lbl_mismatch.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 8.5pt;")
        lbl_mismatch.setFixedWidth(120)
        mm_layout.addWidget(lbl_mismatch)

        self.combo_on_mismatch = QComboBox()
        self.combo_on_mismatch.addItem("다음 시나리오로 진행", "next")
        self.combo_on_mismatch.addItem("다른 시나리오로 점프 (Jump)", "jump")
        self.combo_on_mismatch.addItem("대기 후 조건 재시도 (Retry)", "retry")
        self.combo_on_mismatch.addItem("오토 즉시 정지 (Stop)", "stop")
        self.combo_on_mismatch.currentIndexChanged.connect(self._on_mismatch_branch_changed)
        mm_layout.addWidget(self.combo_on_mismatch, 1)

        self.combo_jump_mismatch = QComboBox()
        self.combo_jump_mismatch.currentIndexChanged.connect(self._on_field_changed)
        mm_layout.addWidget(self.combo_jump_mismatch, 1)
        layout.addLayout(mm_layout)

        # Retry fail option row (shown only when on_mismatch == "retry")
        self.row_retry_fail = QWidget()
        rf_layout = QHBoxLayout(self.row_retry_fail)
        rf_layout.setContentsMargins(0, 2, 0, 2)
        rf_layout.setSpacing(6)

        self.lbl_retry_fail = QLabel("재시도 모두 소진 시 ➔")
        self.lbl_retry_fail.setStyleSheet("color: #b91c1c; font-weight: bold; font-size: 8.5pt;")
        self.lbl_retry_fail.setFixedWidth(135)
        rf_layout.addWidget(self.lbl_retry_fail)

        self.combo_retry_fail_action = QComboBox()
        self.combo_retry_fail_action.addItem("오토 즉시 정지 (Stop)", "stop")
        self.combo_retry_fail_action.addItem("다른 시나리오로 점프 (Jump)", "jump")
        self.combo_retry_fail_action.addItem("다음 시나리오로 진행 (Next)", "next")
        self.combo_retry_fail_action.currentIndexChanged.connect(self._on_retry_fail_action_changed)
        rf_layout.addWidget(self.combo_retry_fail_action, 1)

        self.combo_retry_fail_jump = QComboBox()
        self.combo_retry_fail_jump.currentIndexChanged.connect(self._on_field_changed)
        rf_layout.addWidget(self.combo_retry_fail_jump, 1)

        layout.addWidget(self.row_retry_fail)

        # Retry & Post Delay options row
        opt_layout = QHBoxLayout()
        opt_layout.setSpacing(6)
        self.lbl_retry_cnt = QLabel("재시도:")
        self.lbl_retry_cnt.setStyleSheet("font-size: 8.5pt;")
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(1, 999)
        self.spin_retries.setValue(5)
        self.spin_retries.setSuffix(" 회")
        self.spin_retries.valueChanged.connect(self._on_field_changed)

        self.lbl_retry_sec = QLabel("간격:")
        self.lbl_retry_sec.setStyleSheet("font-size: 8.5pt;")
        self.spin_retry_sec = QDoubleSpinBox()
        self.spin_retry_sec.setRange(0.1, 60.0)
        self.spin_retry_sec.setValue(1.0)
        self.spin_retry_sec.setSingleStep(0.2)
        self.spin_retry_sec.setSuffix(" 초")
        self.spin_retry_sec.valueChanged.connect(self._on_field_changed)

        opt_layout.addWidget(self.lbl_retry_cnt)
        opt_layout.addWidget(self.spin_retries)
        opt_layout.addWidget(self.lbl_retry_sec)
        opt_layout.addWidget(self.spin_retry_sec)

        opt_layout.addSpacing(10)

        lbl_delay = QLabel("완료 후 대기:")
        lbl_delay.setStyleSheet("font-size: 8.5pt;")
        opt_layout.addWidget(lbl_delay)
        self.spin_post_delay = QDoubleSpinBox()
        self.spin_post_delay.setRange(0.0, 60.0)
        self.spin_post_delay.setValue(0.0)
        self.spin_post_delay.setSingleStep(0.5)
        self.spin_post_delay.setSuffix(" 초")
        self.spin_post_delay.valueChanged.connect(self._on_field_changed)
        opt_layout.addWidget(self.spin_post_delay)

        opt_layout.addStretch()
        layout.addLayout(opt_layout)

        return grp

    # ==========================================
    # Lower Section: Action Sequence Card (Hand)
    # ==========================================
    def _create_action_card(self) -> QGroupBox:
        grp = QGroupBox("✋ 액션 시퀀스 (Action Sequence - 실행 동작)")
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(6, 10, 6, 6)
        layout.setSpacing(4)

        # Sequence Selection / Link Bar (액션 시퀀스 모듈화 연결)
        seq_bar = QHBoxLayout()
        seq_bar.setSpacing(4)
        lbl_seq = QLabel("🔗 연결 시퀀스:")
        lbl_seq.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        seq_bar.addWidget(lbl_seq)

        self.combo_sequence = QComboBox()
        self.combo_sequence.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_sequence.currentIndexChanged.connect(self._on_sequence_combo_changed)
        seq_bar.addWidget(self.combo_sequence, 1)

        self.btn_save_as_seq = QPushButton("💾 시퀀스로 등록...")
        self.btn_save_as_seq.setToolTip("현재 시나리오의 액션 목록을 재사용 가능한 '액션 시퀀스 모듈'로 등록하고 연결합니다.")
        self.btn_save_as_seq.clicked.connect(self._on_save_as_new_sequence)
        seq_bar.addWidget(self.btn_save_as_seq)

        self.btn_unlink_seq = QPushButton("🔓 연결 해제")
        self.btn_unlink_seq.setToolTip("연결된 공용 시퀀스를 해제하고 인스턴트 액션 시퀀스로 복제합니다.")
        self.btn_unlink_seq.clicked.connect(self._on_unlink_sequence)
        seq_bar.addWidget(self.btn_unlink_seq)

        self.btn_manage_seq = QPushButton("⚙️ 모듈 관리...")
        self.btn_manage_seq.setToolTip("등록된 모듈(인식조건, 액션시퀀스) 관리 탭으로 이동")
        self.btn_manage_seq.clicked.connect(self._on_manage_conditions)
        seq_bar.addWidget(self.btn_manage_seq)

        layout.addLayout(seq_bar)

        self.lbl_seq_status = QLabel("")
        self.lbl_seq_status.setStyleSheet("color: #64748b; font-size: 8pt; padding: 1px 2px;")
        layout.addWidget(self.lbl_seq_status)

        # Quick Add Buttons Bar + Copy from other scenario (2 Rows for neat layout)
        # Row 1: Quick Add Buttons
        add_bar_row1 = QHBoxLayout()
        add_bar_row1.setSpacing(4)

        btn_add_click = QPushButton("🖱️+클릭")
        btn_add_click.clicked.connect(lambda: self._on_quick_add_action("mouse_click"))
        add_bar_row1.addWidget(btn_add_click)

        btn_add_drag = QPushButton("↔️+드래그")
        btn_add_drag.clicked.connect(lambda: self._on_quick_add_action("mouse_drag"))
        add_bar_row1.addWidget(btn_add_drag)

        btn_add_key = QPushButton("⌨️+키")
        btn_add_key.clicked.connect(lambda: self._on_quick_add_action("key_press"))
        add_bar_row1.addWidget(btn_add_key)

        btn_add_text = QPushButton("📝+텍스트")
        btn_add_text.clicked.connect(lambda: self._on_quick_add_action("text_type"))
        add_bar_row1.addWidget(btn_add_text)

        btn_add_delay = QPushButton("⏳+대기")
        btn_add_delay.clicked.connect(lambda: self._on_quick_add_action("delay"))
        add_bar_row1.addWidget(btn_add_delay)

        btn_add_log = QPushButton("💬+로그")
        btn_add_log.clicked.connect(lambda: self._on_quick_add_action("log_message"))
        add_bar_row1.addWidget(btn_add_log)

        add_bar_row1.addStretch()

        # 50px Reference Thumbnail for Action (Hand)
        self.lbl_thumb_act = ClickableThumbnailLabel(
            border_color="#10b981",
            tooltip="🎯 액션 조건 레퍼런스 이미지 (가로 50px)\n클릭 시 액션 좌표 지정 작업창 열기"
        )
        self.lbl_thumb_act.clicked.connect(self._on_pick_coord_for_selected_action)
        self.lbl_thumb_act.hide()
        add_bar_row1.addWidget(self.lbl_thumb_act)

        layout.addLayout(add_bar_row1)

        # Row 2: Operation Recording & Sequence Copy
        add_bar_row2 = QHBoxLayout()
        add_bar_row2.setSpacing(4)

        btn_record = QPushButton("⏺️ 조작 녹화")
        btn_record.setStyleSheet("color: #dc2626; font-weight: bold;")
        btn_record.setToolTip("타겟 게임 창에서 직접 마우스 클릭 및 드래그를 조작하여 실시간으로 액션을 녹화합니다.")
        btn_record.clicked.connect(self._on_start_operation_recording)
        add_bar_row2.addWidget(btn_record)

        self.btn_copy_act = QPushButton("📋 가져오기...")
        self.btn_copy_act.setToolTip("다른 시나리오의 액션 시퀀스를 복사해와서 조합합니다.")
        self.btn_copy_act.clicked.connect(self._on_copy_actions_from_other)
        add_bar_row2.addWidget(self.btn_copy_act)

        add_bar_row2.addStretch()
        layout.addLayout(add_bar_row2)

        # Actions Table
        self.tbl_actions = DraggableActionsTableWidget()
        self.tbl_actions.setColumnCount(6)
        self.tbl_actions.setHorizontalHeaderLabels(["#", "액션 유형", "좌표 / 키 / 텍스트", "오프셋", "대기", "로그"])
        self.tbl_actions.setWordWrap(True)
        self.tbl_actions.sig_row_reordered.connect(self._on_action_row_reordered)
        hdr_act = self.tbl_actions.horizontalHeader()
        for c in range(6):
            hdr_act.setSectionResizeMode(c, QHeaderView.Interactive)
        hdr_act.resizeSection(0, 36)
        hdr_act.resizeSection(1, 95)
        hdr_act.resizeSection(2, 115)
        hdr_act.resizeSection(3, 58)
        hdr_act.resizeSection(4, 58)
        hdr_act.resizeSection(5, 140)
        self.tbl_actions.verticalHeader().setDefaultSectionSize(26)
        self.tbl_actions.verticalHeader().setMinimumSectionSize(24)
        self.tbl_actions.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_actions.setMinimumHeight(95)
        self.tbl_actions.setMaximumHeight(200)

        # 델리게이트 연결: 오프셋, 대기, 로그 열에 대해 평상시 깔끔한 텍스트 출력 및 클릭 시 즉시 인라인 편집 지원
        self.action_column_delegate = ActionColumnDelegate(self, self.tbl_actions)
        self.tbl_actions.setItemDelegateForColumn(3, self.action_column_delegate)
        self.tbl_actions.setItemDelegateForColumn(4, self.action_column_delegate)
        self.tbl_actions.setItemDelegateForColumn(5, self.action_column_delegate)
        self.tbl_actions.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed
        )
        self.tbl_actions.cellClicked.connect(self._on_action_cell_clicked)
        self.tbl_actions.cellDoubleClicked.connect(self._on_action_cell_double_clicked)
        layout.addWidget(self.tbl_actions)

        # Actions Control Buttons - Row 1: Item Manipulation (Edit, Pick Coord, Delete, Up, Down)
        act_ctrl_row1 = QHBoxLayout()
        act_ctrl_row1.setSpacing(4)
        btn_edit_act = QPushButton("✏️ 편집")
        btn_edit_act.clicked.connect(self._on_edit_action)
        act_ctrl_row1.addWidget(btn_edit_act)

        btn_pick_coord_act = QPushButton("🎯 액션 시퀀스 이미지로 좌표 지정...")
        btn_pick_coord_act.setToolTip("액션 시퀀스 이미지로 좌표 지정 작업창을 열어 레퍼런스 이미지 상에서 좌표를 직접 지정 및 편집합니다.")
        btn_pick_coord_act.clicked.connect(self._on_pick_coord_for_selected_action)
        act_ctrl_row1.addWidget(btn_pick_coord_act)

        btn_del_act = QPushButton("🗑️ 삭제")
        btn_del_act.clicked.connect(self._on_delete_action)
        act_ctrl_row1.addWidget(btn_del_act)

        btn_up_act = QPushButton("⬆️ 위로")
        btn_up_act.clicked.connect(self._on_move_action_up)
        act_ctrl_row1.addWidget(btn_up_act)

        btn_down_act = QPushButton("⬇️ 아래로")
        btn_down_act.clicked.connect(self._on_move_action_down)
        act_ctrl_row1.addWidget(btn_down_act)

        act_ctrl_row1.addStretch()
        layout.addLayout(act_ctrl_row1)

        # Actions Control Buttons - Row 2: Test & Execution (Single Action & Full Sequence)
        act_ctrl_row2 = QHBoxLayout()
        act_ctrl_row2.setSpacing(4)

        self.btn_test_act = QPushButton("⚡ 선택 액션 즉시 실행")
        self.btn_test_act.setStyleSheet("color: #2563eb; font-weight: bold;")
        self.btn_test_act.setToolTip("목록에서 선택한 단일 액션을 현재 타겟 창에 즉시 테스트 실행합니다.")
        self.btn_test_act.clicked.connect(self._on_test_action_now)
        act_ctrl_row2.addWidget(self.btn_test_act)

        self.btn_test_all_act = QPushButton("▶ 전체 시퀀스 실행 테스트")
        self.btn_test_all_act.setStyleSheet("color: #16a34a; font-weight: bold;")
        self.btn_test_all_act.setToolTip("이 시나리오에 등록된 모든 액션을 등록된 순서대로 순차 테스트 실행합니다.")
        self.btn_test_all_act.clicked.connect(self._on_test_all_actions_now)
        act_ctrl_row2.addWidget(self.btn_test_all_act)

        act_ctrl_row2.addStretch()
        layout.addLayout(act_ctrl_row2)

        # Row 3: Action Custom Log Option (비워두면 오프, 입력하면 온)
        log_bar = QHBoxLayout()
        log_bar.setSpacing(6)
        lbl_action_log = QLabel("💬 액션 실행 시 로그 출력:")
        lbl_action_log.setToolTip("이 시나리오의 액션들이 실행될 때 로그 창에 출력할 문장입니다. (비워두면 오프, 입력하면 온)")
        self.txt_action_log = QLineEdit()
        self.txt_action_log.setPlaceholderText("원하는 로그 문장을 입력하세요 (비워두면 출력 안 함)")
        self.txt_action_log.setEnabled(True)
        self.txt_action_log.textChanged.connect(self._on_action_log_text_changed)
        log_bar.addWidget(lbl_action_log)
        log_bar.addWidget(self.txt_action_log, 1)
        layout.addLayout(log_bar)

        return grp

    # ==========================================
    # Data Loading & Syncing
    # ==========================================
    # ==========================================
    # Data Loading, Draft Management & Undo/Redo
    # ==========================================
    def set_target_hwnd(self, hwnd: int):
        self.target_hwnd = hwnd

    def set_scenario(self, scenario: Optional[Scenario], target_hwnd: int = 0, project: Optional[Project] = None):
        """Bind and display a scenario in the inspector as an isolated working draft."""
        self.original_scenario = scenario
        self.target_hwnd = target_hwnd
        self.project = project

        if not scenario:
            self.current_scenario = None
            if hasattr(self, "condition_stack"):
                self.condition_stack.setCurrentIndex(0)
            if hasattr(self, "action_stack"):
                self.action_stack.setCurrentIndex(0)
            self.stack.setCurrentIndex(0)
            self.inspector_undo_stack.clear()
            self.inspector_redo_stack.clear()
            self.is_dirty = False
            self._update_save_cancel_buttons()
            return

        # Create working draft copy so edits don't prematurely mutate the original
        self.current_scenario = copy.deepcopy(scenario)
        self.inspector_undo_stack.clear()
        self.inspector_redo_stack.clear()
        self.is_dirty = False

        self._load_scenario_to_ui(self.current_scenario)
        self._update_save_cancel_buttons()

    def _load_scenario_to_ui(self, scenario: Scenario):
        """Populates UI controls from a Scenario instance."""
        self._is_loading = True
        try:
            if hasattr(self, "condition_stack"):
                self.condition_stack.setCurrentIndex(1)
            if hasattr(self, "action_stack"):
                self.action_stack.setCurrentIndex(1)
            self.stack.setCurrentIndex(1)
            if hasattr(self, "lbl_action_status"):
                self.lbl_action_status.setText(f"s{scenario.scenario_number} [{scenario.name}]")
            self._populate_jump_combos()

            # 1. Header & Identity
            self.lbl_inspector_status.setText(f"고유 s{scenario.scenario_number} [{scenario.name}]")
            self.lbl_step_badge.setText(f"실행 #{scenario.step_number}")
            self.spin_scen_num.blockSignals(True)
            self.spin_scen_num.setValue(scenario.scenario_number)
            self.spin_scen_num.blockSignals(False)
            self.lbl_id.setText(f"ID: {scenario.id}")
            self.txt_name.setText(scenario.name)
            self.chk_enabled.setChecked(scenario.enabled)

            # Node Type & Loop Settings
            self.combo_node_type.blockSignals(True)
            idx_nt = self.combo_node_type.findData(scenario.node_type)
            self.combo_node_type.setCurrentIndex(idx_nt if idx_nt >= 0 else 0)
            self.combo_node_type.blockSignals(False)

            self.combo_loop_mode.blockSignals(True)
            idx_lm = self.combo_loop_mode.findData(scenario.loop_mode)
            self.combo_loop_mode.setCurrentIndex(idx_lm if idx_lm >= 0 else 0)
            self.combo_loop_mode.blockSignals(False)

            self.spin_loop_cnt.blockSignals(True)
            self.spin_loop_cnt.setValue(scenario.loop_count)
            self.spin_loop_cnt.blockSignals(False)

            self._update_node_type_visibility()

            # 2. Branching
            idx_match = self.combo_on_match.findData(scenario.on_match)
            if idx_match >= 0:
                self.combo_on_match.setCurrentIndex(idx_match)
            self._select_jump_target(self.combo_jump_match, scenario.jump_target_on_match)

            idx_mismatch = self.combo_on_mismatch.findData(scenario.on_mismatch)
            if idx_mismatch >= 0:
                self.combo_on_mismatch.setCurrentIndex(idx_mismatch)
            self._select_jump_target(self.combo_jump_mismatch, scenario.jump_target_on_mismatch)

            # Retry failure action
            rf_action = getattr(scenario, "retry_fail_action", "stop")
            idx_rf = self.combo_retry_fail_action.findData(rf_action)
            if idx_rf >= 0:
                self.combo_retry_fail_action.setCurrentIndex(idx_rf)
            self._select_jump_target(self.combo_retry_fail_jump, getattr(scenario, "retry_fail_jump_target", ""))

            self.spin_retries.setValue(scenario.retry_max_count)
            self.spin_retry_sec.setValue(scenario.retry_interval_sec)
            self.spin_post_delay.setValue(scenario.post_delay_seconds)

            self._update_branch_visibility()

            # 3. Condition & Module Link
            self._populate_condition_combo()
            eff_cond = self._get_active_condition()
            self.chk_has_condition.setChecked(eff_cond is not None)
            if eff_cond:
                idx_op = self.combo_cond_logic.findData(eff_cond.logic_operator)
                if idx_op >= 0:
                    self.combo_cond_logic.setCurrentIndex(idx_op)
            self._refresh_points_table()
            self.lbl_cond_test_result.setVisible(False)

            # 4. Actions & Sequence Link
            self._populate_sequence_combo()
            self._refresh_actions_table()

            # 5. Action Custom Log
            custom_log = getattr(scenario, "custom_log", "")
            self.txt_action_log.blockSignals(True)
            self.txt_action_log.setText(custom_log)
            self.txt_action_log.setEnabled(True)
            self.txt_action_log.blockSignals(False)

            # 6. Update 50px Reference Thumbnails (Condition Card & Action Card)
            self._update_reference_thumbnails()

        finally:
            self._is_loading = False

    def _record_undo_state(self):
        """Pushes current working draft to inspector undo stack before a new modification."""
        if self._is_loading or self._is_undoing_redoing or not self.current_scenario:
            return
        snapshot = self.current_scenario.to_dict()
        if self.inspector_undo_stack and self.inspector_undo_stack[-1] == snapshot:
            return
        self.inspector_undo_stack.append(snapshot)
        if len(self.inspector_undo_stack) > 50:
            self.inspector_undo_stack.pop(0)
        self.inspector_redo_stack.clear()

    def _mark_dirty(self):
        """Marks the inspector draft as having unsaved changes and updates buttons."""
        self.is_dirty = True
        self._update_save_cancel_buttons()

    def _update_save_cancel_buttons(self):
        """Updates enablement and visual styles for Save, Cancel, Undo, and Redo buttons."""
        has_scen = (self.current_scenario is not None)
        can_undo = bool(self.inspector_undo_stack)
        can_redo = bool(self.inspector_redo_stack)

        self.btn_save_inspector.setEnabled(has_scen and self.is_dirty)
        self.btn_cancel_inspector.setEnabled(has_scen and self.is_dirty)
        if hasattr(self, "btn_save_action"):
            self.btn_save_action.setEnabled(has_scen and self.is_dirty)
        if hasattr(self, "btn_cancel_action"):
            self.btn_cancel_action.setEnabled(has_scen and self.is_dirty)
        self.btn_undo_inspector.setEnabled(can_undo)
        self.btn_redo_inspector.setEnabled(can_redo)

        if not has_scen:
            self.lbl_dirty_indicator.setText("")
        elif self.is_dirty:
            self.lbl_dirty_indicator.setText("● 변경사항 있음")
            self.lbl_dirty_indicator.setStyleSheet("font-size: 8pt; color: #ea580c; font-weight: bold;")
        else:
            self.lbl_dirty_indicator.setText("✓ 저장됨")
            self.lbl_dirty_indicator.setStyleSheet("font-size: 8pt; color: #16a34a; font-weight: bold;")

    def _on_save_inspector(self):
        """Applies working draft scenario to original scenario and notifies main window."""
        if not self.original_scenario or not self.current_scenario:
            return

        draft_dict = self.current_scenario.to_dict()
        updated_scen = Scenario.from_dict(draft_dict)

        for f_name in updated_scen.__dataclass_fields__:
            setattr(self.original_scenario, f_name, getattr(updated_scen, f_name))

        self.is_dirty = False
        self._update_save_cancel_buttons()
        self.sig_scenario_saved.emit(self.original_scenario)
        self.sig_scenario_changed.emit(self.original_scenario)
        self.sig_log.emit("SUCCESS", f"💾 시나리오 s{self.original_scenario.scenario_number} [{self.original_scenario.name}] 변경사항이 저장되었습니다.")

    def _on_cancel_inspector(self):
        """Reverts working draft back to original scenario state."""
        if not self.original_scenario:
            return
        self.current_scenario = copy.deepcopy(self.original_scenario)
        self.inspector_undo_stack.clear()
        self.inspector_redo_stack.clear()
        self.is_dirty = False
        self._load_scenario_to_ui(self.current_scenario)
        self._update_save_cancel_buttons()
        self.sig_log.emit("INFO", f"↩️ 시나리오 s{self.original_scenario.scenario_number} 변경사항을 취소했습니다.")

    def _on_undo_inspector(self):
        """Undoes last edit in inspector."""
        if not self.inspector_undo_stack or not self.current_scenario:
            return
        cur_snapshot = self.current_scenario.to_dict()
        self.inspector_redo_stack.append(cur_snapshot)

        prev_snapshot = self.inspector_undo_stack.pop()
        self._is_undoing_redoing = True
        try:
            self.current_scenario = Scenario.from_dict(prev_snapshot)
            self._load_scenario_to_ui(self.current_scenario)
        finally:
            self._is_undoing_redoing = False

        self.is_dirty = (self.original_scenario and self.current_scenario.to_dict() != self.original_scenario.to_dict())
        self._update_save_cancel_buttons()

    def _on_redo_inspector(self):
        """Redoes previously undone edit in inspector."""
        if not self.inspector_redo_stack or not self.current_scenario:
            return
        cur_snapshot = self.current_scenario.to_dict()
        self.inspector_undo_stack.append(cur_snapshot)

        next_snapshot = self.inspector_redo_stack.pop()
        self._is_undoing_redoing = True
        try:
            self.current_scenario = Scenario.from_dict(next_snapshot)
            self._load_scenario_to_ui(self.current_scenario)
        finally:
            self._is_undoing_redoing = False

        self.is_dirty = (self.original_scenario and self.current_scenario.to_dict() != self.original_scenario.to_dict())
        self._update_save_cancel_buttons()

    def _update_reference_thumbnails(self):
        """
        Updates the 50px reference image thumbnails:
        - Condition reference thumbnail inside Condition Card (Eye)
        - Action reference thumbnail inside Action Card (Hand)
        """
        if not self.current_scenario:
            if hasattr(self, "lbl_thumb_cond"):
                self.lbl_thumb_cond.hide()
            if hasattr(self, "lbl_thumb_act"):
                self.lbl_thumb_act.hide()
            return

        cond_path = None
        eff_cond = self._get_active_condition()
        if eff_cond and getattr(eff_cond, "reference_image_path", None):
            cond_path = to_absolute_path(eff_cond.reference_image_path)

        act_path = getattr(self.current_scenario, "last_action_image_path", None)
        acts = self._get_active_actions_list()
        if not act_path and acts:
            for act in acts:
                if getattr(act, "reference_image_path", None):
                    act_path = act.reference_image_path
                    break
        if act_path:
            act_path = to_absolute_path(act_path)

        # 1. Scenario Node Reference Snapshot (Header Card)
        if hasattr(self, "lbl_node_snapshot"):
            eff_snap_path = self.current_scenario.get_effective_reference_image(self.project)
            abs_snap = to_absolute_path(eff_snap_path) if eff_snap_path else None
            if abs_snap and os.path.isfile(abs_snap):
                self.lbl_node_snapshot.set_image(abs_snap, hide_on_empty=False, max_w=76, max_h=52)
                fname = os.path.basename(abs_snap)
                source_tag = "노드 고유 지정" if self.current_scenario.reference_image_path else "인식조건 연동 (기본값)"
                self.lbl_node_snapshot.setToolTip(
                    f"📸 시나리오 노드 스냅샷 [{source_tag}]\n"
                    f"파일: {fname}\n"
                    f"클릭: 스냅샷 변경 / 갤러리 / 캡처 메뉴 열기"
                )
            else:
                self.lbl_node_snapshot.set_image(None, hide_on_empty=False, max_w=76, max_h=52)
                self.lbl_node_snapshot.setToolTip(
                    "📸 시나리오 노드 스냅샷 (지정 안 됨 - 빈칸)\n"
                    "인식 조건에 지정된 레퍼런스 이미지를 기본값으로 불러오며,\n"
                    "클릭하여 갤러리 또는 타겟 창 캡처로 노드 스냅샷을 지정할 수 있습니다."
                )

        # 2. Condition Card Thumbnail
        if hasattr(self, "lbl_thumb_cond"):
            has_cond = self.lbl_thumb_cond.set_image(cond_path)
            if has_cond and cond_path:
                fname = os.path.basename(cond_path)
                self.lbl_thumb_cond.setToolTip(
                    f"👁️ 인식 조건 레퍼런스 (가로 50px)\n클릭 시 조건/색상 편집기 열기\n파일: {fname}"
                )

        # 3. Action Card Thumbnail
        if hasattr(self, "lbl_thumb_act"):
            has_act = self.lbl_thumb_act.set_image(act_path)
            if has_act and act_path:
                fname = os.path.basename(act_path)
                self.lbl_thumb_act.setToolTip(
                    f"🎯 액션 좌표 지정 레퍼런스 (가로 50px)\n클릭 시 액션 좌표 지정 작업창 열기\n파일: {fname}"
                )

    def _on_node_snapshot_clicked(self):
        """Displays options menu when user clicks the scenario node snapshot box."""
        if not self.current_scenario:
            return

        menu = QMenu(self)
        act_gallery = menu.addAction("🖼️ 레퍼런스 갤러리에서 선택...")
        act_capture = menu.addAction("📸 현재 게임창 캡처하여 지정...")
        menu.addSeparator()

        eff_cond = self._get_active_condition()
        if eff_cond and getattr(eff_cond, "reference_image_path", None):
            act_edit_cond_img = menu.addAction("🎯 이미지에서 인식 조건 좌표 지정...")
        else:
            act_edit_cond_img = None

        if self.current_scenario.reference_image_path is not None:
            act_reset_cond = menu.addAction("🔄 인식 조건 레퍼런스 이미지로 초기화 (기본값)")
        else:
            act_reset_cond = None

        act_clear = menu.addAction("❌ 스냅샷 비우기 (빈칸으로 두기)")

        selected = menu.exec_(QCursor.pos())
        if selected == act_gallery:
            from ui.reference_gallery_dialog import ReferenceGalleryDialog
            dlg = ReferenceGalleryDialog(self.project, target_hwnd=self.target_hwnd, picker_mode=True, parent=self)
            if dlg.exec_() == QDialog.Accepted:
                sel_path = dlg.get_selected_image_path()
                if sel_path and os.path.exists(sel_path):
                    self.current_scenario.reference_image_path = to_relative_path(sel_path)
                    self._on_field_changed()
                    self._update_reference_thumbnails()
        elif selected == act_capture:
            if not self.target_hwnd:
                QMessageBox.warning(self, "타겟 창 없음", "타겟 게임 창이 선택되어 있지 않습니다.")
                return
            img = ScreenCapture.capture_client_area(self.target_hwnd)
            if img:
                from core.path_utils import get_references_dir
                save_dir = get_references_dir()
                os.makedirs(save_dir, exist_ok=True)
                import datetime
                now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = f"capture_{now_str}.png"
                ref_path = os.path.join(save_dir, fname)
                img.save(ref_path, "PNG")
                rel_path = to_relative_path(ref_path)
                self.current_scenario.reference_image_path = rel_path
                self._on_field_changed()
                self._update_reference_thumbnails()
                QMessageBox.information(self, "캡처 완료", f"타겟 창 화면을 캡처하여 노드 스냅샷으로 저장했습니다:\n{fname}")
            else:
                QMessageBox.warning(self, "캡처 실패", "타겟 창을 캡처할 수 없습니다.")
        elif act_edit_cond_img and selected == act_edit_cond_img:
            self._on_open_canvas_editor()
        elif act_reset_cond and selected == act_reset_cond:
            self.current_scenario.reference_image_path = None
            self._on_field_changed()
            self._update_reference_thumbnails()
        elif selected == act_clear:
            self.current_scenario.reference_image_path = ""
            self._on_field_changed()
            self._update_reference_thumbnails()

    def _on_action_log_toggled(self, checked: bool):
        # Kept for backward compatibility
        pass

    def _on_action_log_text_changed(self, text: str):
        if not self._is_loading and self.current_scenario:
            clean = text.strip()
            self.current_scenario.custom_log = clean
            self._on_field_changed()

    def _populate_jump_combos(self):
        for combo in [self.combo_jump_match, self.combo_jump_mismatch, self.combo_retry_fail_jump]:
            combo.clear()
            combo.addItem("(선택 안 함)", "")
            if self.project:
                for s in self.project.scenarios:
                    if self.current_scenario and s.id == self.current_scenario.id:
                        continue
                    combo.addItem(f"고유 s{s.scenario_number} (실행 #{s.step_number}) [{s.name}]", s.id)

    def _select_jump_target(self, combo: QComboBox, target_id: str):
        idx = combo.findData(target_id)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)

    def _on_retry_fail_action_changed(self):
        if hasattr(self, "combo_retry_fail_jump") and hasattr(self, "combo_retry_fail_action"):
            is_jump_fail = (self.combo_retry_fail_action.currentData() == "jump")
            self.combo_retry_fail_jump.setVisible(is_jump_fail)
        self._on_field_changed()

    def _update_branch_visibility(self):
        is_jump_match = (self.combo_on_match.currentData() == "jump")
        self.combo_jump_match.setVisible(is_jump_match)

        is_jump_mismatch = (self.combo_on_mismatch.currentData() == "jump")
        self.combo_jump_mismatch.setVisible(is_jump_mismatch)

        is_retry = (self.combo_on_mismatch.currentData() == "retry")
        self.lbl_retry_cnt.setVisible(is_retry)
        self.spin_retries.setVisible(is_retry)
        self.lbl_retry_sec.setVisible(is_retry)
        self.spin_retry_sec.setVisible(is_retry)
        if hasattr(self, "row_retry_fail"):
            self.row_retry_fail.setVisible(is_retry)
            if is_retry:
                is_jump_fail = (self.combo_retry_fail_action.currentData() == "jump")
                self.combo_retry_fail_jump.setVisible(is_jump_fail)

    def _refresh_points_table(self):
        eff_cond = self._get_active_condition()
        if not self.current_scenario or not eff_cond:
            self.tbl_points.setRowCount(0)
            return

        pts = eff_cond.points
        self.tbl_points.setRowCount(len(pts))

        for row, pt in enumerate(pts):
            # 0. Number
            it_no = QTableWidgetItem(f"p{row + 1}")
            it_no.setTextAlignment(Qt.AlignCenter)
            self.tbl_points.setItem(row, 0, it_no)

            # 1. Coordinates
            it_coord = QTableWidgetItem(f"({pt.x}, {pt.y})")
            it_coord.setTextAlignment(Qt.AlignCenter)
            self.tbl_points.setItem(row, 1, it_coord)

            # 2. Color Swatch + RGB
            cell_w = QWidget()
            c_lay = QHBoxLayout(cell_w)
            c_lay.setContentsMargins(4, 1, 4, 1)
            c_lay.setSpacing(5)
            c_lay.addWidget(ColorChipWidget(pt.r, pt.g, pt.b, 15))
            lbl_rgb = QLabel(f"RGB({pt.r},{pt.g},{pt.b})")
            lbl_rgb.setStyleSheet("font-family: monospace; font-size: 8.5pt;")
            c_lay.addWidget(lbl_rgb)
            c_lay.addStretch()
            self.tbl_points.setCellWidget(row, 2, cell_w)

            # 3. Tolerance SpinBox (Inline edit)
            spin_tol = QSpinBox()
            spin_tol.setRange(0, 255)
            spin_tol.setValue(pt.tolerance)
            spin_tol.valueChanged.connect(lambda val, p=pt: self._on_point_tolerance_changed(p, val))
            self.tbl_points.setCellWidget(row, 3, spin_tol)

            # 4. Mode Combo (Inline edit)
            combo_m = QComboBox()
            combo_m.addItem("일치 (Match)", "match")
            combo_m.addItem("불일치 (Invert)", "not_match")
            combo_m.setCurrentIndex(1 if pt.match_mode == "not_match" else 0)
            combo_m.currentIndexChanged.connect(lambda idx, p=pt: self._on_point_mode_changed(p, idx))
            self.tbl_points.setCellWidget(row, 4, combo_m)

            # 5. Delete Button (✕)
            btn_del = QPushButton("✕")
            btn_del.setToolTip("이 인식 조건 포인트 삭제")
            btn_del.setFixedSize(24, 22)
            btn_del.setStyleSheet("color: #ef4444; font-weight: bold; border: 1px solid #fca5a5; border-radius: 3px; background-color: #fef2f2; padding: 0;")
            btn_del.clicked.connect(lambda _, p=pt: self._on_delete_single_point(p))
            self.tbl_points.setCellWidget(row, 5, btn_del)

    # ==========================================
    # Condition (Module) Management Methods
    # ==========================================
    def _get_active_condition(self) -> Optional[Condition]:
        """Returns the active Condition (from linked Condition module if condition_id is set, else scenario.condition)."""
        if not self.current_scenario:
            return None
        if getattr(self.current_scenario, "condition_id", None) and self.project:
            cond = self.project.find_condition(self.current_scenario.condition_id)
            if cond is not None:
                return cond
        return self.current_scenario.condition

    def _populate_condition_combo(self):
        """Populates condition combobox with (인스턴트 인식 조건) and project condition modules."""
        if not hasattr(self, "combo_condition"):
            return
        self.combo_condition.blockSignals(True)
        self.combo_condition.clear()
        self.combo_condition.addItem("(인스턴트 인식 조건)", "")

        selected_idx = 0
        if self.project:
            for idx, cond in enumerate(self.project.conditions, start=1):
                c_num = getattr(cond, "condition_number", idx)
                self.combo_condition.addItem(f"🔗 [C{c_num}] {cond.name} ({len(cond.points)}개 포인트)", cond.id)
                if self.current_scenario and getattr(self.current_scenario, "condition_id", None) == cond.id:
                    selected_idx = idx

        self.combo_condition.setCurrentIndex(selected_idx)
        self.combo_condition.blockSignals(False)
        self._update_condition_status_label()

    def _update_condition_status_label(self):
        if not hasattr(self, "lbl_cond_mod_status"):
            return
        if not self.current_scenario:
            self.lbl_cond_mod_status.setText("")
            self.btn_unlink_cond.setEnabled(False)
            return

        cond_id = getattr(self.current_scenario, "condition_id", None)
        if cond_id and self.project:
            cond = self.project.find_condition(cond_id)
            if cond:
                seq_info = ""
                if cond.action_sequence_id:
                    linked_seq = self.project.find_action_sequence(cond.action_sequence_id)
                    if linked_seq:
                        seq_info = f" ➔ 액션연결: [A{linked_seq.sequence_number}] {linked_seq.name}"
                self.lbl_cond_mod_status.setText(f"🔗 공용 인식조건 [C{cond.condition_number}] '{cond.name}' 연결됨{seq_info}")
                self.lbl_cond_mod_status.setStyleSheet("color: #2563eb; font-size: 8pt; font-weight: bold; padding: 1px 2px;")
                self.btn_unlink_cond.setEnabled(True)
                return
        self.lbl_cond_mod_status.setText("⚡ 인스턴트 인식 조건 (모듈화하여 재사용하려면 '조건으로 등록'을 누르세요)")
        self.lbl_cond_mod_status.setStyleSheet("color: #64748b; font-size: 8pt; padding: 1px 2px;")
        self.btn_unlink_cond.setEnabled(False)

    def _on_condition_combo_changed(self, idx: int):
        if self._is_loading or not self.current_scenario:
            return
        self._record_undo_state()
        cond_id = self.combo_condition.currentData()
        self.current_scenario.condition_id = cond_id if cond_id else None

        eff_cond = self._get_active_condition()
        if eff_cond:
            # If this condition has a default action_sequence_id, auto-link to scenario
            if eff_cond.action_sequence_id and getattr(self.current_scenario, "sequence_id", None) != eff_cond.action_sequence_id:
                self.current_scenario.sequence_id = eff_cond.action_sequence_id
                self._populate_sequence_combo()
                self._refresh_actions_table()
            elif getattr(self.current_scenario, "sequence_id", None) and not eff_cond.action_sequence_id:
                eff_cond.action_sequence_id = self.current_scenario.sequence_id

            idx_op = self.combo_cond_logic.findData(eff_cond.logic_operator)
            if idx_op >= 0:
                self.combo_cond_logic.setCurrentIndex(idx_op)
            self.chk_has_condition.setChecked(True)
        else:
            self.chk_has_condition.setChecked(False)

        self._update_condition_status_label()
        self._refresh_points_table()
        self._update_reference_thumbnails()
        self._mark_dirty()
        self._on_field_changed()

    def _on_save_as_new_condition(self):
        if not self.current_scenario:
            return
        eff_cond = self._get_active_condition()
        default_name = eff_cond.name if (eff_cond and eff_cond.name) else f"{self.current_scenario.name} 인식조건"
        name, ok = QInputDialog.getText(self, "새 인식조건 모듈 등록", "인식조건 이름:", text=default_name)
        if not ok or not name.strip():
            return
        self._record_undo_state()
        points = copy.deepcopy(eff_cond.points) if eff_cond else []
        logic_op = eff_cond.logic_operator if eff_cond else self.combo_cond_logic.currentData()
        ref_path = getattr(eff_cond, "reference_image_path", None) if eff_cond else None

        new_cond = Condition(
            name=name.strip(),
            logic_operator=logic_op or "AND",
            points=points,
            reference_image_path=ref_path,
            action_sequence_id=getattr(self.current_scenario, "sequence_id", None)
        )
        if self.project:
            self.project.add_condition(new_cond)
        self.current_scenario.condition_id = new_cond.id
        self._populate_condition_combo()
        self._refresh_points_table()
        self._update_reference_thumbnails()
        self._mark_dirty()
        self._on_field_changed()
        self.sig_log.emit("INFO", f"💾 새 인식조건 모듈 [C{new_cond.condition_number}] '{new_cond.name}'이 등록되어 연결되었습니다.")

    def _on_unlink_condition(self):
        if not self.current_scenario or not getattr(self.current_scenario, "condition_id", None):
            return
        self._record_undo_state()
        eff_cond = self._get_active_condition()
        if eff_cond:
            self.current_scenario.condition = copy.deepcopy(eff_cond)
        self.current_scenario.condition_id = None
        self._populate_condition_combo()
        self._refresh_points_table()
        self._mark_dirty()
        self._on_field_changed()
        self.sig_log.emit("INFO", f"🔓 인식조건 연결이 해제되어 '{self.current_scenario.name}' 인스턴트 인식 조건으로 복제되었습니다.")

    def _on_manage_conditions(self):
        self.sig_modules_manager_requested.emit()

    # ==========================================
    # Action Sequence (Module) Management Methods
    # ==========================================
    def _get_active_actions_list(self) -> List[Action]:
        """Returns the active list of actions (from linked ActionSequence if sequence_id is set, else scenario.actions)."""
        if not self.current_scenario:
            return []
        if getattr(self.current_scenario, "sequence_id", None) and self.project:
            seq = self.project.find_action_sequence(self.current_scenario.sequence_id)
            if seq is not None:
                return seq.actions
        return self.current_scenario.actions

    def _populate_sequence_combo(self):
        """Populates sequence combobox with (인스턴트 액션 시퀀스) and project action sequences."""
        if not hasattr(self, "combo_sequence"):
            return
        self.combo_sequence.blockSignals(True)
        self.combo_sequence.clear()
        self.combo_sequence.addItem("(인스턴트 액션 시퀀스)", "")

        selected_idx = 0
        if self.project:
            for idx, seq in enumerate(self.project.action_sequences, start=1):
                s_num = getattr(seq, "sequence_number", idx)
                self.combo_sequence.addItem(f"🔗 [A{s_num}] {seq.name} ({len(seq.actions)}개 액션)", seq.id)
                if self.current_scenario and getattr(self.current_scenario, "sequence_id", None) == seq.id:
                    selected_idx = idx

        self.combo_sequence.setCurrentIndex(selected_idx)
        self.combo_sequence.blockSignals(False)
        self._update_sequence_status_label()

    def _update_sequence_status_label(self):
        if not hasattr(self, "lbl_seq_status"):
            return
        if not self.current_scenario:
            self.lbl_seq_status.setText("")
            self.btn_unlink_seq.setEnabled(False)
            return

        seq_id = getattr(self.current_scenario, "sequence_id", None)
        if seq_id and self.project:
            seq = self.project.find_action_sequence(seq_id)
            if seq:
                self.lbl_seq_status.setText(f"🔗 공용 액션 시퀀스 [A{seq.sequence_number}] '{seq.name}' 연결됨 (수정 시 공유 시나리오에 공통 적용)")
                self.lbl_seq_status.setStyleSheet("color: #16a34a; font-size: 8pt; font-weight: bold; padding: 1px 2px;")
                self.btn_unlink_seq.setEnabled(True)
                return
        self.lbl_seq_status.setText("⚡ 인스턴트 액션 시퀀스 (모듈화하여 재사용하려면 '시퀀스로 등록'을 누르세요)")
        self.lbl_seq_status.setStyleSheet("color: #64748b; font-size: 8pt; padding: 1px 2px;")
        self.btn_unlink_seq.setEnabled(False)

    def _on_sequence_combo_changed(self, idx: int):
        if self._is_loading or not self.current_scenario:
            return
        self._record_undo_state()
        seq_id = self.combo_sequence.currentData()
        self.current_scenario.sequence_id = seq_id if seq_id else None

        # Wire with condition's action_sequence_id
        eff_cond = self._get_active_condition()
        if eff_cond and self.current_scenario.sequence_id:
            eff_cond.action_sequence_id = self.current_scenario.sequence_id

        self._update_sequence_status_label()
        self._update_condition_status_label()
        self._refresh_actions_table()
        self._mark_dirty()
        self._on_field_changed()

    def _on_save_as_new_sequence(self):
        if not self.current_scenario:
            return
        default_name = f"{self.current_scenario.name} 액션 시퀀스"
        name, ok = QInputDialog.getText(self, "새 액션 시퀀스 모듈 등록", "액션 시퀀스 이름:", text=default_name)
        if not ok or not name.strip():
            return
        self._record_undo_state()
        new_seq = ActionSequence(
            name=name.strip(),
            actions=copy.deepcopy(self._get_active_actions_list()),
            last_action_image_path=getattr(self.current_scenario, "last_action_image_path", None)
        )
        if self.project:
            self.project.add_action_sequence(new_seq)
        self.current_scenario.sequence_id = new_seq.id

        eff_cond = self._get_active_condition()
        if eff_cond:
            eff_cond.action_sequence_id = new_seq.id

        self._populate_sequence_combo()
        self._update_condition_status_label()
        self._refresh_actions_table()
        self._mark_dirty()
        self._on_field_changed()
        self.sig_log.emit("INFO", f"💾 새 액션 시퀀스 모듈 [A{new_seq.sequence_number}] '{new_seq.name}'이 등록되어 연결되었습니다.")

    def _on_unlink_sequence(self):
        if not self.current_scenario or not getattr(self.current_scenario, "sequence_id", None):
            return
        self._record_undo_state()
        active_acts = self._get_active_actions_list()
        self.current_scenario.actions = copy.deepcopy(active_acts)
        self.current_scenario.sequence_id = None
        self._populate_sequence_combo()
        self._refresh_actions_table()
        self._mark_dirty()
        self._on_field_changed()
        self.sig_log.emit("INFO", f"🔓 시퀀스 연결이 해제되어 '{self.current_scenario.name}' 인스턴트 액션 시퀀스로 복제되었습니다.")

    def _on_manage_sequences(self):
        if not self.project:
            return
        from ui.action_sequence_manager_dialog import ActionSequenceManagerDialog
        cur_seq_id = getattr(self.current_scenario, "sequence_id", None) if self.current_scenario else None
        dlg = ActionSequenceManagerDialog(self.project, current_sequence_id=cur_seq_id, parent=self)
        if dlg.exec_() == ActionSequenceManagerDialog.Accepted:
            if self.current_scenario and dlg.selected_sequence_id:
                self._record_undo_state()
                self.current_scenario.sequence_id = dlg.selected_sequence_id
                self._mark_dirty()
                self._on_field_changed()
        self._populate_sequence_combo()
        self._refresh_actions_table()

    def _refresh_actions_table(self):
        if not self.current_scenario:
            self.tbl_actions.setRowCount(0)
            return

        actions = self._get_active_actions_list()
        self.tbl_actions.setRowCount(len(actions))

        for row, act in enumerate(actions):
            # 0. Action Numbering (a1, a2, a3...)
            it_no = QTableWidgetItem(f"a{row + 1}")
            it_no.setTextAlignment(Qt.AlignCenter)
            it_no.setToolTip(f"액션 고유 번호 a{row + 1}")
            it_no.setFlags(it_no.flags() & ~Qt.ItemIsEditable)
            self.tbl_actions.setItem(row, 0, it_no)

            # 1. Action Type (상세 설정 내용을 통합하여 간략 표기)
            if act.action_type == "mouse_click":
                btn_name = {"left": "좌", "right": "우", "middle": "휠"}.get(act.mouse_button, act.mouse_button)
                if act.click_type == "double":
                    type_str = f"🖱️ 더블{btn_name}클릭"
                elif act.repeat_count > 1:
                    type_str = f"🖱️ {btn_name}클릭({act.repeat_count}회)"
                else:
                    type_str = f"🖱️ {btn_name}클릭"
            elif act.action_type == "mouse_drag":
                type_str = f"↔️ 드래그({act.drag_duration_ms}ms)"
            elif act.action_type == "key_press":
                type_str = "⌨️ 키 조합" if act.modifiers else "⌨️ 키 입력"
            elif act.action_type == "text_type":
                type_str = "📝 텍스트"
            elif act.action_type == "delay":
                type_str = "⏳ 대기"
            elif act.action_type == "sound_beep":
                type_str = "🔔 비프음"
            elif act.action_type == "log_message":
                type_str = "📋 로그"
            else:
                type_str = act.action_type

            it_type = QTableWidgetItem(type_str)
            it_type.setTextAlignment(Qt.AlignCenter)
            it_type.setFlags(it_type.flags() & ~Qt.ItemIsEditable)
            self.tbl_actions.setItem(row, 1, it_type)

            # 2. Target / Param
            if act.action_type == "mouse_click":
                target_str = f"({act.x}, {act.y})"
            elif act.action_type == "mouse_drag":
                target_str = f"({act.x}, {act.y}) ➔ ({act.end_x}, {act.end_y})"
            elif act.action_type == "key_press":
                if act.modifiers:
                    target_str = f"[{'+'.join(act.modifiers)}+{act.key}]"
                else:
                    target_str = f"[{act.key}]"
            elif act.action_type == "text_type":
                target_str = f'"{act.text}"'
            elif act.action_type == "delay":
                target_str = f"{act.delay_seconds:.1f}초"
            elif act.action_type == "sound_beep":
                target_str = f"{act.beep_freq}Hz ({act.beep_duration_ms}ms)"
            elif act.action_type == "log_message":
                target_str = act.log_text if act.log_text else "-"
            else:
                target_str = "-"

            it_target = QTableWidgetItem(target_str)
            it_target.setTextAlignment(Qt.AlignCenter)
            it_target.setFlags(it_target.flags() & ~Qt.ItemIsEditable)
            self.tbl_actions.setItem(row, 2, it_target)

            # 3. Anti-ban Coord Offset Option (평상시 깔끔한 텍스트, 클릭 시 콤보박스 편집)
            if act.action_type in ("mouse_click", "mouse_drag"):
                ab_mode = getattr(act, "coord_anti_ban", "weak")
                offset_map = {"weak": "약", "strong": "강", "none": "해제"}
                offset_str = offset_map.get(ab_mode, "약")
                it_offset = QTableWidgetItem(offset_str)
                it_offset.setTextAlignment(Qt.AlignCenter)
                it_offset.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
                it_offset.setToolTip("클릭하여 안티밴 좌표 오프셋 수정 (약 / 강 / 해제)")
            else:
                it_offset = QTableWidgetItem("-")
                it_offset.setTextAlignment(Qt.AlignCenter)
                it_offset.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.tbl_actions.setItem(row, 3, it_offset)

            # 4. Delay (평상시 깔끔한 텍스트, 클릭 시 상하 화살표 없는 직접 입력 스핀박스 편집)
            delay_str = f"{act.delay_seconds:.1f}s" if act.delay_seconds > 0 else "-"
            it_delay = QTableWidgetItem(delay_str)
            it_delay.setTextAlignment(Qt.AlignCenter)
            it_delay.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
            it_delay.setToolTip("클릭하여 대기 시간 직접 입력 (초)")
            self.tbl_actions.setItem(row, 4, it_delay)

            # 5. Log Column (평상시 깔끔한 텍스트, 클릭 시 텍스트필드 직접 입력 편집)
            cur_log = getattr(act, "custom_log", "")
            if not cur_log and act.action_type == "log_message":
                cur_log = getattr(act, "log_text", "")
            it_log = QTableWidgetItem(cur_log if cur_log else "-")
            if cur_log:
                it_log.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                it_log.setToolTip(cur_log)
            else:
                it_log.setTextAlignment(Qt.AlignCenter)
                it_log.setToolTip("클릭하여 로그 문구 입력 (비워두면 꺼짐)")
            it_log.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
            self.tbl_actions.setItem(row, 5, it_log)

        # 내용과 줄바꿈에 맞춰 행 높이 자동 조절
        self.tbl_actions.resizeRowsToContents()

    def _get_action_at(self, row: int) -> Optional[Action]:
        """Safely returns the Action instance at row index in current scenario or active sequence."""
        acts = self._get_active_actions_list()
        if 0 <= row < len(acts):
            return acts[row]
        return None

    def _on_action_cell_clicked(self, row: int, col: int):
        """Single click on editable column opens inline editor immediately."""
        if col in (3, 4, 5):
            item = self.tbl_actions.item(row, col)
            if item and (item.flags() & Qt.ItemIsEditable):
                self.tbl_actions.editItem(item)

    def _on_action_cell_double_clicked(self, row: int, col: int):
        """Double clicking type/coord columns opens SingleActionDialog."""
        if col in (0, 1, 2):
            self._on_edit_action()

    def _on_inline_offset_changed(self, act: Action, new_mode: str):
        """Inline handler for changing action anti-ban offset in table."""
        if self._is_loading or not self.current_scenario:
            return
        if getattr(act, "coord_anti_ban", "weak") != new_mode:
            self._record_undo_state()
            act.coord_anti_ban = new_mode
            self._mark_dirty()
            self._on_field_changed()

    def _on_inline_delay_changed(self, act: Action, new_delay: float):
        """Inline handler for changing action delay in table."""
        if self._is_loading or not self.current_scenario:
            return
        if round(getattr(act, "delay_seconds", 0.0), 2) != round(new_delay, 2):
            self._record_undo_state()
            act.delay_seconds = new_delay
            self._mark_dirty()
            self._on_field_changed()

    def _on_inline_log_changed(self, act: Action, new_log: str, edit_widget: Optional[QLineEdit] = None):
        """Inline handler for changing action log message in table."""
        if self._is_loading or not self.current_scenario:
            return
        clean_log = new_log.strip()
        if getattr(act, "custom_log", "") != clean_log:
            self._record_undo_state()
            act.custom_log = clean_log
            if edit_widget:
                edit_widget.setToolTip(clean_log if clean_log else "로그 문구 (비워두면 꺼짐)")
            self._mark_dirty()
            self._on_field_changed()

    def _on_action_row_reordered(self, from_row: int, to_row: int):
        """Reorders actions in the current scenario via safe drag-and-drop."""
        if not self.current_scenario or from_row == to_row:
            return
        acts = self._get_active_actions_list()
        if 0 <= from_row < len(acts) and 0 <= to_row < len(acts):
            self._record_undo_state()
            item = acts.pop(from_row)
            acts.insert(to_row, item)
            self._refresh_actions_table()
            self.tbl_actions.selectRow(to_row)
            self._mark_dirty()
            self._on_field_changed()
            self.sig_log.emit("INFO", f"↕️ 액션 순서 이동: a{from_row + 1} ➔ a{to_row + 1}")

    # ==========================================
    # Field Change Handlers
    # ==========================================
    def _on_scenario_number_changed(self, val: int):
        if self._is_loading or not self.current_scenario:
            return
        self._record_undo_state()
        self.current_scenario.scenario_number = val
        self._mark_dirty()

    def _on_field_changed(self):
        if self._is_loading or not self.current_scenario:
            return

        self._record_undo_state()

        self.current_scenario.name = self.txt_name.text()
        self.current_scenario.enabled = self.chk_enabled.isChecked()

        self.current_scenario.on_match = self.combo_on_match.currentData()
        self.current_scenario.jump_target_on_match = self.combo_jump_match.currentData() if self.current_scenario.on_match == "jump" else ""

        self.current_scenario.on_mismatch = self.combo_on_mismatch.currentData()
        self.current_scenario.jump_target_on_mismatch = self.combo_jump_mismatch.currentData() if self.current_scenario.on_mismatch == "jump" else ""

        if hasattr(self, "combo_retry_fail_action"):
            self.current_scenario.retry_fail_action = self.combo_retry_fail_action.currentData() or "stop"
        if hasattr(self, "combo_retry_fail_jump"):
            self.current_scenario.retry_fail_jump_target = self.combo_retry_fail_jump.currentData() if self.current_scenario.retry_fail_action == "jump" else ""

        self.current_scenario.retry_max_count = self.spin_retries.value()
        self.current_scenario.retry_interval_sec = self.spin_retry_sec.value()
        self.current_scenario.post_delay_seconds = self.spin_post_delay.value()
        if hasattr(self, "txt_action_log"):
            self.current_scenario.custom_log = self.txt_action_log.text().strip()

        if self.current_scenario.condition:
            self.current_scenario.condition.logic_operator = self.combo_cond_logic.currentData()

        # Node type & Loop controls
        if hasattr(self, "combo_node_type"):
            self.current_scenario.node_type = self.combo_node_type.currentData() or "normal"
        if hasattr(self, "combo_loop_mode"):
            self.current_scenario.loop_mode = self.combo_loop_mode.currentData() or "count"
        if hasattr(self, "spin_loop_cnt"):
            self.current_scenario.loop_count = self.spin_loop_cnt.value()

        self._update_reference_thumbnails()
        self._mark_dirty()

    def _on_node_type_changed(self):
        if self._is_loading or not self.current_scenario:
            return
        nt = self.combo_node_type.currentData() or "normal"
        self.current_scenario.node_type = nt
        self._update_node_type_visibility()
        self._on_field_changed()

    def _on_loop_mode_changed(self):
        if self._is_loading or not self.current_scenario:
            return
        lm = self.combo_loop_mode.currentData() or "count"
        self.current_scenario.loop_mode = lm
        if lm in ("until_match", "while_match") and not self.current_scenario.condition:
            self.chk_has_condition.setChecked(True)
        self._on_field_changed()

    def _update_node_type_visibility(self):
        if not self.current_scenario:
            return
        nt = self.combo_node_type.currentData() or "normal"
        is_start = (nt == "loop_start")
        is_end = (nt == "loop_end")

        self.loop_container.setVisible(is_start)
        self.lbl_loop_end_info.setVisible(is_end)

        if is_start:
            self.condition_card.setTitle("👁️ 루프 탈출 / 지속 인식 조건 (Eye)")
            self.condition_card.setVisible(True)
            self.branch_card.setVisible(False)
            self.action_card.setVisible(True)
        elif is_end:
            self.condition_card.setVisible(False)
            self.branch_card.setVisible(False)
            self.action_card.setVisible(False)
        else:
            self.condition_card.setTitle("👁️ 색상 인식 조건 (Eye)")
            self.condition_card.setVisible(True)
            self.branch_card.setVisible(True)
            self.action_card.setVisible(True)

    def _on_match_branch_changed(self):
        self._update_branch_visibility()
        self._on_field_changed()

    def _on_mismatch_branch_changed(self):
        self._update_branch_visibility()
        self._on_field_changed()

    def _on_has_condition_toggled(self, state):
        if self._is_loading or not self.current_scenario:
            return

        if state == Qt.Checked:
            eff_cond = self._get_active_condition()
            if not eff_cond:
                self.current_scenario.condition = Condition(
                    name=f"{self.current_scenario.name} 조건",
                    logic_operator=self.combo_cond_logic.currentData(),
                    points=[]
                )
        else:
            self.current_scenario.condition = None
            self.current_scenario.condition_id = None
            self._populate_condition_combo()

        self._refresh_points_table()
        self._update_condition_status_label()
        self._on_field_changed()

    def _on_point_tolerance_changed(self, point: ColorPoint, val: int):
        point.tolerance = val
        self.sig_scenario_changed.emit(self.current_scenario)

    def _on_point_mode_changed(self, point: ColorPoint, idx: int):
        point.match_mode = "not_match" if idx == 1 else "match"
        self.sig_scenario_changed.emit(self.current_scenario)

    # ==========================================
    # Condition Point Management & Combination
    # ==========================================
    def _on_copy_condition_from_other(self):
        if not self.project or not self.current_scenario:
            return
        other_scenarios = [s for s in self.project.scenarios if s.id != self.current_scenario.id and s.get_effective_condition(self.project) and s.get_effective_condition(self.project).points]
        if not other_scenarios:
            QMessageBox.information(self, "조건 가져오기", "가져올 수 있는 조건을 가진 다른 시나리오가 없습니다.")
            return

        menu = QMenu(self)
        for s in other_scenarios:
            s_cond = s.get_effective_condition(self.project)
            action = menu.addAction(f"고유 s{s.scenario_number} [{s.name}] - {len(s_cond.points)}개 포인트 ({s_cond.logic_operator})")
            action.triggered.connect(lambda checked, src=s: self._copy_condition_from(src))
        menu.exec_(self.btn_copy_cond.mapToGlobal(self.btn_copy_cond.rect().bottomLeft()))

    def _copy_condition_from(self, source_scenario: Scenario):
        src_cond = source_scenario.get_effective_condition(self.project) if hasattr(source_scenario, "get_effective_condition") else source_scenario.condition
        if not src_cond:
            return
        eff_cond = self._get_active_condition()
        if self.current_scenario.condition_id and self.project:
            mod_cond = self.project.find_condition(self.current_scenario.condition_id)
            if mod_cond:
                mod_cond.points = copy.deepcopy(src_cond.points)
                mod_cond.logic_operator = src_cond.logic_operator
                mod_cond.reference_image_path = src_cond.reference_image_path
        else:
            self.current_scenario.condition = copy.deepcopy(src_cond)
        self.chk_has_condition.setChecked(True)
        idx_op = self.combo_cond_logic.findData(src_cond.logic_operator)
        if idx_op >= 0:
            self.combo_cond_logic.setCurrentIndex(idx_op)
        self._refresh_points_table()
        self._update_reference_thumbnails()
        self._on_field_changed()
        self.sig_log.emit("INFO", f"[{self.current_scenario.name}] 고유 s{source_scenario.scenario_number} [{source_scenario.name}]의 인식 조건을 복사하여 조합했습니다.")

    def _on_open_canvas_editor(self):
        if not self.current_scenario:
            return

        eff_cond = self._get_active_condition()
        if not eff_cond:
            eff_cond = Condition(name=f"{self.current_scenario.name} 조건")
            self.current_scenario.condition = eff_cond

        try:
            dlg = ConditionEditorDialog(
                condition=eff_cond,
                project=self.project,
                current_scenario_id=self.current_scenario.id,
                target_hwnd=self.target_hwnd,
                parent=self
            )
            if dlg.exec_() == ConditionEditorDialog.Accepted:
                updated = dlg.get_condition()
                eff_cond.points = updated.points
                eff_cond.logic_operator = updated.logic_operator
                eff_cond.reference_image_path = updated.reference_image_path
                self._refresh_points_table()
                self._update_reference_thumbnails()
                self._on_field_changed()
        except Exception as e:
            self.sig_log.emit("ERROR", f"캔버스 편집기 실행 오류: {e}")
            QMessageBox.critical(self, "오류", f"캔버스 편집기를 여는 중 오류가 발생했습니다:\n{e}")

    def _on_add_point(self):
        if not self.current_scenario:
            return
        eff_cond = self._get_active_condition()
        if not eff_cond:
            eff_cond = Condition(name=f"{self.current_scenario.name} 조건")
            self.current_scenario.condition = eff_cond
            self.chk_has_condition.setChecked(True)

        new_pt = ColorPoint(x=100, y=100, r=255, g=255, b=255, tolerance=20)
        eff_cond.points.append(new_pt)
        self._refresh_points_table()
        self.tbl_points.selectRow(len(eff_cond.points) - 1)
        self._on_field_changed()

    def _on_delete_single_point(self, pt: ColorPoint):
        eff_cond = self._get_active_condition()
        if not self.current_scenario or not eff_cond:
            return
        if pt in eff_cond.points:
            self._record_undo_state()
            eff_cond.points.remove(pt)
            self._refresh_points_table()
            self._on_field_changed()
            self.sig_log.emit("INFO", f"🗑️ 인식 조건 포인트 ({pt.x}, {pt.y}) 삭제됨")

    def _on_delete_point(self):
        eff_cond = self._get_active_condition()
        if not self.current_scenario or not eff_cond:
            return
        rows = self.tbl_points.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if 0 <= row < len(eff_cond.points):
            self._record_undo_state()
            del eff_cond.points[row]
            self._refresh_points_table()
            self._on_field_changed()
            self.sig_log.emit("INFO", f"🗑️ 선택한 인식 조건 포인트 삭제됨")

    def _on_test_condition_now(self):
        eff_cond = self._get_active_condition()
        if not self.current_scenario or not eff_cond:
            QMessageBox.information(self, "조건 없음", "테스트할 조건이 없습니다.")
            return

        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "상단에서 타겟 게임 창을 먼저 선택해주세요.")
            return

        cond = eff_cond
        try:
            matched, details = ConditionEvaluator.evaluate(cond, self.target_hwnd)

            self.lbl_cond_test_result.setVisible(True)
            if matched:
                self.lbl_cond_test_result.setText(f"✅ [일치] {len(cond.points)}개 포인트 검사 완료: 조건 부합!")
                self.lbl_cond_test_result.setStyleSheet("color: #16a34a; font-weight: bold;")
                self.sig_log.emit("SUCCESS", f"[{self.current_scenario.name}] 실시간 판정 테스트: 조건 일치!")
            else:
                fail_count = sum(1 for d in details if not d.get("passed", False))
                self.lbl_cond_test_result.setText(f"❌ [불일치] 총 {len(cond.points)}개 중 {fail_count}개 포인트 불일치")
                self.lbl_cond_test_result.setStyleSheet("color: #dc2626; font-weight: bold;")
                mismatch_info = ConditionEvaluator.format_mismatch_log(details, max_items=5)
                mismatch_str = f"\n  └ 불일치: {mismatch_info}" if mismatch_info else ""
                self.sig_log.emit("WARN", f"[{self.current_scenario.name}] 실시간 판정 테스트: 불일치 ({fail_count}개 포인트 오차 초과){mismatch_str}")
        except Exception as e:
            self.lbl_cond_test_result.setVisible(True)
            self.lbl_cond_test_result.setText(f"⚠️ 판정 오류: {e}")
            self.lbl_cond_test_result.setStyleSheet("color: #dc2626; font-weight: bold;")
            self.sig_log.emit("ERROR", f"[{self.current_scenario.name}] 판정 테스트 오류: {e}")

    # ==========================================
    # Action Sequence Management & Combination
    # ==========================================
    def _on_copy_actions_from_other(self):
        if not self.project or not self.current_scenario:
            return
        other_scenarios = [s for s in self.project.scenarios if s.id != self.current_scenario.id and (s.actions or getattr(s, "sequence_id", None))]
        if not other_scenarios:
            QMessageBox.information(self, "액션 가져오기", "가져올 수 있는 액션을 가진 다른 시나리오가 없습니다.")
            return

        menu = QMenu(self)
        for s in other_scenarios:
            eff_acts = s.get_effective_actions(self.project) if hasattr(s, "get_effective_actions") else s.actions
            action = menu.addAction(f"고유 s{s.scenario_number} [{s.name}] - {len(eff_acts)}개 액션 ({s.get_actions_summary(self.project)})")
            action.triggered.connect(lambda checked, src=s: self._copy_actions_from(src))
        menu.exec_(self.btn_copy_act.mapToGlobal(self.btn_copy_act.rect().bottomLeft()))

    def _copy_actions_from(self, source_scenario: Scenario):
        source_acts = source_scenario.get_effective_actions(self.project) if hasattr(source_scenario, "get_effective_actions") else source_scenario.actions
        if not source_acts:
            return
        self._record_undo_state()
        acts = self._get_active_actions_list()
        acts.clear()
        acts.extend(copy.deepcopy(source_acts))
        if self.current_scenario.sequence_id is None:
            self.current_scenario.actions = copy.deepcopy(acts)
        self._refresh_actions_table()
        self._mark_dirty()
        self._on_field_changed()
        self.sig_log.emit("INFO", f"[{self.current_scenario.name}] 고유 s{source_scenario.scenario_number} [{source_scenario.name}]의 액션 시퀀스를 복사하여 조합했습니다.")

    def _on_quick_add_action(self, action_type: str):
        if not self.current_scenario:
            return

        act = Action(action_type=action_type)
        if action_type == "mouse_click":
            act.x, act.y = 100, 100
            act.delay_seconds = 0.5
        elif action_type == "mouse_drag":
            act.x, act.y = 100, 100
            act.end_x, act.end_y = 300, 300
            act.drag_duration_ms = 500
            act.delay_seconds = 0.5
        elif action_type == "key_press":
            act.key = "Enter"
            act.delay_seconds = 0.5
        elif action_type == "text_type":
            act.text = "Hello"
            act.delay_seconds = 0.5
        elif action_type == "delay":
            act.delay_seconds = 2.0
        elif action_type == "log_message":
            act.log_text = "액션 실행 완료"
            act.delay_seconds = 0.2

        self._record_undo_state()
        acts = self._get_active_actions_list()
        acts.append(act)
        if self.current_scenario.sequence_id is None:
            self.current_scenario.actions = acts
        self._refresh_actions_table()
        self.tbl_actions.selectRow(len(acts) - 1)
        self._mark_dirty()
        self._on_field_changed()

    def _on_edit_action(self):
        if not self.current_scenario:
            return
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        acts = self._get_active_actions_list()
        if not (0 <= row < len(acts)):
            return
        act = acts[row]

        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        last_action_img = getattr(self.current_scenario, "last_action_image_path", None) if self.current_scenario else None
        ref_path = to_absolute_path(last_action_img) if last_action_img else CoordinatePickerDialog.get_last_used_image_path()
        dlg = SingleActionDialog(
            action=act,
            target_hwnd=self.target_hwnd,
            reference_image_path=ref_path,
            scenario=self.current_scenario,
            parent=self
        )
        if dlg.exec_() == SingleActionDialog.Accepted:
            self._record_undo_state()
            acts[row] = dlg.get_action()
            if hasattr(dlg, "reference_image_path") and dlg.reference_image_path:
                rel_p = to_relative_path(dlg.reference_image_path)
                self.current_scenario.last_action_image_path = rel_p
                if self.current_scenario.sequence_id and self.project:
                    seq = self.project.find_action_sequence(self.current_scenario.sequence_id)
                    if seq:
                        seq.last_action_image_path = rel_p
                CoordinatePickerDialog.set_last_used_image_path(dlg.reference_image_path)
            self._refresh_actions_table()
            self.tbl_actions.selectRow(row)
            self._mark_dirty()
            self._on_field_changed()

    def _on_start_operation_recording(self):
        if not self.current_scenario:
            return
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "먼저 메인 창 상단에서 타겟 게임 창을 선택해주세요.")
            return
        from ui.recording_hud import RecordingHud
        hud = RecordingHud(target_hwnd=self.target_hwnd, parent=self)
        if hud.exec_() == RecordingHud.Accepted:
            recorded = hud.recorder.recorded_actions
            if recorded:
                self._record_undo_state()
                acts = self._get_active_actions_list()
                acts.extend(recorded)
                if self.current_scenario.sequence_id is None:
                    self.current_scenario.actions = acts
                self._refresh_actions_table()
                self._mark_dirty()
                self._on_field_changed()
                self.sig_log.emit("INFO", f"⏺️ 조작 녹화 완료: {len(recorded)}개 액션이 추가되었습니다.")

    def _on_pick_coord_for_selected_action(self):
        if not self.current_scenario:
            return
        rows = self.tbl_actions.selectionModel().selectedRows()
        row = rows[0].row() if rows else 0
        acts = self._get_active_actions_list()
        act = acts[row] if (acts and 0 <= row < len(acts)) else None

        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        last_action_img = getattr(self.current_scenario, "last_action_image_path", None) if self.current_scenario else None
        ref_path = to_absolute_path(last_action_img) if last_action_img else CoordinatePickerDialog.get_last_used_image_path()
        dlg = CoordinatePickerDialog(
            image_path=ref_path,
            target_hwnd=self.target_hwnd,
            initial_x=act.x if act else 0,
            initial_y=act.y if act else 0,
            drag_mode=(act.action_type == "mouse_drag") if act else False,
            initial_end_x=act.end_x if (act and act.action_type == "mouse_drag") else 0,
            initial_end_y=act.end_y if (act and act.action_type == "mouse_drag") else 0,
            actions=acts,
            selected_action_index=row if act else 0,
            scenario=self.current_scenario,
            project=self.project,
            parent=self
        )
        if dlg.exec_() == CoordinatePickerDialog.Accepted:
            self._record_undo_state()
            new_acts = dlg.get_actions()
            acts.clear()
            acts.extend(new_acts)
            if dlg.current_image_path:
                rel_p = to_relative_path(dlg.current_image_path)
                self.current_scenario.last_action_image_path = rel_p
                if self.current_scenario.sequence_id and self.project:
                    seq = self.project.find_action_sequence(self.current_scenario.sequence_id)
                    if seq:
                        seq.last_action_image_path = rel_p
                CoordinatePickerDialog.set_last_used_image_path(dlg.current_image_path)
            self._refresh_actions_table()
            self._mark_dirty()
            self._on_field_changed()
            self.sig_log.emit("INFO", "🎯 액션 시퀀스 좌표 및 목록이 업데이트되었습니다.")

    def _on_delete_action(self):
        if not self.current_scenario:
            return
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        acts = self._get_active_actions_list()
        if not (0 <= row < len(acts)):
            return
        self._record_undo_state()
        del acts[row]
        self._refresh_actions_table()
        self._mark_dirty()
        self._on_field_changed()

    def _on_move_action_up(self):
        if not self.current_scenario:
            return
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows or rows[0].row() == 0:
            return
        r = rows[0].row()
        acts = self._get_active_actions_list()
        if not (1 <= r < len(acts)):
            return
        self._record_undo_state()
        acts[r - 1], acts[r] = acts[r], acts[r - 1]
        self._refresh_actions_table()
        self.tbl_actions.selectRow(r - 1)
        self._mark_dirty()
        self._on_field_changed()

    def _on_move_action_down(self):
        if not self.current_scenario:
            return
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        acts = self._get_active_actions_list()
        if not (0 <= r < len(acts) - 1):
            return
        self._record_undo_state()
        acts[r + 1], acts[r] = acts[r], acts[r + 1]
        self._refresh_actions_table()
        self.tbl_actions.selectRow(r + 1)
        self._mark_dirty()
        self._on_field_changed()

    def _on_test_action_now(self):
        if not self.current_scenario:
            return
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "선택 필요", "실행할 액션을 목록에서 선택해주세요.")
            return
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "상단에서 타겟 게임 창을 먼저 선택해주세요.")
            return

        acts = self._get_active_actions_list()
        if not (0 <= rows[0].row() < len(acts)):
            return
        act = acts[rows[0].row()]
        use_anti_ban = getattr(self.project, "anti_ban_enabled", False) if self.project else False
        should_anti_ban = use_anti_ban
        offset_sec = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0))) if self.project else 1.0
        jitter = round(random.uniform(0.0, offset_sec), 3) if (should_anti_ban and offset_sec > 0) else 0.0

        coord_mode = getattr(act, "coord_anti_ban", "weak")
        if coord_mode == "none" or act.action_type not in ("mouse_click", "mouse_drag"):
            act_offset_range = 0
            coord_str = ""
        elif coord_mode == "strong":
            act_offset_range = getattr(self.project, "anti_ban_coord_strong", 15) if self.project else 15
            coord_str = f" [좌표 강 ±{act_offset_range}px]"
        else:
            act_offset_range = getattr(self.project, "anti_ban_coord_weak", 5) if self.project else 5
            coord_str = f" [좌표 약 ±{act_offset_range}px]"

        orig_t = act.delay_seconds if act.action_type == "delay" else getattr(act, "delay_seconds", 0.0)
        ab_t = round(orig_t + jitter, 2)
        sleep_total = ab_t if should_anti_ban else orig_t

        if act.action_type == "delay":
            act_msg = f"{sleep_total:.2f}초 (원본 {orig_t:.2f}초 + 안티밴 {jitter:.2f}초) 대기" if (should_anti_ban and jitter > 0) else f"{sleep_total:.1f}초 대기"
        else:
            time_str = f" (안티밴 +{jitter:.2f}초)" if (should_anti_ban and jitter > 0) else ""
            act_msg = f"{act.get_summary()}{coord_str}{time_str}"

        try:
            if act.action_type == "log_message":
                self.sig_log.emit("USER", f"  [사용자 로그] {act.log_text}")
            elif getattr(act, "custom_log", ""):
                self.sig_log.emit("USER", f"  [사용자 로그] {act.custom_log}")

            InputController.execute_action(
                act, self.target_hwnd,
                apply_anti_ban=use_anti_ban,
                offset_range=act_offset_range,
                min_delay=0.0,
                max_delay=offset_sec,
                precomputed_jitter=jitter
            )
            self.sig_log.emit("ACTION", f"테스트 액션 실행 완료: [{act_msg}]")
        except Exception as e:
            self.sig_log.emit("ERROR", f"액션 실행 실패: {e}")
            QMessageBox.critical(self, "실행 오류", f"액션 실행 중 오류 발생:\n{e}")

    def _on_test_all_actions_now(self):
        if not self.current_scenario:
            return
        actions = self._get_active_actions_list()
        if not actions:
            QMessageBox.information(self, "액션 없음", "실행할 액션이 시퀀스에 없습니다.")
            return
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "상단에서 타겟 게임 창을 먼저 선택해주세요.")
            return

        total = len(actions)
        self.sig_log.emit("INFO", f"▶ [{self.current_scenario.name}] 전체 액션 시퀀스 테스트 시작 (총 {total}개)...")
        scen_log = self.txt_action_log.text().strip() if hasattr(self, "txt_action_log") else getattr(self.current_scenario, "custom_log", "")
        if scen_log:
            self.sig_log.emit("USER", f"  [액션 로그] {scen_log}")

        if hasattr(self, "btn_test_all_act"):
            self.btn_test_all_act.setEnabled(False)
        if hasattr(self, "btn_test_act"):
            self.btn_test_act.setEnabled(False)

        use_anti_ban = getattr(self.project, "anti_ban_enabled", False) if self.project else False
        offset_sec = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0))) if self.project else 1.0

        try:
            for idx, act in enumerate(actions, 1):
                self.tbl_actions.selectRow(idx - 1)
                QApplication.processEvents()

                should_anti_ban = use_anti_ban
                jitter = round(random.uniform(0.0, offset_sec), 3) if (should_anti_ban and offset_sec > 0) else 0.0

                coord_mode = getattr(act, "coord_anti_ban", "weak")
                if coord_mode == "none" or act.action_type not in ("mouse_click", "mouse_drag"):
                    act_offset_range = 0
                    coord_str = ""
                elif coord_mode == "strong":
                    act_offset_range = getattr(self.project, "anti_ban_coord_strong", 15) if self.project else 15
                    coord_str = f" [좌표 강 ±{act_offset_range}px]"
                else:
                    act_offset_range = getattr(self.project, "anti_ban_coord_weak", 5) if self.project else 5
                    coord_str = f" [좌표 약 ±{act_offset_range}px]"

                orig_t = act.delay_seconds if act.action_type == "delay" else getattr(act, "delay_seconds", 0.0)
                ab_t = round(orig_t + jitter, 2)
                sleep_total = ab_t if should_anti_ban else orig_t

                if act.action_type == "delay":
                    act_msg = f"{sleep_total:.2f}초 (원본 {orig_t:.2f}초 + 안티밴 {jitter:.2f}초) 대기" if (should_anti_ban and jitter > 0) else f"{sleep_total:.1f}초 대기"
                else:
                    time_str = f" (안티밴 +{jitter:.2f}초)" if (should_anti_ban and jitter > 0) else ""
                    act_msg = f"{act.get_summary()}{coord_str}{time_str}"

                self.sig_log.emit("ACTION", f"  [{idx}/{total}] 액션 실행: {act_msg}")

                if act.action_type == "log_message":
                    self.sig_log.emit("USER", f"  [사용자 로그] {act.log_text}")
                elif getattr(act, "custom_log", ""):
                    self.sig_log.emit("USER", f"  [사용자 로그] {act.custom_log}")

                if act.action_type == "delay" and act.delay_seconds > 0.05:
                    remaining = sleep_total
                    while remaining > 0:
                        step_sleep = min(0.1, remaining)
                        time.sleep(step_sleep)
                        remaining -= step_sleep
                        QApplication.processEvents()
                else:
                    if self.target_hwnd:
                        InputController.execute_action(
                            act, self.target_hwnd,
                            apply_anti_ban=use_anti_ban,
                            offset_range=act_offset_range,
                            min_delay=0.0,
                            max_delay=offset_sec,
                            precomputed_jitter=jitter
                        )
                    else:
                        time.sleep(0.08)

                time.sleep(0.04)
                QApplication.processEvents()

                time.sleep(0.05)
                QApplication.processEvents()

            self.sig_log.emit("SUCCESS", f"✅ [{self.current_scenario.name}] 전체 액션 시퀀스({total}개) 테스트 실행 완료")
        except Exception as e:
            self.sig_log.emit("ERROR", f"액션 시퀀스 실행 중 오류: {e}")
            QMessageBox.critical(self, "실행 오류", f"액션 시퀀스 실행 중 오류 발생:\n{e}")
        finally:
            if hasattr(self, "btn_test_all_act"):
                self.btn_test_all_act.setEnabled(True)
            if hasattr(self, "btn_test_act"):
                self.btn_test_act.setEnabled(True)

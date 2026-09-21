"""
Target Window Picker Dialog for FGOA.
Lists visible windows and provides manual target resolution input with recommended presets.
"""
from typing import Optional, List, Tuple
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QMessageBox, QTabWidget, QWidget, QComboBox, QSpinBox,
    QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt, QTimer
from core.window_manager import WindowManager, WindowInfo


PRESET_RESOLUTIONS: List[Tuple[str, int, int]] = [
    ("📱 1920 × 1080 (FHD 16:9 - LDPlayer/블루스택/녹스 기본)", 1920, 1080),
    ("📱 1600 × 900 (HD+ 16:9 - 고해상도 앱플레이어)", 1600, 900),
    ("📱 1280 × 720 (HD 16:9 - 표준 앱플레이어)", 1280, 720),
    ("📱 2560 × 1440 (QHD 16:9 - 초고해상도 모니터)", 2560, 1440),
    ("📱 960 × 540 (qHD 16:9 - 저사양 멀티 앱플레이어)", 960, 540),
    ("📱 1600 × 940 (앱플레이어 창모드 기본값)", 1600, 940),
    ("📱 1080 × 1920 (세로 모드 FHD)", 1080, 1920),
    ("📱 720 × 1280 (세로 모드 HD)", 720, 1280),
    ("✏️ 사용자 직접 입력 (Custom)", 0, 0),
]


class WindowPickerDialog(QDialog):
    """
    Dialog for selecting a running application window or manually specifying
    a target resolution using recommended presets.
    """

    def __init__(
        self,
        current_hwnd: int = 0,
        current_width: int = 1600,
        current_height: int = 900,
        current_title: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("타겟 애플리케이션 창 및 해상도 선택")
        self.resize(760, 540)
        self.selected_window: Optional[WindowInfo] = None
        self.current_hwnd = current_hwnd
        self.current_width = current_width or 1600
        self.current_height = current_height or 900
        self.current_title = current_title or "가상 타겟 해상도"
        self.all_windows: List[WindowInfo] = []

        self._init_ui()
        self._refresh_window_list()

        # If current_hwnd is 0 and we have a remembered resolution, highlight Tab 2
        if self.current_hwnd == 0 and self.current_width > 0:
            self.tabs.setCurrentIndex(0)  # default to window list, but preset tab is ready

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Tab Widget: Running Windows vs Manual Resolution Input
        self.tabs = QTabWidget()

        # ==========================================
        # Tab 1: Running Windows List
        # ==========================================
        tab_list = QWidget()
        l_layout = QVBoxLayout(tab_list)
        l_layout.setContentsMargins(8, 8, 8, 8)
        l_layout.setSpacing(8)

        # Search bar & Refresh
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("창 제목 검색:"))
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("검색할 창 이름 입력 (예: LDPlayer, Nox, BlueStacks...)")
        self.txt_filter.textChanged.connect(self._filter_list)
        top_bar.addWidget(self.txt_filter)

        btn_refresh = QPushButton("🔄 새로고침")
        btn_refresh.clicked.connect(self._refresh_window_list)
        top_bar.addWidget(btn_refresh)
        l_layout.addLayout(top_bar)

        # Window Table
        self.tbl_windows = QTableWidget()
        self.tbl_windows.setColumnCount(4)
        self.tbl_windows.setHorizontalHeaderLabels(["HWND", "창 제목", "클라이언트 해상도", "PID"])
        self.tbl_windows.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_windows.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_windows.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_windows.itemDoubleClicked.connect(self._on_table_double_clicked)
        l_layout.addWidget(self.tbl_windows)

        # Help info
        info_lbl = QLabel("💡 상대 좌표는 선택한 창의 안쪽 클라이언트 영역(좌상단 0,0)을 기준으로 계산됩니다.")
        info_lbl.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        l_layout.addWidget(info_lbl)

        self.tabs.addTab(tab_list, "🖥️ 실행 중인 창 목록에서 선택")

        # ==========================================
        # Tab 2: Manual Target Resolution Input & Presets
        # ==========================================
        tab_manual = QWidget()
        m_layout = QVBoxLayout(tab_manual)
        m_layout.setContentsMargins(12, 12, 12, 12)
        m_layout.setSpacing(12)

        grp_preset = QGroupBox("추천 해상도 프리셋 선택")
        p_layout = QVBoxLayout(grp_preset)
        p_layout.setContentsMargins(12, 14, 12, 12)
        p_layout.setSpacing(10)

        lbl_preset_desc = QLabel("자주 사용하는 앱플레이어 및 모니터 해상도 프리셋을 선택하면 아래 가로/세로 값이 자동 채워집니다:")
        lbl_preset_desc.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        p_layout.addWidget(lbl_preset_desc)

        self.combo_presets = QComboBox()
        for name, w, h in PRESET_RESOLUTIONS:
            self.combo_presets.addItem(name, (w, h))
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        p_layout.addWidget(self.combo_presets)

        m_layout.addWidget(grp_preset)

        # Custom Dimensions Group
        grp_custom = QGroupBox("타겟 해상도 직접 지정")
        form_custom = QFormLayout(grp_custom)
        form_custom.setContentsMargins(12, 14, 12, 12)
        form_custom.setSpacing(12)

        # Width SpinBox
        self.spin_width = QSpinBox()
        self.spin_width.setRange(100, 7680)
        self.spin_width.setSingleStep(10)
        self.spin_width.setValue(self.current_width)
        form_custom.addRow("가로 너비 (Width, px):", self.spin_width)

        # Height SpinBox
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 4320)
        self.spin_height.setSingleStep(10)
        self.spin_height.setValue(self.current_height)
        form_custom.addRow("세로 높이 (Height, px):", self.spin_height)

        # Target Title
        self.txt_custom_title = QLineEdit(self.current_title or "가상 타겟 해상도")
        self.txt_custom_title.setPlaceholderText("타겟 명칭 입력 (예: LDPlayer 가상 해상도)")
        form_custom.addRow("타겟 명칭 / 라벨:", self.txt_custom_title)

        m_layout.addWidget(grp_custom)

        # Manual Info Banner
        manual_help = QLabel(
            "💡 게임 앱이 현재 PC에서 실행 중이지 않거나, 다른 기기용 시나리오/이미지를 작업할 때 유용합니다.\n"
            "   직접 지정한 해상도가 캔버스 편집기 및 시나리오 좌표의 기준(0, 0 ~ W, H)으로 적용됩니다."
        )
        manual_help.setStyleSheet(
            "background-color: #f1f5f9; color: #334155; padding: 8px 12px; "
            "border: 1px solid #cbd5e1; border-radius: 6px; font-size: 8.5pt;"
        )
        m_layout.addWidget(manual_help)
        m_layout.addStretch()

        self.tabs.addTab(tab_manual, "📐 해상도 직접 입력 (추천 프리셋)")
        layout.addWidget(self.tabs)

        # ==========================================
        # Bottom Action Bar
        # ==========================================
        bot_bar = QHBoxLayout()
        self.btn_activate = QPushButton("👁️ 선택 창 활성화 확인")
        self.btn_activate.clicked.connect(self._on_activate_clicked)
        bot_bar.addWidget(self.btn_activate)

        bot_bar.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        bot_bar.addWidget(btn_cancel)

        self.btn_select = QPushButton("🎯 타겟으로 선택 / 지정")
        self.btn_select.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 18px;")
        self.btn_select.clicked.connect(self._on_confirm_selection)
        bot_bar.addWidget(self.btn_select)

        layout.addLayout(bot_bar)

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, idx: int):
        self.btn_activate.setEnabled(idx == 0)
        if idx == 1:
            self.btn_select.setText("🎯 이 해상도로 직접 지정")
        else:
            self.btn_select.setText("🎯 타겟 창으로 선택")

    def _on_preset_changed(self, index: int):
        data = self.combo_presets.currentData()
        if data and data != (0, 0):
            w, h = data
            self.spin_width.setValue(w)
            self.spin_height.setValue(h)
            preset_name = self.combo_presets.currentText().split("(")[0].strip()
            self.txt_custom_title.setText(f"{preset_name} ({w}×{h})")

    def _refresh_window_list(self):
        self.all_windows = WindowManager.get_all_visible_windows()
        self._filter_list()

    def _filter_list(self):
        query = self.txt_filter.text().strip().lower()
        filtered = [w for w in self.all_windows if query in w.title.lower()]

        self.tbl_windows.setRowCount(len(filtered))
        selected_row = -1

        for row, w in enumerate(filtered):
            # HWND
            it_hwnd = QTableWidgetItem(f"{w.hwnd} (0x{w.hwnd:X})")
            it_hwnd.setTextAlignment(Qt.AlignCenter)
            self.tbl_windows.setItem(row, 0, it_hwnd)

            # Title
            it_title = QTableWidgetItem(w.title)
            self.tbl_windows.setItem(row, 1, it_title)

            # Resolution
            it_res = QTableWidgetItem(f"{w.client_width} × {w.client_height}")
            it_res.setTextAlignment(Qt.AlignCenter)
            self.tbl_windows.setItem(row, 2, it_res)

            # PID
            it_pid = QTableWidgetItem(str(w.pid))
            it_pid.setTextAlignment(Qt.AlignCenter)
            self.tbl_windows.setItem(row, 3, it_pid)

            # Store WindowInfo
            it_title.setData(Qt.UserRole, w)

            if w.hwnd == self.current_hwnd:
                selected_row = row

        if selected_row >= 0:
            self.tbl_windows.selectRow(selected_row)

    def _get_selected_window_info(self) -> Optional[WindowInfo]:
        rows = self.tbl_windows.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        item = self.tbl_windows.item(row, 1)
        if item:
            return item.data(Qt.UserRole)
        return None

    def _on_activate_clicked(self):
        win = self._get_selected_window_info()
        if win and win.hwnd:
            WindowManager.bring_to_foreground(win.hwnd)
        else:
            QMessageBox.information(self, "활성화 불가", "활성화할 실행 중인 윈도우가 목록에서 선택되지 않았습니다.")

    def _on_table_double_clicked(self, item):
        self._on_confirm_selection()

    def _on_confirm_selection(self):
        current_tab = self.tabs.currentIndex()

        if current_tab == 0:
            # 1. From Running Window List
            win = self._get_selected_window_info()
            if not win:
                QMessageBox.warning(self, "선택 필요", "타겟으로 지정할 창을 목록에서 선택해주세요.\n(또는 '해상도 직접 입력' 탭에서 해상도를 직접 지정할 수 있습니다.)")
                return
            self.selected_window = win
            self.accept()
        else:
            # 2. From Manual Resolution Input
            w = self.spin_width.value()
            h = self.spin_height.value()
            title = self.txt_custom_title.text().strip() or f"직접 지정 해상도 ({w}×{h})"

            self.selected_window = WindowInfo(
                hwnd=0,
                title=title,
                client_width=w,
                client_height=h,
                screen_x=0,
                screen_y=0,
                pid=0,
                process_name="Manual"
            )
            self.accept()

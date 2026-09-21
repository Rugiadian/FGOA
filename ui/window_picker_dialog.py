"""
Target Window Picker Dialog for FGOA.
Lists visible windows and provides interactive window selection tools.
"""
from typing import Optional, List
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from core.window_manager import WindowManager, WindowInfo


class WindowPickerDialog(QDialog):
    """Dialog for enumerating and selecting a target application window."""

    def __init__(self, current_hwnd: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("타겟 애플리케이션 창 선택")
        self.resize(720, 500)
        self.selected_window: Optional[WindowInfo] = None
        self.current_hwnd = current_hwnd
        self.all_windows: List[WindowInfo] = []

        self._init_ui()
        self._refresh_window_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Search bar & Refresh
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("창 제목 검색:"))
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("검색할 창 이름 입력...")
        self.txt_filter.textChanged.connect(self._filter_list)
        top_bar.addWidget(self.txt_filter)

        btn_refresh = QPushButton("🔄 새로고침")
        btn_refresh.clicked.connect(self._refresh_window_list)
        top_bar.addWidget(btn_refresh)

        layout.addLayout(top_bar)

        # Window Table
        self.tbl_windows = QTableWidget()
        self.tbl_windows.setColumnCount(4)
        self.tbl_windows.setHorizontalHeaderLabels(["HWND", "창 제목", "클라이언트 해상도", "PID"])
        self.tbl_windows.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_windows.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_windows.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_windows.itemDoubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self.tbl_windows)

        # Control & Help
        info_lbl = QLabel("💡 상대 좌표는 선택한 창의 안쪽 클라이언트 영역(좌상단 0,0)을 기준으로 계산됩니다.")
        info_lbl.setStyleSheet("color: #8da4c4; font-size: 8.5pt;")
        layout.addWidget(info_lbl)

        # Action Buttons
        bot_bar = QHBoxLayout()
        btn_activate = QPushButton("👁️ 선택 창 활성화 확인")
        btn_activate.clicked.connect(self._on_activate_clicked)
        bot_bar.addWidget(btn_activate)

        bot_bar.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        bot_bar.addWidget(btn_cancel)

        btn_select = QPushButton("🎯 타겟 창으로 선택")
        btn_select.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 16px;")
        btn_select.clicked.connect(self._on_select_clicked)
        bot_bar.addWidget(btn_select)

        layout.addLayout(bot_bar)

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
        if win:
            WindowManager.bring_to_foreground(win.hwnd)

    def _on_table_double_clicked(self, item):
        self._on_select_clicked()

    def _on_select_clicked(self):
        win = self._get_selected_window_info()
        if not win:
            QMessageBox.warning(self, "선택 필요", "타겟으로 지정할 창을 목록에서 선택해주세요.")
            return
        self.selected_window = win
        self.accept()

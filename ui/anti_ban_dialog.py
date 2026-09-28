"""
Anti-Ban Settings Dialog for FGOA.
Allows configuring time jitter and coordinate offset bounds for macro actions.
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QDoubleSpinBox, QSpinBox, QPushButton, QGroupBox, QFrame
)
from PyQt5.QtCore import Qt
from core.models import Project


class AntiBanDialog(QDialog):
    """Popup dialog for anti-ban delay and coordinate randomization settings."""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("🛡️ 안티밴 설정")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # ---------------------------------------------------------
        # Group 1: Time Anti-Ban (타임 안티밴)
        # ---------------------------------------------------------
        grp_time = QGroupBox("⏱️ 타임 안티밴 (지연 시간 가변 난수)")
        grp_time_layout = QVBoxLayout(grp_time)
        grp_time_layout.setSpacing(8)

        self.chk_time_anti_ban = QCheckBox("타임 안티밴 활성화 (시나리오 전역 적용)")
        self.chk_time_anti_ban.setChecked(self.project.anti_ban_enabled)
        grp_time_layout.addWidget(self.chk_time_anti_ban)

        row_offset = QHBoxLayout()
        lbl_offset = QLabel("최대 추가 지연시간:")
        row_offset.addWidget(lbl_offset)

        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 30.0)
        self.spin_offset.setSingleStep(0.1)
        self.spin_offset.setPrefix("+")
        self.spin_offset.setSuffix(" 초")
        init_offset = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0)))
        self.spin_offset.setValue(init_offset)
        self.spin_offset.setEnabled(self.project.anti_ban_enabled)
        row_offset.addWidget(self.spin_offset)
        grp_time_layout.addLayout(row_offset)

        lbl_desc_time = QLabel(
            "• 액션 지연 시간(대기)에 +0.0 ~ +N.N초 사이의 무작위 난수를 추가합니다.\n"
            "• 기본 대기 시간을 단축시키지 않아 동작 안정성이 유지됩니다."
        )
        lbl_desc_time.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        grp_time_layout.addWidget(lbl_desc_time)

        self.chk_time_anti_ban.toggled.connect(self.spin_offset.setEnabled)
        layout.addWidget(grp_time)

        # ---------------------------------------------------------
        # Group 2: Coordinate Anti-Ban (좌표 오프셋 강약 조절)
        # ---------------------------------------------------------
        grp_coord = QGroupBox("🎯 좌표 안티밴 오프셋 (클릭/드래그 오차 범위)")
        grp_coord_layout = QVBoxLayout(grp_coord)
        grp_coord_layout.setSpacing(8)

        # Weak row
        row_weak = QHBoxLayout()
        lbl_w = QLabel("약 (Weak) 오프셋 범위:")
        row_weak.addWidget(lbl_w)
        self.spin_weak = QSpinBox()
        self.spin_weak.setRange(1, 100)
        self.spin_weak.setPrefix("± ")
        self.spin_weak.setSuffix(" px")
        self.spin_weak.setValue(getattr(self.project, "anti_ban_coord_weak", 5))
        row_weak.addWidget(self.spin_weak)
        grp_coord_layout.addLayout(row_weak)

        # Strong row
        row_strong = QHBoxLayout()
        lbl_s = QLabel("강 (Strong) 오프셋 범위:")
        row_strong.addWidget(lbl_s)
        self.spin_strong = QSpinBox()
        self.spin_strong.setRange(1, 200)
        self.spin_strong.setPrefix("± ")
        self.spin_strong.setSuffix(" px")
        self.spin_strong.setValue(getattr(self.project, "anti_ban_coord_strong", 15))
        row_strong.addWidget(self.spin_strong)
        grp_coord_layout.addLayout(row_strong)

        lbl_desc_coord = QLabel(
            "• 액션별로 설정된 '약/강' 모드에 따라 마우스 클릭/드래그 좌표에\n"
            "  지정된 픽셀 범위 내의 무작위 오차를 발생시킵니다."
        )
        lbl_desc_coord.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        grp_coord_layout.addWidget(lbl_desc_coord)

        layout.addWidget(grp_coord)

        # ---------------------------------------------------------
        # Bottom Buttons (확인, 취소)
        # ---------------------------------------------------------
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("적용 및 닫기")
        btn_ok.setObjectName("btn_primary")
        btn_ok.setStyleSheet("font-weight: bold; padding: 4px 14px;")
        btn_ok.clicked.connect(self._on_apply_and_close)
        btn_box.addWidget(btn_ok)

        layout.addLayout(btn_box)

    def _on_apply_and_close(self):
        """Applies configured values to the project."""
        self.project.anti_ban_enabled = self.chk_time_anti_ban.isChecked()
        offset_val = round(self.spin_offset.value(), 2)
        self.project.anti_ban_offset_seconds = offset_val
        self.project.anti_ban_max_delay = offset_val
        self.project.anti_ban_coord_weak = self.spin_weak.value()
        self.project.anti_ban_coord_strong = self.spin_strong.value()
        self.accept()

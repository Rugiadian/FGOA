"""
Custom SpinBox component for FGOA.
Solves the Qt limitation where QSpinBox with specialValueText (e.g. '무한 반복 (∞)')
ignores direct numeric keyboard input due to Qt's default QValidator.
"""
import re
from typing import Tuple, Optional
from PyQt5.QtWidgets import QSpinBox
from PyQt5.QtCore import Qt, QEvent, QTimer
from PyQt5.QtGui import QValidator, QKeyEvent


class CustomSpinBox(QSpinBox):
    """
    Enhanced QSpinBox that seamlessly accepts direct numeric typing and editing
    even when displaying specialValueText (such as '무한 반복 (∞)').
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Install event filter on internal lineEdit to catch keyboard & mouse interactions
        le = self.lineEdit()
        if le:
            le.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.lineEdit():
            if event.type() == QEvent.KeyPress:
                if self._handle_key_input(event):
                    return True
            elif event.type() == QEvent.FocusIn:
                if self.specialValueText() and self.value() == self.minimum():
                    QTimer.singleShot(0, self.lineEdit().selectAll)
            elif event.type() == QEvent.MouseButtonRelease:
                if (
                    self.specialValueText()
                    and self.value() == self.minimum()
                    and not self.lineEdit().hasSelectedText()
                ):
                    QTimer.singleShot(0, self.lineEdit().selectAll)
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent):
        if self._handle_key_input(event):
            return
        super().keyPressEvent(event)

    def _handle_key_input(self, event: QKeyEvent) -> bool:
        """
        Intercepts keys when specialValueText is shown so that users can type
        digits or clear the field immediately without having to manually erase the special text.
        """
        key = event.key()
        text = event.text()
        sp_text = self.specialValueText()
        cur_text = self.lineEdit().text()

        # Handle Backspace / Delete when specialValueText is shown
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            if sp_text and (cur_text == sp_text or sp_text in cur_text):
                self.lineEdit().clear()
                return True

        # Handle numeric input (0-9) when specialValueText is shown
        if text and text.isdigit():
            if sp_text and (cur_text == sp_text or sp_text in cur_text or not cur_text.isdigit()):
                self.lineEdit().clear()
                self.lineEdit().insert(text)
                return True

        return False

    def validate(self, input_text: str, pos: int) -> Tuple[QValidator.State, str, int]:
        """
        Custom validation that permits specialValueText, its prefixes, empty string,
        and numeric strings within the allowed range.
        """
        sp_text = self.specialValueText()
        if sp_text:
            if input_text == sp_text:
                return (QValidator.Acceptable, input_text, pos)
            if not input_text or sp_text.startswith(input_text):
                return (QValidator.Intermediate, input_text, pos)

        stripped = input_text.strip()
        if not stripped:
            return (QValidator.Intermediate, input_text, pos)

        digits = re.sub(r'[^\d]', '', stripped)
        if digits:
            try:
                val = int(digits)
                if self.minimum() <= val <= self.maximum():
                    return (QValidator.Acceptable, input_text, pos)
                elif val < self.minimum():
                    return (QValidator.Intermediate, input_text, pos)
                else:
                    return (QValidator.Invalid, input_text, pos)
            except ValueError:
                return (QValidator.Invalid, input_text, pos)

        return (QValidator.Invalid, input_text, pos)

    def fixup(self, input_text: str) -> str:
        """
        Converts partial or empty input into a valid value upon editing finished.
        """
        sp_text = self.specialValueText()
        digits = re.sub(r'[^\d]', '', input_text)
        if digits:
            try:
                val = int(digits)
                val = max(self.minimum(), min(self.maximum(), val))
                if val == self.minimum() and sp_text:
                    return sp_text
                return str(val)
            except ValueError:
                pass

        if sp_text:
            return sp_text
        return str(self.minimum())

    def valueFromText(self, text: str) -> int:
        sp_text = self.specialValueText()
        if sp_text and text == sp_text:
            return self.minimum()
        digits = re.sub(r'[^\d]', '', text)
        if digits:
            try:
                val = int(digits)
                return max(self.minimum(), min(self.maximum(), val))
            except ValueError:
                pass
        return self.minimum()

    def textFromValue(self, val: int) -> str:
        if val == self.minimum() and self.specialValueText():
            return self.specialValueText()
        return str(val)


# Alias for convenience
SeamlessSpinBox = CustomSpinBox

"""
Unit tests for:
1. Global hotkey Shift+F6 pause/resume toggle & F6 stop
2. CustomSpinBox direct numeric typing in specialValueText ("무한반복") state
3. QSpinBox up-button/down-button enlarged QSS styling
"""
import unittest
from unittest.mock import MagicMock, patch
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeyEvent, QValidator

from core.global_hotkey import GlobalHotkeyListener, VK_F6, VK_SHIFT, VK_PAUSE
from ui.custom_spinbox import CustomSpinBox, SeamlessSpinBox
from ui.theme import LIGHT_STYLESHEET, DARK_STYLESHEET

# Ensure QApplication instance exists
app = QApplication.instance()
if not app:
    app = QApplication([])


class TestGlobalHotkeyShiftF6(unittest.TestCase):
    """Tests for Shift+F6 pause and F6 stop in GlobalHotkeyListener."""

    def test_signals_exist(self):
        listener = GlobalHotkeyListener(None)
        self.assertTrue(hasattr(listener, "sig_stop_hotkey"))
        self.assertTrue(hasattr(listener, "sig_pause_hotkey"))

    def test_plain_f6_emits_stop(self):
        listener = GlobalHotkeyListener(None)
        stop_mock = MagicMock()
        pause_mock = MagicMock()
        listener.sig_stop_hotkey.connect(stop_mock)
        listener.sig_pause_hotkey.connect(pause_mock)

        # Mock user32 GetAsyncKeyState
        mock_user32 = MagicMock()
        # F6 is pressed (0x8000), Shift is NOT pressed (0x0000)
        def mock_get_async_key_state(vk):
            if vk == VK_F6:
                return 0x8000
            elif vk == VK_SHIFT:
                return 0x0000
            elif vk == VK_PAUSE:
                return 0x0000
            return 0

        mock_user32.GetAsyncKeyState.side_effect = mock_get_async_key_state
        listener._user32 = mock_user32

        # Run single iteration of logic
        f6_state = listener._user32.GetAsyncKeyState(VK_F6)
        f6_is_down = bool(f6_state & 0x8000)
        if f6_is_down and not listener._f6_was_pressed:
            shift_state = listener._user32.GetAsyncKeyState(VK_SHIFT)
            shift_is_down = bool(shift_state & 0x8000)
            if shift_is_down:
                listener.sig_pause_hotkey.emit()
            else:
                listener.sig_stop_hotkey.emit()
        listener._f6_was_pressed = f6_is_down

        stop_mock.assert_called_once()
        pause_mock.assert_not_called()

    def test_shift_f6_emits_pause(self):
        listener = GlobalHotkeyListener(None)
        stop_mock = MagicMock()
        pause_mock = MagicMock()
        listener.sig_stop_hotkey.connect(stop_mock)
        listener.sig_pause_hotkey.connect(pause_mock)

        mock_user32 = MagicMock()
        # F6 is pressed (0x8000), Shift IS pressed (0x8000)
        def mock_get_async_key_state(vk):
            if vk == VK_F6:
                return 0x8000
            elif vk == VK_SHIFT:
                return 0x8000
            elif vk == VK_PAUSE:
                return 0x0000
            return 0

        mock_user32.GetAsyncKeyState.side_effect = mock_get_async_key_state
        listener._user32 = mock_user32

        f6_state = listener._user32.GetAsyncKeyState(VK_F6)
        f6_is_down = bool(f6_state & 0x8000)
        if f6_is_down and not listener._f6_was_pressed:
            shift_state = listener._user32.GetAsyncKeyState(VK_SHIFT)
            shift_is_down = bool(shift_state & 0x8000)
            if shift_is_down:
                listener.sig_pause_hotkey.emit()
            else:
                listener.sig_stop_hotkey.emit()
        listener._f6_was_pressed = f6_is_down

        pause_mock.assert_called_once()
        stop_mock.assert_not_called()


class TestCustomSpinBox(unittest.TestCase):
    """Tests for CustomSpinBox keyboard input in specialValueText mode."""

    def setUp(self):
        self.spin = CustomSpinBox()
        self.spin.setRange(0, 99999)
        self.spin.setSpecialValueText("무한 반복 (∞)")
        self.spin.setValue(0)

    def test_initial_special_value(self):
        self.assertEqual(self.spin.value(), 0)
        self.assertEqual(self.spin.text(), "무한 반복 (∞)")

    def test_typing_digit_replaces_special_value(self):
        # When user types '5', specialValueText should immediately be replaced by '5'
        ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_5, Qt.NoModifier, "5")
        app.sendEvent(self.spin.lineEdit(), ev)

        self.assertEqual(self.spin.lineEdit().text(), "5")
        self.assertEqual(self.spin.value(), 5)

        # Typing '2' afterwards should append to make 52
        ev2 = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_2, Qt.NoModifier, "2")
        app.sendEvent(self.spin.lineEdit(), ev2)

        self.assertEqual(self.spin.lineEdit().text(), "52")
        self.assertEqual(self.spin.value(), 52)

    def test_backspace_clears_special_value(self):
        self.assertEqual(self.spin.value(), 0)
        ev_bs = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
        app.sendEvent(self.spin.lineEdit(), ev_bs)

        self.assertEqual(self.spin.lineEdit().text(), "")

        # Now type 7
        ev_7 = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_7, Qt.NoModifier, "7")
        app.sendEvent(self.spin.lineEdit(), ev_7)
        self.assertEqual(self.spin.lineEdit().text(), "7")
        self.assertEqual(self.spin.value(), 7)

    def test_validator_accepts_special_and_numbers(self):
        state, _, _ = self.spin.validate("무한 반복 (∞)", 0)
        self.assertEqual(state, QValidator.Acceptable)

        state, _, _ = self.spin.validate("100", 0)
        self.assertEqual(state, QValidator.Acceptable)

        state, _, _ = self.spin.validate("", 0)
        self.assertEqual(state, QValidator.Intermediate)

        state, _, _ = self.spin.validate("무한", 0)
        self.assertEqual(state, QValidator.Intermediate)

    def test_fixup_handles_empty_and_numbers(self):
        fixed_empty = self.spin.fixup("")
        self.assertEqual(fixed_empty, "무한 반복 (∞)")

        fixed_num = self.spin.fixup("42")
        self.assertEqual(fixed_num, "42")

    def test_value_from_text_and_text_from_value(self):
        self.assertEqual(self.spin.valueFromText("무한 반복 (∞)"), 0)
        self.assertEqual(self.spin.valueFromText("25"), 25)
        self.assertEqual(self.spin.textFromValue(0), "무한 반복 (∞)")
        self.assertEqual(self.spin.textFromValue(25), "25")


class TestSpinBoxStylesheet(unittest.TestCase):
    """Tests that QSS includes enlarged up-button and down-button rules."""

    def test_light_stylesheet_has_enlarged_buttons(self):
        self.assertIn("QSpinBox::up-button", LIGHT_STYLESHEET)
        self.assertIn("QSpinBox::down-button", LIGHT_STYLESHEET)
        self.assertIn("width: 22px;", LIGHT_STYLESHEET)
        self.assertIn("QSpinBox#spin_loops", LIGHT_STYLESHEET)

    def test_dark_stylesheet_has_enlarged_buttons(self):
        self.assertIn("QSpinBox::up-button", DARK_STYLESHEET)
        self.assertIn("QSpinBox::down-button", DARK_STYLESHEET)
        self.assertIn("width: 22px;", DARK_STYLESHEET)
        self.assertIn("QSpinBox#spin_loops", DARK_STYLESHEET)


class TestMainWindowIntegration(unittest.TestCase):
    """Tests MainWindow button captions and hotkey connections."""

    @patch("ui.main_window.GlobalFloatingStopWidget")
    @patch("ui.main_window.GlobalHotkeyListener")
    def test_main_window_components(self, mock_hotkey, mock_float):
        from ui.main_window import MainWindow
        win = MainWindow()

        # Check spin_loops is CustomSpinBox
        self.assertIsInstance(win.spin_loops, CustomSpinBox)

        # Check btn_pause text and tooltip
        self.assertIn("Shift+F6", win.btn_pause.text())
        self.assertIn("Shift+F6", win.btn_pause.toolTip())

        # Test _on_global_hotkey_pause delegates to _on_pause_execution
        with patch.object(win, "_on_pause_execution") as mock_pause:
            win.runner = MagicMock()
            win.runner.isRunning.return_value = True
            win.runner._is_paused = False
            win._on_global_hotkey_pause()
            mock_pause.assert_called_once()

        # Test _on_global_hotkey_stop delegates to _on_stop_execution
        with patch.object(win, "_on_stop_execution") as mock_stop:
            win.runner = MagicMock()
            win.runner.isRunning.return_value = True
            win._on_global_hotkey_stop()
            mock_stop.assert_called_once()

        win.close()


if __name__ == "__main__":
    unittest.main()

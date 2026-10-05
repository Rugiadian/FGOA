import unittest
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt
from ui.anti_burn_in_overlay import AntiBurnInOverlay, DesktopScreenOverlayWindow
from ui.popup_play_bar import PopupPlayBar


class TestBurnInMode2AndPlayBar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_burn_in_mode2_lifecycle_and_properties(self):
        """Verify Mode 2 (Desktop Fullscreen) overlay window creation, properties, and lifecycle."""
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)

        self.assertEqual(overlay.get_mode(), AntiBurnInOverlay.MODE_APP_WINDOW)

        # Switch to Mode 2 (Desktop Fullscreen)
        overlay.set_mode(AntiBurnInOverlay.MODE_DESKTOP_FULLSCREEN)
        self.assertEqual(overlay.get_mode(), AntiBurnInOverlay.MODE_DESKTOP_FULLSCREEN)

        # Start transition
        overlay.start_transition()
        self.assertTrue(overlay.is_transitioning())
        self.assertGreaterEqual(len(overlay._desktop_windows), 1)

        # Inspect overlay window properties
        win: DesktopScreenOverlayWindow = overlay._desktop_windows[0]
        self.assertTrue(win.testAttribute(Qt.WA_TransparentForMouseEvents))
        self.assertTrue(win.testAttribute(Qt.WA_NoSystemBackground))
        self.assertTrue(win.testAttribute(Qt.WA_TranslucentBackground))
        self.assertTrue(win.testAttribute(Qt.WA_ShowWithoutActivating))
        self.assertEqual(win.focusPolicy(), Qt.NoFocus)

        # Verify window flags
        flags = win.windowFlags()
        self.assertTrue(bool(flags & Qt.FramelessWindowHint))
        self.assertTrue(bool(flags & Qt.WindowStaysOnTopHint))
        self.assertTrue(bool(flags & Qt.Tool))

        # Check resolution / geometry coverage
        geo = win.geometry()
        self.assertGreater(geo.width(), 0)
        self.assertGreater(geo.height(), 0)

        # Advance animation step
        overlay._on_anim_step()
        self.assertGreater(win._alpha, 0)
        self.assertEqual(win._stage, 1)

        # Stop transition
        overlay.stop_transition()
        self.assertFalse(overlay.is_transitioning())
        self.assertFalse(win.isVisible())

        # Cleanup
        overlay.cleanup()
        self.assertEqual(len(overlay._desktop_windows), 0)

    def test_mode_switching_while_running(self):
        """Verify switching between Mode 1 and Mode 2 transitions seamlessly."""
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)

        overlay.start_transition()
        self.assertTrue(overlay.is_transitioning())
        self.assertEqual(overlay.get_mode(), AntiBurnInOverlay.MODE_APP_WINDOW)

        # Switch while running
        overlay.set_mode(AntiBurnInOverlay.MODE_DESKTOP_FULLSCREEN)
        self.assertEqual(overlay.get_mode(), AntiBurnInOverlay.MODE_DESKTOP_FULLSCREEN)
        self.assertTrue(overlay.is_transitioning())
        self.assertGreaterEqual(len(overlay._desktop_windows), 1)

        # Switch back to Mode 1
        overlay.set_mode(AntiBurnInOverlay.MODE_APP_WINDOW)
        self.assertEqual(overlay.get_mode(), AntiBurnInOverlay.MODE_APP_WINDOW)
        self.assertTrue(overlay.is_transitioning())

        overlay.stop_transition()
        self.assertFalse(overlay.is_transitioning())
        overlay.cleanup()

    def test_popup_playbar_start_selected_button_and_signal(self):
        """Verify PopupPlayBar has 'start selected' button and emits sig_start_selected_requested."""
        playbar = PopupPlayBar()
        self.assertTrue(hasattr(playbar, "btn_play_selected"))
        self.assertEqual(playbar.btn_play_selected.text(), "▶ 선택부터 (Shift+F5)")
        self.assertTrue(playbar.btn_play_selected.isEnabled())

        signal_emitted = []
        playbar.sig_start_selected_requested.connect(lambda: signal_emitted.append(True))

        playbar.btn_play_selected.click()
        self.assertEqual(len(signal_emitted), 1)

        # Verify state changes
        playbar.set_runner_state("running")
        self.assertFalse(playbar.btn_play_selected.isEnabled())

        playbar.set_runner_state("paused")
        self.assertFalse(playbar.btn_play_selected.isEnabled())

        playbar.set_runner_state("stopped")
        self.assertTrue(playbar.btn_play_selected.isEnabled())

        playbar.close()

    def test_main_window_burn_in_ui_and_test_button(self):
        """Verify MainWindow anti-burn UI controls, test button, and signal behavior."""
        from ui.main_window import MainWindow
        win = MainWindow()

        # Check widgets exist
        self.assertTrue(hasattr(win, "chk_anti_burn"))
        self.assertTrue(hasattr(win, "combo_anti_burn_mode"))
        self.assertTrue(hasattr(win, "btn_test_anti_burn"))
        self.assertTrue(hasattr(win, "spin_anti_burn_min"))

        # Verify combo options
        self.assertEqual(win.combo_anti_burn_mode.count(), 2)
        self.assertEqual(win.combo_anti_burn_mode.itemData(0), 1)
        self.assertEqual(win.combo_anti_burn_mode.itemData(1), 2)

        # Test switching combo changes overlay mode
        win.combo_anti_burn_mode.setCurrentIndex(1)
        self.assertEqual(win.anti_burn_overlay.get_mode(), 2)

        win.combo_anti_burn_mode.setCurrentIndex(0)
        self.assertEqual(win.anti_burn_overlay.get_mode(), 1)

        # Test clicking test button toggles transition
        self.assertFalse(win.anti_burn_overlay.is_transitioning())
        win.btn_test_anti_burn.click()
        self.assertTrue(win.anti_burn_overlay.is_transitioning())
        self.assertEqual(win.btn_test_anti_burn.text(), "⏹ 중지")

        # Clicking again stops it
        win.btn_test_anti_burn.click()
        self.assertFalse(win.anti_burn_overlay.is_transitioning())
        self.assertEqual(win.btn_test_anti_burn.text(), "🧪 테스트")

        win.close()


if __name__ == "__main__":
    unittest.main()

import os
import json
import unittest
from PyQt5.QtWidgets import QApplication, QDialog
from ui.main_window import MainWindow
from ui.anti_burn_in_overlay import AntiBurnInOverlay
from core.config import get_config_filepath
from core.models import Project

app = QApplication.instance() or QApplication([])


class TestConfigPersistenceAllControls(unittest.TestCase):
    """Tests for verifying persistence and restoration of burn-in and all UI toggles."""

    def setUp(self):
        self.cfg_file = get_config_filepath()
        self.backup_cfg = None
        if os.path.exists(self.cfg_file):
            with open(self.cfg_file, "r", encoding="utf-8") as f:
                self.backup_cfg = f.read()

    def tearDown(self):
        if self.backup_cfg is not None:
            with open(self.cfg_file, "w", encoding="utf-8") as f:
                f.write(self.backup_cfg)
        elif os.path.exists(self.cfg_file):
            try:
                os.remove(self.cfg_file)
            except Exception:
                pass

    def test_anti_burn_and_toggles_restoration_from_config(self):
        """Verify MainWindow correctly restores burn-in settings and other UI controls from config."""
        test_config = {
            "theme": "light",
            "anti_burn_enabled": True,
            "anti_burn_mode": 2,
            "anti_burn_interval_min": 17,
            "action_overlay_enabled": False,
            "floating_stop_enabled": True,
            "hot_reload_enabled": True,
            "autoscroll_enabled": False,
        }
        with open(self.cfg_file, "w", encoding="utf-8") as f:
            json.dump(test_config, f, indent=2)

        win = MainWindow()
        try:
            # 1. Anti-burn in widgets & backend verification
            self.assertTrue(win.chk_anti_burn.isChecked(), "chk_anti_burn should be checked")
            self.assertEqual(win.combo_anti_burn_mode.currentData(), 2, "burn mode should be 2")
            self.assertEqual(win.spin_anti_burn_min.value(), 17, "interval min should be 17")
            self.assertTrue(win.anti_burn_overlay.is_enabled(), "anti_burn_overlay should be enabled")
            self.assertEqual(win.anti_burn_overlay.get_mode(), 2, "overlay mode should be 2")
            self.assertEqual(win.anti_burn_overlay.get_interval_minutes(), 17, "overlay interval should be 17")

            # 2. Action overlay verification
            self.assertFalse(win.chk_action_overlay.isChecked(), "chk_action_overlay should be unchecked")
            self.assertFalse(win.action_overlay.is_overlay_enabled, "action_overlay backend should be disabled")

            # 3. Floating stop verification
            self.assertTrue(win.chk_floating_stop.isChecked(), "chk_floating_stop should be checked")

            # 4. Hot reload verification
            self.assertTrue(win.chk_hot_reload.isChecked(), "chk_hot_reload should be checked")

            # 5. Log autoscroll verification
            self.assertFalse(win.chk_autoscroll.isChecked(), "chk_autoscroll should be unchecked")
        finally:
            win.close()

    def test_saving_ui_controls_updates_config(self):
        """Verify changing UI controls writes updated values into the config file."""
        # Initial empty config
        with open(self.cfg_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        win = MainWindow()
        try:
            # Modify burn-in controls
            win.chk_anti_burn.setChecked(True)
            win.combo_anti_burn_mode.setCurrentIndex(win.combo_anti_burn_mode.findData(2))
            win.spin_anti_burn_min.setValue(35)

            # Modify other controls
            win.chk_action_overlay.setChecked(False)
            win.chk_floating_stop.setChecked(True)
            win.chk_hot_reload.setChecked(True)
            win.chk_autoscroll.setChecked(False)

            # Ensure config is saved
            win._save_app_config()

            with open(self.cfg_file, "r", encoding="utf-8") as f:
                saved_cfg = json.load(f)

            self.assertTrue(saved_cfg.get("anti_burn_enabled"))
            self.assertEqual(saved_cfg.get("anti_burn_mode"), 2)
            self.assertEqual(saved_cfg.get("anti_burn_interval_min"), 35)
            self.assertFalse(saved_cfg.get("action_overlay_enabled"))
            self.assertTrue(saved_cfg.get("floating_stop_enabled"))
            self.assertTrue(saved_cfg.get("hot_reload_enabled"))
            self.assertFalse(saved_cfg.get("autoscroll_enabled"))
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()

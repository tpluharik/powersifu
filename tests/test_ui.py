import ast
import unittest
from pathlib import Path


UI_SOURCE = Path(__file__).resolve().parents[1] / "src" / "powersifu" / "ui.py"


class SettingsWindowContractTests(unittest.TestCase):
    def test_widget_fields_do_not_shadow_methods(self):
        module = ast.parse(UI_SOURCE.read_text(encoding="utf-8"))
        settings_window = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow"
        )
        method_names = {
            node.name for node in settings_window.body if isinstance(node, ast.FunctionDef)
        }
        assigned_fields = {
            node.attr
            for node in ast.walk(settings_window)
            if isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        }

        self.assertFalse(
            method_names & assigned_fields,
            f"Widget fields shadow methods: {sorted(method_names & assigned_fields)}",
        )


if __name__ == "__main__":
    unittest.main()

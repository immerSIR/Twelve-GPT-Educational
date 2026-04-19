import ast
import pathlib
import unittest


class FullInternetAnalystPromptTests(unittest.TestCase):
    def test_system_prompt_renders_with_literal_json_example(self):
        source_path = pathlib.Path("pages/full_internet_analyst.py")
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source)

        function_node = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "_system_prompt"
        )
        function_source = ast.get_source_segment(source, function_node)

        namespace = {"_TODAY": "2026-04-13", "_SEASON": "2025/26"}
        exec(function_source, namespace)

        prompt = namespace["_system_prompt"]("pt")

        self.assertIn("Today's date is 2026-04-13. Current European football season: 2025/26.", prompt)
        self.assertIn("Write entirely in `pt`.", prompt)
        self.assertIn('  "masthead": "Twelve Sport",', prompt)
        self.assertIn('  "newspaper_style": "broadsheet",', prompt)
        self.assertIn('  "competition": "PRIMEIRA LIGA MATCHDAY REPORT",', prompt)
        self.assertIn('"key_numbers": [', prompt)
        self.assertIn('"coach_watch": {', prompt)
        self.assertIn("Write as continuous flowing prose", prompt)
        self.assertIn('Use `newspaper_style: "broadsheet"`', prompt)
        self.assertIn("NEVER use bold section headers", prompt)
        self.assertNotIn("__TODAY__", prompt)
        self.assertNotIn("__SEASON__", prompt)
        self.assertNotIn("__ANSWER_LANGUAGE__", prompt)


if __name__ == "__main__":
    unittest.main()

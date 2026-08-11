import json
import os
import unittest

MEMORY_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestInjectMemoryExtension(unittest.TestCase):
    def test_extension_file_exists(self):
        """Verify extensions/inject-memory.ts exists and has correct exports."""
        ext_path = os.path.join(MEMORY_PKG_DIR, "extensions", "inject-memory.ts")
        self.assertTrue(os.path.exists(ext_path))
        with open(ext_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("loadAndDeduplicateMemories", content)
        self.assertIn("formatMemoriesBlock", content)
        self.assertIn("before_agent_start", content)

    def test_package_json_manifest(self):
        """Verify package.json registers extensions."""
        manifest_path = os.path.join(MEMORY_PKG_DIR, "package.json")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("pi", data)
        self.assertIn("extensions", data["pi"])
        self.assertIn("./extensions", data["pi"]["extensions"])

if __name__ == "__main__":
    unittest.main()

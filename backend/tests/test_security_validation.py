"""Tests for path and SQL identifier validation."""
import os
import tempfile
import unittest

from security_validation import (
    is_safe_geospatial_layer_name,
    is_safe_relative_data_path,
    is_safe_sql_identifier,
    is_safe_subprocess_layer_name,
    normalized_upload_relative_path,
    path_is_under,
    quote_sql_identifier,
    upload_has_allowed_extension,
    UPLOAD_FOLDER_EXTENSIONS,
)


class TestSqlIdentifiers(unittest.TestCase):
    def test_safe_identifiers(self):
        self.assertTrue(is_safe_sql_identifier("My_Table"))
        self.assertTrue(is_safe_sql_identifier("BMP Areas (2020)"))

    def test_rejects_injection(self):
        self.assertFalse(is_safe_sql_identifier('x"; DROP TABLE users;--'))
        self.assertFalse(is_safe_sql_identifier(""))
        self.assertFalse(is_safe_sql_identifier("a" * 200))

    def test_quote_requires_safe(self):
        self.assertEqual(quote_sql_identifier("T1"), '"T1"')
        with self.assertRaises(ValueError):
            quote_sql_identifier("bad;name")


class TestRelativePaths(unittest.TestCase):
    def test_safe_paths(self):
        self.assertTrue(is_safe_relative_data_path("folder/data.db3"))
        self.assertTrue(is_safe_relative_data_path("a/b/map.tif"))

    def test_rejects_traversal(self):
        self.assertFalse(is_safe_relative_data_path("../etc/passwd"))
        self.assertFalse(is_safe_relative_data_path("foo/../../secret.db3"))
        self.assertFalse(is_safe_relative_data_path("/absolute/path.db3"))
        self.assertFalse(is_safe_relative_data_path("a/./../b.db3"))

    def test_normalized_upload_path(self):
        self.assertEqual(
            normalized_upload_relative_path("proj/sub/file.db3"),
            "proj/sub/file.db3",
        )
        self.assertIsNone(normalized_upload_relative_path("../../x.db3"))


class TestPathIsUnder(unittest.TestCase):
    def test_under_base(self):
        with tempfile.TemporaryDirectory() as base:
            sub = os.path.join(base, "child", "file.txt")
            os.makedirs(os.path.dirname(sub), exist_ok=True)
            open(sub, "w", encoding="utf-8").close()
            self.assertTrue(path_is_under(base, sub))
            outside = os.path.join(os.path.dirname(base), "outside.txt")
            self.assertFalse(path_is_under(base, outside))


class TestUploadExtensions(unittest.TestCase):
    def test_allowed(self):
        self.assertTrue(
            upload_has_allowed_extension("x.db3", UPLOAD_FOLDER_EXTENSIONS)
        )
        self.assertFalse(
            upload_has_allowed_extension("x.exe", UPLOAD_FOLDER_EXTENSIONS)
        )


class TestLayerNames(unittest.TestCase):
    def test_subprocess_layer(self):
        self.assertTrue(is_safe_subprocess_layer_name("layer_1"))
        self.assertFalse(is_safe_subprocess_layer_name("layer;rm"))

    def test_geospatial_layer_with_space(self):
        self.assertTrue(is_safe_geospatial_layer_name("Field Areas"))
        self.assertFalse(is_safe_geospatial_layer_name('x";DROP'))


if __name__ == "__main__":
    unittest.main()

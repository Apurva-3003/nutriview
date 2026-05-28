"""Tests for request argument validators."""
import json
import unittest
from unittest.mock import MagicMock

from validate import (
    validate_convert_to_gpkg_files,
    validate_geotiff_path_param,
    validate_get_data_args,
    validate_get_tables_args,
    validate_guest_permissions_payload,
    validate_login_payload,
    validate_upload_folder_files,
)


class TestLoginPayload(unittest.TestCase):
    def test_valid(self):
        out = validate_login_payload({"username": " admin ", "password": "secret"})
        self.assertEqual(out["username"], "admin")

    def test_rejects_missing(self):
        self.assertIn("error", validate_login_payload({}))
        self.assertIn("error", validate_login_payload({"username": "x", "password": ""}))


class TestDbTablesAndGetData(unittest.TestCase):
    def _minimal_get_data_args(self):
        return {
            "db_tables": json.dumps([{"db": "proj/data.db3", "table": "Runoff"}]),
            "columns": "All",
            "id": "[]",
            "id_column": "ID",
            "start_date": "",
            "end_date": "",
            "date_type": "Date",
            "interval": "daily",
            "method": json.dumps(["Equal"]),
            "statistics": json.dumps(["None"]),
        }

    def test_valid_get_data(self):
        out = validate_get_data_args(self._minimal_get_data_args())
        self.assertNotIn("error", out)

    def test_rejects_bad_table_name(self):
        args = self._minimal_get_data_args()
        args["db_tables"] = json.dumps(
            [{"db": "proj/data.db3", "table": 'x"; DROP TABLE t;--'}]
        )
        out = validate_get_data_args(args)
        self.assertIn("error", out)

    def test_rejects_bad_columns(self):
        args = self._minimal_get_data_args()
        args["columns"] = json.dumps(["col;injection"])
        out = validate_get_data_args(args)
        self.assertIn("error", out)


class TestGetTables(unittest.TestCase):
    def test_valid_db_path(self):
        out = validate_get_tables_args({"db_path": "watershed/model.db3"})
        self.assertEqual(out["db_path"], "watershed/model.db3")

    def test_rejects_traversal(self):
        out = validate_get_tables_args({"db_path": "../secret.db3"})
        self.assertIn("error", out)


class TestUploadValidators(unittest.TestCase):
    def _mock_file(self, name):
        f = MagicMock()
        f.filename = name
        return f

    def test_upload_folder_rejects_exe(self):
        out = validate_upload_folder_files([self._mock_file("a.exe")])
        self.assertEqual(out["error"], "File type not allowed.")

    def test_gpkg_rejects_traversal(self):
        out = validate_convert_to_gpkg_files([self._mock_file("../../evil.shp")])
        self.assertIn("error", out)


class TestGeotiffParam(unittest.TestCase):
    def test_valid(self):
        self.assertIn("ok", validate_geotiff_path_param("maps/layer.tif"))

    def test_rejects_traversal(self):
        self.assertIn("error", validate_geotiff_path_param("../secret.tif"))


class TestGuestPermissions(unittest.TestCase):
    def test_valid_flags(self):
        self.assertIn("ok", validate_guest_permissions_payload({"read": True}))

    def test_rejects_unknown_key(self):
        self.assertIn("error", validate_guest_permissions_payload({"admin": True}))


if __name__ == "__main__":
    unittest.main()

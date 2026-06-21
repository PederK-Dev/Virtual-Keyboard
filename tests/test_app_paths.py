import os
import tempfile
import unittest

from app_paths import APP_DIRECTORY_NAME, bundled_resource, user_data_directory


class UserDataDirectoryTests(unittest.TestCase):
    def test_source_build_uses_source_directory(self):
        source = os.path.join("project", "app.py")
        expected = os.path.dirname(os.path.abspath(source))

        self.assertEqual(
            user_data_directory(source, environ={}, frozen=False),
            expected,
        )

    def test_packaged_build_uses_roaming_appdata(self):
        with tempfile.TemporaryDirectory() as appdata:
            result = user_data_directory(
                "ignored.py",
                environ={"APPDATA": appdata},
                frozen=True,
            )

            self.assertEqual(result, os.path.join(appdata, APP_DIRECTORY_NAME))
            self.assertTrue(os.path.isdir(result))

    def test_packaged_build_falls_back_to_local_appdata(self):
        with tempfile.TemporaryDirectory() as local_appdata:
            result = user_data_directory(
                "ignored.py",
                environ={"LOCALAPPDATA": local_appdata},
                frozen=True,
            )

            self.assertEqual(
                result,
                os.path.join(local_appdata, APP_DIRECTORY_NAME),
            )


class BundledResourceTests(unittest.TestCase):
    def test_source_resource_is_relative_to_source_file(self):
        source = os.path.join("project", "app.py")
        result = bundled_resource(source, os.path.join("assets", "icon.ico"))

        self.assertEqual(
            result,
            os.path.join(os.path.dirname(os.path.abspath(source)), "assets", "icon.ico"),
        )

    def test_packaged_resource_uses_bundle_root(self):
        result = bundled_resource(
            "ignored.py",
            os.path.join("assets", "icon.ico"),
            bundle_root=os.path.join("bundle", "temporary"),
        )

        self.assertEqual(
            result,
            os.path.join("bundle", "temporary", "assets", "icon.ico"),
        )


if __name__ == "__main__":
    unittest.main()

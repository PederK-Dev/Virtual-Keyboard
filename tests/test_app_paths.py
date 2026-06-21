import os
import tempfile
import unittest

from app_paths import APP_DIRECTORY_NAME, user_data_directory


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


if __name__ == "__main__":
    unittest.main()

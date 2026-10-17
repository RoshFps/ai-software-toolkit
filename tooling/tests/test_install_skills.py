"""Check that install-skills.sh only installs skills by their directory name."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tooling" / "install-skills.sh"


def install(target, *names, extra=()):
    command = ["bash", str(SCRIPT), "--target", str(target), *extra]
    for name in names:
        command += ["--skill", name]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


class SkillNameTests(unittest.TestCase):
    def test_rejects_names_that_are_not_a_single_directory(self):
        for name in ("", ".", "..", "../skills/address-pr-findings", "address-pr-findings/references"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "skills"
                result = install(target, name, extra=("--replace-existing",))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid skill name", result.stderr)
                self.assertFalse(target.exists(), "nothing is written before names are checked")

    def test_rejects_a_bad_name_listed_after_a_good_one(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            result = install(target, "address-pr-findings", "../escape")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target / "address-pr-findings").exists())

    def test_installs_a_valid_name(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            result = install(target, "address-pr-findings")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "address-pr-findings" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()

import tempfile
import os
import shutil
import chroma_agent.device_plugins.audit.lustre
from chroma_agent.device_plugins.audit.lustre import (
    LnetAudit,
    MdtAudit,
    MgsAudit,
    LustreAudit,
)
from iml_common.test.command_capture_testcase import CommandCaptureTestCase
from tests.test_utils import PatchedContextTestCase


class TestLustreAuditClassMethods(PatchedContextTestCase):
    def setUp(self):
        tests = os.path.join(os.path.dirname(__file__), "..")
        self.test_root = os.path.join(
            tests, "data/lustre_versions/2.9.58_86_g2383a62/mds_mgs"
        )
        super(TestLustreAuditClassMethods, self).setUp()

    def test_kmod_is_loaded(self):
        """Test that LustreAudit.kmod_is_loaded() works."""
        assert MgsAudit.kmod_is_loaded()

    def test_device_is_present(self):
        """Test that LustreAudit.device_is_present() works."""
        assert MdtAudit.device_is_present()

    def test_is_available(self):
        """Test that LustreAudit.is_available() works."""
        assert LnetAudit.is_available()


class TestLustreAuditScanner(PatchedContextTestCase):
    def test_2x_audit_scanner(self):
        tests = os.path.join(os.path.dirname(__file__), "..")
        self.test_root = os.path.join(
            tests, "data/lustre_versions/2.9.58_86_g2383a62/mds_mgs"
        )
        super(TestLustreAuditScanner, self).setUp()
        list = [
            cls.__name__
            for cls in chroma_agent.device_plugins.audit.lustre.local_audit_classes()
        ]
        self.assertEqual(list, ["LnetAudit", "MdtAudit", "MgsAudit"])


class TestLustreAudit(PatchedContextTestCase):
    def setUp(self):
        tests = os.path.join(os.path.dirname(__file__), "..")
        self.test_root = os.path.join(
            tests, "data/lustre_versions/2.9.58_86_g2383a62/mds_mgs"
        )
        super(TestLustreAudit, self).setUp()
        self.audit = LustreAudit()

    def test_version(self):
        self.assertEqual(self.audit.version, "2.9.58_86_g2383a62")

    def test_version_info(self):
        self.assertEqual(self.audit.version_info, self.audit.LustreVersion(2, 9, 58))


class TestGitLustreVersion(PatchedContextTestCase):
    def setUp(self):
        tests = os.path.join(os.path.dirname(__file__), "..")
        self.test_root = os.path.join(
            tests, "data/lustre_versions/2.9.58_86_g2383a62/mds_mgs"
        )
        super(TestGitLustreVersion, self).setUp()
        self.audit = LustreAudit()

    def test_version(self):
        self.assertEqual(self.audit.version, "2.9.58_86_g2383a62")

    def test_version_info(self):
        self.assertEqual(self.audit.version_info, self.audit.LustreVersion(2, 9, 58))


class TestMisformedLustreVersion(PatchedContextTestCase):
    def setUp(self):
        tests = os.path.join(os.path.dirname(__file__), "..")
        self.test_root = os.path.join(tests, "data/lustre_versions/2.bad/mds_mgs")
        super(TestMisformedLustreVersion, self).setUp()
        self.audit = LustreAudit()

    def test_version(self):
        self.assertEqual(self.audit.version, "2.bad")

    def test_version_info(self):
        self.assertEqual(self.audit.version_info, self.audit.LustreVersion(2, 0, 0))


class TestMissingLustreVersion(CommandCaptureTestCase):
    """No idea how this might happen, but it shouldn't crash the audit."""

    def setUp(self):
        super(TestMissingLustreVersion, self).setUp()
        self.add_command(
            ("lctl", "get_param", "-n", "version"),
            rc=2,
            stderr="error: get_param: param_path 'version': No such file or directory",
        )
        self.audit = LustreAudit()

    def test_version(self):
        self.assertEqual(self.audit.version, "0.0.0")

    def test_version_info(self):
        self.assertEqual(self.audit.version_info, self.audit.LustreVersion(0, 0, 0))


class TestLustreAuditGoodHealth(CommandCaptureTestCase):
    def setUp(self):
        super(TestLustreAuditGoodHealth, self).setUp()
        self.add_command(
            ("lctl", "get_param", "-n", "health_check"), stdout="healthy\n"
        )
        self.audit = LustreAudit()

    def test_health_check_healthy(self):
        self.assertEqual(self.audit.health_check(), "healthy")

    def test_healthy_true(self):
        assert self.audit.is_healthy()


class TestLustreAuditBadHealth(CommandCaptureTestCase):
    def setUp(self):
        super(TestLustreAuditBadHealth, self).setUp()
        self.add_command(
            ("lctl", "get_param", "-n", "health_check"), stdout="NOT HEALTHY\n"
        )
        self.audit = LustreAudit()

    def test_health_check_not_healthy(self):
        self.assertEqual(self.audit.health_check(), "NOT HEALTHY")

    def test_healthy_false(self):
        assert not self.audit.is_healthy()

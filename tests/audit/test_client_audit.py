import tempfile
import mock

from chroma_agent.device_plugins.audit.lustre import ClientAudit
from tests.test_utils import PatchedContextTestCase


class TestClientAudit(PatchedContextTestCase):
    def setUp(self):
        self.test_root = tempfile.mkdtemp()
        super(TestClientAudit, self).setUp()

        client_mount = {
            "target": "/mnt/lustre_clients/testfs",
            "source": "10.0.0.129@tcp:/testfs",
            "fs_type": "lustre",
            "opts": "rw",
        }

        def mock_scanner_cmd(cmd):
            if cmd == "GetMounts":
                return [client_mount]
            else:
                return {"blockDevices": {}, "zed": {}, "localMounts": [client_mount]}

        mock.patch(
            "chroma_agent.device_plugins.block_devices.scanner_cmd", mock_scanner_cmd
        ).start()

        self.audit = ClientAudit()

    def test_audit_is_available(self):
        assert ClientAudit.is_available()

    def test_gathered_mount_list(self):
        actual_list = self.audit.metrics()["raw"]["lustre_client_mounts"]
        expected_list = [
            dict(
                mountspec="10.0.0.129@tcp:/testfs",
                mountpoint="/mnt/lustre_clients/testfs",
            )
        ]
        self.assertEqual(actual_list, expected_list)

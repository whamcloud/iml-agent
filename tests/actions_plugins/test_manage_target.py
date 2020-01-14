import mock
from django.utils import unittest

from iml_common.blockdevices.blockdevice import BlockDevice
from iml_common.blockdevices.blockdevice_zfs import BlockDeviceZfs
from iml_common.test.command_capture_testcase import (
    CommandCaptureTestCase,
    CommandCaptureCommand,
)
from tests.lib.agent_unit_testcase import AgentUnitTestCase


class TestFormatTarget(CommandCaptureTestCase):
    block_device_list = [
        BlockDevice("linux", "/dev/foo"),
        BlockDevice("zfs", "lustre1"),
    ]

    def setUp(self):
        super(TestFormatTarget, self).setUp()

        from chroma_agent.action_plugins import manage_targets

        self.manage_targets = manage_targets
        mock.patch(
            "iml_common.blockdevices.blockdevice_zfs.BlockDeviceZfs._check_module"
        ).start()
        mock.patch(
            "iml_common.blockdevices.blockdevice_linux.BlockDeviceLinux._check_module"
        ).start()

        self.addCleanup(mock.patch.stopall)

    def _mkfs_path(self, block_device, target_name):
        """ The mkfs path could be different for different block_device types. Today it isn't but it was when this
        method was added and so rather than remove the method I've made it return the same value for both cases and
        perhaps in the future it will be called into use again
        """
        if block_device.device_type == "linux":
            return block_device.device_path
        elif block_device.device_type == "zfs":
            return "%s/%s" % (block_device.device_path, target_name)

        assert "Unknown device type %s" % block_device.device_type

    def _setup_run_exceptions(self, block_device, run_args):
        self._run_command = CommandCaptureCommand(tuple(filter(None, run_args)))

        self.add_commands(
            CommandCaptureCommand(("/usr/sbin/udevadm", "info", "--path=/module/zfs")),
            CommandCaptureCommand(("zpool", "set", "failmode=panic", "lustre1")),
            CommandCaptureCommand(
                ("dumpe2fs", "-h", "/dev/foo"),
                stdout="Inode size: 1024\nInode count: 1024\n",
            ),
            CommandCaptureCommand(
                ("blkid", "-p", "-o", "value", "-s", "TYPE", "/dev/foo"),
                stdout="%s\n" % block_device.preferred_fstype,
            ),
            CommandCaptureCommand(
                ("blkid", "-p", "-o", "value", "-s", "UUID", "/dev/foo"),
                stdout="123456789\n",
            ),
            CommandCaptureCommand(
                ("zpool", "list", "-H", "-o", "name"), stdout="lustre1"
            ),
            CommandCaptureCommand(
                ("zfs", "get", "-H", "-o", "value", "guid", "lustre1/OST0000"),
                stdout="9845118046416187754",
            ),
            CommandCaptureCommand(
                ("zfs", "get", "-H", "-o", "value", "guid", "lustre1/MDT0000"),
                stdout="9845118046416187755",
            ),
            CommandCaptureCommand(
                ("zfs", "get", "-H", "-o", "value", "guid", "lustre1/MGS0000"),
                stdout="9845118046416187756",
            ),
            CommandCaptureCommand(("zfs", "list", "-H", "-o", "name", "-r", "lustre1")),
            CommandCaptureCommand(("modprobe", "%s" % block_device.preferred_fstype)),
            CommandCaptureCommand(
                ("modprobe", "osd_%s" % block_device.preferred_fstype)
            ),
            self._run_command,
        )

    def test_mdt_mkfs(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--mdt",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "MDT0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MDT0000",
                backfstype=block_device.preferred_fstype,
                target_types=["mdt"],
            )

            self.assertRanCommand(self._run_command)

    def test_mgs_mkfs(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--mgs",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "MGS0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MGS0000",
                backfstype=block_device.preferred_fstype,
                target_types=["mgs"],
            )

            self.assertRanCommand(self._run_command)

    def test_ost_mkfs(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--ost",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "MDT0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MDT0000",
                backfstype=block_device.preferred_fstype,
                target_types=["ost"],
            )

            self.assertRanCommand(self._run_command)

    def test_single_mgs_one_nid(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--ost",
                    "--mgsnode=1.2.3.4@tcp",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "OST0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="OST0000",
                backfstype=block_device.preferred_fstype,
                target_types=["ost"],
                mgsnode=[["1.2.3.4@tcp"]],
            )

            self.assertRanCommand(self._run_command)

    def test_mgs_pair_one_nid(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--ost",
                    "--mgsnode=1.2.3.4@tcp",
                    "--mgsnode=1.2.3.5@tcp",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "OST0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                target_types=["ost"],
                target_name="OST0000",
                backfstype=block_device.preferred_fstype,
                device_type=block_device.device_type,
                mgsnode=[["1.2.3.4@tcp"], ["1.2.3.5@tcp"]],
            )

            self.assertRanCommand(self._run_command)

    def test_single_mgs_multiple_nids(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--ost",
                    "--mgsnode=1.2.3.4@tcp0,4.3.2.1@tcp1",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "OST0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                target_types=["ost"],
                target_name="OST0000",
                backfstype=block_device.preferred_fstype,
                device_type=block_device.device_type,
                mgsnode=[["1.2.3.4@tcp0", "4.3.2.1@tcp1"]],
            )

            self.assertRanCommand(self._run_command)

    def test_mgs_pair_multiple_nids(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--ost",
                    "--mgsnode=1.2.3.4@tcp0,4.3.2.1@tcp1",
                    "--mgsnode=1.2.3.5@tcp0,4.3.2.2@tcp1",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "OST0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                target_name="OST0000",
                backfstype=block_device.preferred_fstype,
                target_types=["ost"],
                device_type=block_device.device_type,
                mgsnode=[
                    ["1.2.3.4@tcp0", "4.3.2.1@tcp1"],
                    ["1.2.3.5@tcp0", "4.3.2.2@tcp1"],
                ],
            )

            self.assertRanCommand(self._run_command)

    # this test does double-duty in testing tuple opts and also
    # the multiple target_types special case
    def test_tuple_opts(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--mgs",
                    "--mdt",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "MGS0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MGS0000",
                backfstype=block_device.preferred_fstype,
                target_types=["mgs", "mdt"],
            )

            self.assertRanCommand(self._run_command)

    def test_dict_opts(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--param",
                    "foo=bar",
                    "--param",
                    "baz=qux thud",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "MGS0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MGS0000",
                backfstype=block_device.preferred_fstype,
                param={"foo": "bar", "baz": "qux thud"},
            )

            self.assertRanCommand(self._run_command)

    def test_flag_opts(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--dryrun",
                    "--backfstype=%s" % block_device.preferred_fstype,
                    '--mkfsoptions="mountpoint=none"'
                    if block_device.device_type == "zfs"
                    else "",
                    self._mkfs_path(block_device, "MGS0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MGS0000",
                backfstype=block_device.preferred_fstype,
                dryrun=True,
            )

            self.assertRanCommand(self._run_command)

    def test_zero_opt(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--index=0",
                    "--mkfsoptions=%s"
                    % (
                        "-x 30 --y --z=83"
                        if block_device.device_type == "linux"
                        else '"mountpoint=none"'
                    ),
                    "--backfstype=%s" % block_device.preferred_fstype,
                    self._mkfs_path(block_device, "MGS0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MGS0000",
                backfstype=block_device.preferred_fstype,
                index=0,
                mkfsoptions="-x 30 --y --z=83"
                if block_device.device_type == "linux"
                else '"mountpoint=none"',
            )
            self.assertRanCommand(self._run_command)

    def test_other_opts(self):
        for block_device in self.block_device_list:
            self._setup_run_exceptions(
                block_device,
                (
                    "mkfs.lustre",
                    "--index=42",
                    "--mkfsoptions=%s"
                    % (
                        "-x 30 --y --z=83"
                        if block_device.device_type == "linux"
                        else '"mountpoint=none"'
                    ),
                    "--backfstype=%s" % block_device.preferred_fstype,
                    self._mkfs_path(block_device, "MGS0000"),
                ),
            )

            self.manage_targets.format_target(
                device=block_device.device_path,
                device_type=block_device.device_type,
                target_name="MGS0000",
                backfstype=block_device.preferred_fstype,
                index=42,
                mkfsoptions="-x 30 --y --z=83"
                if block_device.device_type == "linux"
                else '"mountpoint=none"',
            )

            self.assertRanCommand(self._run_command)

    def test_unknown_opt(self):
        self.assertRaises(
            TypeError, self.manage_targets.format_target, unknown="whatever"
        )


class TestXMLParsing(unittest.TestCase):
    xml_crm_mon = """<?xml version="1.0"?>
<crm_mon version="1.1.18">
    <summary>
        <stack type="corosync" />
        <current_dc present="true" version="1.1.18-11.el7_5.3-2b07d5c5a9" name="iml-mds01.iml" id="1" with_quorum="true" />
        <last_update time="Tue Oct 23 16:09:16 2018" />
        <last_change time="Sat Oct 20 13:34:12 2018" user="root" client="cibadmin" origin="iml-mds01.iml" />
        <nodes_configured number="2" expected_votes="unknown" />
        <resources_configured number="5" disabled="0" blocked="0" />
        <cluster_options stonith-enabled="true" symmetric-cluster="true" no-quorum-policy="stop" maintenance-mode="false" />
    </summary>
    <nodes>
        <node name="iml-mds01.iml" id="2" online="true" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="false" resources_running="3" type="member" />
        <node name="iml-mds02.iml" id="1" online="true" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="false" resources_running="2" type="member" />
    </nodes>
    <resources>
        <resource id="st-fencing" resource_agent="stonith:fence_chroma" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
            <node name="iml-mds01.iml" id="2" cached="false"/>
        </resource>
        <resource id="MGS_054510" resource_agent="ocf::lustre:Lustre" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
            <node name="iml-mds02.iml" id="1" cached="false"/>
        </resource>
        <group id="group-fs1-MDT0001_41549d" number_resources="2" >
             <resource id="fs1-MDT0001_41549d-zfs" resource_agent="ocf::chroma:ZFS" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                 <node name="iml-mds01.iml" id="2" cached="false"/>
             </resource>
             <resource id="fs1-MDT0001_41549d" resource_agent="ocf::lustre:Lustre" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
                 <node name="iml-mds01.iml" id="2" cached="false"/>
             </resource>
        </group>
        <resource id="fs1-MDT0000_6cc06e" resource_agent="ocf::chroma:Target" role="Started" target_role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1" >
            <node name="iml-mds01.iml" id="1" cached="false"/>
        </resource>
   </resources>
   <node_attributes>
        <node name="iml-mds01.iml">
        </node>
        <node name="iml-mds02.iml">
        </node>
    </node_attributes>
</crm_mon>
    """

    def test_get_resource_locations(self):
        from chroma_agent.action_plugins import manage_targets

        self.assertDictEqual(
            manage_targets._get_resource_locations(self.xml_crm_mon),
            {
                "fs1-MDT0000_6cc06e": "iml-mds01.iml",
                "fs1-MDT0001_41549d-zfs": "iml-mds01.iml",
                "fs1-MDT0001_41549d": "iml-mds01.iml",
                "MGS_054510": "iml-mds02.iml",
            },
        )


class TestCheckBlockDevice(CommandCaptureTestCase, AgentUnitTestCase):
    def setUp(self):
        super(TestCheckBlockDevice, self).setUp()

        from chroma_agent.action_plugins import manage_targets

        self.manage_targets = manage_targets
        mock.patch(
            "iml_common.blockdevices.blockdevice_zfs.BlockDeviceZfs._check_module"
        ).start()
        mock.patch(
            "iml_common.blockdevices.blockdevice_linux.BlockDeviceLinux._check_module"
        ).start()

        self.addCleanup(mock.patch.stopall)

    def test_occupied_device_ldiskfs(self):
        self.add_commands(
            CommandCaptureCommand(
                ("blkid", "-p", "-o", "value", "-s", "TYPE", "/dev/sdb"),
                stdout="ext4\n",
            )
        )

        self.assertAgentError(
            self.manage_targets.check_block_device("/dev/sdb", "linux"),
            "Filesystem found: type 'ext4'",
        )
        self.assertRanAllCommands()

    def test_mbr_device_ldiskfs(self):
        self.add_commands(
            CommandCaptureCommand(
                ("blkid", "-p", "-o", "value", "-s", "TYPE", "/dev/sdb"), stdout="\n"
            )
        )

        self.assertAgentOK(self.manage_targets.check_block_device("/dev/sdb", "linux"))
        self.assertRanAllCommands()

    def test_empty_device_ldiskfs(self):
        self.add_commands(
            CommandCaptureCommand(
                ("blkid", "-p", "-o", "value", "-s", "TYPE", "/dev/sdb"), rc=2
            )
        )

        self.assertAgentOK(self.manage_targets.check_block_device("/dev/sdb", "linux"))
        self.assertRanAllCommands()

    def test_occupied_device_zfs(self):
        self.add_command(
            ("zfs", "list", "-H", "-o", "name", "-r", "pool1"),
            stdout="pool1\npool1/dataset_1\n",
        )

        self.assertAgentError(
            self.manage_targets.check_block_device("pool1", "zfs"),
            "Dataset 'dataset_1' found on zpool 'pool1'",
        )
        self.assertRanAllCommands()

    def test_empty_device_zfs(self):
        self.add_command(
            ("zfs", "list", "-H", "-o", "name", "-r", "pool1"), stdout="pool1\n"
        )

        self.assertAgentOK(self.manage_targets.check_block_device("pool1", "zfs"))
        self.assertRanAllCommands()

    @unittest.skip(
        "Unimplemented, need to test running check_block_device on a zfs dataset"
    )
    def test_dataset_device_zfs(self):
        pass


class TestCheckImportExport(AgentUnitTestCase):
    """
    Test that the correct blockdevice methods are called, implementation of methods tested in
    test_blockdevice_zfs therefore don't repeat command capturing here
    """

    zpool = "zpool"
    zpool_dataset = "%s/dataset" % zpool

    def setUp(self):
        super(TestCheckImportExport, self).setUp()

        from chroma_agent.action_plugins import manage_targets

        self.manage_targets = manage_targets

        self.patch_init_modules = mock.patch.object(BlockDeviceZfs, "_check_module")
        self.patch_init_modules.start()
        self.mock_import_ = mock.Mock(return_value=None)
        self.patch_import_ = mock.patch.object(
            BlockDeviceZfs, "import_", self.mock_import_
        )
        self.patch_import_.start()
        self.mock_export = mock.Mock(return_value=None)
        self.patch_export = mock.patch.object(
            BlockDeviceZfs, "export", self.mock_export
        )
        self.patch_export.start()

        self.addCleanup(mock.patch.stopall)

    def test_import_device_ldiskfs(self):
        for with_pacemaker in [True, False]:
            self.assertAgentOK(
                self.manage_targets.import_target("linux", "/dev/sdb", with_pacemaker)
            )

    def test_export_device_ldiskfs(self):
        self.assertAgentOK(self.manage_targets.export_target("linux", "/dev/sdb"))

    def test_import_device_zfs(self):
        for with_pacemaker in [True, False]:
            self.mock_import_.reset_mock()
            self.assertAgentOK(
                self.manage_targets.import_target(
                    "zfs", self.zpool_dataset, with_pacemaker
                )
            )
            # Force parameter only supplied on import on retry
            self.mock_import_.assert_called_once_with(False)

    def test_import_device_zfs_with_pacemaker_force(self):
        """ Verify force is used only on retry when message indicates """
        self.mock_import_.side_effect = ["import using -f", None]

        self.assertAgentOK(
            self.manage_targets.import_target("zfs", self.zpool_dataset, True)
        )
        self.mock_import_.assert_has_calls([mock.call(False), mock.call(True)])

    def test_import_device_zfs_with_pacemaker_fail(self):
        """ Verify force is used only on retry when message indicates """
        self.mock_import_.side_effect = ["no such pool available", None]

        self.assertAgentError(
            self.manage_targets.import_target("zfs", self.zpool_dataset, True),
            "no such pool available",
        )
        self.mock_import_.assert_called_once_with(False)

    def test_export_device_zfs(self):
        self.assertAgentOK(self.manage_targets.export_target("zfs", self.zpool_dataset))
        self.mock_export.assert_called_once_with()

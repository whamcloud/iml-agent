import json
import os

from django.utils import unittest
from mock import patch

from chroma_agent.device_plugins.block_devices import get_local_mounts


class TestBase(unittest.TestCase):
    test_host_fqdn = "vm5.foo.com"

    def setUp(self):
        super(TestBase, self).setUp()
        self.test_root = os.path.join(
            os.path.dirname(__file__), "..", "data", "device_plugins"
        )
        self.addCleanup(patch.stopall)

    def load(self, filename):
        return open(os.path.join(self.test_root, filename)).read()

    def check(self, skip_keys, expect, result, x):
        from toolz import pipe
        from toolz.curried import map as cmap, filter as cfilter

        def cmpval(key):
            expected = expect[x][key]
            actual = result[x][key]
            if type(expected) is dict:
                self.check(skip_keys, expect[x], result[x], key)
            else:
                self.assertEqual(
                    actual,
                    expected,
                    "item {} ({}) in {} does not match expected ({})".format(
                        key, actual, x, expected
                    ),
                )

        pipe(
            expect[x].keys(), cfilter(lambda y: y not in skip_keys), cmap(cmpval), list
        )


class TestFormattedBlockDevices(TestBase):
    """ Verify aggregator output parsed through block_devices matches expected agent output """

    def setUp(self):
        super(TestFormattedBlockDevices, self).setUp()

        self.fixture = json.loads(self.load(u"scanner-lu-mounted.out"))
        self.addCleanup(patch.stopall)

    def get_patched_local_mounts(self, fixture):
        with patch(
            "chroma_agent.device_plugins.block_devices.scanner_cmd",
            return_value=fixture,
        ):
            return get_local_mounts()

    def test_local_mounts_parsing(self):
        mounts = self.get_patched_local_mounts(self.fixture)
        expected_mounts = [
            (u"-hosts", u"/net", u"autofs"),
            (u"/dev/mapper/vg_00-lv_root", u"/", u"ext4"),
            (u"/dev/mapper/vg_00-lv_swap", u"swap", u"swap"),
            (u"/dev/vda1", u"/boot", u"ext3"),
            (u"/etc/auto.misc", u"/misc", u"autofs"),
            (u"auto.direct", u"/root/chef", u"autofs"),
            (u"auto.direct", u"/root/lab", u"autofs"),
            (u"auto.direct", u"/scratch", u"autofs"),
            (u"auto.home", u"/home", u"autofs"),
            (u"cgroup", u"/sys/fs/cgroup/blkio", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/cpu,cpuacct", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/cpuset", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/devices", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/freezer", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/hugetlb", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/memory", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/net_cls,net_prio", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/perf_event", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/pids", u"cgroup"),
            (u"cgroup", u"/sys/fs/cgroup/systemd", u"cgroup"),
            (u"configfs", u"/sys/kernel/config", u"configfs"),
            (u"debugfs", u"/sys/kernel/debug", u"debugfs"),
            (u"devpts", u"/dev/pts", u"devpts"),
            (u"devtmpfs", u"/dev", u"devtmpfs"),
            (u"hugetlbfs", u"/dev/hugepages", u"hugetlbfs"),
            (u"mqueue", u"/dev/mqueue", u"mqueue"),
            (u"nfsd", u"/proc/fs/nfsd", u"nfsd"),
            (u"proc", u"/proc", u"proc"),
            (u"pstore", u"/sys/fs/pstore", u"pstore"),
            (u"securityfs", u"/sys/kernel/security", u"securityfs"),
            (u"sunrpc", u"/var/lib/nfs/rpc_pipefs", u"rpc_pipefs"),
            (u"sysfs", u"/sys", u"sysfs"),
            (u"systemd-1", u"/proc/sys/fs/binfmt_misc", u"autofs"),
            (u"tmpfs", u"/dev/shm", u"tmpfs"),
            (u"tmpfs", u"/run", u"tmpfs"),
            (u"tmpfs", u"/run/user/0", u"tmpfs"),
            (u"tmpfs", u"/sys/fs/cgroup", u"tmpfs"),
            (
                u"zfs_pool_scsi0QEMU_QEMU_HARDDISK_disk11",
                u"/zfs_pool_scsi0QEMU_QEMU_HARDDISK_disk11",
                u"zfs",
            ),
            (
                u"zfs_pool_scsi0QEMU_QEMU_HARDDISK_disk11/mgt_index0",
                u"/mnt/mdt",
                u"lustre",
            ),
        ]
        self.assertEqual(set(mounts), set(expected_mounts))

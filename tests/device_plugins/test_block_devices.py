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


#        p = re.compile('\d+:\d+$')
#        print 'Omitted devices:'
#        print (set(self.expected['devs'].keys()) - set([mm for mm in self.expected['devs'].keys() if p.match(mm)]))
#        ccheck = curry(self.check, [], self.expected['devs'], self.block_devices['devs'])
#
#        map(
#            lambda x: ccheck(x),
#            [mm for mm in self.expected['devs'].keys() if p.match(mm)]
#        )

# todo: ensure we are testing all variants from relevant fixture:
# - partition
# - dm-0 linear lvm
# - dm-2 striped lvm

#    def test_block_device_local_fs_parsing(self):
#        key = 'local_fs'
#        map(
#            # lambda x: self.assertListEqual(self.expected[key][x],
#            #                                self.block_devices[key][x]),
#            # fixme: currently the Mountpoint of the local mount is not being provided by block_devices.py
#            lambda x: self.assertEqual(self.expected[key][x][1],
#                                       self.block_devices[key][x][1]),
#            self.expected[key].keys()
#        )
#
#    def test_block_device_lvs_parsing(self):
#        key = 'lvs'
#        # uuid format changed with output now coming from device-scanner
#        ccheck = curry(self.check, ['uuid'], self.expected[key], self.block_devices[key])
#
#        map(
#            lambda x: ccheck(x),
#            self.expected[key].keys()
#        )
#
#    def test_block_device_mds_parsing(self):
#        key = 'mds'
#        ccheck = curry(self.check, [], self.expected[key], self.block_devices[key])
#
#        map(
#            lambda x: ccheck(x),
#            self.expected[key].keys()
#        )
#
#    def test_block_device_vgs_parsing(self):
#        key = 'vgs'
#        ccheck = curry(self.check, ['uuid'], self.expected[key], self.block_devices[key])
#
#        map(
#            lambda x: ccheck(x),
#            self.expected[key].keys()
#        )


# class TestBlockDevices(TestBase):
#    """ Verify aggregator output parsed through block_devices matches expected agent output """
#    zpool_result = {u'0x0123456789abcdef': {'block_device': 'zfspool:0x0123456789abcdef',
#                                            'drives': {u'8:64', u'8:32', u'8:65', u'8:41',
#                                                       u'8:73', u'8:33'},
#                                            'name': u'testPool4',
#                                            'path': u'testPool4',
#                                            'size': 10670309376,
#                                            'uuid': u'0x0123456789abcdef'}}
#    dataset_result = {u'0xDB55C7876B45A0FB-testPool4/f1-OST0000': {'block_device':
#                                                                   'zfsset:0xDB55C7876B45A0FB-testPool4/f1-OST0000',
#                                                                   'drives': {u'8:64', u'8:32', u'8:65', u'8:41',
#                                                                              u'8:73', u'8:33'},
#                                                                   'name': u'testPool4/f1-OST0000',
#                                                                   'path': u'testPool4/f1-OST0000',
#                                                                   'size': 0,
#                                                                   'uuid': u'0xDB55C7876B45A0FB-testPool4/f1-OST0000'}}
#
#    def setUp(self):
#        super(TestBlockDevices, self).setUp()
#
#        self.fixture = compose(json.loads, self.load)(u'device_aggregator.text')
#        self.block_devices = self.get_patched_block_devices(dict(self.fixture))
#        self.expected = json.loads(self.load(u'agent_plugin.json'))['result']['linux']
#
#    def get_patched_block_devices(self, fixture):
#        with patch('chroma_core.plugins.block_devices.aggregator_get', return_value=fixture):
#            return get_block_devices(self.test_host_fqdn)
#
#    def patch_zed_data(self, fixture, host_fqdn, pools=None, zfs=None, props=None):
#        """ overwrite with supplied structures or if None supplied in parameters, copy from existing host """
#        # take copy of fixture so we return a new one and leave the original untouched
#        fixture = dict(fixture)
#
#        # copy existing host data if simulating new host
#        host_data = json.loads(fixture.setdefault(host_fqdn,
#                                                  fixture[self.test_host_fqdn]))
#        host_data['zed'] = {'zpools': pools if pools is not None else host_data['zed']['zpools'],
#                            'zfs': zfs if zfs is not None else host_data['zed']['zfs'],
#                            'props': props if props is not None else host_data['zed']['props']}
#
#        fixture[host_fqdn] = json.dumps(host_data)
#
#        return fixture
#
#    @staticmethod
#    def get_test_pool(state='ACTIVE'):
#        return {
#          "guid": '0x0123456789abcdef',
#          "name": 'testPool4',
#          "state": state,
#          "size": 10670309376,
#          "datasets": [],
#          "vdev": {'Root': {'children': [
#            {
#              "Disk": {
#                "path": '/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_disk2-part1',
#                "path_id": 'scsi-0QEMU_QEMU_HARDDISK_disk2-part1',
#                "phys_path": 'virtio-pci-0000:00:05.0-scsi-0:0:0:1',
#                "whole_disk": True,
#                "is_log": False
#              }
#            },
#            {
#              "Disk": {
#                "path": '/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_disk4-part1',
#                "path_id": 'scsi-0QEMU_QEMU_HARDDISK_disk4-part1',
#                "phys_path": 'virtio-pci-0000:00:05.0-scsi-0:0:0:3',
#                "whole_disk": True,
#                "is_log": False
#              }
#            }]
#          }}
#        }
#
#    def test_block_device_nodes_parsing(self):
#        p = re.compile('\d+:\d+$')
#        ccheck = curry(self.check, [], self.expected['devs'], self.block_devices['devs'])
#
#        map(
#            lambda x: ccheck(x),
#            [mm for mm in self.expected['devs'].keys() if p.match(mm)]
#        )
#
#        # todo: ensure we are testing all variants from relevant fixture:
#        # - partition
#        # - dm-0 linear lvm
#        # - dm-2 striped lvm
#
#    def test_get_drives(self):
#        self.assertEqual(get_drives([child['Disk'] for child in self.get_test_pool()['vdev']['Root']['children']],
#                                    self.block_devices['devs']),
#                         {u'8:64', u'8:32', u'8:65', u'8:41', u'8:73', u'8:33'})
#
#    def test_discover_zpools(self):
#        """ verify block devices are unchanged when no accessible pools exist on other hosts """
#        original_block_devices = dict(self.block_devices)
#        self.assertEqual(discover_zpools(self.block_devices, self.fixture),
#                         original_block_devices)
#
#    def test_discover_zpools_unavailable_other(self):
#        """ verify block devices are unchanged when locally active pool exists unavailable on other hosts """
#        fixture = self.patch_zed_data(dict(self.fixture),
#                                      self.test_host_fqdn,
#                                      {'0x0123456789abcdef': self.get_test_pool('ACTIVE')},
#                                      {},
#                                      {})
#
#        original_block_devices = self.get_patched_block_devices(dict(fixture))
#
#        fixture = self.patch_zed_data(dict(fixture),
#                                      'vm6.foo.com',
#                                      {'0x0123456789abcdef': self.get_test_pool('UNAVAIL')},
#                                      {},
#                                      {})
#
#        self.assertEqual(self.get_patched_block_devices(fixture), original_block_devices)
#
#    def test_discover_zpools_exported_other(self):
#        """ verify block devices are unchanged when locally active pool exists exported on other hosts """
#        fixture = self.patch_zed_data(dict(self.fixture),
#                                      self.test_host_fqdn,
#                                      {'0x0123456789abcdef': self.get_test_pool('ACTIVE')},
#                                      {},
#                                      {})
#
#        original_block_devices = self.get_patched_block_devices(dict(fixture))
#
#        fixture = self.patch_zed_data(dict(fixture),
#                                      'vm6.foo.com',
#                                      {'0x0123456789abcdef': self.get_test_pool('EXPORTED')},
#                                      {},
#                                      {})
#
#        self.assertEqual(self.get_patched_block_devices(fixture), original_block_devices)
#
#    def test_discover_zpools_unknown(self):
#        """ verify block devices are updated when accessible but unknown pools are active on other hosts """
#        # remove pool and zfs data from fixture
#        fixture = self.patch_zed_data(self.fixture,
#                                      self.test_host_fqdn,
#                                      {},
#                                      {},
#                                      {})
#
#        block_devices = self.get_patched_block_devices(dict(fixture))
#
#        # no pools or datasets should be reported after processing
#        block_devices = discover_zpools(block_devices, fixture)
#        [self.assertEqual(block_devices[key], {}) for key in ['zfspools', 'zfsdatasets']]
#
#        # add pool and zfs data to fixture for another host
#        fixture = self.patch_zed_data(fixture,
#                                      'vm6.foo.com',
#                                      {'0x0123456789abcdef': self.get_test_pool('ACTIVE')},
#                                      {},
#                                      {})
#
#        block_devices = self.get_patched_block_devices(fixture)
#
#        # new pool on other host should be reported after processing, because drives are shared
#        self.assertEqual(block_devices['zfspools'], self.zpool_result)
#
#    def test_discover_dataset_unknown(self):
#        """ verify block devices are updated when accessible but unknown datasets are active on other hosts """
#        # copy pool and zfs data to fixture for another host
#        fixture = self.patch_zed_data(self.fixture,
#                                      'vm6.foo.com')
#
#        # remove pool and zfs data from fixture for current host
#        fixture = self.patch_zed_data(fixture,
#                                      self.test_host_fqdn,
#                                      {},
#                                      {},
#                                      {})
#
#        block_devices = self.get_patched_block_devices(fixture)
#
#        # datasets should be reported after processing
#        self.assertEqual(block_devices['zfspools'], {})
#        self.assertEqual(block_devices['zfsdatasets'], self.dataset_result)
#
#    def test_discover_zpools_both_active(self):
#        """ verify exception thrown when accessible active pools are active on other hosts """
#        fixture = self.patch_zed_data(self.fixture,
#                                      self.test_host_fqdn,
#                                      {'0x0123456789abcdef': self.get_test_pool('ACTIVE')},
#                                      {},
#                                      {})
#
#        block_devices = self.get_patched_block_devices(fixture)
#
#        fixture = self.patch_zed_data(self.fixture,
#                                      'vm6.foo.com',
#                                      {'0x0123456789abcdef': self.get_test_pool('ACTIVE')},
#                                      {},
#                                      {})
#
#        with self.assertRaises(RuntimeError):
#            discover_zpools(block_devices, fixture)
#
#    def test_ignore_exported_zpools(self):
#        """ verify exported pools are not reported """
#        fixture = self.patch_zed_data(self.fixture,
#                                      self.test_host_fqdn,
#                                      {'0x0123456789abcdef': self.get_test_pool('EXPORTED')},
#                                      {},
#                                      {})
#
#        block_devices = self.get_patched_block_devices(fixture)
#
#        self.assertEqual(block_devices['zfspools'], {})
#        self.assertEqual(block_devices['zfsdatasets'], {})
#
#    def test_ignore_other_exported_zpools(self):
#        """ verify elsewhere exported pools are not reported """
#        fixture = self.patch_zed_data(self.fixture,
#                                      self.test_host_fqdn,
#                                      {},
#                                      {},
#                                      {})
#
#        fixture = self.patch_zed_data(fixture,
#                                      'vm6.foo.com',
#                                      {'0x0123456789abcdef': self.get_test_pool('EXPORTED')},
#                                      {},
#                                      {})
#
#        block_devices = self.get_patched_block_devices(fixture)
#
#        self.assertEqual(block_devices['zfspools'], {})
#        self.assertEqual(block_devices['zfsdatasets'], {})

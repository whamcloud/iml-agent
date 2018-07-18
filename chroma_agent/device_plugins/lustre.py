# Copyright (c) 2017 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.


from collections import defaultdict, namedtuple
import os
import glob
import ConfigParser

from chroma_agent.lib.shell import AgentShell
from chroma_agent.log import daemon_log
from chroma_agent.log import console_log
from chroma_agent import version as agent_version
from chroma_agent.plugin_manager import DevicePlugin
from chroma_agent import plugin_manager
from chroma_agent.device_plugins.linux import LinuxDevicePlugin
from iml_common.lib.exception_sandbox import exceptionSandBox
from chroma_agent.device_plugins.block_devices import parse_local_mounts, scanner_cmd
from chroma_agent.lib.yum_utils import yum_util
from iml_common.lib.date_time import IMLDateTime

from iml_common.filesystems.filesystem import FileSystem
from iml_common.blockdevices.blockdevice import BlockDevice

# FIXME: weird naming, 'LocalAudit' is the class that fetches stats
from chroma_agent.device_plugins.audit import local


VersionInfo = namedtuple('VersionInfo', ['epoch', 'version', 'release', 'arch'])

def process_zfs_mount(device, data, zfs_mounts):
    # If zfs-backed target/dataset, lookup underlying pool to get uuid
    # and nested dataset in zed structures to access lustre svname (label).
    dev_root = device.split('/')[0]
    if dev_root not in [d for d, _, _ in zfs_mounts]:
        daemon_log.debug('lustre device is not zfs')
        return None, None

    pool = next(
        p for p in data['zed'].values()
        if p['name'] == dev_root
    )
    dataset = next(
        d for d in pool['datasets']
        if d['name'] == device
    )

    fs_label = next(
        p['value'] for p in dataset['props']
        if p['name'] == 'lustre:svname'  # used to be fsname
    )

    fs_uuid = dataset['guid']

    return fs_label, fs_uuid


def process_lvm_mount(device, data):
    try:
        bdev = next(
            (v['paths'], v['lvUuid']) for v in data['blockDevices'].itervalues()
            if device in v['paths'] and v.get('lvUuid')
        )
    except StopIteration:
        daemon_log.debug('lustre device is not lvm')
        return None, None

    label_prefix = '/dev/disk/by-label/'
    fs_label = next(
        p.split(label_prefix, 1)[1] for p in bdev[0] if p.startswith(label_prefix)
    )

    return fs_label, bdev[1]


class LustrePlugin(DevicePlugin):
    delta_fields = ['capabilities', 'properties', 'mounts', 'resource_locations']

    def __init__(self, session):
        self.reset_state()
        super(LustrePlugin, self).__init__(session)

    def reset_state(self):
        self._mount_cache = defaultdict(dict)

    @exceptionSandBox(console_log, {})
    def _scan_mounts(self):
        mounts = {}

        data = scanner_cmd("Stream")
        local_mounts = parse_local_mounts(data['localMounts'])
        zfs_mounts = [(d, m, f) for d, m, f in local_mounts if f == 'zfs']
        lustre_mounts = [(d, m, f) for d, m, f in local_mounts if f == 'lustre']

        for device, mntpnt, _ in lustre_mounts:
            fs_label, fs_uuid = process_zfs_mount(device, data, zfs_mounts)

            if not fs_label:
                fs_label, fs_uuid = process_lvm_mount(device, data)

                if not fs_label:
                    # todo: derive information directly from device-scanner output for ldiskfs
                    # Assume that while a filesystem is mounted, its UUID and LABEL don't change.
                    # Therefore we can avoid repeated blkid calls with a little caching.
                    if device in self._mount_cache:
                        fs_uuid = self._mount_cache[device]['fs_uuid']
                        fs_label = self._mount_cache[device]['fs_label']
                    else:
                        # Sending none as the type means BlockDevice will use it's local cache to work the type.
                        # This is not a good method, and we should work on a way of not storing such state but for the
                        # present it is the best we have.
                        try:
                            fs_uuid = BlockDevice(None, device).uuid
                            fs_label = FileSystem(None, device).label

                            # If we have scanned the devices then it is safe to cache the values.
                            if LinuxDevicePlugin.devices_scanned:
                                self._mount_cache[device]['fs_uuid'] = fs_uuid
                                self._mount_cache[device]['fs_label'] = fs_label
                        except AgentShell.CommandExecutionError:
                            continue

            recovery_status = {}
            try:
                recovery_file = glob.glob("/proc/fs/lustre/*/%s/recovery_status" % fs_label)[0]
                recovery_status_text = open(recovery_file).read()
                for line in recovery_status_text.split("\n"):
                    tokens = line.split(":")
                    if len(tokens) != 2:
                        continue
                    k = tokens[0].strip()
                    v = tokens[1].strip()
                    recovery_status[k] = v
            except IndexError:
                # If the recovery_status file doesn't exist,
                # we will return an empty dict for recovery info
                pass

            mounts[device] = {
                'fs_uuid': fs_uuid,
                'mount_point': mntpnt,
                'recovery_status': recovery_status
            }

        # Drop cached info about anything that is no longer mounted
        for k in self._mount_cache.keys():
            if k not in mounts:
                del self._mount_cache[k]

        return mounts.values()

    def _scan(self, initial=False):
        started_at = IMLDateTime.utcnow().isoformat()
        audit = local.LocalAudit()

        # Only set resource_locations if we have the management package
        try:
            from chroma_agent.action_plugins import manage_targets
            resource_locations = manage_targets.get_resource_locations()
        except ImportError:
            resource_locations = None

        mounts = self._scan_mounts()

        # FIXME: HYD-1095 we should be sending a delta instead of a full dump every time
        # FIXME: At this time the 'capabilities' attribute is unused on the manager
        return {
            "started_at": started_at,
            "agent_version": agent_version(),
            "capabilities": plugin_manager.ActionPluginManager().capabilities,
            "metrics": audit.metrics(),
            "properties": audit.properties(),
            "mounts": mounts,
            "resource_locations": resource_locations
        }

    def start_session(self):
        self.reset_state()
        self._reset_delta()
        return self._delta_result(self._scan(initial=True), self.delta_fields)

    def update_session(self):
        return self._delta_result(self._scan(), self.delta_fields)

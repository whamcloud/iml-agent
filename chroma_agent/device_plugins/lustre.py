# Copyright (c) 2018 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.


from collections import defaultdict, namedtuple
import os
import ConfigParser

from chroma_agent.lib.shell import AgentShell
from chroma_agent.log import daemon_log
from chroma_agent.log import console_log
from chroma_agent import version as agent_version
from chroma_agent.plugin_manager import DevicePlugin
from chroma_agent import plugin_manager
from chroma_agent.device_plugins.linux import LinuxDevicePlugin
from chroma_agent.device_plugins.block_devices import get_lustre_mount_info, scanner_cmd
from chroma_agent.lib.yum_utils import yum_util
from iml_common.lib.date_time import IMLDateTime

from iml_common.filesystems.filesystem import FileSystem
from iml_common.blockdevices.blockdevice import BlockDevice

# FIXME: weird naming, 'LocalAudit' is the class that fetches stats
from chroma_agent.device_plugins.audit import local


VersionInfo = namedtuple("VersionInfo", ["epoch", "version", "release", "arch"])


class LustrePlugin(DevicePlugin):
    delta_fields = ["capabilities", "properties", "mounts", "resource_locations"]

    def __init__(self, session):
        self.reset_state()
        super(LustrePlugin, self).__init__(session)

    def reset_state(self):
        pass

    def _scan_mounts(self):
        try:
            mounts = {}

            (kind, dev_tree) = scanner_cmd("Stream").items().pop()

            lustre_info = []
            get_lustre_mount_info(kind, dev_tree, lustre_info)

            for mount, fs_uuid, fs_label in lustre_info:
                device = mount.get("source")
                mntpnt = mount.get("target")

                recovery_status = {}

                try:
                    lines = AgentShell.try_run(
                        ["lctl", "get_param", "-n", "*.%s.recovery_status" % fs_label]
                    )
                    for line in lines.split("\n"):
                        tokens = line.split(":")
                        if len(tokens) != 2:
                            continue
                        k = tokens[0].strip()
                        v = tokens[1].strip()
                        recovery_status[k] = v
                except Exception:
                    # If the recovery_status file doesn't exist,
                    # we will return an empty dict for recovery info
                    pass

                mounts[device] = {
                    "fs_uuid": fs_uuid,
                    "mount_point": mntpnt,
                    "recovery_status": recovery_status,
                }

            return mounts.values()
        except Exception as e:
            console_log.warning("Error scanning mounts: {}".format(e))
            return {}

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
            "resource_locations": resource_locations,
        }

    def start_session(self):
        self.reset_state()
        self._reset_delta()
        return self._delta_result(self._scan(initial=True), self.delta_fields)

    def update_session(self):
        return self._delta_result(self._scan(), self.delta_fields)

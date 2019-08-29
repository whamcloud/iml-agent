# Copyright (c) 2019 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.

#
# This file contains function only called by old chroma Target Resource Agent
#

import os
import xml.etree.ElementTree as ET

from chroma_agent.lib.pacemaker import cibxpath
from chroma_agent.action_plugins.manage_targets import get_target_config, import_target
from chroma_agent.device_plugins.block_devices import get_local_mounts
from chroma_agent.log import console_log
from iml_common.filesystems.filesystem import FileSystem
from iml_common.lib.agent_rpc import agent_result_is_ok
from iml_common.lib.agent_rpc import agent_result_is_error


def target_running(uuid):
    # This is called by the Target RA from corosync
    from os import _exit

    try:
        info = get_target_config(uuid)
    except (KeyError, TypeError) as err:
        # it can't possibly be running here if the config entry for
        # it doesn't even exist, or if the store doesn't even exist!
        console_log.warning("Exception getting target config: %s", err)
        _exit(1)

    filesystem = FileSystem(info["backfstype"], info["bdev"])

    for devices, mntpnt, _ in get_local_mounts():
        if (mntpnt == info["mntpt"]) and next(
            (
                True
                for device in devices
                if filesystem.devices_match(device, info["bdev"], uuid)
            ),
            False,
        ):
            _exit(0)

    console_log.warning(
        "Did not find mount with matching mntpt and device for %s", uuid
    )
    _exit(1)


def mount_target(uuid, pacemaker_ha_operation):
    # This is called by the Target RA from corosync
    info = get_target_config(uuid)

    import_retries = 60
    succeeded = False

    while import_retries > 0:
        # This loop is needed due pools not being immediately importable during
        # STONITH operations. Track: https://github.com/zfsonlinux/zfs/issues/6727
        result = import_target(
            info["device_type"], info["bdev"], pacemaker_ha_operation
        )
        succeeded = agent_result_is_ok(result)
        if succeeded:
            break
        elif (not pacemaker_ha_operation) or (info["device_type"] != "zfs"):
            exit(-1)
        time.sleep(1)
        import_retries -= 1

    if succeeded is False:
        exit(-1)

    filesystem = FileSystem(info["backfstype"], info["bdev"])

    try:
        filesystem.mount(info["mntpt"])
    except RuntimeError as err:
        # Make sure we export any pools when a mount fails
        export_target(info["device_type"], info["bdev"])

        raise err


def unmount_target(uuid):
    # This is called by the Target RA from corosync

    # only unmount targets that are controlled by chroma:Target
    try:
        result = cibxpath("query", "//primitive")
    except OSError as err:
        if err.rc == errno.ENOENT:
            exit(-1)
        raise err

    dom = ET.fromstring(result.stdout)

    # Searches for <nvpair name="target" value=uuid> in
    # <primitive provider="chroma" type="Target"> in dom
    if (
        next(
            (
                ops
                for res in dom.findall(".//primitive")
                if res.get("provider") == "chroma" and res.get("type") == "Target"
                for ops in res.findall(".//nvpair")
                if ops.get("name") == "target" and ops.get("value") == uuid
            ),
            None,
        )
        is not None
    ):
        return
    dom.unlink()

    info = get_target_config(uuid)

    filesystem = FileSystem(info["backfstype"], info["bdev"])

    filesystem.umount()

    if agent_result_is_error(export_target(info["device_type"], info["bdev"])):
        exit(-1)


ACTIONS = [target_running, mount_target, unmount_target]

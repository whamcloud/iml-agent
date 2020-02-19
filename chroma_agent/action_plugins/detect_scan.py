# Copyright (c) 2019 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.


from datetime import datetime

from chroma_agent.lib.pacemaker import PacemakerConfig, PacemakerConfigurationError
from chroma_agent.lib.shell import AgentShell
from chroma_agent.device_plugins.block_devices import get_mounted_path, scanner_cmd
from iml_common.blockdevices.blockdevice import BlockDevice
from chroma_agent.log import daemon_log
from chroma_agent import config


class LocalTargets(object):
    """
    Allows local targets to be examined.
    Note the targets are only examined once with the results cached.
    Detecting change therefore requires a new instance
    to be created and queried.
    """

    def __init__(self, target_devices):
        # Working set: accumulate device paths for each (uuid, name).  This is
        # necessary because in multipathed environments we will see the same
        # lustre target on more than one block device.  The reason we use name
        # as well as UUID is that two logical targets can have the same UUID
        # when we see a combined MGS+MDT
        uuid_name_to_target = {}

        mount_point_map = {}
        try:
            pc = PacemakerConfig()
            for res in pc.resource_list:
                res = pc.get_resource(res)
                if not res:
                    continue
                agent = "%s:%s:%s" % (
                    res.get("class"),
                    res.get("provider"),
                    res.get("type"),
                )
                if agent == "ocf:lustre:Lustre":
                    mount = next(
                        i.get("value")
                        for i in res.findall("./instance_attributes/nvpair")
                        if i.get("name") == "mountpoint"
                    )
                elif agent == "ocf:ddn:lustre-server":
                    mount = next(
                        i.get("value")
                        for i in res.findall("./instance_attributes/nvpair")
                        if i.get("name") == "directory"
                    )
                elif agent == "ocf:chroma:Target":
                    # if a chroma:Target device exists, then agent-management will be installed
                    from chroma_agent.action_plugins.manage_targets import (
                        get_target_config,
                    )

                    uuid = next(
                        i.get("value")
                        for i in res.findall("./instance_attributes/nvpair")
                        if i.get("name") == "target"
                    )
                    info = get_target_config(uuid)
                    mount = info["mntpt"]
                else:
                    continue
                mount_point_map[mount] = res.get("id")
        except PacemakerConfigurationError:
            pass

        for device in sorted(target_devices, cmp=LocalTargets.comparator):
            block_device = BlockDevice(device["type"], device["path"])

            # If the target_device has no uuid then it doesn't have a filesystem and is of no use to use, but
            # for now let's fill it in an see what happens.
            if device["uuid"] is None:
                try:
                    device["uuid"] = block_device.uuid
                except AgentShell.CommandExecutionError:
                    pass

            # OK, so we really don't have a uuid for this, so we won't find a lustre filesystem on it.
            if device["uuid"] is None:
                daemon_log.info(
                    "Device %s had no UUID and so will not be examined for Lustre"
                    % device["path"]
                )
                continue

            targets = block_device.targets(uuid_name_to_target, device, daemon_log)

            dev_tree = scanner_cmd("Stream").get("Root")
            mnt_point = get_mounted_path(device["path"], dev_tree)
            mounted = mnt_point is not None

            for name in targets.names:
                daemon_log.info(
                    "Device {} contained name: {} and is {}mounted".format(
                        device["path"], name, "" if mounted else "un"
                    )
                )

                try:
                    target_dict = uuid_name_to_target[(device["uuid"], name)]
                    target_dict["devices"].append(device)
                except KeyError:
                    target_dict = {
                        "name": name,
                        "uuid": device["uuid"],
                        "params": targets.params,
                        "device_paths": [device["path"]],
                        "mounted": mounted,
                        "mount_point": mnt_point,
                        "type": device["type"],
                        "ha_label": mount_point_map.get(mnt_point),
                    }
                    uuid_name_to_target[(device["uuid"], name)] = target_dict

        self.targets = uuid_name_to_target.values()

    @classmethod
    def comparator(cls, a, b):
        value = cmp(a["type"], b["type"])

        if value == 0:
            value = cmp(a["uuid"], b["uuid"])

        if value == 0:
            value = cmp(a["path"], b["path"])

        return value


class MgsTargets(object):
    TARGET_NAME_REGEX = "([\w-]+)-(MDT|OST)\w+"

    def __init__(self, local_targets):
        super(MgsTargets, self).__init__()
        self.filesystems = {}

        mgs_target = None

        for t in local_targets:
            if t["name"] == "MGS" and t["mounted"]:
                mgs_target = t

        if mgs_target:
            daemon_log.info("Searching Lustre logs for filesystems")

            block_device = BlockDevice(
                mgs_target["type"], mgs_target["device_paths"][0]
            )

            self.filesystems = block_device.mgs_targets(daemon_log)


def detect_scan(target_devices=None):
    """Look for Lustre on possible devices

    Save the input devices when possible.  Then future calls will
    not need to specify the target_devices
    """

    right_now = str(datetime.now())

    if target_devices is not None:
        target_devices_time_stamped = dict(
            timestamp=right_now, target_devices=target_devices
        )
        config.update(
            "settings", "last_detect_scan_target_devices", target_devices_time_stamped
        )

    try:
        # Recall the last target_devices used in this method
        settings = config.get("settings", "last_detect_scan_target_devices")
    except KeyError:
        # This method was never called with a non-null target_devices
        # or the setting file holding the device record is not found.
        daemon_log.warn(
            "detect_scan improperly called without target_devices "
            "and without a previous call's target_devices to use."
        )

        # TODO: Consider an exception here. But, since this is a rare case, it seems reasonable to return emptiness
        # TODO: If this raised an exception, it should be a handled one in any client, and that seems too heavy
        local_targets = LocalTargets([])
        timestamp = right_now

    else:
        # Have target devices, so process them
        timestamp = settings["timestamp"]
        daemon_log.info(
            "detect_scan called at %s with target_devices saved on %s"
            % (str(datetime.now()), timestamp)
        )
        local_targets = LocalTargets(settings["target_devices"])

    # Return the discovered Lustre components on the target devices, may return emptiness.
    mgs_targets = MgsTargets(local_targets.targets)
    return {
        "target_devices_saved_timestamp": timestamp,
        "local_targets": local_targets.targets,
        "mgs_targets": mgs_targets.filesystems,
    }


ACTIONS = [detect_scan]
CAPABILITIES = []

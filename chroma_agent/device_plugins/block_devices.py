# Copyright (c) 2018 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.
import errno
import json
import os
import re
import socket
from collections import defaultdict
from collections import namedtuple
from toolz.curried import map as cmap, filter as cfilter
from toolz.functoolz import pipe, curry
from chroma_agent.lib.shell import AgentShell
from iml_common.blockdevices.blockdevice import BlockDevice


def scanner_cmd(cmd):
    # Because we are pulling from device-scanner,
    # It is very important that we wait for
    # the udev queue to settle before requesting new data
    AgentShell.run(["udevadm", "settle"])

    client = socket.socket(socket.AF_UNIX)
    client.settimeout(10)
    client.connect_ex("/var/run/device-scanner.sock")
    client.sendall(json.dumps(cmd) + "\n")

    out = ""
    begin = 0

    while True:
        out += client.recv(1024)
        # Messages are expected to be separated by a newline
        # But sometimes it is not placed in the end of the line
        # Thus, take out only the first one
        idx = out.find("\n", begin)

        if idx >= 0:

            try:
                return json.loads(out[:idx])
            except ValueError:
                return None
        begin = len(out)


def get_default(prop, default_value, x):
    y = x.get(prop, default_value)
    return y if y is not None else default_value


def is_path_mounted(path, dev_tree):
    if path in get_default("paths", [], dev_tree) and get_default(
        "mount", None, dev_tree
    ):
        return True

    children = cmap(lambda x: x.values().pop(), get_default("children", [], dev_tree))

    return next((True for c in children if is_path_mounted(path, c)), False)


def get_lustre_mount_info(kind, dev_tree, xs):
    mount = get_default("mount", None, dev_tree)

    if mount and mount.get("fs_type") == "lustre":
        if kind == "Dataset":
            fs_label = next(
                prop["value"]
                for prop in dev_tree["props"]
                if prop["name"] == "lustre:svname"  # used to be fsname
            )

            fs_uuid = dev_tree["guid"]

        elif kind == "LogicalVolume":
            fs_uuid = dev_tree["uuid"]

            label_prefix = "/dev/disk/by-label/"

            fs_label = next(
                p.split(label_prefix, 1)[1]
                for p in dev_tree["paths"]
                if p.startswith(label_prefix)
            )
        else:
            fs_uuid = dev_tree["fs_uuid"]
            fs_label = dev_tree["fs_label"]

        xs.append((mount, fs_uuid, fs_label))

    else:
        children = cmap(
            lambda x: x.items().pop(), get_default("children", [], dev_tree)
        )

        for (kind, c) in children:
            get_lustre_mount_info(kind, c, xs)


def parse_local_mounts(xs):
    """ process block device info returned by device-scanner to produce
        a legacy version of local mounts
    """
    return [(d["source"], d["target"], d["fs_type"]) for d in xs]


def get_local_mounts():
    xs = scanner_cmd("GetMounts")
    return parse_local_mounts(xs)

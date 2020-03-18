# Copyright (c) 2018 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.


import re
import socket
import platform

from chroma_agent.lib.shell import AgentShell
from chroma_agent.device_plugins.audit import BaseAudit
from chroma_agent.device_plugins.audit.mixins import FileSystemMixin


class NodeAudit(BaseAudit, FileSystemMixin):
    def __init__(self, **kwargs):
        super(NodeAudit, self).__init__(**kwargs)

        self.raw_metrics["node"] = {}

    def metrics(self):
        """Returns a hash of metric values."""
        return {"raw": self.raw_metrics}

    def properties(self):
        """Returns less volatile node data suitable for host validation.

        If the fetched property is expensive to compute, it should be cached / updated less frequently.
        """
        zfs_not_installed, stdout, stderr = AgentShell.run_old(["which", "zfs"])

        return {
            "zfs_installed": not zfs_not_installed,
            "distro": platform.linux_distribution()[0],
            "distro_version": float(
                ".".join(platform.linux_distribution()[1].split(".")[:2])
            ),
            "python_version_major_minor": float(
                "%s.%s"
                % (
                    platform.python_version_tuple()[0],
                    platform.python_version_tuple()[1],
                )
            ),
            "python_patchlevel": int(platform.python_version_tuple()[2]),
            "kernel_version": platform.release(),
        }

# Copyright (c) 2018 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.

import subprocess
import re
import os
import errno

from chroma_agent.lib.shell import AgentShell
from chroma_agent.device_plugins.action_runner import CallbackAfterResponse
from chroma_agent.log import daemon_log
from chroma_agent import config
from chroma_agent.conf import ENV_PATH
from chroma_agent.crypto import Crypto
from chroma_agent.lib.yum_utils import yum_util
from iml_common.lib.agent_rpc import agent_result, agent_error, agent_result_ok
from iml_common.lib.service_control import ServiceControl

REPO_PATH = "/etc/yum.repos.d"


def configure_repo(filename, file_contents):
    crypto = Crypto(ENV_PATH)
    full_filename = os.path.join(REPO_PATH, filename)
    temp_full_filename = full_filename + ".tmp"

    # this format needs to match create_repo() in manager agent-bootstrap-script
    file_contents = file_contents.format(
        crypto.AUTHORITY_FILE, crypto.PRIVATE_KEY_FILE, crypto.CERTIFICATE_FILE
    )

    try:
        file_handle = os.fdopen(
            os.open(temp_full_filename, os.O_WRONLY | os.O_CREAT, 0o644), "w"
        )
        file_handle.write(file_contents)
        file_handle.close()
        os.rename(temp_full_filename, full_filename)
    except OSError as error:
        return agent_error(str(error))

    return agent_result_ok


def unconfigure_repo(filename):
    full_filename = os.path.join(REPO_PATH, filename)

    try:
        os.remove(full_filename)
    except OSError as error:
        if error.errno != errno.ENOENT:
            return agent_error(str(error))

    return agent_result_ok


def update_profile(profile):
    """
    Sets the profile to the profile_name by fetching the profile from the manager
    :param profile_name:
    :return: error or result OK
    """
    old_profile = config.get("settings", "profile")
    """
    This is an incomplete solution but the incompleteness is at the bottom of the stack and we need this as a fix up
    for 2.2 release.

    What really needs to happen here is that the profile contains the name of the packages to install and then this
    code would diff the old list and the new list and remove and add appropriately. For now we are just going to do that
    in a hard coded way using the managed property.

    To do this properly the profile needs to contain the packages and the endpoint needs to return them. We are going to
    need it and when we do this function and profiles will need to be extended.

    This code might want to use the update_pacakges as well but it's not clear and we are in a pickle here. This code is
    not bad and doesn't have bad knock on effects.
    """

    if old_profile["managed"] != profile["managed"]:
        if profile["managed"]:
            action = "install"
        else:
            action = "remove"

        try:
            yum_util(action, packages=["python2-iml-agent-management"])
        except AgentShell.CommandExecutionError as cee:
            return agent_error(
                "Unable to set profile because yum returned %s" % cee.result.stdout
            )

    config.update("settings", "profile", profile)

    return agent_result_ok


def remove_packages(packages):
    if packages != []:
        yum_util("remove", packages=packages)

    return agent_result_ok


def install_packages(repos, packages):
    """
    Explicitly evaluate and install or update any specific-version dependencies and satisfy even if
    that involves installing an older package than is already installed.
    Primary use case is installing lustre-modules, which depends on a specific kernel package.

    :param repos: List of strings, yum repo names
    :param packages: List of strings, yum package names
    :return: package report of the format given by the lustre device plugin
    """
    if packages != []:
        yum_util("clean")

        out = yum_util("requires", enablerepo=repos, packages=packages)
        for requirement in [l.strip() for l in out.strip().split("\n")]:
            match = re.match("([^\)/]*) = (.*)", requirement)
            if match:
                require_package, require_version = match.groups()
                packages.append("%s-%s" % (require_package, require_version))

        yum_util("install", enablerepo=repos, packages=packages)

        error = _check_HYD4050()

        if error:
            return agent_error(error)

    ServiceControl.create("iml-update-check").start(0)

    return agent_result_ok


def _check_HYD4050():
    """
    HYD-4050 means that kernels are not installed with a default kernel or the initramfs isn't present.

    This function checks for these cases and returns an error message if a problem exists.

    return: None if everything is OK, error message if not.
    """

    #  Make sure that there is an initramfs for the booting kernel
    try:
        default_kernel = AgentShell.try_run(["grubby", "--default-kernel"]).strip()
    except AgentShell.CommandExecutionError:
        return (
            "Unable to determine your default kernel.  "
            "This node may not boot successfully until grub "
            "is fixed to have a default kernel to boot."
        )

    default_kernel_version = default_kernel[default_kernel.find("-") + 1 :]
    initramfs = "/boot/initramfs-%s.img" % default_kernel_version

    if not os.path.isfile(initramfs):
        return (
            "There is no initramfs (%s) for the default kernel (%s).  "
            "This node may not boot successfully until an initramfs "
            "is created." % (initramfs, default_kernel_version)
        )

    return None


def kernel_status():
    """
    :return: {'running': {'kernel-X.Y.Z'}, 'required': <'kernel-A.B.C' or None>}
    """
    running_kernel = "kernel-%s" % AgentShell.try_run(["uname", "-r"]).strip()

    if AgentShell.run(["rpm", "-q", "--whatprovides", "kmod-lustre"]).rc == 0:
        # on a server, a required kernel is a lustre patched kernel since we
        # are building storage servers that can support both ldiskfs and zfs
        try:
            required_kernel = next(
                k
                for k in sorted(
                    AgentShell.try_run(["rpm", "-q", "kernel"]).split("\n"),
                    reverse=True,
                )
                if "_lustre" in k
            )
        except (AgentShell.CommandExecutionError, StopIteration):
            required_kernel = None
    elif AgentShell.run(["rpm", "-q", "kmod-lustre-client"]).rc == 0:
        # but on a worker, we can ask kmod-lustre-client what the required
        # kernel is
        try:
            required_kernel_prefix = next(
                k
                for k in AgentShell.try_run(
                    ["rpm", "-q", "--requires", "kmod-lustre-client"]
                ).split("\n")
                if "kernel >=" in k
            ).split(" >= ")[1]
            required_kernel = AgentShell.try_run(
                ["rpm", "-q", "kernel-%s*" % required_kernel_prefix]
            ).split("\n")[0]
        except (AgentShell.CommandExecutionError, StopIteration):
            required_kernel = None
    else:
        required_kernel = None

    available_kernels = []
    for installed_kernel in AgentShell.try_run(["rpm", "-q", "kernel"]).split("\n"):
        if installed_kernel:
            available_kernels.append(installed_kernel)

    return {
        "running": running_kernel,
        "required": required_kernel,
        "available": available_kernels,
    }


def selinux_status():
    """
    Get selinux status on node
    :return: {'status': 'Disabled'}
    """
    status = "Disabled"
    rc = AgentShell.run(["getenforce"])
    if rc.rc == 0:
        status = rc.stdout.strip()

    return {"status": status}


def restart_agent():
    def _shutdown():
        daemon_log.info("Restarting iml-storage-server.target")
        # Use subprocess.Popen instead of try_run because we don't want to
        # wait for completion.
        subprocess.Popen(["systemctl", "restart", "iml-storage-server.target"])

    raise CallbackAfterResponse(None, _shutdown)


ACTIONS = [
    configure_repo,
    unconfigure_repo,
    install_packages,
    remove_packages,
    kernel_status,
    selinux_status,
    restart_agent,
    update_profile,
]
CAPABILITIES = ["manage_updates"]

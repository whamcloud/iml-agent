# Copyright (c) 2018 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.


import errno
import os
import re
import time
import socket
from xml.dom.minidom import parseString

from chroma_agent import config
from chroma_agent.action_plugins.manage_pacemaker import PreservePacemakerCorosyncState
from chroma_agent.device_plugins.block_devices import get_local_mounts
from chroma_agent.lib.shell import AgentShell
from chroma_agent.log import console_log
from iml_common.blockdevices.blockdevice import BlockDevice
from iml_common.filesystems.filesystem import FileSystem
from iml_common.lib.agent_rpc import agent_error
from iml_common.lib.agent_rpc import agent_result
from iml_common.lib.agent_rpc import agent_result_ok
from iml_common.lib.agent_rpc import agent_ok_or_error
from iml_common.lib.agent_rpc import agent_result_is_error
from iml_common.lib.agent_rpc import agent_result_is_ok
from iml_common.lib.exception_sandbox import exceptionSandBox
from iml_common.lib.util import platform_info

def writeconf_target(device=None, target_types=(), mgsnode=(), fsname=None,
                     failnode=(), servicenode=(), param=None, index=None,
                     comment=None, mountfsoptions=None, network=(),
                     erase_params=False, nomgs=False, writeconf=False,
                     dryrun=False, verbose=False, quiet=False):
    # freeze a view of the namespace before we start messing with it
    args = dict(locals())

    options = []

    # Workaround for tunefs.lustre being sensitive to argument order:
    # erase-params has to come first or it overrides preceding options.
    # (LU-1462)
    early_flag_options = {
        'erase_params': '--erase-params'
    }
    for arg, val in early_flag_options.items():
        if args[arg]:
            options.append("%s" % val)

    tuple_options = ["target_types", "mgsnode", "failnode", "servicenode", "network"]
    for name in tuple_options:
        arg = args[name]
        # ensure that our tuple arguments are always tuples, and not strings
        if not hasattr(arg, "__iter__"):
            arg = (arg,)

        if name == "target_types":
            for target in arg:
                options.append("--%s" % target)
        elif name == 'mgsnode':
            for mgs_nids in arg:
                options.append("--%s=%s" % (name, ",".join(mgs_nids)))
        else:
            if len(arg) > 0:
                options.append("--%s=%s" % (name, ",".join(arg)))

    dict_options = ["param"]
    for name in dict_options:
        arg = args[name]
        if arg:
            for key in arg:
                if arg[key] is not None:
                    options.extend(["--%s" % name, "%s=%s" % (key, arg[key])])

    flag_options = {
        'nomgs': '--nomgs',
        'writeconf': '--writeconf',
        'dryrun': '--dryrun',
        'verbose': '--verbose',
        'quiet': '--quiet',
    }
    for arg in flag_options:
        if args[arg]:
            options.append("%s" % flag_options[arg])

    # everything else
    handled = set(flag_options.keys() + early_flag_options.keys() + tuple_options + dict_options)
    for name in set(args.keys()) - handled:
        if name == "device":
            continue
        value = args[name]

        if value is not None:
            options.append("--%s=%s" % (name, value))

    AgentShell.try_run(['tunefs.lustre'] + options + [device])


def get_resource_location(resource_name):
    '''
    Given a resource name testfs-MDT0000_f64edc for example, return the host it is mounted on
    :param resource_name: Name of resource to find.
    :return: host currently mounted on or None if not mounted.
    '''
    locations = get_resource_locations()

    if not isinstance(locations, dict):
        # Pacemaker not running, or no resources configured yet
        return None

    return locations.get(resource_name)

def _get_resource_locations(xml):
    # allow testing
    dom = parseString(xml)

    locations = {}
    for res in dom.getElementsByTagName('resource'):
        agent = res.getAttribute("resource_agent")
        if agent in ["ocf::chroma:Target", "ocf::lustre:Lustre"]:
            resid = res.getAttribute("id")
            if res.getAttribute("role") in ["Started", "Stopping"] and res.getAttribute("failed") == "false":
                node = res.getElementsByTagName("node")[0]
                locations[resid] = node.getAttribute("name")
            else:
                locations[resid] = None

    return locations

@exceptionSandBox(console_log, None)
def get_resource_locations():
    """Parse `crm_mon -1` to identify where (if anywhere) resources
    (i.e. targets) are running
    returns [ resoure_id: location|None, ... ]
    """
    try:
        result = AgentShell.run(["crm_mon", "-1", "-r", "-X"])
    except OSError, err:
        # ENOENT is fine here.  Pacemaker might not be installed yet.
        if err.errno != errno.ENOENT:
            raise

    if result.rc != 0:
        # Pacemaker not running, or no resources configured yet
        return {"crm_mon_error": {"rc": result.rc,
                                  "stdout": result.stdout,
                                  "stderr": result.stderr}}

    return _get_resource_locations(result.stdout)

def check_block_device(path, device_type):
    """
    Precursor to formatting a device: check if there is already a filesystem on it.

    :param path: Path to a block device
    :param device_type: The type of device the path references
    :return The filesystem type of the filesystem on the device, or None if unoccupied.
    """
    return agent_ok_or_error(BlockDevice(device_type, path).filesystem_info)


def format_target(device_type, target_name, device, backfstype,
                  target_types=(), mgsnode=(), fsname=None,
                  failnode=(), servicenode=(), param={}, index=None,
                  comment=None, mountfsoptions=None, network=(),
                  device_size=None, mkfsoptions=None,
                  reformat=False, stripe_count_hint=None, iam_dir=False,
                  dryrun=False, verbose=False, quiet=False):
    """Perform a mkfs.lustre operation on a target device.
       Device may be a number of devices, block"""

    # freeze a view of the namespace before we start messing with it
    args = dict(locals())
    options = []

    # Now remove the locals that are not parameters for mkfs.
    del args['device_type']
    del args['target_name']

    tuple_options = ["target_types", "mgsnode", "failnode", "servicenode", "network"]
    for name in tuple_options:
        arg = args[name]
        # ensure that our tuple arguments are always tuples, and not strings
        if not hasattr(arg, "__iter__"):
            arg = (arg,)

        if name == "target_types":
            for target in arg:
                options.append("--%s" % target)
        elif name == 'mgsnode':
            for mgs_nids in arg:
                options.append("--%s=%s" % (name, ",".join(mgs_nids)))
        else:
            if len(arg) > 0:
                options.append("--%s=%s" % (name, ",".join(arg)))

    flag_options = {
        'dryrun': '--dryrun',
        'reformat': '--reformat',
        'iam_dir': '--iam-dir',
        'verbose': '--verbose',
        'quiet': '--quiet',
    }

    for arg in flag_options:
        if args[arg]:
            options.append("%s" % flag_options[arg])

    dict_options = ["param"]
    for name in dict_options:
        for key, value in args[name].items():
            if value is not None:
                options.extend(["--%s" % name, "%s=%s" % (key, value)])

    # everything else
    handled = set(flag_options.keys() + tuple_options + dict_options)
    for name in set(args.keys()) - handled:
        if name == "device":
            continue
        value = args[name]
        if value is not None:
            options.append("--%s=%s" % (name, value))

    # cache BlockDevice to store knowledge of the device_type at this path
    BlockDevice(device_type, device)
    filesystem = FileSystem(backfstype, device)

    return filesystem.mkfs(target_name, options)


def _mkdir_p_concurrent(path):
    # To cope with concurrent calls with a common sub-path, we have to do
    # this in two steps:
    #  1. Create the common portion (e.g. /mnt/whamfs/)
    #  2. Create the unique portion (e.g. /mnt/whamfs/ost0/)
    # If we tried to do a single os.makedirs, we could get an EEXIST when
    # colliding on the creation of the common portion and therefore miss
    # creating the unique portion.

    path = path.rstrip("/")

    def mkdir_silent(path):
        try:
            os.makedirs(path)
        except OSError, err:
            if err.errno == errno.EEXIST:
                pass
            else:
                raise err

    parent = os.path.split(path)[0]
    mkdir_silent(parent)
    mkdir_silent(path)


def register_target(device_path, mount_point, backfstype):
    filesystem = FileSystem(backfstype, device_path)

    _mkdir_p_concurrent(mount_point)

    filesystem.mount(mount_point)

    filesystem.umount()

    return {'label': filesystem.label}


def _unconfigure_target_ha(ha_label, info, force=False):
    if force:
        extra = ["--force"]
    else:
        extra = []

    result = AgentShell.run(['pcs', 'resource', 'delete', ha_label] + extra)
    if info['backfstype'] == "zfs":
        AgentShell.run(['pcs', 'resource', 'delete', '%s-zfs' % ha_label] + extra)

    return result


def unconfigure_target_ha(primary, ha_label, uuid):
    '''
    Unconfigure the target high availability

    :param primary: Boolean if localhost is primary
    :param ha_label: String that identifies resource
    :param uuid: UUID that identifies config
    :return: Value using simple return protocol
     '''

    with PreservePacemakerCorosyncState():
        info = _get_target_config(uuid)
        if get_resource_location(ha_label):
            return agent_error("cannot unconfigure-ha: %s is still running " % ha_label)

        _unconfigure_target_priority(primary, ha_label)

        if primary:
            result = _unconfigure_target_ha(ha_label, info)

            if result.rc != 0 and result.rc != 234:
                return agent_error("Error %s trying to cleanup resource %s" % (result.rc, ha_label))

        return agent_result_ok


def unconfigure_target_store(uuid):
    '''
    Remove target directory and config store for given uuid.

    :param uuid: UUID identifying target
    '''
    try:
        target = _get_target_config(uuid)
        os.rmdir(target['mntpt'])
    except KeyError:
        console_log.warn("Cannot retrieve target information")
    except IOError:
        console_log.warn("Cannot remove target mount folder: %s" % target['mntpt'])
    config.delete('targets', uuid)


def configure_target_store(device, uuid, mount_point, backfstype, device_type):
    # Logically this should be config.set - but an error condition exists where the
    # configure_target_store steps fail later on and so the config exists but the manager doesn't
    # know. Meaning that a set fails because of a duplicate, where as an update doesn't.  So use
    # update because that updates or creates.
    config.update('targets', uuid, {'bdev': device,
                                    'mntpt': mount_point,
                                    'backfstype': backfstype,
                                    'device_type': device_type})


def _this_node():
    # Hostname. This is a shorterm point fix that will allow us to make HP2 release more
    # functional. Between el6 and el7 (truthfully we should probably be looking at Pacemaker or
    # Corosync versions) Pacemaker started to use fully qualified domain names rather than just the
    # nodename.  lotus-33vm15.lotus.hpdd.lab.intel.com vs lotus-33vm15. To keep compatiblity easily
    # we have to make the contraints follow the same fqdn vs node.
    if platform_info.distro_version >= 7.0:
        node = socket.getfqdn()
    else:
        node = os.uname()[1]
    return node


def _unconfigure_target_priority(primary, ha_label):
    if primary:
        preference = "primary"
    else:
        preference = "secondary"
    return AgentShell.run(['pcs', 'constraint', 'location', 'remove', "%s-%s" % (ha_label, preference)])


def _configure_target_priority(primary, ha_label, node):
    if primary:
        score = 20
        preference = "primary"
    else:
        score = 10
        preference = "secondary"

    result = AgentShell.run(['pcs', 'constraint', 'location', 'add',
                             "%s-%s" % (ha_label, preference), '%s-lu' % ha_label, node, "%d" % score])

    if result.rc == 76:
        console_log.warn("A constraint with the name %s-%s already exists" %
                         (ha_label, preference))
        result.rc = 0

    return result


def _configure_target_ha(ha_label, info, enabled=False):
    if enabled:
        extra = []
    else:
        extra = ['--disabled']

    if info['device_type'] == 'zfs':
        extra += ['--group', 'group-%s' % ha_label]
        zpool = info['bdev'].split("/")[0]
        result = AgentShell.run(['pcs', 'resource', 'create',
                                 '%s-zfs' % ha_label, 'ocf:chroma:ZFS', 'pool=%s' % zpool,
                                 'op', 'start', 'timeout=90', 'op', 'stop', 'timeout=90'] + extra)
        if result.rc != 0:
            # @@ remove Lustre resource?
            return agent_error("Failed to create ZFS resource for zpool:%s for resource %s" %
                               (zpool, ha_label))
        realpath = info['bdev']

    else:
        # Because of LU-11461 find realpath of devices and use that as Lustre target
        result = AgentShell.run(['realpath', info['bdev']])
        if result.rc == 0:
            realpath = result.stdout.strip()
        else:
            realpath = info['bdev']

    # Create Lustre resource and add target=uuid as an attribute
    result = AgentShell.run(['pcs', 'resource', 'create', ha_label, 'ocf:lustre:Lustre',
                             'target=%s' % realpath, 'mountpoint=%s' % info['mntpt']] + extra)

    if result.rc != 0 and info['device_type'] == 'zfs':
        console_log.error("Failed to create resource %s" % ha_label)
        AgentShell.run(['pcs', 'resource', 'delete', '%s-zfs' % ha_label])

    return result

def configure_target_ha(primary, device, ha_label, uuid, mount_point):
    '''
    Configure the target high availability

    :return: Value using simple return protocol
    '''

    _mkdir_p_concurrent(mount_point)

    if primary:
        info = _get_target_config(uuid)
        # If the target already exists with the same params, skip.
        # If it already exists with different params, that is an error
        if _resource_exists(ha_label):
            if info['bdev'] == device and info['mntpt'] == mount_point:
                return agent_result_ok
            else:
                return agent_error("A resource with the name %s already exists" % ha_label)
        if info['bdev'] != device or info['mntpt'] != mount_point:
            console_log.error("Mismatch for %s do not match configured (%s on %s) != (%s on %s)" %
                              (ha_label, device, mount_point, info['bdev'], info['mntpt']))
        _configure_target_ha(ha_label, info)

    _configure_target_priority(primary, ha_label, _this_node())

    return agent_result_ok


def mount_target(uuid, pacemaker_ha_operation):
    # This is called by the Target RA from corosync
    info = _get_target_config(uuid)

    import_retries = 60
    succeeded = False

    for i in xrange(import_retries):
        # This loop is needed due pools not being immediately importable during
        # STONITH operations. Track: https://github.com/zfsonlinux/zfs/issues/6727
        result = import_target(info['device_type'], info['bdev'], pacemaker_ha_operation)
        succeeded = agent_result_is_ok(result)
        if succeeded:
            break
        elif (not pacemaker_ha_operation) or (info['device_type'] != 'zfs'):
            exit(-1)
        time.sleep(1)

    if succeeded is False:
        exit(-1)

    filesystem = FileSystem(info['backfstype'], info['bdev'])

    try:
        filesystem.mount(info['mntpt'])
    except RuntimeError, err:
        # Make sure we export any pools when a mount fails
        export_target(info['device_type'], info['bdev'])

        raise err


def unmount_target(uuid):
    # This is called by the Target RA from corosync

    # only unmount targets that are controlled by chroma:Target
    try:
        result = AgentShell.run(['cibadmin', '--query'])
    except OSError, err:
        if err.errno != errno.ENOENT:
            raise
    if result.rc != 0:
        exit(-1)
    dom = parseString(result.stdout)

    # Searches for <nvpair name="target" value=uuid> in <primitive provider="chroma" type="Target"> in dom
    if not next((ops for res in dom.getElementsByTagName('primitive')
                 if res.getAttribute("provider") == "chroma" and res.getAttribute("type") == "Target"
                 for ops in res.getElementsByTagName('nvpair')
                 if ops.getAttribute("name") == "target" and ops.getAttribute("value") == uuid),
                False):
        return

    info = _get_target_config(uuid)

    filesystem = FileSystem(info['backfstype'], info['bdev'])

    filesystem.umount()

    if agent_result_is_error(export_target(info['device_type'], info['bdev'])):
        exit(-1)


def import_target(device_type, path, pacemaker_ha_operation):
    """
    Passed a device type and a path import the device if such an operation make sense. For example a jbod scsi
    disk does not have the concept of import whilst zfs does.
    :param device_type: the type of device to import
    :param path: path of device to import
    :param pacemaker_ha_operation: This import is at the request of pacemaker. In HA operations the device may
               often have not have been cleanly exported because the previous mounted node failed in operation.
    :return: None or an Error message
    """
    blockdevice = BlockDevice(device_type, path)

    error = blockdevice.import_(False)
    if error:
        if '-f' in error and pacemaker_ha_operation:
            error = blockdevice.import_(True)

    if error:
        console_log.error("Error importing pool: '%s'" % error)

    return agent_ok_or_error(error)


def export_target(device_type, path):
    """
    Passed a device type and a path export the device if such an operation make sense. For example a jbod scsi
    disk does not have the concept of export whilst zfs does.
    :param path: path of device to export
    :param device_type: the type of device to export
    :return: None or an Error message
    """

    blockdevice = BlockDevice(device_type, path)

    error = blockdevice.export()

    if error:
        console_log.error("Error exporting pool: '%s'" % error)

    return agent_ok_or_error(error)


def _wait_target(ha_label, started):
    '''
    Wait for a target to be started/stopped
    :param ha_label: Label of target to wait for
    :param started: True if waiting for started, False if waiting for stop.
    :return: True if successful.
    '''

    # Now wait for it to stop, if a lot of things are starting/stopping this can take a long long time.
    # So if the number of things started is changing we keep going, but when nothing at all has stopped
    # for 2 minutes we timeout, but an overall timeout of 20 minutes.
    master_timeout = 1200
    activity_timeout = 120
    started_items = -1

    while (master_timeout > 0) and (activity_timeout > 0):
        locations = get_resource_locations()

        if (locations.get(ha_label) is not None) == started:
            return True

        current_started_items = reduce(lambda x, y: x + 1 if y is not None else x, [0] + locations.values())

        if started_items != current_started_items:
            started_items = current_started_items
            activity_timeout = 120

        time.sleep(1)

        master_timeout -= 1
        activity_timeout -= 1

    return False

def _resource_exists(ha_label):
    '''
    Check if a resource exists in current configuration.
    :return: True if exists
    '''
    result = AgentShell.run(["crm_resource", "-W", "-r", ha_label])
    return result.rc == 0

def start_target(ha_label):
    '''
    Start the high availability target

    Return: Value using simple return protocol
    '''
    # HYD-1989: brute force, try up to 3 times to start the target
    i = 0
    while True:
        i += 1

        # This section could just try enabling the group- if -zfs exists, but doing them
        # individually is safer, since if one is enabled and one isn't, enabling the group
        # doesn't enable the disabled resource.
        error = AgentShell.run_canned_error_message(['pcs', 'resource', 'enable', ha_label])
        if error:
            return agent_error(error)
        if _resource_exists(ha_label+'-zfs'):
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'enable', ha_label+'-zfs'])

        # now wait for it to start
        if _wait_target(ha_label, True):
            location = get_resource_location(ha_label)
            if not location:
                return agent_error("Started %s but now can't locate it!" % ha_label)
            return agent_result(location)

        else:
            # try to leave things in a sane state for a failed mount
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'disable', ha_label])

            if error:
                return agent_error(error)

            if i < 4:
                console_log.info("failed to start target %s" % ha_label)
            else:
                return agent_error("Failed to start target %s" % ha_label)


def stop_target(ha_label):
    '''
    Stop the high availability target

    Return: Value using simple return protocol
    '''
    # HYD-7230: brute force, try up to 3 times to stop the target
    i = 0
    while True:
        i += 1

        # Issue the command to Pacemaker to stop the target
        if _resource_exists(ha_label+'-zfs'):
            # Group disable will disable all members of group regardless of current status
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'disable', 'group-'+ha_label])
        else:
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'disable', ha_label])

        if error:
            return agent_error(error)

        if _wait_target(ha_label, False):
            return agent_result_ok

        if i < 4:
            console_log.info("failed to stop target %s" % ha_label)
        else:
            return agent_error("failed to stop target %s" % ha_label)


def _move_target(target_label, dest_node):
    """
    common plumbing for failover/failback. Move the target with label to the destination node.

    :param target_label: The label of the node to move
    :param dest_node: The target to move it to.
    :return: None if successful or an error message if an error occurred.
    """

    # Issue the command to Pacemaker to move the target
    arg_list = ['crm_resource', '--resource', target_label, '--move', '--node', dest_node]

    # For on going debug purposes, lets get the resource locations at the beginning. This provides useful
    # log output in the case where things don't work.
    AgentShell.run(['crm_mon', '-1'])

    # Now before we start cleanup anything that has gone on before. HA is a fickle old thing and this will make sure
    # that everything is clean before we start.
    AgentShell.try_run(['crm_resource', '--resource', target_label, '--cleanup'])

    result = AgentShell.run(arg_list)

    if result.rc != 0:
        return "Error (%s) running '%s': '%s' '%s'" % (result.rc, " ".join(arg_list), result.stdout, result.stderr)

    timeout = 100

    # Now wait for it to complete its move, this will succeed quickly if it was already there
    while timeout > 0:
        if get_resource_location(target_label) == dest_node:
            break

        time.sleep(1)
        timeout -= 1

    # now delete the constraint that crm_resource --move created
    AgentShell.try_run(['crm_resource', '--resource', target_label, '--un-move', '--node', dest_node])

    if timeout <= 0:
        return "Failed to move target %s to node %s" % (target_label, dest_node)

    return None


def _find_resource_constraint(ha_label, location):
    stdout = AgentShell.try_run(["crm_resource", "-r", ha_label, "-a"])

    for line in stdout.rstrip().split("\n"):
        match = re.match(r"\s+:\s+Node\s+([^\s]+)\s+\(score=[^\s]+ id=%s-%s\)" %
                         (ha_label, location), line)
        if match:
            return match.group(1)

    return None


def _failoverback_target(ha_label, destination):
    """Fail a target over to the  destination node

    Return: Value using simple return protocol
    """
    node = _find_resource_constraint(ha_label, destination)
    if not node:
        return agent_error("Unable to find the %s server for '%s'" % (destination, ha_label))

    error = _move_target(ha_label, node)

    if error:
        return agent_error(error)

    return agent_result_ok


def failover_target(ha_label):
    """
    Fail a target over to its secondary node

    Return: Value using simple return protocol
    """
    return _failoverback_target(ha_label, "secondary")


def failback_target(ha_label):
    """
    Fail a target back to its primary node

    Return: None if OK, else return an Error string
    """
    return _failoverback_target(ha_label, "primary")


def _get_target_config(uuid):
    info = config.get('targets', uuid)

    # Some history, previously the backfstype, device_type was not stored so if not present presume ldiskfs/linux
    if ('backfstype' not in info) or ('device_type' not in info):
        info['backfstype'] = info.get('backfstype', 'ldiskfs')
        info['device_type'] = info.get('device_type', 'linux')
        config.update('targets', uuid, info)
    return info


def target_running(uuid):
    # This is called by the Target RA from corosync
    from os import _exit
    try:
        info = _get_target_config(uuid)
    except (KeyError, TypeError) as err:
        # it can't possibly be running here if the config entry for
        # it doesn't even exist, or if the store doesn't even exist!
        console_log.warning("Exception getting target config: " + err)
        _exit(1)

    filesystem = FileSystem(info['backfstype'], info['bdev'])

    for device, mntpnt, fstype in get_local_mounts():
        if (mntpnt == info['mntpt']) and filesystem.devices_match(device, info['bdev'], uuid):
            _exit(0)

    console_log.warning("Did not find mount with matching mntpt and device for %s" % uuid)
    _exit(1)


def purge_configuration(mgs_device_path, mgs_device_type, filesystem_name):
    mgs_blockdevice = BlockDevice(mgs_device_type, mgs_device_path)

    return agent_ok_or_error(mgs_blockdevice.purge_filesystem_configuration(filesystem_name, console_log))


def convert_targets(force=False):
    '''
    Convert existing ocf:chroma:Target to ocf:chroma:ZFS + ocf:lustre:Lustre
    '''
    try:
        result = AgentShell.run(['cibadmin', '--query'])
    except OSError, err:
        if err.errno != errno.ENOENT:
            raise

    if result.rc != 0:
        # Pacemaker not running, or no resources configured yet
        return {"crm_mon_error": {"rc": result.rc,
                                  "stdout": result.stdout,
                                  "stderr": result.stderr}}

    dom = parseString(result.stdout)

    this_node = _this_node()

    # node elements are numbered from 1
    # dc-uuid is the node id of the domain controller
    dcuuid = next((node.getAttribute('uname') for node in dom.getElementsByTagName('node')
                   if node.getAttribute("id") == dom.documentElement.getAttribute('dc-uuid')), "")
    if dcuuid != this_node and not force:
        console_log.info("This is not Pacemaker DC %s this is %s" % (dcuuid, this_node))
        return

    # Build map of resource -> [ primary node, secondary node ]
    locations = {}
    for con in dom.getElementsByTagName('rsc_location'):
        ha_label = con.getAttribute("rsc")
        if not locations.get(ha_label):
            locations[ha_label] = {}
        if con.getAttribute("id") == ha_label+"-primary":
            ind = 0
        elif con.getAttribute("id") == ha_label+"-secondary":
            ind = 1
        else:
            console_log.info("Unknown constraint: "+con.getAttribute("id"))
            continue
        locations[ha_label][ind] = con.getAttribute("node")

    active = get_resource_locations()

    AgentShell.run(['pcs', 'property', 'set', 'maintenance-mode=true'])

    wait_list = []
    for res in dom.getElementsByTagName('primitive'):
        if not (res.getAttribute("provider") == "chroma" and res.getAttribute("type") == "Target"):
            continue

        ha_label = res.getAttribute("id")

        info = None
        for ops in res.getElementsByTagName('nvpair'):
            if ops.getAttribute("name") == "target":
                uuid = ops.getAttribute("value")
                try:
                    info = _get_target_config(uuid)
                except Exception as err:
                    console_log.debug("Could not get info for uuid " + uuid)
                break

        if not info:
            console_log.error("No local info for resource: "+ ha_label)
            continue

        _unconfigure_target_priority(False, ha_label)
        _unconfigure_target_priority(True, ha_label)
        _unconfigure_target_ha(ha_label, info, True)
        _configure_target_ha(ha_label, info, (active.get(ha_label) is not None))
        _configure_target_priority(True, ha_label, locations[ha_label][0])
        _configure_target_priority(False, ha_label, locations[ha_label][1])
        wait_list.append([ha_label, (active.get(ha_label) is not None)])

    # wait for last item
    for wait in wait_list:
        console_log.info("Waiting on "+wait[0])
        _wait_target(wait[0], wait[1])
    AgentShell.run(['pcs', 'property', 'unset', 'maintenance-mode'])

ACTIONS = [purge_configuration, register_target,
           configure_target_ha, unconfigure_target_ha,
           mount_target, unmount_target,
           import_target, export_target,
           start_target, stop_target,
           format_target, check_block_device,
           writeconf_target, failback_target,
           failover_target, target_running,
           convert_targets,
           configure_target_store, unconfigure_target_store]

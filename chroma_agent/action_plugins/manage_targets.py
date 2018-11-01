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
    options += [early_flag_options[arg] for arg in early_flag_options if args[arg]]

    single = "--{}".format
    double = "--{}={}".format

    tuple_options = ["target_types", "mgsnode", "failnode", "servicenode", "network"]
    for name in tuple_options:
        arg = args[name]
        # ensure that our tuple arguments are always tuples, and not strings
        if not hasattr(arg, "__iter__"):
            arg = (arg,)

        if name == "target_types":
            options += [single(target) for target in arg]
        elif name == 'mgsnode':
            options += [double(name, ",".join(mgs_nids)) for mgs_nids in arg]
        elif len(arg) > 0:
            options.append(double(name, ",".join(arg)))

    dict_options = ["param"]
    for name in dict_options:
        arg = args[name]
        if arg:
            options += [x for key in arg
                        if arg[key] is not None
                        for x in [single(name), "{}={}".format(key, arg[key])]]

    # flag options
    flag_options = ['writeconf', 'quiet', 'dryrun', 'nomgs', 'verbose']
    options += [single(arg) for arg in flag_options if args[arg]]

    # everything else
    handled = set(flag_options + early_flag_options.keys() + tuple_options + dict_options)
    options += [double(name, args[name]) for name in set(args.keys()) - handled
                if name != "device" and args[name] is not None]

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
            if res.getAttribute("role") in ["Started", "Stopping"] and \
               res.getAttribute("failed") == "false":
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
                  failnode=(), servicenode=(), param=None, index=None,
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

    single = "--{}".format
    double = "--{}={}".format

    tuple_options = ["target_types", "mgsnode", "failnode", "servicenode", "network"]
    for name in tuple_options:
        arg = args[name]
        # ensure that our tuple arguments are always tuples, and not strings
        if not hasattr(arg, "__iter__"):
            arg = (arg,)

        if name == "target_types":
            options += [single(target) for target in arg]
        elif name == 'mgsnode':
            options += [double(name, ",".join(mgs_nids)) for mgs_nids in arg]
        elif len(arg) > 0:
            options.append(double(name, ",".join(arg)))

    flag_options = {
        'dryrun': '--dryrun',
        'reformat': '--reformat',
        'iam_dir': '--iam-dir',
        'verbose': '--verbose',
        'quiet': '--quiet',
    }
    options += [flag_options[arg] for arg in flag_options if args[arg]]

    dict_options = ["param"]
    for name in dict_options:
        arg = args[name]
        if arg:
            options += [x for key in arg
                        if arg[key] is not None
                        for x in [single(name), "{}={}".format(key, arg[key])]]

    # everything else
    handled = set(flag_options.keys() + tuple_options + dict_options)
    options += [double(name, args[name]) for name in set(args.keys()) - handled
                if name != "device" and args[name] is not None]

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


def _zfs_name(ha_label):
    # Name of zfs resource in resource group for given lustre ha_label
    return "{}-zfs".format(ha_label)


def _group_name(ha_label):
    # Name of resource group for given ha_label
    return "group-{}".format(ha_label)

def _constraint(ha_label, primary):
    if primary:
        preference = "primary"
    else:
        preference = "secondary"
    return "{}-{}".format(ha_label, preference)

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
        AgentShell.run(['pcs', 'resource', 'delete', _zfs_name(ha_label)] + extra)

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
            return agent_error("cannot unconfigure-ha: {} is still running ".format(ha_label))

        _unconfigure_target_priority(primary, ha_label)

        if primary:
            result = _unconfigure_target_ha(ha_label, info)

            if result.rc != 0 and result.rc != 234:
                return agent_error("Error {} trying to cleanup resource {}".format(result.rc,
                                                                                   ha_label))

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
        console_log.warn("Cannot remove target mount folder: %s", target['mntpt'])
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
    return socket.getfqdn()


def _unconfigure_target_priority(primary, ha_label):
    return AgentShell.run(['pcs', 'constraint', 'location', 'remove',
                           _constraint(ha_label, primary)])


def _configure_target_priority(primary, ha_label, node):
    if primary:
        score = "20"
    else:
        score = "10"

    name = _constraint(ha_label, primary)
    result = AgentShell.run(['pcs', 'constraint', 'location', 'add', name, ha_label, node, score])

    if result.rc == 76:
        console_log.warn("A constraint with the name %s already exists", name)
        result.rc = 0

    return result


def _configure_target_ha(ha_label, info, enabled=False):
    if enabled:
        extra = []
    else:
        extra = ['--disabled']

    if info['device_type'] == 'zfs':
        extra += ['--group', _group_name(ha_label)]
        zpool = info['bdev'].split("/")[0]
        result = AgentShell.run(['pcs', 'resource', 'create',
                                 _zfs_name(ha_label), 'ocf:chroma:ZFS', 'pool={}'.format(zpool),
                                 'op', 'start', 'timeout=90', 'op', 'stop', 'timeout=90'] + extra)
        if result.rc != 0:
            console_log.error("Resource (%s) create failed:%d: %s", zpool, result.rc, result.stderr)
            return result

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
                             'target={}'.format(realpath),
                             'mountpoint={}'.format(info['mntpt'])] + extra)

    if result.rc != 0:
        console_log.error("Failed to create resource %s:%d: %s",
                          ha_label, result.rc, result.stderr)

        if info['device_type'] == 'zfs':
            AgentShell.run(['pcs', 'resource', 'delete', _zfs_name(ha_label)])

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
                return agent_error("A resource with the name {} already exists".format(ha_label))
        if info['bdev'] != device or info['mntpt'] != mount_point:
            console_log.error("Mismatch for %s do not match configured (%s on %s) != (%s on %s)",
                              ha_label, device, mount_point, info['bdev'], info['mntpt'])
        result = _configure_target_ha(ha_label, info)
        if result.rc != 0:
            return agent_error("Failed to create {}: {}".format(ha_label, result.rc))

    _configure_target_priority(primary, ha_label, _this_node())

    return agent_result_ok


def mount_target(uuid, pacemaker_ha_operation):
    # This is called by the Target RA from corosync
    info = _get_target_config(uuid)

    import_retries = 60
    succeeded = False

    while import_retries > 0:
        # This loop is needed due pools not being immediately importable during
        # STONITH operations. Track: https://github.com/zfsonlinux/zfs/issues/6727
        result = import_target(info['device_type'], info['bdev'], pacemaker_ha_operation)
        succeeded = agent_result_is_ok(result)
        if succeeded:
            break
        elif (not pacemaker_ha_operation) or (info['device_type'] != 'zfs'):
            exit(-1)
        time.sleep(1)
        import_retries -= 1

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

    # Searches for <nvpair name="target" value=uuid> in
    # <primitive provider="chroma" type="Target"> in dom
    if not next((ops for res in dom.getElementsByTagName('primitive')
                 if res.getAttribute("provider") == "chroma" and res.getAttribute("type") == "Target"
                 for ops in res.getElementsByTagName('nvpair')
                 if ops.getAttribute("name") == "target" and ops.getAttribute("value") == uuid),
                False):
        return
    dom.unlink()

    info = _get_target_config(uuid)

    filesystem = FileSystem(info['backfstype'], info['bdev'])

    filesystem.umount()

    if agent_result_is_error(export_target(info['device_type'], info['bdev'])):
        exit(-1)


def import_target(device_type, path, pacemaker_ha_operation):
    """
    Passed a device type and a path import the device if such an operation make sense.
    For example a jbod scsi disk does not have the concept of import whilst zfs does.
    :param device_type: the type of device to import
    :param path: path of device to import
    :param pacemaker_ha_operation: This import is at the request of pacemaker. In HA operations the
    device may often have not have been cleanly exported because the previous mounted node failed
    in operation.
    :return: None or an Error message

    """
    blockdevice = BlockDevice(device_type, path)

    error = blockdevice.import_(False)
    if error:
        if '-f' in error and pacemaker_ha_operation:
            error = blockdevice.import_(True)

    if error:
        console_log.error("Error importing pool: '%s'", error)

    return agent_ok_or_error(error)


def export_target(device_type, path):
    """
    Passed a device type and a path export the device if such an operation make sense.
    For example a jbod scsi disk does not have the concept of export whilst zfs does.
    :param path: path of device to export
    :param device_type: the type of device to export
    :return: None or an Error message
    """

    blockdevice = BlockDevice(device_type, path)

    error = blockdevice.export()

    if error:
        console_log.error("Error exporting pool: '%s'", error)

    return agent_ok_or_error(error)


def _wait_target(ha_label, started):
    '''
    Wait for a target to be started/stopped
    :param ha_label: Label of target to wait for
    :param started: True if waiting for started, False if waiting for stop.
    :return: True if successful.
    '''

    # Now wait for it to stop, if a lot of things are starting/stopping this can take a long long
    # time.  So if the number of things started is changing we keep going, but when nothing at all
    # has stopped for 2 minutes we timeout, but an overall timeout of 20 minutes.
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

        error = AgentShell.run_canned_error_message(['pcs', 'resource', 'enable', ha_label])
        if error:
            return agent_error(error)
        if _resource_exists(_zfs_name(ha_label)):
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'enable',
                                                         _zfs_name(ha_label)])
            if error:
                return agent_error(error)
        if _resource_exists(_group_name(ha_label)):
            # enable group also, in case group was disabled
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'enable',
                                                         _group_name(ha_label)])
            if error:
                return agent_error(error)

        # now wait for it to start
        if _wait_target(ha_label, True):
            location = get_resource_location(ha_label)
            if not location:
                return agent_error("Started {} but now can't locate it!".format(ha_label))
            return agent_result(location)

        else:
            # try to leave things in a sane state for a failed mount
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'disable', ha_label])

            if error:
                return agent_error(error)

            if i < 4:
                console_log.info("failed to start target %s", ha_label)
            else:
                return agent_error("Failed to start target {}".format(ha_label))


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
        if _resource_exists(_zfs_name(ha_label)):
            # Group disable will disable all members of group regardless of current status
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'disable',
                                                         _group_name(ha_label)])
        else:
            error = AgentShell.run_canned_error_message(['pcs', 'resource', 'disable', ha_label])

        if error:
            return agent_error(error)

        if _wait_target(ha_label, False):
            return agent_result_ok

        if i < 4:
            console_log.info("failed to stop target %s", ha_label)
        else:
            return agent_error("Failed to stop target {}".format(ha_label))


def _move_target(target_label, dest_node):
    """
    common plumbing for failover/failback. Move the target with label to the destination node.

    :param target_label: The label of the node to move
    :param dest_node: The target to move it to.
    :return: None if successful or an error message if an error occurred.
    """

    # Issue the command to Pacemaker to move the target
    arg_list = ['crm_resource', '--resource', target_label, '--move', '--node', dest_node]

    # For on going debug purposes, lets get the resource locations at the beginning.
    # This provides useful log output in the case where things don't work.
    AgentShell.run(['crm_mon', '-1'])

    # Now before we start cleanup anything that has gone on before. HA is a fickle
    # old thing and this will make sure that everything is clean before we start.
    AgentShell.try_run(['crm_resource', '--resource', target_label, '--cleanup'])

    result = AgentShell.run(arg_list)

    if result.rc != 0:
        return "Error ({}) running '{}': '{}' '{}'".format(result.rc, " ".join(arg_list),
                                                           result.stdout, result.stderr)

    timeout = 100

    # Now wait for it to complete its move, this will succeed quickly if it was already there
    while timeout > 0:
        if get_resource_location(target_label) == dest_node:
            break

        time.sleep(1)
        timeout -= 1

    # now delete the constraint that crm_resource --move created
    AgentShell.try_run(['crm_resource', '--resource', target_label, '--un-move',
                        '--node', dest_node])

    if timeout <= 0:
        return "Failed to move target {} to node {}".format(target_label, dest_node)

    return None


def _find_resource_constraint(ha_label, primary):
    stdout = AgentShell.try_run(["crm_resource", "-r", ha_label, "-a"])

    for line in stdout.rstrip().split("\n"):
        match = re.match(r"\s+:\s+Node\s+([^\s]+)\s+\(score=[^\s]+ id={}\)".format(_constraint(ha_label, primary)),
                         line)
        if match:
            return match.group(1)

    return None


def _failoverback_target(ha_label, primary):
    """Fail a target over to the  destination node

    Return: Value using simple return protocol
    """
    node = _find_resource_constraint(ha_label, primary)
    if not node:
        return agent_error("Unable to find the {} server for '{}'".format('primary' if primary else 'secondary', ha_label))

    error = _move_target(ha_label, node)

    if error:
        return agent_error(error)

    return agent_result_ok


def failover_target(ha_label):
    """
    Fail a target over to its secondary node

    Return: Value using simple return protocol
    """
    return _failoverback_target(ha_label, False)


def failback_target(ha_label):
    """
    Fail a target back to its primary node

    Return: None if OK, else return an Error string
    """
    return _failoverback_target(ha_label, True)


def _get_target_config(uuid):
    info = config.get('targets', uuid)

    # Some history, previously the backfstype, device_type was not stored so if
    # not present presume ldiskfs/linux
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
        console_log.warning("Exception getting target config: %s", err)
        _exit(1)

    filesystem = FileSystem(info['backfstype'], info['bdev'])

    for device, mntpnt in get_local_mounts()[0:2]:
        if (mntpnt == info['mntpt']) and filesystem.devices_match(device, info['bdev'], uuid):
            _exit(0)

    console_log.warning("Did not find mount with matching mntpt and device for %s", uuid)
    _exit(1)


def purge_configuration(mgs_device_path, mgs_device_type, filesystem_name):
    mgs_bdev = BlockDevice(mgs_device_type, mgs_device_path)

    return agent_ok_or_error(mgs_bdev.purge_filesystem_configuration(filesystem_name, console_log))


def convert_targets(force=False):
    '''
    Convert existing ocf:chroma:Target to ZFS + Lustre
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
        console_log.info("This is not Pacemaker DC %s this is %s", dcuuid, this_node)
        return

    # Build map of resource -> [ primary node, secondary node ]
    locations = {}
    for con in dom.getElementsByTagName('rsc_location'):
        ha_label = con.getAttribute("rsc")
        if not locations.get(ha_label):
            locations[ha_label] = {}
        if con.getAttribute("id") == _constraint(ha_label, True):
            ind = 0
        elif con.getAttribute("id") == _constraint(ha_label, False):
            ind = 1
        else:
            console_log.info("Unknown constraint: %s", con.getAttribute("id"))
            continue
        locations[ha_label][ind] = con.getAttribute("node")

    active = get_resource_locations()

    AgentShell.run(['pcs', 'property', 'set', 'maintenance-mode=true'])

    wait_list = []
    for res in dom.getElementsByTagName('primitive'):
        if not (res.getAttribute("provider") == "chroma" and res.getAttribute("type") == "Target"):
            continue

        ha_label = res.getAttribute("id")

        # _get_target_config() will raise KeyError if uuid doesn't exist locally
        # next() will raise StopIteration if it doesn't find attribute target
        try:
            info = next(_get_target_config(ops.getAttribute("value"))
                        for ops in res.getElementsByTagName('nvpair')
                        if ops.getAttribute("name") == "target")
        except Exception as err:
            console_log.error("No local info for resource: %s", ha_label)
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
        console_log.info("Waiting on %s", wait[0])
        _wait_target(*wait)
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

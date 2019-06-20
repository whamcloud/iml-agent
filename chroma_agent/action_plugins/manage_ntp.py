# Copyright (c) 2018 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.


from iml_common.lib.ntp import NTPConfig
from iml_common.lib.agent_rpc import agent_ok_or_error
from iml_common.lib.service_control import ServiceControl


ntp_service = ServiceControl.create("ntpd")
chrony_service = ServiceControl.create("chronyd")


def unconfigure_ntp():
    """
    Unconfigure the ntp client

    :return: Value using simple return protocol
    """
    return configure_ntp(None)


def configure_ntp(ntp_server):
    """
    Change the ntp configuration file to use the server passed

    :return: Value using simple return protocol
    """
    error = NTPConfig().add(ntp_server)
    if error:
        return error
    else:
        chrony_service.stop(validate_time=0.5)
        chrony_service.disable()
        ntp_service.enable()
        return agent_ok_or_error(ntp_service.restart())


ACTIONS = [configure_ntp, unconfigure_ntp]
CAPABILITIES = ["manage_ntp"]

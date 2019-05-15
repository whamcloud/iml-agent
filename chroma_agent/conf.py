# Copyright (c) 2019 DDN. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.

import os

ENV_PATH = "/etc/iml"


def set_server_url(url):
    if not os.path.exists(ENV_PATH):
        os.makedirs(ENV_PATH)

    with open("{}/manager-url.conf".format(ENV_PATH), "w+") as f:
        f.write("IML_MANAGER_URL={}\n".format(url))


def remove_server_url():
    os.unlink("{}/manager-url.conf".format(ENV_PATH))


def set_iml_profile(name, repos):
    """
    Setup /etc/iml/profile.conf
    """
    if not os.path.exists(ENV_PATH):
        os.makedirs(ENV_PATH)

    with open("{}/profile.conf".format(ENV_PATH), "w+") as f:
        if name:
            f.write("IML_PROFILE_NAME={}\n".format(name))
        if repos:
            f.write("IML_PROFILE_REPOS={}\n".format(",".join(repos)))


def remove_iml_profile():
    os.unlink("{}/profile.conf".format(ENV_PATH))

# Copyright (c) 2018 Intel Corporation. All rights reserved.
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file.

import os

ENV_PATH = '/etc/iml'


def set_server_url(url):
    if not os.path.exists(ENV_PATH):
        os.makedirs(ENV_PATH)

    with open('{}/manager-url.conf'.format(ENV_PATH), 'w+') as f:
        f.write("IML_MANAGER_URL={}\n".format(url))


def remove_server_url():
    os.unlink('{}/manager-url.conf'.format(ENV_PATH))

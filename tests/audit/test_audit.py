import os
import mock

import chroma_agent.device_plugins.audit
from chroma_agent.device_plugins.audit.local import LocalAudit

from tests.test_utils import PatchedContextTestCase
from iml_common.test.command_capture_testcase import CommandCaptureTestCase

from chroma_agent.lib.shell import ResultStore, filter_log_output

import unittest

cib_configured_result = """<primitive class="stonith" id="vboxfence" type="fence_vbox">
    <instance_attributes id="vboxfence-instance_attributes">
        <nvpair id="vboxfence-instance_attributes-ipaddr" name="ipaddr" value="10.0.2.2"/>
        <nvpair id="vboxfence-instance_attributes-login" name="login" value="root"/>
        <nvpair id="vboxfence-instance_attributes-passwd" name="passwd" value="abc123def456"/>
    </instance_attributes>
    <operations>
        <op id="vboxfence-monitor-interval-60s" interval="60s" name="monitor"/>
    </operations>
</primitive>"""


class ResultStoreTestCase(unittest.TestCase):
    def setUp(self):
        super(ResultStoreTestCase, self).setUp()

    def test_filter_output(self):
        output = filter_log_output(cib_configured_result)

        self.assertEqual(
            """<primitive class="stonith" id="vboxfence" type="fence_vbox">
    <instance_attributes id="vboxfence-instance_attributes">
        <nvpair id="vboxfence-instance_attributes-ipaddr" name="ipaddr" value="10.0.2.2"/>
        <nvpair id="vboxfence-instance_attributes-login" name="login" value="root"/>
        <nvpair id="vboxfence-instance_attributes-passwd" name="passwd" value="******"/>
    </instance_attributes>
    <operations>
        <op id="vboxfence-monitor-interval-60s" interval="60s" name="monitor"/>
    </operations>
</primitive>""",
            output,
        )

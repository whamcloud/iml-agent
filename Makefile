NAME          := iml-agent
SUBPACKAGES   := management
TEST_DEPS     := python2-tablib python2-iml-common1.3 python-netaddr \
                 python2-toolz python-django
MODULE_SUBDIR  = chroma_agent

include include/python-localsrc.mk

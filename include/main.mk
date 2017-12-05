space :=
space +=
SCM_COMMIT_NUMBER	:= $(shell git rev-list HEAD | wc -l)
ifeq ($(strip $(JOB_NAME)),)
JENKINS_BUILD_TAG	:=
else
JENKINS_BUILD_TAG	:= $(shell echo .jenkins-$(JOB_NAME)-$(BUILD_NUMBER) | \
                                   sed -e 's/arch=[^,-]*,\?-\?//' \
                                       -e 's/distro=[^,-]*,\?-\?//' \
                                       -e 's,[/-],_,g')
endif
SCM_DESCRIPTION		:= $(shell msg=$$(git log -n 1 --abbrev-commit); \
                                   if echo "$$msg" | \
                                   grep -q "^    Create-Tag:"; then \
                                   echo "$$msg" | \
                                   sed -ne '/^    Create-Tag:/s/RC[0-9]*//;s/^.*: *v//p;/^    Create-Tag:/s/P[0-9]*//'; fi)
ifeq ($(strip $(SCM_DESCRIPTION)),)
SCM_DESCRIPTION		:= $(subst -,$(space),$(shell git describe --tags \
                                                      --match v[0-9]* | \
                                                      sed -e 's/^v//' \
                                                          -e 's/RC[0-9]*//' \
                                                          -e 's/P[0-9]*//'))
endif

# Stable variable names exported to packaging and code
BUILD_NUMBER		:= $(SCM_COMMIT_NUMBER)
VERSION			:= $(subst $(space),-,$(SCM_DESCRIPTION))
PACKAGE_VERSION		:= $(word 1, $(SCM_DESCRIPTION))
PACKAGE_RELEASE		:= $(subst $(space),.,$(wordlist 2, 10, $(SCM_DESCRIPTION)))
ifeq ($(strip $(PACKAGE_RELEASE)),)
	IS_RELEASE := True
	# We use the build number in a package's release field in
	# order to distinguish between RCs with identical version fields.
	# e.g. 2.0.0.0-2983 (RC1), 2.0.0.0-2987 (RC2)
	# The important thing is that newer RCs must upgrade older ones,
	# and end-users only really care about the %{version} field.
	PACKAGE_RELEASE := $(BUILD_NUMBER)
else
	IS_RELEASE := False
	# In development, we embed the rest of the git describe output
	# in order to easily understand the provenance of a package.
	# The commits-since-tag number will ensure that newer packages
	# are preferred, since RPM's version parsing works left-to-right.
	PACKAGE_RELEASE := $(BUILD_NUMBER).$(PACKAGE_RELEASE)$(JENKINS_BUILD_TAG)

	# Display this in the UI to make ID easier in dev/test
	BUILD_NUMBER := $(JENKINS_BUILD_TAG)
endif

RPM_SPEC      := python-$(NAME).spec

ifndef DIST_VERSION
DIST_VERSION	     := $(PACKAGE_VERSION)
else
RPM_DIST_VERSION_ARG := --define dist_version\ $(DIST_VERSION)
endif

RPM_DIST=$(subst .centos,,$(shell rpm --eval %dist))

# probably a way to determine this from parsespec methods
ALL_PKGS := $(NAME) $(addprefix $(NAME)-,$(SUBPACKAGES))

PACKAGE_VRD   := $(PACKAGE_VERSION)-$(PACKAGE_RELEASE)$(RPM_DIST)

TARGET_SRPM   := _topdir/SRPMS/python-$(NAME)-$(PACKAGE_VRD).src.rpm

TARGET_RPMS   := $(addprefix _topdir/RPMS/noarch/python-,  \
                   $(addsuffix -$(PACKAGE_VRD).noarch.rpm, \
                     $(ALL_PKGS)))
  
RPM_SOURCES   := $(shell spectool --define version\ $(PACKAGE_VERSION) \
		                  $(RPM_DIST_VERSION_ARG)              \
		                  -l $(RPM_SPEC) | sed -e 's/.*\///')

MODULE_SUBDIR ?= $(subst -,_,$(NAME))

# should always remove the sources if DIST_VERSION was set
ifneq ($(DIST_VERSION),$(PACKAGE_VERSION))
    $(shell rm -f $(RPM_SOURCES))
endif

RPMBUILD_ARGS += $(RPM_DIST_VERSION_ARG)                       \
		 --define "_topdir $$(pwd)/_topdir"            \
		 --define "version $(PACKAGE_VERSION)"         \
		 --define "package_release $(PACKAGE_RELEASE)" \
		 --define "%dist $(RPM_DIST)"

$(shell { echo 'VERSION = "$(VERSION)"';                                    \
	  echo 'PACKAGE_VERSION = "$(PACKAGE_VERSION)"';                    \
	  echo 'BUILD = "$(BUILD_NUMBER)"';                                 \
	  echo 'IS_RELEASE = $(IS_RELEASE)'; } > scm_version.py.tmp;        \
	  if ! cmp scm_version.py.tmp $(MODULE_SUBDIR)/scm_version.py; then \
	      cp scm_version.py.tmp $(MODULE_SUBDIR)/scm_version.py;        \
	  fi)

all: rpms

develop:
	python setup.py develop

cleandist:
	rm -rf dist
	mkdir dist

tarball: dist/$(NAME)-$(PACKAGE_VERSION).tar.gz

dist/$(NAME)-$(PACKAGE_VERSION).tar.gz: Makefile
	echo "jenkins_fold:start:Make Agent Tarball"
	rm -f MANIFEST
	python setup.py sdist
	# TODO - is this really necessary?  time precedence
	#        of the tarball vs. the product in _topdir/
	#        should simply require that any older product
	#        in _topdir/ will just be rebuilt
	# if we made a new tarball, get rid of all previous
	# build product
	rm -rf _topdir
	echo "jenkins_fold:end:Make Agent Tarball"

dist: dist/$(NAME)-$(PACKAGE_VERSION).tar.gz

_topdir/SOURCES/%: %
	mkdir -p _topdir/SOURCES
	cp $< $@

ifneq ($(DIST_VERSION),$(PACKAGE_VERSION))
$(RPM_SOURCES): dist/$(NAME)-$(PACKAGE_VERSION).tar.gz
# this builds the RPM from the Source(s) specified in
# the specfile.  i don't think this is what we want here.
# here, we want to build an rpm from the source tree
# let's see what time tells us we want to do
	if ! spectool $(RPM_DIST_VERSION_ARG)                  \
		   -g $(RPM_SPEC); then                        \
	    echo "Failed to fetch $@.";                        \
	    echo "Is this an unpublished version still?";      \
	    echo "Perhaps you want to assign a PR branch name" \
	         "to DIST_VERSION in your make";               \
	    echo "command?";                                   \
	    exit 1;                                            \
	fi
else
_topdir/SOURCES/$(NAME)-$(PACKAGE_VERSION).tar.gz: \
	dist/$(NAME)-$(PACKAGE_VERSION).tar.gz
	mkdir -p _topdir/SOURCES
	cp dist/$(NAME)-$(PACKAGE_VERSION).tar.gz _topdir/SOURCES
endif

_topdir/SPECS/$(RPM_SPEC): $(RPM_SPEC)
	mkdir -p _topdir/SPECS
	cp $< $@

srpm: $(TARGET_SRPM)

$(TARGET_SRPM): $(addprefix _topdir/SOURCES/, $(RPM_SOURCES)) \
		_topdir/SPECS/$(RPM_SPEC)
	mkdir -p _topdir/SRPMS
	rpmbuild $(RPMBUILD_ARGS) -bs _topdir/SPECS/$(RPM_SPEC)

rpms: $(TARGET_RPMS)

# see https://stackoverflow.com/questions/2973445/ for why we subst
# the "rpm" for "%" to effectively turn this into a multiple matching
# target pattern rule
$(subst rpm,%,$(TARGET_RPMS)): \
		$(addprefix _topdir/SOURCES/, $(RPM_SOURCES)) \
		_topdir/SPECS/$(RPM_SPEC)
	echo "jenkins_fold:start:Make Agent RPMS"
	rm -rf $(addprefix _topdir/, BUILD RPMS)
	mkdir -p $(addprefix _topdir/, BUILD $(addprefix RPMS/,noarch x86_64))
	rpmbuild $(RPMBUILD_ARGS) -bb _topdir/SPECS/$(RPM_SPEC)
	echo "jenkins_fold:end:Make Agent RPMS"

build_test: $(TARGET_SRPM)
	mock $(RPM_DIST_VERSION_ARG)                   \
	     -D version\ $(PACKAGE_VERSION)            \
	     -D package_release\ $(PACKAGE_RELEASE) $<


test_dependencies:
	test_deps="$(TEST_DEPS)";                               \
	if rpm --version && yum --version &&                    \
	   ! rpm -q $$test_deps >/dev/null 2>&1; then           \
	    echo "Some dependencies need installing...";        \
	    echo "You will need sudo root privilledges for yum" \
	    sudo yum -y install $$test_deps;                    \
	fi

test: test_dependencies
	@nosetests $(NOSE_ARGS)

deps: $(subst -,_,$(NAME)).egg-info/SOURCES.txt
	sed -e 's/^/dist\/python-$(NAME)-$(PACKAGE_VERSION).tar.gz: /' < $< > deps

include deps

# it's not clear yet that we need/want this
#rpm_deps: $(RPM_SPEC)
#	spectool -l $(RPM_SPEC) | \
#	    sed -e 's/^Source[0-9][0-9]*: \(.*\/\)\(.*\)/\2: ; curl -L -O \1\2/' > $@
#
#include rpm_deps

%.egg-info/SOURCES.txt:
	python setup.py egg_info

tags:
	ctags -R .

clean: cleandist
	rm -rf _topdir

.PHONY: rpms srpm test test_dependencies build_test dist cleandist develop all clean

include include/copr.mk

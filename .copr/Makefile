BUILDROOT:=$(shell [ -d "/build" ] && echo "/build" || echo ".")
TMPDIR:=$(shell mktemp -d)

srpm:
	python --version || dnf -y install python2-setuptools
	mkdir -p ${TMPDIR}/_topdir/SOURCES
	mkdir -p ${TMPDIR}/scratch
	rm -rf ${BUILDROOT}/_topdir
	cp -r ${BUILDROOT}/* ${TMPDIR}/scratch
	cd ${TMPDIR}/scratch; \
	python setup.py sdist -d ${TMPDIR}/_topdir/SOURCES/

	rpmbuild -bs -D "_topdir ${TMPDIR}/_topdir" ${TMPDIR}/scratch/python-iml-agent.spec
	cp -r ${TMPDIR}/_topdir/SRPMS/* $(outdir)
	rm -rf ${TMPDIR}


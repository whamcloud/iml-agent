BUILDROOT:=$(shell [ -d "/build" ] && echo "/build" || echo ".")
TMPDIR:=$(shell mktemp -d)

srpm:
	python2 --version || dnf -y install python2-setuptools
	mkdir -p ${TMPDIR}/_topdir/SOURCES
	mkdir -p ${TMPDIR}/scratch
	cp -r ./* ${TMPDIR}/scratch
	cd ${TMPDIR}/scratch; \
	python2 setup.py sdist -d ${TMPDIR}/_topdir/SOURCES/

	rpmbuild -bs -D "_topdir ${TMPDIR}/_topdir" ${TMPDIR}/scratch/python-iml-agent.spec
	cp -rf ${TMPDIR}/_topdir ${BUILDROOT}/
	cp -r ${TMPDIR}/_topdir/SRPMS/* $(outdir)
	rm -rf ${TMPDIR}


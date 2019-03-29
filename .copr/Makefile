srpm:
	rm -rf /tmp/_topdir
	rm -rf /tmp/scratch
	mkdir -p /tmp/_topdir/SOURCES
	mkdir -p /tmp/scratch
	rm -rf /build/_topdir
	cp -r /build/* /tmp/scratch
	cd /tmp/scratch; \
	python setup.py sdist -d /tmp/_topdir/SOURCES/

	rpmbuild -bs -D "_topdir /tmp/_topdir" /tmp/scratch/python-iml-agent.spec
	cp -r /tmp/_topdir/SRPMS/* $(outdir)

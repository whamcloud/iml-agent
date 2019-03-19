srpm:
	rm -rf _topdir *.rpm
	mkdir -p _topdir/SOURCES/
	python setup.py sdist -d _topdir/SOURCES/
	rpmbuild -bs -D "%_topdir /build/_topdir" python-iml-agent.spec
	cp -f _topdir/SRPMS/*.rpm $(outdir)

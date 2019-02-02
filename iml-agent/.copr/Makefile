srpm:
	rm -rf /tmp/_topdir
	rm -rf /tmp/scratch
	mkdir -p /tmp/scratch
	mkdir -p /tmp/_topdir/SOURCES
	cp -r ./* /tmp/scratch
	cd /tmp/scratch; \
	cargo package
	cp /tmp/scratch/target/package/*.crate /tmp/_topdir/SOURCES
	cp /tmp/scratch/Cargo.lock /tmp/_topdir/SOURCES
	cd /tmp/_topdir/SOURCES; \
	bash -c "spectool -g <(rpmspec -P /tmp/scratch/rust-iml-agent.spec --define '_topdir /tmp/_topdir') --define '_topdir /tmp/_topdir'"

	rpmbuild -bs --define "_topdir /tmp/_topdir" rust-iml-agent.spec
	cp -r /tmp/_topdir/SRPMS/* $(outdir)



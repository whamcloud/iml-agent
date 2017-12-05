all: test

develop:
	python setup.py develop

cleandist:
	rm -rf dist
	mkdir dist

test_dependencies:
	test_deps="python2-tablib python2-iml-common1.3  \
		   python-netaddr python2-toolz";        \
	if rpm --version && yum --version &&             \
	   ! rpm -q $$test_deps >/dev/null 2>&1; then    \
	    echo "Some dependencies need installing..."; \
	    sudo yum -y install $$test_deps;             \
	fi

test: test_dependencies
	@nosetests $(NOSE_ARGS)

tags:
	ctags -R .

.PHONY: test test_dependencies develop all

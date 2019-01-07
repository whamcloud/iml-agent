srpm:
	dnf -y install 'dnf-command(copr)' rpmdevtools wget
	dnf -y --setopt=reposdir=/tmp/yum.repos.d copr enable clime/rpkg-client
	dnf -y install rpkg
	python setup.py sdist -d ./
	rpkg srpm --outdir=$(outdir) --spec=python-iml-agent.spec

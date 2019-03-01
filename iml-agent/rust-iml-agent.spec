# Generated by rust2rpm

%global crate iml-agent
%define preversion alpha.1
%define preversionsep .

Name:           rust-%{crate}
Version:        0.1.0
Release:        1%{preversionsep}%{preversion}%{?dist}
Summary:        "IML Agent Daemon and CLI"

License:        MIT

URL:            https://crates.io/crates/iml-agent
Source0:        https://crates.io/api/v1/crates/%{crate}/%{version}-%{preversion}/download#/%{crate}-%{version}-%{preversion}.crate
Source1:        Cargo.lock
%cargo_bundle_crates -l 1

ExclusiveArch:  x86_64

BuildRequires:  rust
BuildRequires:  cargo

%description
%{summary}.

%prep
%autosetup -n %{crate}-%{version}-alpha.1 -p1
%cargo_prep

%build
%cargo_build

%install
%cargo_install
mkdir -p %{buildroot}%{_unitdir}
mkdir -p %{buildroot}%{_presetdir}
cp systemd-units/%{name}.{service,path} %{buildroot}%{_unitdir}
cp systemd-units/00-%{name}.preset %{buildroot}%{_presetdir}

%files
%{_bindir}/%{crate}
%{_bindir}/%{crate}-daemon
%doc %{_cargometadir}/%{name}.json
%attr(0644,root,root)%{_unitdir}/%{name}.service
%attr(0644,root,root)%{_unitdir}/%{name}.path
%attr(0644,root,root)%{_presetdir}/00-%{name}.preset

%post
systemctl preset %{name}.path

%preun
%systemd_preun %{name}.path
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.path

%changelog
* Tue Feb 05 2019 Joe Grund <jgrund@whamcloud.com> - 0.1.0-1
- Initial package

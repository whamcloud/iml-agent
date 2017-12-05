# local settings
-include copr-local.mk

copr_rpm: $(RPM_SPEC)
ifndef COPR_OWNER
	    $(error COPR_OWNER needs to be set in ../copr-local.mk)
endif
ifndef COPR_PROJECT
	    $(error COPR_PROJECT needs to be set in ../copr-local.mk)
endif
	copr-cli build $(COPR_OWNER)/$(COPR_PROJECT) $<

copr_build:
ifndef COPR_OWNER
	    $(error COPR_OWNER needs to be set in ../copr-local.mk)
endif
ifndef COPR_PROJECT
	    $(error COPR_PROJECT needs to be set in ../copr-local.mk)
endif
	copr-cli buildscm --clone-url                                   \
			    https://github.com/intel-hpdd/iml-agent.git \
	                  --commit build-rpms                           \
		          --method make_srpm                            \
	                  $(COPR_OWNER)/$(COPR_PROJECT) $<

iml_copr_rpm: $(RPM_SPEC)
	copr-cli --config ~/.config/copr-mfl build \
	         managerforlustre/manager-for-lustre $<

.PHONY: copr_rpm copr_build iml_copr_rpm

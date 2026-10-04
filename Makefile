# POTA Trip Planner — Debian package build
#
#   make            build the .deb (same as `make deb`)
#   make deb        build the .deb into ./dist/
#   make install    build + sudo dpkg -i (builds venv on target, enables+starts service)
#   make uninstall  sudo dpkg -r potatrip
#   make clean      remove build artifacts
#
# The package is Architecture: all — it ships NO pre-built binaries. The
# python3 venv is created ON THE TARGET at install time (postinst runs
# `python3 -m venv` + `pip install`), so the same .deb works on amd64
# and arm64 (Raspberry Pi OS Bookworm) alike.
#
# The package installs:
#   /opt/PotaTrip/            app.py, index.html, requirements.txt, LICENSE
#   /opt/PotaTrip/.venv/      python3 venv built on the target at install time
#   /usr/local/bin/potatrip   launcher (runs app.py with the venv python)
#   /lib/systemd/system/potatrip.service   systemd unit (enabled + started in postinst)
#   /var/lib/potatrip/        writable state (park cache, log), owned by user 'potatrip'

PACKAGE    := potatrip
VERSION    ?= 2.0.0
ARCH       := all
DEB        := dist/$(PACKAGE)_$(VERSION)_$(ARCH).deb

APP_SRC    := app.py index.html README.md requirements.txt LICENSE
PKG_ROOT   := opt/PotaTrip
STAGE      := build/stage
DESTDIR    := $(STAGE)

.PHONY: all deb install uninstall clean stage

all: deb

# ---------------------------------------------------------------- build .deb
deb: $(DEB)

$(DEB): $(APP_SRC) packaging/control.template packaging/preinst packaging/postinst packaging/postrm packaging/potatrip.service packaging/potatrip-launcher
	@$(MAKE) --no-print-directory stage
	@mkdir -p dist
	fakeroot sh -c 'chown -R root:root "$(STAGE)" && dpkg-deb --root-owner-group --build "$(STAGE)" "$(DEB)"'
	@echo "Built: $(DEB)"

# Assemble the staging tree. No venv here — postinst builds it on the target.
stage:
	rm -rf $(STAGE)
	mkdir -p $(DESTDIR)/$(PKG_ROOT) $(DESTDIR)/usr/local/bin $(DESTDIR)/lib/systemd/system $(DESTDIR)/var/lib/potatrip
	cp $(APP_SRC) $(DESTDIR)/$(PKG_ROOT)/
	cp packaging/potatrip-launcher $(DESTDIR)/usr/local/bin/potatrip
	chmod 755 $(DESTDIR)/usr/local/bin/potatrip
	cp packaging/potatrip.service $(DESTDIR)/lib/systemd/system/potatrip.service
	# Control file
	mkdir -p $(STAGE)/DEBIAN
	sed -e 's/@VERSION@/$(VERSION)/g' -e 's/@ARCH@/$(ARCH)/g' \
		packaging/control.template > $(STAGE)/DEBIAN/control
	cp packaging/preinst packaging/postinst packaging/postrm $(STAGE)/DEBIAN/
	chmod 755 $(STAGE)/DEBIAN/preinst $(STAGE)/DEBIAN/postinst $(STAGE)/DEBIAN/postrm

# ---------------------------------------------------------------- install/uninstall
install: deb
	sudo dpkg -i $(DEB)

uninstall:
	sudo dpkg -r $(PACKAGE)

clean:
	rm -rf build dist

# POTA Trip Planner — Debian package build
#
#   make            build the .deb (same as `make deb`)
#   make deb        build the .deb into ./dist/
#   make install    build + sudo dpkg -i (creates venv, systemd unit, enables+starts)
#   make uninstall  sudo dpkg -r potatrip
#   make clean      remove build artifacts
#
# The package installs:
#   /opt/potatrip/            app.py + self-contained python3 venv (flask, pandas, geopy, requests)
#   /usr/local/bin/potatrip   launcher (runs app.py with the venv python)
#   /lib/systemd/system/potatrip.service   systemd unit (enabled + started in postinst)
#   /var/lib/potatrip/        writable state (park cache, log), owned by user 'potatrip'

PACKAGE    := potatrip
VERSION    ?= 2.0.0
ARCH       := $(shell dpkg --print-architecture)
DEB        := dist/$(PACKAGE)_$(VERSION)_$(ARCH).deb

APP_SRC    := app.py index.html README.md requirements.txt
PKG_ROOT   := opt/potatrip
VENV_DIR   := $(PKG_ROOT)/venv
STAGE      := build/stage
DESTDIR    := $(STAGE)

PYTHON     ?= python3
PIP        := $(DESTDIR)/$(VENV_DIR)/bin/pip

.PHONY: all deb install uninstall clean venv stage

all: deb

# ---------------------------------------------------------------- build .deb
deb: $(DEB)

$(DEB): $(APP_SRC) packaging/control.template packaging/preinst packaging/postinst packaging/postrm packaging/potatrip.service packaging/potatrip-launcher
	@$(MAKE) --no-print-directory stage
	@mkdir -p dist
	fakeroot sh -c 'chown -R root:root "$(STAGE)" && dpkg-deb --root-owner-group --build "$(STAGE)" "$(DEB)"'
	@echo "Built: $(DEB)"

# Assemble the staging tree with the venv already populated (offline install).
stage:
	rm -rf $(STAGE)
	mkdir -p $(DESTDIR)/$(PKG_ROOT) $(DESTDIR)/usr/local/bin $(DESTDIR)/lib/systemd/system $(DESTDIR)/var/lib/potatrip
	cp $(APP_SRC) $(DESTDIR)/$(PKG_ROOT)/
	cp packaging/potatrip-launcher $(DESTDIR)/usr/local/bin/potatrip
	chmod 755 $(DESTDIR)/usr/local/bin/potatrip
	cp packaging/potatrip.service $(DESTDIR)/lib/systemd/system/potatrip.service
	# Dedicated python3 environment, built at its final path inside the stage.
	$(PYTHON) -m venv $(DESTDIR)/$(VENV_DIR)
	$(PIP) install --no-cache-dir -r requirements.txt
	# Repoint any staging-path shebangs/config at the real install location.
	find $(DESTDIR)/$(VENV_DIR)/bin -maxdepth 1 -type f | xargs -r sed -i \
		's|$(CURDIR)/$(STAGE)/$(PKG_ROOT)|/$(PKG_ROOT)|g'
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

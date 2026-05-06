#!/usr/bin/env bash
# Tek sefer: Netdata health dosyalarını /etc altına kopyalar ve servisi yeniler.
# Çalıştırma (yerelde): ssh guezelwebdesign 'bash ~/apply-netdata-health-on-vps.sh'

set -euo pipefail
PATCH="${HOME}/netdata-health-patch"
for f in ram_usage.conf load_average.conf reboot_notify.conf; do
  test -f "${PATCH}/${f}" || { echo "Eksik: ${PATCH}/${f}" >&2; exit 1; }
done
sudo cp "${PATCH}/ram_usage.conf" "${PATCH}/load_average.conf" /etc/netdata/health.d/
sudo cp "${PATCH}/reboot_notify.conf" /etc/netdata/health.d/
sudo chmod 644 /etc/netdata/health.d/ram_usage.conf \
  /etc/netdata/health.d/load_average.conf \
  /etc/netdata/health.d/reboot_notify.conf
sudo systemctl reload netdata 2>/dev/null || sudo systemctl restart netdata
echo "Netdata health güncellendi."

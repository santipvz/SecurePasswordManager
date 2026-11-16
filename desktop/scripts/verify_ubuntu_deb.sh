#!/usr/bin/env bash
# Run as root inside a disposable Ubuntu 24.04 container.
set -euo pipefail

package_dir=${1:?Supply the directory containing the test package}
shopt -s nullglob
package_files=( "$package_dir"/*.deb )
if [[ ${#package_files[@]} != 1 ]]; then
    echo "Expected one Ubuntu package" >&2
    exit 1
fi
package_file=${package_files[0]}
package=secure-password-manager
desktop_name='Secure Password Manager'
launcher="/usr/share/applications/$desktop_name.desktop"
core="/usr/lib/$desktop_name/vault-process/cpass-vault-process"
docs="/usr/share/doc/$package"
vault=/home/ubuntu/.local/share/SecurePasswordManager/vault.spm
backup=/home/ubuntu/backup.spm
work=$(mktemp -d)

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends "$package_file" \
    dbus-daemon desktop-file-utils jq libgtk-3-bin libgl1-mesa-dri xauth xdotool xvfb
test "$(dpkg-deb -f "$package_file" Package)" = "$package"
test "$(dpkg-deb -f "$package_file" Architecture)" = amd64
desktop-file-validate "$launcher"
test -x "$core"
test -s "$docs/copyright"
grep -Fq '@fontsource/inter' "$docs/licenses/frontend.md"
test -s "$docs/licenses/python/CPython.txt"
test -d "$docs/licenses/rust"
for tool in python3 cargo rustc node npm; do
    if command -v "$tool"; then
        echo "Unexpected development tool in clean test environment: $tool" >&2
        exit 1
    fi
done

runuser -u ubuntu -- env GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 \
    xvfb-run -a dbus-run-session -- bash -ec '
        gtk-launch "$1"
        timeout 20s xdotool search --sync --onlyvisible --name "^$1$" >/dev/null
    ' bash "$desktop_name"
echo "The installed desktop launcher opened the application as a standard user."

runuser -u ubuntu -- "$core" <<'EOF' > "$work/create.jsonl"
{"version":1,"id":1,"operation":"create","path":"/home/ubuntu/.local/share/SecurePasswordManager/vault.spm","master":"Synthetic vault test password"}
{"version":1,"id":2,"operation":"save_entry","name":"Synthetic account","username":"fixture@example.test","password":"Synthetic entry secret"}
{"version":1,"id":3,"operation":"backup","destination":"/home/ubuntu/backup.spm"}
EOF
jq -se 'length == 3 and .[0].result.unlocked and .[1].result.name == "Synthetic account" and .[2].result.saved' \
    "$work/create.jsonl" >/dev/null
sha256sum "$vault" "$backup" > "$work/vault.sha256"

# Install the same payload with a higher package version to exercise the upgrade path.
version=$(dpkg-deb -f "$package_file" Version)
dpkg-deb -R "$package_file" "$work/upgrade"
sed -i "s/^Version: .*/Version: ${version}+smoke1/" "$work/upgrade/DEBIAN/control"
dpkg-deb --build --root-owner-group "$work/upgrade" "$work/upgrade.deb" >/dev/null
dpkg -i "$work/upgrade.deb"
test "$(dpkg-query -W -f='${Version}' "$package")" = "${version}+smoke1"
sha256sum --check "$work/vault.sha256"

runuser -u ubuntu -- "$core" <<'EOF' > "$work/reopen.jsonl"
{"version":1,"id":1,"operation":"open","master":"Synthetic vault test password"}
{"version":1,"id":2,"operation":"list","query":"fixture@example.test"}
{"version":1,"id":3,"operation":"open","path":"/home/ubuntu/backup.spm","master":"Synthetic vault test password"}
{"version":1,"id":4,"operation":"entry_password","name":"Synthetic account"}
EOF
jq -se 'length == 4 and .[0].result.unlocked
    and .[1].result.entries == [{"name":"Synthetic account","username":"fixture@example.test","url":""}]
    and .[2].result.unlocked and .[3].result.password == "Synthetic entry secret"' "$work/reopen.jsonl" >/dev/null

dpkg --purge "$package"
test ! -e "$launcher"
sha256sum --check "$work/vault.sha256"
echo "Upgrade and purge preserved the original encrypted vault and backup."

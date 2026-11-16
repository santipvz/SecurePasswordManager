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
previous_package=${2:-}
package=secure-password-manager
desktop_name='Secure Password Manager'
launcher="/usr/share/applications/$desktop_name.desktop"
core="/usr/lib/$desktop_name/vault-process/cpass-vault-process"
docs="/usr/share/doc/$package"
vault=/home/ubuntu/.local/share/SecurePasswordManager/vault.spm
backup=/home/ubuntu/backup.spm
work=$(mktemp -d)
ci_scripts=$(realpath "$(dirname "$0")/../../scripts")

test "$(dpkg-deb -f "$package_file" Package)" = "$package"
test "$(dpkg-deb -f "$package_file" Architecture)" = amd64
version=$(dpkg-deb -f "$package_file" Version)
initial_package=$package_file
if [[ -n $previous_package ]]; then
    test "$(dpkg-deb -f "$previous_package" Package)" = "$package"
    test "$(dpkg-deb -f "$previous_package" Architecture)" = amd64
    dpkg --compare-versions "$(dpkg-deb -f "$previous_package" Version)" lt "$version"
    initial_package=$previous_package
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# The minimal Ubuntu image excludes documentation by default.
apt-get -o "DPkg::Options::=--path-include=$docs/*" install -y --no-install-recommends "$initial_package" \
    dbus-daemon desktop-file-utils jq libgtk-3-bin libgl1-mesa-dri xauth xdotool xvfb
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

launch_desktop() {
    runuser -u ubuntu -- env GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 \
        xvfb-run -a dbus-run-session -- bash -ec '
            gtk-launch "$1"
            timeout 20s xdotool search --sync --onlyvisible --name "^$1$" >/dev/null
        ' bash "$desktop_name"
    echo "The installed desktop launcher opened the application as a standard user."
}

launch_desktop

runuser -u ubuntu -- "$core" <<'EOF' > "$work/create.jsonl"
{"version":1,"id":1,"operation":"create","path":"/home/ubuntu/.local/share/SecurePasswordManager/vault.spm","master":"Synthetic vault test password"}
{"version":1,"id":2,"operation":"save_entry","name":"Synthetic account","username":"fixture@example.test","password":"Synthetic entry secret"}
{"version":1,"id":3,"operation":"backup","destination":"/home/ubuntu/backup.spm"}
EOF
jq -se 'length == 3 and .[0].result.unlocked and .[1].result.name == "Synthetic account" and .[2].result.saved' \
    "$work/create.jsonl" >/dev/null
sha256sum "$vault" "$backup" > "$work/vault.sha256"

upgrade_package=$package_file
upgrade_version=$version
if [[ -z $previous_package ]]; then
    # Exercise the upgrade path when only the candidate payload is available.
    upgrade_package=$work/upgrade.deb
    upgrade_version=${version}+smoke1
    dpkg-deb -R "$package_file" "$work/upgrade"
    sed -i "s/^Version: .*/Version: $upgrade_version/" "$work/upgrade/DEBIAN/control"
    dpkg-deb --build --root-owner-group "$work/upgrade" "$upgrade_package" >/dev/null
fi
dpkg --path-include="$docs/*" -i "$upgrade_package"
test "$(dpkg-query -W -f='${Version}' "$package")" = "$upgrade_version"
test -s "$docs/licenses/rust/glib-0.18.5/LICENSE"
sha256sum --check "$work/vault.sha256"
if [[ -n $previous_package ]]; then
    launch_desktop
fi

runuser -u ubuntu -- "$core" <<'EOF' > "$work/reopen.jsonl"
{"version":1,"id":1,"operation":"open","master":"Synthetic vault test password"}
{"version":1,"id":2,"operation":"list","query":"fixture@example.test"}
{"version":1,"id":3,"operation":"open","path":"/home/ubuntu/backup.spm","master":"Synthetic vault test password"}
{"version":1,"id":4,"operation":"entry_password","name":"Synthetic account"}
EOF
jq -se 'length == 4 and .[0].result.unlocked
    and .[1].result.entries == [{"name":"Synthetic account","username":"fixture@example.test","url":""}]
    and .[2].result.unlocked and .[3].result.password == "Synthetic entry secret"' "$work/reopen.jsonl" >/dev/null

# Install test tooling only after checking that the app works without system Python.
apt-get install -y --no-install-recommends python3 webkit2gtk-driver
runuser -u ubuntu -- env GDK_BACKEND=x11 LIBGL_ALWAYS_SOFTWARE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 \
    xvfb-run -a dbus-run-session -- python3 "$ci_scripts/smoke_installed_desktop.py" \
    /usr/bin/secure-password-manager-desktop

dpkg --purge "$package"
test ! -e "$launcher"
sha256sum --check "$work/vault.sha256"
echo "Upgrade and purge preserved the original encrypted vault and backup."

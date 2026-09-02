#!/bin/sh
# ai-generated: verified, rollback-capable Debian server installer.
set -eu

PROGRAM=olcrtc-native-installer
DEFAULT_REPOSITORY=qqweqwe287-art/olcrtc
REPOSITORY=${OLCRTC_RELEASE_REPOSITORY:-$DEFAULT_REPOSITORY}
RELEASE=${OLCRTC_RELEASE:-latest}
INSTANCE=main
CONFIG_SOURCE=
REPLACE_CONFIG=0
START_SERVICE=0
MIGRATE_V011=0
FRESH=0
MANIFEST_PIN=${OLCRTC_MANIFEST_SHA256:-}

LIB_DIR=/usr/local/lib/olcrtc-native
RELEASES_DIR=$LIB_DIR/releases
CURRENT_LINK=$LIB_DIR/current
CONFIG_DIR=/etc/olcrtc-native
STATE_DIR=/var/lib/olcrtc-native
UNIT_PATH=/etc/systemd/system/olcrtc-native@.service
ADMIN_UNIT_PATH=/etc/systemd/system/olcrtc-native-admin.service
UNINSTALL_PATH=/usr/local/sbin/olcrtc-native-uninstall-server
INSTALL_PATH=/usr/local/sbin/olcrtc-native-install-server
BIN_LINK=/usr/local/bin/olcrtc-native
TMP_DIR=
FRESH_PREPARED=0
FRESH_COMMITTED=0
LEGACY_ACTIVE=
LEGACY_BACKUP=

# ai-generated
say() {
    printf '%s: %s\n' "$PROGRAM" "$*"
}

# ai-generated
die() {
    printf '%s: error: %s\n' "$PROGRAM" "$*" >&2
    exit 1
}

# ai-generated
usage() {
    cat <<'EOF'
Usage: install-server.sh [options]

Options:
  --release TAG         install an exact release tag (default: latest)
  --repository OWNER/REPO
                        release repository (default: qqweqwe287-art/olcrtc)
  --instance NAME       systemd instance and config name (default: main)
  --config FILE         install this YAML as /etc/olcrtc-native/NAME.yaml
  --replace-config      allow --config to replace an existing config
  --start               enable and start the selected instance
  --migrate-v0.1.1      explicitly migrate one prior fork instance after backup
  --fresh               back up, replace and remove the old Manager after the new UI starts
  -h, --help            show this help

Environment:
  OLCRTC_MANIFEST_SHA256 pins manifest.tsv to an expected SHA-256.
  OLCRTC_RELEASE_REPOSITORY and OLCRTC_RELEASE set the same defaults as flags.
EOF
}

# ai-generated
cleanup() {
    if [ "$FRESH_PREPARED" -eq 1 ] && [ "$FRESH_COMMITTED" -ne 1 ]; then
        say "fresh install did not complete; restarting the previous Manager"
        for unit in $LEGACY_ACTIVE; do
            systemctl start "$unit" >/dev/null 2>&1 || true
        done
    fi
    if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
        rm -rf -- "$TMP_DIR"
    fi
}

trap cleanup EXIT HUP INT TERM

# ai-generated
require_root() {
    [ "$(id -u)" -eq 0 ] || die "run as root"
}

# ai-generated
validate_repository() {
    case "$REPOSITORY" in
        */*/*) die "repository must use OWNER/REPO format" ;;
        */*) ;;
        *) die "repository must use OWNER/REPO format" ;;
    esac
    case "$REPOSITORY" in
        *[!A-Za-z0-9_./-]*|*//*|/*|*/|*..*) die "repository contains unsafe characters" ;;
    esac
}

# ai-generated
validate_instance() {
    case "$INSTANCE" in
        ''|.*|*[!A-Za-z0-9_.-]*|*..*) die "invalid instance name: $INSTANCE" ;;
    esac
}

# ai-generated
validate_release() {
    [ "$RELEASE" = latest ] && return
    case "$RELEASE" in
        ''|*[!A-Za-z0-9._+-]*|.*|*..*) die "invalid release tag: $RELEASE" ;;
    esac
}

# ai-generated
parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --release)
                [ "$#" -ge 2 ] || die "--release requires a value"
                RELEASE=$2
                shift 2
                ;;
            --release=*) RELEASE=${1#*=}; shift ;;
            --repository)
                [ "$#" -ge 2 ] || die "--repository requires a value"
                REPOSITORY=$2
                shift 2
                ;;
            --repository=*) REPOSITORY=${1#*=}; shift ;;
            --instance)
                [ "$#" -ge 2 ] || die "--instance requires a value"
                INSTANCE=$2
                shift 2
                ;;
            --instance=*) INSTANCE=${1#*=}; shift ;;
            --config)
                [ "$#" -ge 2 ] || die "--config requires a value"
                CONFIG_SOURCE=$2
                shift 2
                ;;
            --config=*) CONFIG_SOURCE=${1#*=}; shift ;;
            --replace-config) REPLACE_CONFIG=1; shift ;;
            --start) START_SERVICE=1; shift ;;
            --migrate-v0.1.1) MIGRATE_V011=1; shift ;;
            --fresh) FRESH=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) die "unknown option: $1" ;;
        esac
    done
}

# ai-generated
check_debian() {
    [ -r /etc/os-release ] || die "/etc/os-release is missing"
    os_id=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"' | head -n 1)
    os_version=$(sed -n 's/^VERSION_ID=//p' /etc/os-release | tr -d '"' | head -n 1)
    [ "$os_id" = debian ] || die "only Debian is supported (found: $os_id)"
    [ "$os_version" = 12 ] || die "only Debian 12 is supported (found: $os_version)"

    machine=$(uname -m)
    case "$machine" in
        x86_64|amd64) ARCH=amd64 ;;
        aarch64|arm64) die "Debian arm64 packaging is not available in manifest version 1" ;;
        *) die "unsupported architecture: $machine" ;;
    esac
}

# ai-generated
ensure_dependencies() {
    missing=
    for command_name in curl sha256sum stat tar gzip awk sed grep install systemctl useradd getent python3 base64 openssl qrencode; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            missing="$missing $command_name"
        fi
    done
    [ -z "$missing" ] && return
    command -v apt-get >/dev/null 2>&1 || die "missing commands:$missing"
    say "installing required Debian packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends ca-certificates curl coreutils tar gzip systemd passwd python3 openssl qrencode

    for command_name in curl sha256sum stat tar gzip awk sed grep install systemctl useradd getent python3 base64 openssl qrencode; do
        command -v "$command_name" >/dev/null 2>&1 || die "required command is still missing: $command_name"
    done
}

# ai-generated
download() {
    source_url=$1
    destination=$2
    curl \
        --fail \
        --location \
        --silent \
        --show-error \
        --proto '=https' \
        --tlsv1.2 \
        --connect-timeout 15 \
        --max-time 300 \
        --retry 3 \
        --retry-delay 2 \
        --output "$destination" \
        "$source_url"
}

# ai-generated
manifest_value() {
    key=$1
    awk -F '\t' -v wanted="$key" '$1 == wanted { print $2 }' "$MANIFEST"
}

# ai-generated
validate_manifest() {
    manifest_bytes=$(wc -c <"$MANIFEST" | tr -d '[:space:]')
    [ "$manifest_bytes" -le 65536 ] || die "manifest.tsv is too large"
    awk -F '\t' '
        BEGIN {
            scalar["manifest_version"] = 1
            scalar["version"] = 1
            scalar["wire"] = 1
            scalar["config_schema"] = 1
            scalar["source_repository"] = 1
            scalar["source_commit"] = 1
            scalar["upstream_repository"] = 1
            scalar["upstream_commit"] = 1
            scalar["go_version"] = 1
        }
        /^#/ || NF == 0 { next }
        $1 == "asset" {
            if (NF != 7) exit 20
            if ($2 != "core" && $2 != "bundle") exit 21
            if ($3 != "linux") exit 22
            if ($4 != "amd64" && $4 != "arm64") exit 23
            identity = $2 "/" $3 "/" $4
            if (++asset_seen[identity] != 1) exit 28
            if ($5 !~ /^[A-Za-z0-9][A-Za-z0-9._+-]*$/) exit 29
            if ($6 !~ /^[0-9]+$/ || $6 + 0 <= 0) exit 30
            if ($7 !~ /^[0-9a-f]+$/ || length($7) != 64) exit 31
            assets++
            next
        }
        $1 in scalar {
            if (NF != 2 || ++seen[$1] != 1) exit 24
            next
        }
        { exit 25 }
        END {
            for (key in scalar) if (seen[key] != 1) exit 26
            if (assets != 4) exit 27
            if (asset_seen["core/linux/amd64"] != 1) exit 32
            if (asset_seen["core/linux/arm64"] != 1) exit 33
            if (asset_seen["bundle/linux/amd64"] != 1) exit 34
            if (asset_seen["bundle/linux/arm64"] != 1) exit 35
        }
    ' "$MANIFEST" || die "manifest.tsv has an invalid or unsupported schema"

    [ "$(manifest_value manifest_version)" = 1 ] || die "unsupported manifest version"
    [ "$(manifest_value wire)" = OLC2-OLVC5 ] || die "unsupported wire generation"
    [ "$(manifest_value config_schema)" = 1 ] || die "unsupported config schema"
    [ "$(manifest_value source_repository)" = "$REPOSITORY" ] || die "manifest repository does not match $REPOSITORY"
    [ "$(manifest_value upstream_repository)" = openlibrecommunity/olcrtc ] \
        || die "manifest does not identify the official upstream"

    for key in source_commit upstream_commit; do
        value=$(manifest_value "$key")
        case "$value" in
            *[!0-9a-f]*|'') die "invalid $key in manifest" ;;
        esac
        [ "${#value}" -eq 40 ] || die "invalid $key length in manifest"
    done

    manifest_release=$(manifest_value version)
    case "$manifest_release" in
        ''|*[!A-Za-z0-9._+-]*|.*|*..*) die "unsafe release tag in manifest" ;;
    esac
}

# ai-generated
select_asset() {
    asset_kind=$1
    asset_arch=$2
    row=$(awk -F '\t' -v kind="$asset_kind" -v arch="$asset_arch" '
        $1 == "asset" && $2 == kind && $3 == "linux" && $4 == arch {
            if (++count == 1) value = $5 "\t" $6 "\t" $7
        }
        END { if (count == 1) print value; else exit 1 }
    ' "$MANIFEST") || die "manifest must contain exactly one $asset_kind/linux/$asset_arch asset"

    ASSET_NAME=$(printf '%s\n' "$row" | awk -F '\t' '{print $1}')
    ASSET_SIZE=$(printf '%s\n' "$row" | awk -F '\t' '{print $2}')
    ASSET_SHA=$(printf '%s\n' "$row" | awk -F '\t' '{print $3}')

    case "$ASSET_NAME" in
        ''|*[!A-Za-z0-9._@+-]*|.*|*..*) die "unsafe asset name in manifest" ;;
    esac
    case "$ASSET_SIZE" in
        ''|*[!0-9]*) die "invalid asset size for $ASSET_NAME" ;;
    esac
    [ "$ASSET_SIZE" -gt 0 ] || die "empty asset is not allowed: $ASSET_NAME"
    case "$ASSET_SHA" in
        *[!0-9a-f]*|'') die "invalid SHA-256 for $ASSET_NAME" ;;
    esac
    [ "${#ASSET_SHA}" -eq 64 ] || die "invalid SHA-256 length for $ASSET_NAME"
}

# ai-generated
verify_file() {
    file_path=$1
    expected_size=$2
    expected_sha=$3
    actual_size=$(stat -c '%s' "$file_path")
    [ "$actual_size" = "$expected_size" ] || die "size mismatch for $(basename -- "$file_path")"
    actual_sha=$(sha256sum "$file_path" | awk '{print $1}')
    [ "$actual_sha" = "$expected_sha" ] || die "SHA-256 mismatch for $(basename -- "$file_path")"
}

# ai-generated
resolve_manifest() {
    release_base="https://github.com/$REPOSITORY/releases"
    MANIFEST=$TMP_DIR/manifest.tsv

    if [ "$RELEASE" = latest ]; then
        latest_manifest=$TMP_DIR/manifest.latest.tsv
        download "$release_base/latest/download/manifest.tsv" "$latest_manifest"
        MANIFEST=$latest_manifest
        validate_manifest
        RELEASE=$(manifest_value version)
        exact_manifest=$TMP_DIR/manifest.exact.tsv
        download "$release_base/download/$RELEASE/manifest.tsv" "$exact_manifest"
        latest_sha=$(sha256sum "$latest_manifest" | awk '{print $1}')
        exact_sha=$(sha256sum "$exact_manifest" | awk '{print $1}')
        [ "$latest_sha" = "$exact_sha" ] || die "latest manifest changed while resolving an exact release"
        MANIFEST=$exact_manifest
        validate_manifest
    else
        download "$release_base/download/$RELEASE/manifest.tsv" "$MANIFEST"
        validate_manifest
        [ "$(manifest_value version)" = "$RELEASE" ] || die "manifest version does not match requested release"
    fi

    if [ -n "$MANIFEST_PIN" ]; then
        case "$MANIFEST_PIN" in
            *[!0-9a-f]*|'') die "OLCRTC_MANIFEST_SHA256 is not lowercase hexadecimal" ;;
        esac
        [ "${#MANIFEST_PIN}" -eq 64 ] || die "OLCRTC_MANIFEST_SHA256 must contain 64 characters"
        actual_manifest_sha=$(sha256sum "$MANIFEST" | awk '{print $1}')
        [ "$actual_manifest_sha" = "$MANIFEST_PIN" ] || die "manifest pin does not match"
    fi
}

# ai-generated
download_release_assets() {
    asset_base="https://github.com/$REPOSITORY/releases/download/$RELEASE"

    select_asset core "$ARCH"
    CORE_NAME=$ASSET_NAME
    core_size=$ASSET_SIZE
    core_sha=$ASSET_SHA
    CORE_FILE=$TMP_DIR/$CORE_NAME
    download "$asset_base/$CORE_NAME" "$CORE_FILE"
    verify_file "$CORE_FILE" "$core_size" "$core_sha"

    select_asset bundle amd64
    BUNDLE_NAME=$ASSET_NAME
    bundle_size=$ASSET_SIZE
    bundle_sha=$ASSET_SHA
    BUNDLE_FILE=$TMP_DIR/$BUNDLE_NAME
    download "$asset_base/$BUNDLE_NAME" "$BUNDLE_FILE"
    verify_file "$BUNDLE_FILE" "$bundle_size" "$bundle_sha"
}

# ai-generated
extract_bundle() {
    BUNDLE_DIR=$TMP_DIR/bundle
    mkdir -p "$BUNDLE_DIR"
    listing=$TMP_DIR/bundle.list
    tar -tzf "$BUNDLE_FILE" >"$listing"

    [ -s "$listing" ] || die "Debian bundle is empty"
    while IFS= read -r entry; do
        case "$entry" in
            README.ru.md|build-bundle.sh|install-server.sh|olcrtc-admin.py|olcrtc-native-admin.service|olcrtc-native@.service|server.example.yaml|uninstall-server.sh) ;;
            *) die "unexpected path in Debian bundle: $entry" ;;
        esac
    done <"$listing"

    for required in install-server.sh olcrtc-admin.py olcrtc-native-admin.service olcrtc-native@.service server.example.yaml uninstall-server.sh; do
        [ "$(grep -Fxc "$required" "$listing")" -eq 1 ] || die "bundle must contain exactly one $required"
    done

    tar -tvzf "$BUNDLE_FILE" | awk '$1 !~ /^-/ { exit 1 }' || die "bundle contains a non-regular entry"
    tar -xzf "$BUNDLE_FILE" -C "$BUNDLE_DIR"

    for required in install-server.sh olcrtc-admin.py olcrtc-native-admin.service olcrtc-native@.service server.example.yaml uninstall-server.sh; do
        if [ ! -f "$BUNDLE_DIR/$required" ] || [ -L "$BUNDLE_DIR/$required" ]; then
            die "invalid extracted file: $required"
        fi
    done
}

# ai-generated
smoke_test_binary() {
    chmod 0755 "$CORE_FILE"
    output=$TMP_DIR/core-smoke.log
    if "$CORE_FILE" >"$output" 2>&1; then
        die "olcrtc without a config unexpectedly returned success"
    fi
    grep -F "usage: olcrtc <config.yaml>" "$output" >/dev/null 2>&1 || die "downloaded core failed its executable smoke test"
}

# ai-generated
ensure_service_user() {
    if ! getent group olcrtc-native >/dev/null 2>&1; then
        groupadd --system olcrtc-native
    fi
    if ! getent passwd olcrtc-native >/dev/null 2>&1; then
        useradd --system --gid olcrtc-native --home-dir "$STATE_DIR" --shell /usr/sbin/nologin olcrtc-native
    fi
}

# ai-generated
install_config() {
    mkdir -p "$CONFIG_DIR"
    chown root:olcrtc-native "$CONFIG_DIR"
    chmod 0750 "$CONFIG_DIR"
    [ -e "$CONFIG_DIR/server.example.yaml" ] || install -o root -g olcrtc-native -m 0640 "$BUNDLE_DIR/server.example.yaml" "$CONFIG_DIR/server.example.yaml"

    if [ -z "$CONFIG_SOURCE" ]; then
        return 0
    fi
    if [ ! -f "$CONFIG_SOURCE" ] || [ -L "$CONFIG_SOURCE" ]; then
        die "config is not a regular file: $CONFIG_SOURCE"
    fi
    target=$CONFIG_DIR/$INSTANCE.yaml
    if [ -e "$target" ] && [ "$REPLACE_CONFIG" -ne 1 ]; then
        die "$target already exists; use --replace-config to replace it"
    fi
    grep -Eq '^[[:space:]]*mode:[[:space:]]*srv([[:space:]]*#.*)?$' "$CONFIG_SOURCE" || die "config must set mode: srv"
    if grep -Eq "REPLACE_ME|^[[:space:]]*id:[[:space:]]*['\"]?any['\"]?([[:space:]]*#.*)?$" "$CONFIG_SOURCE"; then
        die "config contains a placeholder or room.id=any"
    fi
    install -o root -g olcrtc-native -m 0640 "$CONFIG_SOURCE" "$target"
}

# ai-generated
install_admin_credentials() {
    credential=$CONFIG_DIR/admin.credentials
    [ -e "$credential" ] && return
    password=$(dd if=/dev/urandom bs=24 count=1 2>/dev/null | base64 | tr -d '\n')
    [ -n "$password" ] || die "could not generate admin password"
    password_file=$TMP_DIR/admin-password
    umask 077
    printf '%s\n' "$password" >"$password_file"
    python3 "$BUNDLE_DIR/olcrtc-admin.py" --init-credentials "$credential" --password-file "$password_file" \
        || die "could not initialize admin credentials"
    chown root:root "$credential"
    chmod 0600 "$credential"
    recovery=/root/olcrtc-native-admin.txt
    printf 'URL: https://SERVER_IP:8443\nLogin: admin\nPassword: %s\n' "$password" >"$recovery"
    chmod 0600 "$recovery"
    unset password
    rm -f -- "$password_file"
    say "one-time admin credentials: $recovery"
}

# ai-generated: create a private self-signed TLS identity for the public admin listener.
install_admin_tls() {
    certificate=$CONFIG_DIR/admin.crt
    private_key=$CONFIG_DIR/admin.key
    if [ -s "$certificate" ] && [ -s "$private_key" ]; then
        return
    fi
    rm -f -- "$certificate" "$private_key"
    openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
        -subj /CN=olcrtc-admin -keyout "$private_key" -out "$certificate" >/dev/null 2>&1 \
        || die "could not create the admin TLS certificate"
    chown root:root "$certificate" "$private_key"
    chmod 0644 "$certificate"
    chmod 0600 "$private_key"
}

# ai-generated
prepare_v011_migration() {
    [ "$MIGRATE_V011" -eq 1 ] || return 0
    legacy_lib=/usr/local/lib/olcrtc
    legacy_config=/etc/olcrtc/$INSTANCE.yaml
    legacy_unit=/etc/systemd/system/olcrtc-server@.service
    [ -d "$legacy_lib" ] || die "v0.1.1 fork files were not found"
    if [ ! -f "$legacy_config" ] || [ -L "$legacy_config" ]; then
        die "legacy config is not a regular file: $legacy_config"
    fi
    [ -f "$legacy_unit" ] || die "legacy template was not found"
    grep -Fqx 'ExecStart=/usr/local/lib/olcrtc/current/olcrtc /etc/olcrtc/%i.yaml' "$legacy_unit" || \
        die "legacy template does not match the prior fork package; it may belong to Oleglog Manager"
    backup=/var/backups/olcrtc-native/v0.1.1-$INSTANCE-$(date +%Y%m%d%H%M%S)
    mkdir -p "$backup"
    cp -p "$legacy_config" "$backup/$INSTANCE.yaml"
    legacy_key=/etc/olcrtc/$INSTANCE.key
    if [ -f "$legacy_key" ] && [ ! -L "$legacy_key" ]; then
        cp -p "$legacy_key" "$backup/$INSTANCE.key"
    fi
    mkdir -p "$CONFIG_DIR"
    [ ! -e "$CONFIG_DIR/$INSTANCE.yaml" ] || die "new namespace already has $INSTANCE.yaml"
    install -o root -g olcrtc-native -m 0640 "$legacy_config" "$CONFIG_DIR/$INSTANCE.yaml"
    if [ -f "$legacy_key" ] && [ ! -L "$legacy_key" ]; then
        install -o root -g olcrtc-native -m 0640 "$legacy_key" "$CONFIG_DIR/$INSTANCE.key"
    fi
    LEGACY_UNIT=olcrtc-server@$INSTANCE.service
    say "prepared explicit v0.1.1 migration; backup: $backup"
}

# ai-generated: enumerate only paths owned by the previous Manager packages.
legacy_paths() {
    for path in \
        /etc/systemd/system/olcrtc-server.service \
        /etc/systemd/system/olcrtc-server@.service \
        /etc/systemd/system/olcrtc-admin.service \
        /usr/local/bin/olcrtc \
        /usr/local/bin/olcrtc-admin \
        /usr/local/bin/olcrtc-launcher \
        /usr/local/lib/olcrtc \
        /etc/olcrtc \
        /var/lib/olcrtc
    do
        if [ -e "$path" ] || [ -L "$path" ]; then
            printf '%s\n' "$path"
        fi
    done
}

# ai-generated: create a recoverable copy and release old ports immediately before cutover.
prepare_fresh_switch() {
    [ "$FRESH" -eq 1 ] || return 0
    paths=$(legacy_paths)
    if [ -z "$paths" ]; then
        say "--fresh requested; no previous Manager files were found"
        FRESH_PREPARED=1
        return 0
    fi
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    LEGACY_BACKUP=/var/backups/olcrtc-native/legacy-manager-$stamp
    mkdir -p "$LEGACY_BACKUP/root"
    chmod 0700 "$LEGACY_BACKUP" "$LEGACY_BACKUP/root"
    : >"$LEGACY_BACKUP/paths.txt"
    printf '%s\n' "$paths" | while IFS= read -r path; do
        [ -n "$path" ] || continue
        cp -a --parents "$path" "$LEGACY_BACKUP/root"
        printf '%s\n' "$path" >>"$LEGACY_BACKUP/paths.txt"
    done
    chmod 0600 "$LEGACY_BACKUP/paths.txt"
    for unit in olcrtc-server.service olcrtc-admin.service; do
        if systemctl is-active --quiet "$unit"; then
            LEGACY_ACTIVE="$LEGACY_ACTIVE $unit"
        fi
        systemctl stop "$unit" >/dev/null 2>&1 || true
    done
    FRESH_PREPARED=1
    say "previous Manager was backed up to $LEGACY_BACKUP"
}

# ai-generated: remove the exact backed-up legacy paths only after the new admin is healthy.
commit_fresh_switch() {
    [ "$FRESH" -eq 1 ] || return 0
    [ "$FRESH_PREPARED" -eq 1 ] || die "fresh switch was not prepared"
    if [ -n "$LEGACY_BACKUP" ] && [ -f "$LEGACY_BACKUP/paths.txt" ]; then
        while IFS= read -r path; do
            case "$path" in
                /etc/systemd/system/olcrtc-server.service|\
                /etc/systemd/system/olcrtc-server@.service|\
                /etc/systemd/system/olcrtc-admin.service|\
                /usr/local/bin/olcrtc|\
                /usr/local/bin/olcrtc-admin|\
                /usr/local/bin/olcrtc-launcher|\
                /usr/local/lib/olcrtc|\
                /etc/olcrtc|\
                /var/lib/olcrtc)
                    rm -rf -- "$path"
                    ;;
                *) die "unsafe path in legacy backup manifest: $path" ;;
            esac
        done <"$LEGACY_BACKUP/paths.txt"
    fi
    systemctl disable olcrtc-server.service olcrtc-admin.service >/dev/null 2>&1 || true
    systemctl daemon-reload
    FRESH_COMMITTED=1
    say "old Manager files were removed; recovery copy: ${LEGACY_BACKUP:-not-needed}"
}

# ai-generated
active_units() {
    systemctl list-units --type=service --state=active --no-legend 'olcrtc-native@*.service' 2>/dev/null |
        awk '{print $1}'
}

# ai-generated
activate_release() {
    old_target=
    old_unit=$TMP_DIR/old-unit
    old_admin_unit=$TMP_DIR/old-admin-unit
    had_old_unit=0
    had_old_admin_unit=0
    if [ -L "$CURRENT_LINK" ]; then
        old_target=$(readlink "$CURRENT_LINK")
    elif [ -e "$CURRENT_LINK" ]; then
        die "$CURRENT_LINK exists and is not a symbolic link"
    fi
    if [ -f "$UNIT_PATH" ]; then
        cp "$UNIT_PATH" "$old_unit"
        had_old_unit=1
    fi
    if [ -f "$ADMIN_UNIT_PATH" ]; then
        cp "$ADMIN_UNIT_PATH" "$old_admin_unit"
        had_old_admin_unit=1
    fi

    release_dir=$RELEASES_DIR/$RELEASE
    stage_dir=$RELEASES_DIR/.stage.$$
    mkdir -p "$RELEASES_DIR"
    rm -rf -- "$stage_dir"
    mkdir -m 0755 "$stage_dir"
    install -o root -g root -m 0755 "$CORE_FILE" "$stage_dir/olcrtc"
    install -o root -g root -m 0755 "$BUNDLE_DIR/olcrtc-admin.py" "$stage_dir/olcrtc-admin.py"
    install -o root -g root -m 0644 "$MANIFEST" "$stage_dir/manifest.tsv"

    if [ -e "$release_dir" ]; then
        installed_sha=$(sha256sum "$release_dir/olcrtc" 2>/dev/null | awk '{print $1}')
        downloaded_sha=$(sha256sum "$CORE_FILE" | awk '{print $1}')
        [ "$installed_sha" = "$downloaded_sha" ] || die "release directory already exists with different content: $release_dir"
        [ -f "$release_dir/olcrtc-admin.py" ] || die "release directory is incomplete: $release_dir"
        rm -rf -- "$stage_dir"
    else
        mv "$stage_dir" "$release_dir"
    fi

    install -o root -g root -m 0644 "$BUNDLE_DIR/olcrtc-native@.service" "$UNIT_PATH"
    install -o root -g root -m 0755 "$BUNDLE_DIR/uninstall-server.sh" "$UNINSTALL_PATH"
    install -o root -g root -m 0755 "$BUNDLE_DIR/install-server.sh" "$INSTALL_PATH"
    install -o root -g root -m 0644 "$BUNDLE_DIR/olcrtc-native-admin.service" "$ADMIN_UNIT_PATH"
    ln -sfn "$LIB_DIR/current/olcrtc" "$BIN_LINK"
    new_link=$LIB_DIR/.current.$$
    ln -s "releases/$RELEASE" "$new_link"
    mv -Tf "$new_link" "$CURRENT_LINK"
    systemctl daemon-reload
    systemctl enable olcrtc-native-admin.service

    units=$(active_units)
    if [ "$START_SERVICE" -eq 1 ]; then
        selected_unit=olcrtc-native@$INSTANCE.service
        case " $units " in
            *" $selected_unit "*) ;;
            *) units="$units $selected_unit" ;;
        esac
        [ -f "$CONFIG_DIR/$INSTANCE.yaml" ] || die "--start requires $CONFIG_DIR/$INSTANCE.yaml"
        systemctl enable "$selected_unit"
    fi

    failed=0
    if ! systemctl restart olcrtc-native-admin.service; then
        failed=1
    elif ! systemctl is-active --quiet olcrtc-native-admin.service; then
        failed=1
    fi
    for unit in $units; do
        [ "$failed" -eq 0 ] || break
        if ! systemctl restart "$unit"; then
            failed=1
            break
        fi
        sleep 2
        if ! systemctl is-active --quiet "$unit"; then
            failed=1
            break
        fi
    done

    if [ "$failed" -eq 0 ]; then
        if [ -n "${LEGACY_UNIT:-}" ] && [ "$START_SERVICE" -eq 1 ]; then
            systemctl disable --now "$LEGACY_UNIT"
            say "stopped migrated legacy instance $LEGACY_UNIT"
        fi
        return
    fi

    say "new release failed to start; rolling back"
    if [ -n "$old_target" ]; then
        rollback_link=$LIB_DIR/.current.rollback.$$
        ln -s "$old_target" "$rollback_link"
        mv -Tf "$rollback_link" "$CURRENT_LINK"
    else
        rm -f -- "$CURRENT_LINK"
    fi
    if [ "$had_old_unit" -eq 1 ]; then
        install -o root -g root -m 0644 "$old_unit" "$UNIT_PATH"
    else
        rm -f -- "$UNIT_PATH"
    fi
    if [ "$had_old_admin_unit" -eq 1 ]; then
        install -o root -g root -m 0644 "$old_admin_unit" "$ADMIN_UNIT_PATH"
    else
        systemctl disable --now olcrtc-native-admin.service >/dev/null 2>&1 || true
        rm -f -- "$ADMIN_UNIT_PATH"
    fi
    systemctl daemon-reload
    if [ "$had_old_admin_unit" -eq 1 ]; then
        systemctl restart olcrtc-native-admin.service >/dev/null 2>&1 || true
    fi
    for unit in $units; do
        systemctl restart "$unit" >/dev/null 2>&1 || true
    done
    die "release activation failed; previous release was restored"
}

parse_args "$@"
validate_repository
validate_instance
validate_release
require_root
check_debian
ensure_dependencies

TMP_DIR=$(mktemp -d /tmp/olcrtc-server.XXXXXX)
[ -d /run/systemd/system ] || die "systemd is not running"

resolve_manifest
say "resolved release $RELEASE, upstream $(manifest_value upstream_commit)"
download_release_assets
extract_bundle
smoke_test_binary
ensure_service_user
mkdir -p "$STATE_DIR"
chown root:olcrtc-native "$STATE_DIR"
chmod 0750 "$STATE_DIR"
install_config
prepare_v011_migration
install_admin_credentials
install_admin_tls
prepare_fresh_switch
activate_release
commit_fresh_switch

say "installed release $RELEASE"
say "example config: $CONFIG_DIR/server.example.yaml"
say "release metadata: $CURRENT_LINK/manifest.tsv"
say "admin UI: https://SERVER_IP:8443 (self-signed TLS)"
if [ "$START_SERVICE" -eq 1 ]; then
    say "service: olcrtc-native@$INSTANCE.service"
else
    say "service was not started; configure $CONFIG_DIR/$INSTANCE.yaml first"
fi


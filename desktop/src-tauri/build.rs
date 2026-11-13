fn main() {
    let manifest = tauri_build::AppManifest::new().commands(&[
        "vault_status",
        "vault_unlock",
        "vault_list",
        "vault_lock",
        "vault_active",
        "vault_activity",
    ]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("failed to build Tauri command permissions");
}

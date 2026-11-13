fn main() {
    let manifest = tauri_build::AppManifest::new().commands(&[
        "vault_status",
        "vault_unlock",
        "vault_unlock_key",
        "vault_select",
        "vault_list",
        "vault_entry_notes",
        "vault_reveal",
        "vault_copy",
        "vault_save",
        "vault_delete",
        "vault_lock",
        "vault_active",
        "vault_activity",
    ]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("failed to build Tauri command permissions");
}

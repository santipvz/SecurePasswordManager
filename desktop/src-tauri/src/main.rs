#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod vault_process;
mod vault_session;

use std::sync::Arc;

use tauri::{webview::NewWindowResponse, Manager, RunEvent, State, Url, WebviewWindowBuilder};
use zeroize::Zeroizing;

use vault_process::Error;
use vault_session::{Entries, Unlocked, VaultSession, VaultStatus};

type Vault<'a> = State<'a, Arc<VaultSession>>;

#[tauri::command]
async fn vault_status(vault: Vault<'_>) -> Result<VaultStatus, Error> {
    vault.status().await
}

#[tauri::command]
async fn vault_unlock(
    vault: Vault<'_>,
    generation: u64,
    master: String,
) -> Result<Unlocked, Error> {
    vault.unlock(generation, Zeroizing::new(master)).await
}

#[tauri::command]
async fn vault_list(vault: Vault<'_>, generation: u64) -> Result<Entries, Error> {
    vault.list(generation).await
}

#[tauri::command]
async fn vault_lock(vault: Vault<'_>) -> Result<u64, Error> {
    Ok(vault.lock().await)
}

#[tauri::command]
fn vault_active(vault: Vault<'_>, generation: u64) -> bool {
    vault.active(generation)
}

#[tauri::command]
fn vault_activity(vault: Vault<'_>, generation: u64) {
    vault.activity(generation);
}

fn local_navigation(url: &Url) -> bool {
    matches!(
        (url.scheme(), url.host_str(), url.port()),
        ("tauri", Some("localhost"), None) | ("http", Some("tauri.localhost"), None)
    ) || (cfg!(dev)
        && matches!(
            (url.scheme(), url.host_str(), url.port()),
            ("http", Some("127.0.0.1"), Some(1420))
        ))
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let executable = if cfg!(windows) {
                "cpass-vault-process.exe"
            } else {
                "cpass-vault-process"
            };
            #[cfg(not(dev))]
            let path = app.path().resolve(
                format!("vault-process/{executable}"),
                tauri::path::BaseDirectory::Resource,
            )?;
            #[cfg(dev)]
            let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("resources/vault-process")
                .join(executable);
            let vault = Arc::new(VaultSession::new(path));
            app.manage(Arc::clone(&vault));
            tauri::async_runtime::spawn(async move { vault.monitor().await });
            WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .on_navigation(local_navigation)
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            vault_status,
            vault_unlock,
            vault_list,
            vault_lock,
            vault_active,
            vault_activity,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Secure Password Manager")
        .run(|app, event| {
            if matches!(event, RunEvent::Exit) {
                let vault = app.state::<Arc<VaultSession>>();
                vault.close();
                tauri::async_runtime::block_on(vault.stop_stale());
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn permits_only_the_configured_local_origins() {
        let allows = |url| local_navigation(&Url::parse(url).unwrap());
        assert!(allows("tauri://localhost/index.html"));
        assert!(allows("http://tauri.localhost/"));
        assert!(!allows("https://example.org/"));
        assert!(!allows("http://tauri.localhost:8080/"));
        assert!(!allows("http://tauri.localhost.example.org/"));
        assert!(!allows("file:///tmp/index.html"));
        assert_eq!(allows("http://127.0.0.1:1420/"), cfg!(dev));
    }
}

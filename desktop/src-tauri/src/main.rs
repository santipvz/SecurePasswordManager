#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod vault_clipboard;
mod vault_dialog;
mod vault_process;
mod vault_session;

use std::sync::Arc;

use serde::Deserialize;
use tauri::{
    webview::NewWindowResponse, Manager, RunEvent, State, Url, WebviewWindow, WebviewWindowBuilder,
};
use tokio::sync::Mutex;
use zeroize::Zeroizing;

use vault_process::{CredentialInput, Error};
use vault_session::{Entries, Entry, Review, Unlocked, VaultSession, VaultStatus};

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

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Selection {
    Default,
    Existing,
    New,
}

#[tauri::command]
async fn vault_select(
    vault: Vault<'_>,
    dialog: State<'_, Mutex<()>>,
    window: WebviewWindow,
    generation: Option<u64>,
    selection: Selection,
) -> Result<Option<VaultStatus>, Error> {
    let _guard = dialog.try_lock().map_err(|_| Error::Busy)?;
    let selection_guard = vault.begin_selection(generation)?;
    let create = matches!(selection, Selection::New);
    let path = match selection {
        Selection::Default => None,
        _ => match vault_dialog::choose(&window, create).await? {
            Some(path) => Some(path),
            None => return Ok(None),
        },
    };
    let selected = selection_guard.commit(path, create)?;
    vault.selected_status(selected).await.map(Some)
}

#[tauri::command]
async fn vault_unlock_key(
    vault: Vault<'_>,
    window: WebviewWindow,
    generation: u64,
    pin: Option<String>,
) -> Result<Unlocked, Error> {
    let pin = pin.map(Zeroizing::new);
    #[cfg(windows)]
    let parent = Some(format!(
        "{:x}",
        window.hwnd().map_err(|_| Error::KeyFailed)?.0 as usize
    ));
    #[cfg(not(windows))]
    let parent = {
        drop(window);
        None
    };
    #[cfg(windows)]
    let pin = {
        drop(pin);
        None
    };
    vault.unlock_key(generation, pin, parent).await
}

#[tauri::command]
async fn vault_list(vault: Vault<'_>, generation: u64) -> Result<Entries, Error> {
    vault.list(generation).await
}

#[tauri::command]
async fn vault_generate(
    vault: Vault<'_>,
    generation: Option<u64>,
    length: u32,
    symbols: bool,
) -> Result<String, Error> {
    vault.generate(generation, length, symbols).await
}

#[tauri::command]
async fn vault_review(vault: Vault<'_>, generation: u64) -> Result<Review, Error> {
    vault.review(generation).await
}

#[tauri::command]
async fn vault_entry_notes(
    vault: Vault<'_>,
    generation: u64,
    name: String,
) -> Result<String, Error> {
    vault.entry_notes(generation, name).await
}

#[tauri::command]
async fn vault_reveal(vault: Vault<'_>, generation: u64, name: String) -> Result<String, Error> {
    vault.reveal(generation, name).await
}

#[tauri::command]
async fn vault_copy(vault: Vault<'_>, generation: u64, name: String) -> Result<(), Error> {
    vault.copy(generation, name).await
}

#[tauri::command]
async fn vault_save(
    vault: Vault<'_>,
    generation: u64,
    entry: CredentialInput,
) -> Result<Entry, Error> {
    vault.save(generation, entry).await
}

#[tauri::command]
async fn vault_delete(vault: Vault<'_>, generation: u64, name: String) -> Result<(), Error> {
    vault.delete(generation, name).await
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
        .manage(Mutex::new(()))
        .plugin(tauri_plugin_dialog::init())
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
            let session_monitor = Arc::clone(&vault);
            tauri::async_runtime::spawn(async move { session_monitor.monitor().await });
            tauri::async_runtime::spawn(async move { vault.monitor_clipboard().await });
            WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .on_navigation(local_navigation)
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            vault_status,
            vault_unlock,
            vault_unlock_key,
            vault_select,
            vault_list,
            vault_generate,
            vault_review,
            vault_entry_notes,
            vault_reveal,
            vault_copy,
            vault_save,
            vault_delete,
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
                tauri::async_runtime::block_on(async {
                    tokio::join!(vault.stop_stale(), vault.clean_clipboard());
                });
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

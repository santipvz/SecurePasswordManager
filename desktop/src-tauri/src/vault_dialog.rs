use std::path::PathBuf;

use tauri::WebviewWindow;
use tauri_plugin_dialog::DialogExt;
use tokio::sync::oneshot;

use crate::vault_process::Error;

pub(crate) async fn choose(window: &WebviewWindow, create: bool) -> Result<Option<PathBuf>, Error> {
    choose_vault(
        window,
        if create {
            "Create a vault"
        } else {
            "Open a vault"
        },
        create.then_some("vault.spm"),
    )
    .await
}

pub(crate) async fn backup_destination(window: &WebviewWindow) -> Result<Option<PathBuf>, Error> {
    choose_vault(window, "Save encrypted backup", Some("vault-backup.spm")).await
}

pub(crate) async fn open_backup(window: &WebviewWindow) -> Result<Option<PathBuf>, Error> {
    choose_vault(window, "Open encrypted backup", None).await
}

async fn choose_vault(
    window: &WebviewWindow,
    title: &str,
    name: Option<&str>,
) -> Result<Option<PathBuf>, Error> {
    let (send, receive) = oneshot::channel();
    let dialog = window
        .dialog()
        .file()
        .set_parent(window)
        .set_title(title)
        .add_filter("Secure Password Manager vault", &["spm"]);
    let selected = move |path| {
        let _ = send.send(path);
    };
    if let Some(name) = name {
        dialog.set_file_name(name).save_file(selected);
    } else {
        dialog.pick_file(selected);
    }
    let Some(path) = receive.await.map_err(|_| Error::DialogFailed)? else {
        return Ok(None);
    };
    let path = path.into_path().map_err(|_| Error::InvalidFile)?;
    vault_path(path, name.is_some()).map(Some)
}

pub(crate) async fn legacy_files(window: &WebviewWindow) -> Result<Option<Vec<PathBuf>>, Error> {
    let (send, receive) = oneshot::channel();
    window
        .dialog()
        .file()
        .set_parent(window)
        .set_title("Import legacy credentials")
        .add_filter("Legacy credentials", &["key"])
        .pick_files(move |paths| {
            let _ = send.send(paths);
        });
    let Some(paths) = receive.await.map_err(|_| Error::DialogFailed)? else {
        return Ok(None);
    };
    if paths.is_empty() || paths.len() > 64 {
        return Err(Error::ImportCount);
    }
    let paths = paths
        .into_iter()
        .map(|path| {
            let path = path.into_path().map_err(|_| Error::InvalidImport)?;
            if path.is_absolute()
                && path.to_str().is_some()
                && path
                    .extension()
                    .is_some_and(|ext| ext.eq_ignore_ascii_case("key"))
            {
                Ok(path)
            } else {
                Err(Error::InvalidImport)
            }
        })
        .collect::<Result<_, _>>()?;
    Ok(Some(paths))
}

fn vault_path(mut path: PathBuf, create: bool) -> Result<PathBuf, Error> {
    if !path.is_absolute() || path.file_name().is_none() || path.to_str().is_none() {
        return Err(Error::InvalidFile);
    }
    if create && path.extension().is_none() {
        path.set_extension("spm");
    }
    if !path
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("spm"))
    {
        return Err(Error::InvalidFile);
    }
    Ok(path)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn limits_native_selection_to_absolute_vault_paths() {
        let name = |path: &str, create| vault_path(path.into(), create);
        assert_eq!(name("/tmp/vault", true), Ok("/tmp/vault.spm".into()));
        assert_eq!(name("/tmp/vault.SPM", false), Ok("/tmp/vault.SPM".into()));
        assert_eq!(name("/tmp/vault", false), Err(Error::InvalidFile));
        assert_eq!(name("vault.spm", true), Err(Error::InvalidFile));
        assert_eq!(name("/tmp/vault.txt", true), Err(Error::InvalidFile));
    }
}

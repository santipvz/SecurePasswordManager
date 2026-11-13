use std::path::PathBuf;

use tauri::WebviewWindow;
use tauri_plugin_dialog::DialogExt;
use tokio::sync::oneshot;

use crate::vault_process::Error;

pub(crate) async fn choose(window: &WebviewWindow, create: bool) -> Result<Option<PathBuf>, Error> {
    let (send, receive) = oneshot::channel();
    let dialog = window
        .dialog()
        .file()
        .set_parent(window)
        .add_filter("Secure Password Manager vault", &["spm"]);
    let selected = move |path| {
        let _ = send.send(path);
    };
    if create {
        dialog
            .set_title("Create a vault")
            .set_file_name("vault.spm")
            .save_file(selected);
    } else {
        dialog.set_title("Open a vault").pick_file(selected);
    }
    let Some(path) = receive.await.map_err(|_| Error::DialogFailed)? else {
        return Ok(None);
    };
    let path = path.into_path().map_err(|_| Error::InvalidFile)?;
    vault_path(path, create).map(Some)
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

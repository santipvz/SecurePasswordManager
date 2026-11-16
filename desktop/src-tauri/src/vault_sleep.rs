use std::sync::Weak;

use gio::{BusType, Cancellable, DBusSignalFlags};
use tauri::{AppHandle, Manager};

use crate::vault_session::VaultSession;

const LOGIN_MANAGER: &str = "org.freedesktop.login1";

pub(crate) fn watch(app: AppHandle, vault: Weak<VaultSession>) {
    gio::bus_get(BusType::System, Cancellable::NONE, move |result| {
        let Ok(bus) = result else {
            return;
        };
        bus.set_exit_on_close(false);
        bus.signal_subscribe(
            Some(LOGIN_MANAGER),
            Some("org.freedesktop.login1.Manager"),
            Some("PrepareForSleep"),
            Some("/org/freedesktop/login1"),
            None,
            DBusSignalFlags::NONE,
            move |_, _, _, _, _, parameters| {
                // Invalidate for both sleep and wake in case delivery was delayed by suspend.
                if let (Some(_), Some(vault)) = (parameters.get::<(bool,)>(), vault.upgrade()) {
                    vault.lock_for_sleep();
                    tauri::async_runtime::spawn(async move {
                        tokio::join!(vault.stop_stale(), vault.clean_clipboard());
                    });
                }
            },
        );
        app.manage(bus);
    });
}

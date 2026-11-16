use std::{
    cell::RefCell,
    os::fd::{FromRawFd, OwnedFd},
    rc::Rc,
    sync::Weak,
};

use gio::{
    glib::{variant::Handle, MainContext, ToVariant},
    prelude::UnixFDListExtManual,
    BusType, Cancellable, DBusCallFlags, DBusConnection, DBusSignalFlags, UnixFDList,
};
use tauri::{AppHandle, Manager};

use crate::vault_session::VaultSession;

const LOGIN_MANAGER: &str = "org.freedesktop.login1";
const MANAGER_PATH: &str = "/org/freedesktop/login1";
const MANAGER_INTERFACE: &str = "org.freedesktop.login1.Manager";

#[derive(Default)]
struct SleepInhibitor {
    revision: u64,
    fd: Option<OwnedFd>,
}

fn inhibit(bus: &DBusConnection, state: &Rc<RefCell<SleepInhibitor>>) {
    let bus = bus.clone();
    let state = Rc::clone(state);
    let revision = state.borrow().revision;
    MainContext::ref_thread_default().spawn_local(async move {
        let parameters = (
            "sleep",
            "Secure Password Manager",
            "Lock the vault before sleeping",
            "delay",
        )
            .to_variant();
        let Ok((reply, fds)) = bus
            .call_with_unix_fd_list_future(
                Some(LOGIN_MANAGER),
                MANAGER_PATH,
                MANAGER_INTERFACE,
                "Inhibit",
                Some(&parameters),
                None,
                DBusCallFlags::NONE,
                2_000,
                UnixFDList::NONE,
            )
            .await
        else {
            return;
        };
        let mut state = state.borrow_mut();
        if state.revision == revision {
            state.fd = reply
                .get::<(Handle,)>()
                .and_then(|(fd,)| fds.get(fd.0).ok())
                // GIO returns an open duplicate whose ownership passes to the caller.
                .map(|fd| unsafe { OwnedFd::from_raw_fd(fd) });
        }
    });
}

pub(crate) fn watch(app: AppHandle, vault: Weak<VaultSession>) {
    gio::bus_get(BusType::System, Cancellable::NONE, move |result| {
        let Ok(bus) = result else {
            return;
        };
        bus.set_exit_on_close(false);
        let vault_on_disconnect = vault.clone();
        bus.connect_closed(move |_, _, _| {
            if let Some(vault) = vault_on_disconnect.upgrade() {
                vault.system_sleep(false);
            }
        });
        let state = Rc::new(RefCell::new(SleepInhibitor::default()));
        let signal_state = Rc::clone(&state);
        bus.signal_subscribe(
            Some(LOGIN_MANAGER),
            Some(MANAGER_INTERFACE),
            Some("PrepareForSleep"),
            Some(MANAGER_PATH),
            None,
            DBusSignalFlags::NONE,
            move |bus, _, _, _, _, parameters| {
                if let (Some((sleeping,)), Some(vault)) =
                    (parameters.get::<(bool,)>(), vault.upgrade())
                {
                    let fd = {
                        let mut state = signal_state.borrow_mut();
                        state.revision += 1;
                        state.fd.take()
                    };
                    vault.system_sleep(sleeping);
                    tauri::async_runtime::spawn(async move {
                        tokio::join!(vault.stop_stale(), vault.clean_clipboard());
                        drop(fd);
                    });
                    if !sleeping {
                        inhibit(bus, &signal_state);
                    }
                }
            },
        );
        inhibit(&bus, &state);
        app.manage(bus);
    });
}

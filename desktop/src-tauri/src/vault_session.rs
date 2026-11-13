use std::{
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use serde::{de::DeserializeOwned, Deserialize, Serialize};
use tokio::{
    sync::{watch, Mutex},
    time::{timeout, Instant},
};
use zeroize::Zeroizing;

use crate::{
    vault_clipboard::VaultClipboard,
    vault_process::{CredentialInput, Error, Operation, Process, Secret},
};

const IDLE_TIMEOUT: Duration = Duration::from_secs(5 * 60);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(15);
const KEY_TIMEOUT: Duration = Duration::from_secs(50);

#[derive(Clone, Default)]
enum Selection {
    #[default]
    Default,
    Existing(PathBuf),
    New(PathBuf),
}

impl Selection {
    fn path(&self) -> Option<&Path> {
        match self {
            Self::Default => None,
            Self::Existing(path) | Self::New(path) => Some(path),
        }
    }

    fn creating(&self) -> bool {
        matches!(self, Self::New(_))
    }
}

#[derive(Clone, Default)]
struct Session {
    generation: u64,
    deadline: Option<Instant>,
    closed: bool,
    selection: Selection,
    choosing: bool,
}

pub(crate) struct SelectionGuard<'a> {
    session: &'a VaultSession,
    generation: u64,
}

impl SelectionGuard<'_> {
    pub(crate) fn commit(&self, path: Option<PathBuf>, create: bool) -> Result<u64, Error> {
        self.session.select(self.generation, path, create)
    }
}

impl Drop for SelectionGuard<'_> {
    fn drop(&mut self) {
        self.session.state.send_if_modified(|state| {
            if state.generation != self.generation || !state.choosing {
                return false;
            }
            state.choosing = false;
            true
        });
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CoreStatus {
    exists: bool,
    unlocked: bool,
    has_security_key: bool,
}

#[derive(Serialize)]
pub(crate) struct VaultStatus {
    exists: bool,
    has_security_key: bool,
    generation: u64,
    creating: bool,
    file_name: Option<String>,
    native_key_prompt: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Opened {
    unlocked: bool,
    has_security_key: bool,
}

#[derive(Debug, Serialize)]
pub(crate) struct Unlocked {
    generation: u64,
    has_security_key: bool,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Entries {
    entries: Vec<Entry>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Entry {
    name: String,
    username: String,
    url: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Notes {
    notes: Secret,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Password {
    password: Secret,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Deleted {
    deleted: bool,
}

pub(crate) struct VaultSession {
    executable: PathBuf,
    process: Mutex<Option<Process>>,
    state: watch::Sender<Session>,
    idle_timeout: Duration,
    request_timeout: Duration,
    clipboard: Arc<VaultClipboard>,
    #[cfg(test)]
    test_directory: Option<PathBuf>,
}

impl VaultSession {
    pub(crate) fn new(executable: PathBuf) -> Self {
        Self {
            executable,
            process: Mutex::new(None),
            state: watch::Sender::new(Session::default()),
            idle_timeout: IDLE_TIMEOUT,
            request_timeout: REQUEST_TIMEOUT,
            clipboard: Arc::default(),
            #[cfg(test)]
            test_directory: None,
        }
    }

    #[cfg(all(test, target_os = "linux"))]
    fn with_test_directory(executable: PathBuf, directory: &Path) -> Self {
        let mut session = Self::new(executable);
        session.test_directory = Some(directory.to_owned());
        session
    }

    fn invalidate(&self, generation: Option<u64>, close: bool) {
        self.state.send_if_modified(|state| {
            if state.closed || generation.is_some_and(|generation| state.generation != generation) {
                return false;
            }
            state.generation += 1;
            state.deadline = None;
            state.closed = close;
            state.choosing = false;
            true
        });
    }

    fn expire(&self) {
        self.state.send_if_modified(|state| {
            if state
                .deadline
                .is_some_and(|deadline| Instant::now() >= deadline)
            {
                state.generation += 1;
                state.deadline = None;
                return true;
            }
            false
        });
    }

    pub(crate) fn active(&self, generation: u64) -> bool {
        self.expire();
        let state = self.state.borrow();
        state.generation == generation && state.deadline.is_some()
    }

    pub(crate) fn activity(&self, generation: u64) {
        self.state.send_if_modified(|state| {
            let now = Instant::now();
            if state.generation == generation
                && state.deadline.is_some_and(|deadline| now < deadline)
            {
                state.deadline = Some(now + self.idle_timeout);
                return true;
            }
            false
        });
    }

    fn select(&self, generation: u64, path: Option<PathBuf>, create: bool) -> Result<u64, Error> {
        let selection = match path {
            None => Selection::Default,
            Some(path) if create => Selection::New(path),
            Some(path) => Selection::Existing(path),
        };
        let changed = self.state.send_if_modified(|state| {
            if state.closed || state.generation != generation || !state.choosing {
                return false;
            }
            state.generation += 1;
            state.selection = selection;
            state.choosing = false;
            true
        });
        changed.then_some(generation + 1).ok_or(Error::Locked)
    }

    pub(crate) fn begin_selection(
        &self,
        expected: Option<u64>,
    ) -> Result<SelectionGuard<'_>, Error> {
        let _request = self.process.try_lock().map_err(|_| Error::Busy)?;
        let mut generation = Err(Error::Locked);
        self.state.send_if_modified(|state| {
            if state.closed
                || state.deadline.is_some()
                || expected.is_some_and(|generation| generation != state.generation)
            {
                return false;
            }
            if state.choosing {
                generation = Err(Error::Busy);
                return false;
            }
            state.choosing = true;
            generation = Ok(state.generation);
            true
        });
        Ok(SelectionGuard {
            session: self,
            generation: generation?,
        })
    }

    pub(crate) async fn lock(&self) -> u64 {
        self.invalidate(None, false);
        let generation = self.state.borrow().generation;
        tokio::join!(self.stop_stale(), self.clean_clipboard());
        generation
    }

    pub(crate) fn close(&self) {
        self.invalidate(None, true);
    }

    pub(crate) async fn clean_clipboard(&self) {
        let clipboard = Arc::clone(&self.clipboard);
        let state = self.state.subscribe();
        let _ = tokio::task::spawn_blocking(move || {
            clipboard.clean(|generation| clipboard_session_active(&state, generation));
        })
        .await;
    }

    pub(crate) async fn monitor_clipboard(&self) {
        let mut state = self.state.subscribe();
        let mut interval = tokio::time::interval(Duration::from_millis(150));
        loop {
            tokio::select! {
                _ = async { drop(state.wait_for(|state| state.closed).await) } => break,
                _ = interval.tick() => {
                    if self.clipboard.needs_cleanup(|generation| self.active(generation)) {
                        self.clean_clipboard().await;
                    }
                }
            }
        }
    }

    pub(crate) async fn stop_stale(&self) {
        let mut process = self.process.lock().await;
        self.remove_stale(&mut process).await;
    }

    async fn remove_stale(&self, process: &mut Option<Process>) {
        let generation = self.state.borrow().generation;
        if let Some(child) = process.take_if(|child| child.generation != generation) {
            child.stop(false).await;
        }
    }

    pub(crate) async fn monitor(&self) {
        let mut interval = tokio::time::interval(Duration::from_millis(250));
        let mut state = self.state.subscribe();
        loop {
            tokio::select! {
                _ = async { drop(state.wait_for(|state| state.closed).await) } => {
                    self.stop_stale().await;
                    return;
                }
                _ = interval.tick() => {
                    self.expire();
                    if let Ok(mut process) = self.process.try_lock() {
                        let (generation, unlocked) = {
                            let state = self.state.borrow();
                            (state.generation, state.deadline.is_some())
                        };
                        let lost = match process.as_mut() {
                            Some(child) => child.generation == generation && child.exited(),
                            None => unlocked,
                        };
                        if lost {
                            self.invalidate(Some(generation), false);
                        }
                        self.remove_stale(&mut process).await;
                    }
                }
            }
        }
    }

    pub(crate) async fn status(&self) -> Result<VaultStatus, Error> {
        self.status_for(None).await
    }

    pub(crate) async fn selected_status(&self, generation: u64) -> Result<VaultStatus, Error> {
        self.status_for(Some(generation)).await
    }

    async fn status_for(&self, generation: Option<u64>) -> Result<VaultStatus, Error> {
        self.request(
            Operation::Status,
            generation,
            |status: CoreStatus, state| {
                if status.unlocked != state.deadline.is_some() {
                    return Err(Error::CommunicationFailed);
                }
                Ok(VaultStatus {
                    exists: status.exists,
                    has_security_key: status.has_security_key,
                    generation: state.generation,
                    creating: state.selection.creating(),
                    native_key_prompt: cfg!(windows),
                    file_name: state
                        .selection
                        .path()
                        .and_then(Path::file_name)
                        .map(|name| name.to_string_lossy().into_owned()),
                })
            },
        )
        .await
    }

    pub(crate) async fn unlock(
        &self,
        generation: u64,
        master: Zeroizing<String>,
    ) -> Result<Unlocked, Error> {
        let operation = if self.state.borrow().selection.creating() {
            Operation::Create { master }
        } else {
            Operation::Open { master }
        };
        self.open(generation, operation).await
    }

    pub(crate) async fn unlock_key(
        &self,
        generation: u64,
        pin: Option<Zeroizing<String>>,
        window: Option<String>,
    ) -> Result<Unlocked, Error> {
        self.open(generation, Operation::OpenKey { pin, window })
            .await
    }

    async fn open(&self, generation: u64, operation: Operation) -> Result<Unlocked, Error> {
        self.request(operation, Some(generation), |opened: Opened, state| {
            if !opened.unlocked {
                return Err(Error::CommunicationFailed);
            }
            if let Selection::New(path) = &state.selection {
                state.selection = Selection::Existing(path.clone());
            }
            state.deadline = Some(Instant::now() + self.idle_timeout);
            Ok(Unlocked {
                generation: state.generation,
                has_security_key: opened.has_security_key,
            })
        })
        .await
    }

    pub(crate) async fn list(&self, generation: u64) -> Result<Entries, Error> {
        self.request(Operation::List, Some(generation), |entries, _| Ok(entries))
            .await
    }

    pub(crate) async fn entry_notes(&self, generation: u64, name: String) -> Result<String, Error> {
        self.request(
            Operation::EntryNotes { name },
            Some(generation),
            |reply: Notes, _| Ok(reply.notes.text().to_owned()),
        )
        .await
    }

    pub(crate) async fn reveal(&self, generation: u64, name: String) -> Result<String, Error> {
        self.request(
            Operation::EntryPassword { name },
            Some(generation),
            |reply: Password, _| Ok(reply.password.text().to_owned()),
        )
        .await
    }

    pub(crate) async fn copy(&self, generation: u64, name: String) -> Result<(), Error> {
        let password = self
            .request(
                Operation::EntryPassword { name },
                Some(generation),
                |reply: Password, _| Ok(reply.password),
            )
            .await?;
        let clipboard = Arc::clone(&self.clipboard);
        let state = self.state.subscribe();
        tokio::task::spawn_blocking(move || {
            clipboard.copy(generation, password, |generation| {
                clipboard_session_active(&state, generation)
            })
        })
        .await
        .map_err(|_| Error::ClipboardUnavailable)?
    }

    pub(crate) async fn save(
        &self,
        generation: u64,
        entry: CredentialInput,
    ) -> Result<Entry, Error> {
        self.request(Operation::SaveEntry(entry), Some(generation), |entry, _| {
            Ok(entry)
        })
        .await
    }

    pub(crate) async fn delete(&self, generation: u64, name: String) -> Result<(), Error> {
        self.request(
            Operation::DeleteEntry { name },
            Some(generation),
            |reply: Deleted, _| {
                reply
                    .deleted
                    .then_some(())
                    .ok_or(Error::CommunicationFailed)
            },
        )
        .await
    }

    async fn request<T: DeserializeOwned, U>(
        &self,
        operation: Operation,
        expected: Option<u64>,
        apply: impl FnOnce(T, &mut Session) -> Result<U, Error>,
    ) -> Result<U, Error> {
        self.expire();
        let mut cancellation = self.state.subscribe();
        let generation = cancellation.borrow().generation;
        let mut slot = self.process.try_lock().map_err(|_| Error::Busy)?;
        self.remove_stale(&mut slot).await;
        let selection = {
            let state = self.state.borrow();
            if state.closed
                || state.generation != generation
                || expected.is_some_and(|expected| expected != generation)
                || (operation.requires_session() && state.deadline.is_none())
            {
                return Err(Error::Locked);
            }
            if operation.opens_vault() {
                if state.choosing {
                    return Err(Error::Busy);
                }
                if state.deadline.is_some() {
                    return Err(Error::AlreadyUnlocked);
                }
            }
            if state.selection.creating() && matches!(operation, Operation::OpenKey { .. }) {
                return Err(Error::KeyFailed);
            }
            state.selection.clone()
        };
        let path = selection
            .path()
            .map(|path| path.to_str().ok_or(Error::InvalidFile))
            .transpose()?;

        if slot.is_none() {
            // A missing process must never recreate an unlocked session.
            if operation.requires_session() {
                self.invalidate(Some(generation), false);
                return Err(Error::Locked);
            }
            *slot = Some(Process::start(
                &self.executable,
                generation,
                #[cfg(test)]
                self.test_directory.as_deref(),
            )?);
        }
        let mut child = slot.take().ok_or(Error::ProcessUnavailable)?;
        let key_request = matches!(operation, Operation::OpenKey { .. });
        let allow_cleanup = key_request || operation.writes_vault();
        let credential_request = operation.requires_session();
        let request_timeout = if key_request {
            KEY_TIMEOUT
        } else {
            self.request_timeout
        };
        let response = tokio::select! {
            biased;
            _ = cancellation.wait_for(|state| state.generation != generation) => Err(Error::Locked),
            result = timeout(request_timeout, child.exchange(operation, path)) => {
                result.unwrap_or(Err(Error::TimedOut))
            }
        };
        self.expire();
        let result = response.and_then(|reply| {
            let mut result = Err(Error::Locked);
            self.state.send_if_modified(|state| {
                if state.generation != generation {
                    return false;
                }
                let previous_deadline = state.deadline;
                result = apply(reply, state);
                state.deadline != previous_deadline
            });
            result
        });

        if matches!(result, Err(error) if !keep_process(error, credential_request)) {
            self.invalidate(Some(generation), false);
            child.stop(allow_cleanup).await;
        } else {
            *slot = Some(child);
        }
        result
    }
}

fn keep_process(error: Error, credential_request: bool) -> bool {
    error == Error::InputTooLarge
        || credential_request
            && matches!(
                error,
                Error::EntryMissing
                    | Error::EntryDuplicate
                    | Error::EntryInvalid
                    | Error::WriteConflict
            )
}

fn clipboard_session_active(state: &watch::Receiver<Session>, generation: u64) -> bool {
    let state = state.borrow();
    state.generation == generation
        && state
            .deadline
            .is_some_and(|deadline| Instant::now() < deadline)
}

#[cfg(all(test, target_os = "linux"))]
#[path = "vault_session_tests.rs"]
mod tests;

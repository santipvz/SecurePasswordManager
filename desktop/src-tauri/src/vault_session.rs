use std::{path::PathBuf, time::Duration};

use serde::{de::DeserializeOwned, Deserialize, Serialize};
use tokio::{
    sync::{watch, Mutex},
    time::{timeout, Instant},
};
use zeroize::Zeroizing;

use crate::vault_process::{Error, Operation, Process};

const IDLE_TIMEOUT: Duration = Duration::from_secs(5 * 60);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Clone, Copy, Default)]
struct Session {
    generation: u64,
    deadline: Option<Instant>,
    closed: bool,
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
struct Entry {
    name: String,
    username: String,
    url: String,
}

pub(crate) struct VaultSession {
    executable: PathBuf,
    process: Mutex<Option<Process>>,
    state: watch::Sender<Session>,
    idle_timeout: Duration,
    request_timeout: Duration,
}

impl VaultSession {
    pub(crate) fn new(executable: PathBuf) -> Self {
        Self {
            executable,
            process: Mutex::new(None),
            state: watch::Sender::new(Session::default()),
            idle_timeout: IDLE_TIMEOUT,
            request_timeout: REQUEST_TIMEOUT,
        }
    }

    fn invalidate(&self, generation: Option<u64>, close: bool) {
        self.state.send_if_modified(|state| {
            if state.closed || generation.is_some_and(|generation| state.generation != generation) {
                return false;
            }
            state.generation += 1;
            state.deadline = None;
            state.closed = close;
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

    pub(crate) async fn lock(&self) -> u64 {
        self.invalidate(None, false);
        let generation = self.state.borrow().generation;
        self.stop_stale().await;
        generation
    }

    pub(crate) fn close(&self) {
        self.invalidate(None, true);
    }

    pub(crate) async fn stop_stale(&self) {
        let mut process = self.process.lock().await;
        self.remove_stale(&mut process).await;
    }

    async fn remove_stale(&self, process: &mut Option<Process>) {
        let generation = self.state.borrow().generation;
        if let Some(child) = process.take_if(|child| child.generation != generation) {
            child.stop().await;
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
                        let state = *self.state.borrow();
                        let lost = match process.as_mut() {
                            Some(child) => child.generation == state.generation && child.exited(),
                            None => state.deadline.is_some(),
                        };
                        if lost {
                            self.invalidate(Some(state.generation), false);
                        }
                        self.remove_stale(&mut process).await;
                    }
                }
            }
        }
    }

    pub(crate) async fn status(&self) -> Result<VaultStatus, Error> {
        self.request(Operation::Status, None, |status: CoreStatus, state| {
            if status.unlocked != state.deadline.is_some() {
                return Err(Error::CommunicationFailed);
            }
            Ok(VaultStatus {
                exists: status.exists,
                has_security_key: status.has_security_key,
                generation: state.generation,
            })
        })
        .await
    }

    pub(crate) async fn unlock(
        &self,
        generation: u64,
        master: Zeroizing<String>,
    ) -> Result<Unlocked, Error> {
        if master.len() >= 64 * 1024 {
            return Err(Error::InputTooLarge);
        }
        self.request(
            Operation::Open { master },
            Some(generation),
            |opened: Opened, state| {
                if !opened.unlocked {
                    return Err(Error::CommunicationFailed);
                }
                state.deadline = Some(Instant::now() + self.idle_timeout);
                Ok(Unlocked {
                    generation: state.generation,
                    has_security_key: opened.has_security_key,
                })
            },
        )
        .await
    }

    pub(crate) async fn list(&self, generation: u64) -> Result<Entries, Error> {
        self.request(Operation::List, Some(generation), |entries, _| Ok(entries))
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
        {
            let state = self.state.borrow();
            if state.closed
                || state.generation != generation
                || expected.is_some_and(|expected| expected != generation)
                || (matches!(operation, Operation::List) && state.deadline.is_none())
            {
                return Err(Error::Locked);
            }
            if matches!(operation, Operation::Open { .. }) && state.deadline.is_some() {
                return Err(Error::AlreadyUnlocked);
            }
        }

        if slot.is_none() {
            // A missing process must never recreate an unlocked session.
            if matches!(operation, Operation::List) {
                self.invalidate(Some(generation), false);
                return Err(Error::Locked);
            }
            *slot = Some(Process::start(&self.executable, generation)?);
        }
        let mut child = slot.take().ok_or(Error::ProcessUnavailable)?;
        let response = tokio::select! {
            biased;
            _ = cancellation.wait_for(|state| state.generation != generation) => Err(Error::Locked),
            result = timeout(self.request_timeout, child.exchange(operation)) => {
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

        if matches!(result, Err(error) if error != Error::InputTooLarge) {
            self.invalidate(Some(generation), false);
            child.stop().await;
        } else {
            *slot = Some(child);
        }
        result
    }
}

#[cfg(all(test, unix))]
#[path = "vault_session_tests.rs"]
mod tests;

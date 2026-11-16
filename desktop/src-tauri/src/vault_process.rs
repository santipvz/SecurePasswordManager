use std::{path::Path, process::Stdio, time::Duration};

use serde::{de::DeserializeOwned, Deserialize, Serialize};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    time::timeout,
};
use zeroize::Zeroizing;

const VERSION: u8 = 1;
const MAX_REQUEST: usize = 64 * 1024;
// The core accepts up to 16 MiB of encrypted input. Its ASCII JSON replies can
// expand four-byte UTF-8 characters to twelve-byte surrogate pairs.
const MAX_REPLY: usize = 50 * 1024 * 1024;
const REAP_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Error {
    Busy,
    Locked,
    AlreadyUnlocked,
    InputTooLarge,
    OpenFailed,
    CreateFailed,
    WeakMaster,
    InvalidFile,
    DialogFailed,
    KeyDisconnected,
    KeyFailed,
    KeyInterrupted,
    KeySetupRequired,
    KeyUnsupported,
    MultipleKeys,
    PinBlocked,
    PinInvalid,
    PinRequired,
    WrongKey,
    FileError,
    EntryMissing,
    GeneratorLength,
    EntryDuplicate,
    EntryInvalid,
    WriteConflict,
    BackupFailed,
    ImportFailed,
    InvalidImport,
    ImportCount,
    IncorrectMaster,
    AlreadyRegistered,
    NoRegisteredKey,
    WriteFailed,
    ClipboardUnavailable,
    ClipboardUnsupported,
    ProcessUnavailable,
    CommunicationFailed,
    TimedOut,
}

pub(crate) enum Operation {
    Status,
    Open {
        master: Zeroizing<String>,
    },
    Create {
        master: Zeroizing<String>,
    },
    OpenKey {
        pin: Option<Zeroizing<String>>,
        window: Option<String>,
    },
    List,
    Generate {
        length: u32,
        symbols: bool,
    },
    Review,
    Backup {
        destination: String,
    },
    ImportLegacy {
        paths: Vec<String>,
    },
    ChangeMaster {
        master: Secret,
        new_master: Secret,
    },
    RegisterKey {
        master: Secret,
        pin: Option<Secret>,
        window: Option<String>,
    },
    RemoveKey {
        master: Secret,
    },
    EntryNotes {
        name: String,
    },
    EntryPassword {
        name: String,
    },
    SaveEntry(CredentialInput),
    DeleteEntry {
        name: String,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CredentialInput {
    previous: Option<String>,
    name: String,
    username: String,
    url: String,
    notes: Secret,
    password: Option<Secret>,
}

#[derive(Deserialize)]
#[serde(from = "String")]
pub(crate) struct Secret(Zeroizing<String>);

impl From<String> for Secret {
    fn from(value: String) -> Self {
        Self(Zeroizing::new(value))
    }
}

impl Secret {
    pub(crate) fn text(&self) -> &str {
        self.0.as_str()
    }
}

impl Operation {
    pub(crate) fn opens_vault(&self) -> bool {
        matches!(
            self,
            Self::Open { .. } | Self::Create { .. } | Self::OpenKey { .. }
        )
    }

    pub(crate) fn requires_session(&self) -> bool {
        !matches!(self, Self::Status | Self::Generate { .. }) && !self.opens_vault()
    }

    pub(crate) fn writes_vault(&self) -> bool {
        matches!(
            self,
            Self::Create { .. }
                | Self::SaveEntry(_)
                | Self::DeleteEntry { .. }
                | Self::Backup { .. }
                | Self::ImportLegacy { .. }
                | Self::ChangeMaster { .. }
                | Self::RegisterKey { .. }
                | Self::RemoveKey { .. }
        )
    }
}

#[derive(Serialize)]
#[serde(tag = "operation", rename_all = "snake_case")]
enum RequestOperation<'a> {
    Status,
    Open {
        master: &'a str,
    },
    Create {
        master: &'a str,
    },
    OpenKey {
        #[serde(skip_serializing_if = "Option::is_none")]
        pin: Option<&'a str>,
        #[serde(skip_serializing_if = "Option::is_none")]
        window: Option<&'a str>,
    },
    List,
    Generate {
        length: u32,
        symbols: bool,
    },
    Review,
    Backup {
        destination: &'a str,
    },
    ImportLegacy {
        paths: &'a [String],
    },
    ChangeMaster {
        master: &'a str,
        new_master: &'a str,
    },
    RegisterKey {
        master: &'a str,
        #[serde(skip_serializing_if = "Option::is_none")]
        pin: Option<&'a str>,
        #[serde(skip_serializing_if = "Option::is_none")]
        window: Option<&'a str>,
    },
    RemoveKey {
        master: &'a str,
    },
    EntryNotes {
        name: &'a str,
    },
    EntryPassword {
        name: &'a str,
    },
    SaveEntry {
        #[serde(skip_serializing_if = "Option::is_none")]
        previous: Option<&'a str>,
        name: &'a str,
        username: &'a str,
        url: &'a str,
        notes: &'a str,
        #[serde(skip_serializing_if = "Option::is_none")]
        password: Option<&'a str>,
    },
    DeleteEntry {
        name: &'a str,
    },
}

#[derive(Serialize)]
struct Request<'a> {
    version: u8,
    id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    path: Option<&'a str>,
    #[serde(flatten)]
    operation: RequestOperation<'a>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reply<T> {
    version: u8,
    id: u64,
    result: Option<T>,
    error: Option<CoreError>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CoreError {
    code: String,
    #[serde(rename = "message")]
    _message: serde::de::IgnoredAny,
}

pub(crate) struct Process {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    next_id: u64,
    pub(crate) generation: u64,
}

impl Process {
    pub(crate) fn start(
        executable: &Path,
        generation: u64,
        #[cfg(test)] directory: Option<&Path>,
    ) -> Result<Self, Error> {
        let mut command = Command::new(executable);
        #[cfg(test)]
        if let Some(directory) = directory {
            command.current_dir(directory);
        }
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        let mut child = command.spawn().map_err(|_| Error::ProcessUnavailable)?;
        let input = child.stdin.take().ok_or(Error::ProcessUnavailable)?;
        let output = BufReader::new(child.stdout.take().ok_or(Error::ProcessUnavailable)?);
        Ok(Self {
            child,
            input,
            output,
            next_id: 1,
            generation,
        })
    }

    pub(crate) fn exited(&mut self) -> bool {
        !matches!(self.child.try_wait(), Ok(None))
    }

    pub(crate) async fn stop(mut self, allow_cancellation: bool) {
        drop(self.input);
        if allow_cancellation
            && matches!(
                timeout(Duration::from_millis(750), self.child.wait()).await,
                Ok(Ok(_))
            )
        {
            return;
        }
        let _ = self.child.start_kill();
        let _ = timeout(REAP_TIMEOUT, self.child.wait()).await;
    }

    pub(crate) async fn exchange<T: DeserializeOwned>(
        &mut self,
        operation: Operation,
        path: Option<&str>,
    ) -> Result<T, Error> {
        let id = self.next_id;
        // JSON numbers must round-trip through the protocol's safe integer range.
        self.next_id = (id % 9_007_199_254_740_991) + 1;
        let mut line = {
            let (request_operation, field_bytes) = match &operation {
                Operation::Status => (RequestOperation::Status, 0),
                Operation::List => (RequestOperation::List, 0),
                Operation::Generate { length, symbols } => (
                    RequestOperation::Generate {
                        length: *length,
                        symbols: *symbols,
                    },
                    0,
                ),
                Operation::Review => (RequestOperation::Review, 0),
                Operation::Backup { destination } => {
                    (RequestOperation::Backup { destination }, destination.len())
                }
                Operation::ImportLegacy { paths } => (
                    RequestOperation::ImportLegacy { paths },
                    paths.iter().map(|path| path.len() + 3).sum(),
                ),
                Operation::ChangeMaster { master, new_master } => (
                    RequestOperation::ChangeMaster {
                        master: master.text(),
                        new_master: new_master.text(),
                    },
                    master.text().len() + new_master.text().len(),
                ),
                Operation::RegisterKey {
                    master,
                    pin,
                    window,
                } => {
                    let pin = pin.as_ref().map(Secret::text);
                    (
                        RequestOperation::RegisterKey {
                            master: master.text(),
                            pin,
                            window: window.as_deref(),
                        },
                        master.text().len() + pin.map_or(0, str::len),
                    )
                }
                Operation::RemoveKey { master } => (
                    RequestOperation::RemoveKey {
                        master: master.text(),
                    },
                    master.text().len(),
                ),
                Operation::Open { master } => (RequestOperation::Open { master }, master.len()),
                Operation::Create { master } => (RequestOperation::Create { master }, master.len()),
                Operation::OpenKey { pin, window } => {
                    let pin = pin.as_ref().map(|value| value.as_str());
                    (
                        RequestOperation::OpenKey {
                            pin,
                            window: window.as_deref(),
                        },
                        pin.map_or(0, str::len),
                    )
                }
                Operation::EntryNotes { name } => {
                    (RequestOperation::EntryNotes { name }, name.len())
                }
                Operation::EntryPassword { name } => {
                    (RequestOperation::EntryPassword { name }, name.len())
                }
                Operation::DeleteEntry { name } => {
                    (RequestOperation::DeleteEntry { name }, name.len())
                }
                Operation::SaveEntry(entry) => {
                    let previous = entry.previous.as_deref();
                    let password = entry.password.as_ref().map(Secret::text);
                    let notes = entry.notes.text();
                    (
                        RequestOperation::SaveEntry {
                            previous,
                            name: &entry.name,
                            username: &entry.username,
                            url: &entry.url,
                            notes,
                            password,
                        },
                        previous.map_or(0, str::len)
                            + entry.name.len()
                            + entry.username.len()
                            + entry.url.len()
                            + notes.len()
                            + password.map_or(0, str::len),
                    )
                }
            };
            let path =
                path.filter(|_| matches!(operation, Operation::Status) || operation.opens_vault());
            let length = field_bytes + path.map_or(0, str::len);
            if length >= MAX_REQUEST {
                return Err(Error::InputTooLarge);
            }
            let request = Request {
                version: VERSION,
                id,
                path,
                operation: request_operation,
            };
            // JSON escaping expands an input byte to at most six bytes.
            let mut line = Zeroizing::new(Vec::with_capacity(256 + 6 * length));
            serde_json::to_writer(&mut *line, &request).map_err(|_| Error::CommunicationFailed)?;
            line
        };
        drop(operation);
        line.push(b'\n');
        if line.len() > MAX_REQUEST {
            return Err(Error::InputTooLarge);
        }
        self.input
            .write_all(&line)
            .await
            .map_err(|_| Error::CommunicationFailed)?;
        drop(line);

        let mut frame = Zeroizing::new(Vec::new());
        (&mut self.output)
            .take((MAX_REPLY + 1) as u64)
            .read_until(b'\n', &mut frame)
            .await
            .map_err(|_| Error::CommunicationFailed)?;
        if frame.len() > MAX_REPLY || frame.last() != Some(&b'\n') {
            return Err(Error::CommunicationFailed);
        }
        let reply: Reply<T> =
            serde_json::from_slice(&frame).map_err(|_| Error::CommunicationFailed)?;
        if reply.version != VERSION || reply.id != id {
            return Err(Error::CommunicationFailed);
        }
        match (reply.result, reply.error) {
            (Some(result), None) => Ok(result),
            (None, Some(error)) => Err(match error.code.as_str() {
                "open_failed" => Error::OpenFailed,
                "create_failed" => Error::CreateFailed,
                "weak_master" => Error::WeakMaster,
                "key_disconnected" => Error::KeyDisconnected,
                "key_failed" => Error::KeyFailed,
                "key_interrupted" => Error::KeyInterrupted,
                "key_setup_required" => Error::KeySetupRequired,
                "key_unsupported" => Error::KeyUnsupported,
                "multiple_keys" => Error::MultipleKeys,
                "pin_blocked" => Error::PinBlocked,
                "pin_invalid" => Error::PinInvalid,
                "pin_required" => Error::PinRequired,
                "wrong_key" => Error::WrongKey,
                "file_error" => Error::FileError,
                "locked" => Error::Locked,
                "generator_length" => Error::GeneratorLength,
                "entry_missing" => Error::EntryMissing,
                "entry_duplicate" => Error::EntryDuplicate,
                "entry_invalid" => Error::EntryInvalid,
                "backup_failed" => Error::BackupFailed,
                "import_failed" => Error::ImportFailed,
                "incorrect_master" => Error::IncorrectMaster,
                "already_registered" => Error::AlreadyRegistered,
                "no_registered_key" => Error::NoRegisteredKey,
                "write_conflict" => Error::WriteConflict,
                "write_failed" => Error::WriteFailed,
                _ => Error::CommunicationFailed,
            }),
            _ => Err(Error::CommunicationFailed),
        }
    }
}

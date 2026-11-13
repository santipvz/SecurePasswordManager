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
}

impl Operation {
    pub(crate) fn opens_vault(&self) -> bool {
        matches!(
            self,
            Self::Open { .. } | Self::Create { .. } | Self::OpenKey { .. }
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
            let (request_operation, secret_length) = match &operation {
                Operation::Status => (RequestOperation::Status, 0),
                Operation::List => (RequestOperation::List, 0),
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
            };
            let path = path.filter(|_| !matches!(operation, Operation::List));
            let length = secret_length + path.map_or(0, str::len);
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
            let mut line = Zeroizing::new(Vec::with_capacity(128 + 6 * length));
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
                _ => Error::CommunicationFailed,
            }),
            _ => Err(Error::CommunicationFailed),
        }
    }
}

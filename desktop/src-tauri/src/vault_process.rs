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
    FileError,
    ProcessUnavailable,
    CommunicationFailed,
    TimedOut,
}

pub(crate) enum Operation {
    Status,
    Open { master: Zeroizing<String> },
    List,
}

#[derive(Serialize)]
#[serde(tag = "operation", rename_all = "snake_case")]
enum RequestOperation<'a> {
    Status,
    Open { master: &'a str },
    List,
}

#[derive(Serialize)]
struct Request<'a> {
    version: u8,
    id: u64,
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
    pub(crate) fn start(executable: &Path, generation: u64) -> Result<Self, Error> {
        let mut command = Command::new(executable);
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

    pub(crate) async fn stop(mut self) {
        drop(self.input);
        let _ = self.child.start_kill();
        let _ = timeout(REAP_TIMEOUT, self.child.wait()).await;
    }

    pub(crate) async fn exchange<T: DeserializeOwned>(
        &mut self,
        operation: Operation,
    ) -> Result<T, Error> {
        let id = self.next_id;
        // JSON numbers must round-trip through the protocol's safe integer range.
        self.next_id = (id % 9_007_199_254_740_991) + 1;
        let mut line = {
            let (request_operation, capacity) = match &operation {
                Operation::Status => (RequestOperation::Status, 128),
                Operation::List => (RequestOperation::List, 128),
                Operation::Open { master } => {
                    (RequestOperation::Open { master }, 128 + 6 * master.len())
                }
            };
            let request = Request {
                version: VERSION,
                id,
                operation: request_operation,
            };
            let mut line = Zeroizing::new(Vec::with_capacity(capacity));
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
                "file_error" => Error::FileError,
                "locked" => Error::Locked,
                _ => Error::CommunicationFailed,
            }),
            _ => Err(Error::CommunicationFailed),
        }
    }
}

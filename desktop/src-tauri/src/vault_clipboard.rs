use std::{sync::Mutex, time::Duration};

use arboard::Clipboard;
#[cfg(target_os = "macos")]
use arboard::SetExtApple;
#[cfg(target_os = "linux")]
use arboard::SetExtLinux;
#[cfg(windows)]
use arboard::SetExtWindows;
use tokio::time::Instant;
use zeroize::Zeroizing;

use crate::vault_process::{Error, Secret};

const COPY_LIFETIME: Duration = Duration::from_secs(30);
const CLEANUP_RETRY: Duration = Duration::from_secs(5);

struct CopiedPassword {
    value: Secret,
    generation: u64,
    expires: Instant,
    retry_until: Instant,
}

impl CopiedPassword {
    fn due(&self, active: impl FnOnce(u64) -> bool) -> bool {
        Instant::now() >= self.expires || !active(self.generation)
    }

    fn clear_if_unchanged(
        &self,
        clipboard: &mut impl ClipboardAccess,
    ) -> Result<(), arboard::Error> {
        match clipboard.read_text() {
            Ok(current) => {
                let current = Zeroizing::new(current);
                if current.as_str() == self.value.text() {
                    clipboard.clear_text()?;
                }
            }
            Err(arboard::Error::ContentNotAvailable | arboard::Error::ConversionFailure) => {}
            Err(error) => return Err(error),
        }
        Ok(())
    }
}

trait ClipboardAccess {
    fn read_text(&mut self) -> Result<String, arboard::Error>;
    fn clear_text(&mut self) -> Result<(), arboard::Error>;
}

impl ClipboardAccess for Clipboard {
    fn read_text(&mut self) -> Result<String, arboard::Error> {
        self.get_text()
    }

    fn clear_text(&mut self) -> Result<(), arboard::Error> {
        self.clear()
    }
}

#[derive(Default)]
struct State {
    clipboard: Option<Clipboard>,
    copied: Option<CopiedPassword>,
}

#[derive(Default)]
pub(crate) struct VaultClipboard(Mutex<State>);

impl VaultClipboard {
    pub(crate) fn copy(
        &self,
        generation: u64,
        value: Secret,
        active: impl Fn(u64) -> bool,
    ) -> Result<(), Error> {
        let mut state = self.0.lock().map_err(|_| Error::ClipboardUnavailable)?;
        if !active(generation) {
            return Err(Error::Locked);
        }
        // The system text clipboard uses NUL-terminated strings on Windows.
        if value.text().contains('\0') {
            return Err(Error::ClipboardUnsupported);
        }
        if state.clipboard.is_none() {
            state.clipboard = Some(Clipboard::new().map_err(|_| Error::ClipboardUnavailable)?);
        }
        let clipboard = state
            .clipboard
            .as_mut()
            .ok_or(Error::ClipboardUnavailable)?;
        let set = clipboard.set();
        #[cfg(any(target_os = "linux", target_os = "macos", windows))]
        let set = set.exclude_from_history();
        #[cfg(windows)]
        let set = set.exclude_from_cloud();
        set.text(value.text())
            .map_err(|_| Error::ClipboardUnavailable)?;
        let expires = Instant::now() + COPY_LIFETIME;
        state.copied = Some(CopiedPassword {
            value,
            generation,
            expires,
            retry_until: expires + CLEANUP_RETRY,
        });
        if !active(generation) {
            Self::clean_state(&mut state, active);
            return Err(Error::Locked);
        }
        Ok(())
    }

    pub(crate) fn needs_cleanup(&self, active: impl FnOnce(u64) -> bool) -> bool {
        self.0.try_lock().is_ok_and(|state| {
            state
                .copied
                .as_ref()
                .is_some_and(|copied| copied.due(active))
        })
    }

    pub(crate) fn clean(&self, active: impl FnOnce(u64) -> bool) {
        if let Ok(mut state) = self.0.lock() {
            Self::clean_state(&mut state, active);
        }
    }

    fn clean_state(state: &mut State, active: impl FnOnce(u64) -> bool) {
        if let (Some(clipboard), Some(copied)) = (&mut state.clipboard, &mut state.copied) {
            let now = Instant::now();
            if !active(copied.generation) {
                copied.retry_until = copied.retry_until.min(now + CLEANUP_RETRY);
            } else if now < copied.expires {
                return;
            }
            if copied.clear_if_unchanged(clipboard).is_ok() || Instant::now() >= copied.retry_until
            {
                state.copied = None;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Default)]
    struct TestClipboard(Option<String>);

    impl ClipboardAccess for TestClipboard {
        fn read_text(&mut self) -> Result<String, arboard::Error> {
            self.0.clone().ok_or(arboard::Error::ContentNotAvailable)
        }

        fn clear_text(&mut self) -> Result<(), arboard::Error> {
            self.0 = None;
            Ok(())
        }
    }

    #[tokio::test(start_paused = true)]
    async fn clears_after_thirty_seconds_or_lock_and_preserves_a_replacement() {
        let copied = CopiedPassword {
            value: "synthetic".to_owned().into(),
            generation: 1,
            expires: Instant::now() + COPY_LIFETIME,
            retry_until: Instant::now() + COPY_LIFETIME + CLEANUP_RETRY,
        };
        let mut clipboard = TestClipboard(Some("synthetic".into()));
        assert!(!copied.due(|generation| generation == 1));
        assert!(copied.due(|_| false));
        tokio::time::advance(COPY_LIFETIME - Duration::from_millis(1)).await;
        assert!(!copied.due(|_| true));
        tokio::time::advance(Duration::from_millis(1)).await;
        assert!(copied.due(|_| true));
        copied.clear_if_unchanged(&mut clipboard).unwrap();
        assert_eq!(clipboard.0, None);
        clipboard.0 = Some("copied in another app".into());
        copied.clear_if_unchanged(&mut clipboard).unwrap();
        assert_eq!(clipboard.0.as_deref(), Some("copied in another app"));
    }
}

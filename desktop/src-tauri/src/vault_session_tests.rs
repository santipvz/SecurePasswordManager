use std::{fs, path::Path, sync::Arc};

use tempfile::TempDir;
use tokio::{task::JoinHandle, time::sleep};

use super::*;

const MASTER: &str = "Synthetic compatibility passphrase";
fn launcher() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fake_vault_process.py")
}

fn fake_core(body: &str) -> (TempDir, Arc<VaultSession>) {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("core.py"),
        format!(
            r#"#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
root = Path.cwd()

def reply(result, **fields):
    response = dict(version=1, id=request["id"], result=result)
    response.update(fields)
    print(json.dumps(response), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    operation = request["operation"]
    if operation == "status":
        reply(dict(exists=True, unlocked=False, has_security_key=False))
        continue
{body}
"#
        ),
    )
    .unwrap();
    let session = Arc::new(VaultSession::with_test_directory(launcher(), dir.path()));
    (dir, session)
}

async fn wait_for_file(path: &Path) {
    timeout(Duration::from_secs(5), async {
        while !path.is_file() {
            sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
}

async fn launch_unlock(session: &Arc<VaultSession>) -> (u64, JoinHandle<Result<Unlocked, Error>>) {
    let generation = session.status().await.unwrap().generation;
    let session = Arc::clone(session);
    (
        generation,
        tokio::spawn(async move { session.unlock(generation, MASTER.to_owned().into()).await }),
    )
}

#[tokio::test]
async fn opens_both_existing_formats_without_modifying_them() {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    let core = manifest.join("resources/vault-process/cpass-vault-process");
    for (fixture, has_security_key) in [("password-v1.spm", false), ("fido2-v2.spm", true)] {
        let dir = tempfile::tempdir().unwrap();
        let original = fs::read(manifest.join("../../tests/fixtures").join(fixture)).unwrap();
        let vault = dir.path().join(fixture);
        fs::write(&vault, &original).unwrap();
        let session = VaultSession::new(core.clone());
        let selection = session.begin_selection(None).unwrap();
        let generation = selection.commit(Some(vault.clone()), false).unwrap();
        let status = session.selected_status(generation).await.unwrap();
        assert!(status.exists);
        assert_eq!(status.has_security_key, has_security_key);
        assert_eq!(
            session
                .unlock(status.generation, "wrong password".to_owned().into())
                .await
                .err(),
            Some(Error::OpenFailed)
        );
        let status = session.status().await.unwrap();
        let unlocked = session
            .unlock(status.generation, MASTER.to_owned().into())
            .await
            .unwrap();
        assert_eq!(unlocked.has_security_key, has_security_key);
        let entries = session.list(unlocked.generation).await.unwrap().entries;
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "Fixture account");
        assert_eq!(entries[0].username, "fixture@example.test");
        let next = session.lock().await;
        assert_ne!(next, unlocked.generation);
        assert!(!session.active(unlocked.generation));
        assert_eq!(
            session.list(unlocked.generation).await.err(),
            Some(Error::Locked)
        );
        assert!(session.process.lock().await.is_none());
        assert_eq!(fs::read(vault).unwrap(), original);
    }
}

#[tokio::test]
async fn manual_lock_cancels_pending_and_rejects_late_unlocks() {
    let (dir, session) = fake_core(
        r#"    if operation == "open":
        if not (root / "started").exists():
            (root / "started").write_text(str(os.getpid()))
            time.sleep(30)
        reply(dict(unlocked=True, has_security_key=False))
"#,
    );
    let (generation, pending) = launch_unlock(&session).await;
    let started = dir.path().join("started");
    wait_for_file(&started).await;
    assert_eq!(session.status().await.err(), Some(Error::Busy));
    let next = session.lock().await;
    assert_eq!(pending.await.unwrap().err(), Some(Error::Locked));
    assert!(session.process.lock().await.is_none());
    assert_eq!(
        session
            .unlock(generation, MASTER.to_owned().into())
            .await
            .err(),
        Some(Error::Locked)
    );
    let unlocked = session
        .unlock(next, MASTER.to_owned().into())
        .await
        .unwrap();
    assert!(session.active(unlocked.generation));
    session.lock().await;
}

#[tokio::test]
async fn closing_cancels_pending_and_prevents_restart() {
    let (dir, session) = fake_core(
        r#"    (root / "started").write_text(str(os.getpid()))
    time.sleep(30)
"#,
    );
    let (generation, pending) = launch_unlock(&session).await;
    let started = dir.path().join("started");
    wait_for_file(&started).await;
    session.close();
    session.stop_stale().await;
    assert_eq!(pending.await.unwrap().err(), Some(Error::Locked));
    assert!(session.process.lock().await.is_none());
    assert_eq!(session.status().await.err(), Some(Error::Locked));
    assert_eq!(
        session
            .unlock(generation, MASTER.to_owned().into())
            .await
            .err(),
        Some(Error::Locked)
    );
}

#[tokio::test]
async fn inactivity_locks_while_a_request_is_pending() {
    let (dir, mut session) = fake_core(
        r#"    if operation == "open":
        reply(dict(unlocked=True, has_security_key=False))
    elif operation == "list":
        (root / "started").touch()
        time.sleep(30)
"#,
    );
    Arc::get_mut(&mut session).unwrap().idle_timeout = Duration::from_secs(2);
    let monitor = tokio::spawn({
        let session = Arc::clone(&session);
        async move { session.monitor().await }
    });
    let generation = session.status().await.unwrap().generation;
    session
        .unlock(generation, MASTER.to_owned().into())
        .await
        .unwrap();
    tokio::time::pause();
    tokio::time::advance(Duration::from_secs(1)).await;
    session.activity(generation);
    tokio::time::advance(Duration::from_secs(1)).await;
    assert!(session.active(generation));
    tokio::time::resume();

    let started = dir.path().join("started");
    let (reply, ()) = tokio::join!(session.list(generation), async {
        wait_for_file(&started).await;
        tokio::time::pause();
        tokio::time::advance(Duration::from_secs(2)).await;
        session.activity(generation);
    });
    assert_eq!(reply.err(), Some(Error::Locked));
    assert!(!session.active(generation));
    session.close();
    monitor.await.unwrap();
    assert!(session.process.lock().await.is_none());
}

#[tokio::test]
async fn detects_child_exit_without_an_in_flight_request() {
    let (_dir, session) = fake_core(
        r#"    reply(dict(unlocked=True, has_security_key=False))
    sys.exit(0)
"#,
    );
    let monitor = tokio::spawn({
        let session = Arc::clone(&session);
        async move { session.monitor().await }
    });
    let generation = session.status().await.unwrap().generation;
    session
        .unlock(generation, MASTER.to_owned().into())
        .await
        .unwrap();
    timeout(Duration::from_secs(5), async {
        while session.active(generation) {
            sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    assert_ne!(session.status().await.unwrap().generation, generation);
    session.close();
    monitor.await.unwrap();
}

#[tokio::test]
async fn rejects_broken_frames_and_restarts_locked() {
    for body in [
        "    sys.exit(0)",
        "    sys.stdout.write('{}'); sys.stdout.flush(); sys.exit(0)",
        "    print('invalid json', flush=True)",
        "    reply(dict(unlocked=True, has_security_key=False), version=2)",
        "    reply(dict(unlocked=True, has_security_key=False), id=request['id'] + 1)",
        "    print(' ' * (51 * 1024 * 1024), flush=True)",
    ] {
        let (_dir, session) = fake_core(body);
        let generation = session.status().await.unwrap().generation;
        assert_eq!(
            session
                .unlock(generation, MASTER.to_owned().into())
                .await
                .err(),
            Some(Error::CommunicationFailed)
        );
        assert!(!session.active(generation));
        assert!(session.process.lock().await.is_none());
        assert_ne!(session.status().await.unwrap().generation, generation);
        session.lock().await;
    }
}

#[tokio::test]
async fn timeout_and_dropped_request_discard_the_process() {
    let (dir, mut session) = fake_core(
        r#"    (root / "started").touch()
    time.sleep(30)
"#,
    );
    let generation = session.status().await.unwrap().generation;
    Arc::get_mut(&mut session).unwrap().request_timeout = Duration::from_secs(1);
    assert_eq!(
        session
            .unlock(generation, MASTER.to_owned().into())
            .await
            .err(),
        Some(Error::TimedOut)
    );
    assert!(session.process.lock().await.is_none());
    fs::remove_file(dir.path().join("started")).unwrap();

    let (_generation, pending) = launch_unlock(&session).await;
    wait_for_file(&dir.path().join("started")).await;
    pending.abort();
    assert!(pending.await.unwrap_err().is_cancelled());
    assert!(session.process.lock().await.is_none());
    session.close();
}

#[tokio::test]
async fn selecting_another_vault_rejects_the_previous_generation() {
    let (dir, session) = fake_core(
        r#"    if operation == "open":
        assert request["path"] == str(root / "selected.spm")
        reply(dict(unlocked=True, has_security_key=False))
"#,
    );
    let old = session.status().await.unwrap().generation;
    let selected = dir.path().join("selected.spm");
    let selection = session.begin_selection(Some(old)).unwrap();
    assert_eq!(
        session.unlock(old, MASTER.to_owned().into()).await.err(),
        Some(Error::Busy)
    );
    let next = selection.commit(Some(selected), false).unwrap();
    assert_eq!(
        session.begin_selection(Some(old)).err(),
        Some(Error::Locked)
    );
    assert_eq!(
        session.unlock(old, MASTER.to_owned().into()).await.err(),
        Some(Error::Locked)
    );
    let status = session.selected_status(next).await.unwrap();
    assert_eq!(status.file_name.as_deref(), Some("selected.spm"));
    assert!(!status.creating);
    let unlocked = session
        .unlock(next, MASTER.to_owned().into())
        .await
        .unwrap();
    assert!(session.active(unlocked.generation));
    assert_eq!(
        session.begin_selection(Some(next)).err(),
        Some(Error::Locked)
    );
    session.lock().await;
}

#[tokio::test]
async fn cancelling_a_key_request_closes_stdin_and_discards_its_reply() {
    let (dir, session) = fake_core(
        r#"    if operation == "open_key":
        assert request["pin"] == "synthetic PIN"
        assert "master" not in request
        (root / "started").touch()
        assert sys.stdin.read() == ""
        (root / "cancelled").touch()
        reply(dict(unlocked=True, has_security_key=True))
"#,
    );
    let generation = session.status().await.unwrap().generation;
    let task = tokio::spawn({
        let session = Arc::clone(&session);
        async move {
            session
                .unlock_key(generation, Some("synthetic PIN".to_owned().into()), None)
                .await
        }
    });
    wait_for_file(&dir.path().join("started")).await;
    let next = session.lock().await;
    assert_eq!(task.await.unwrap().err(), Some(Error::Locked));
    assert_ne!(next, generation);
    assert!(!session.active(generation));
    assert!(dir.path().join("cancelled").is_file());
    assert!(session.process.lock().await.is_none());
}

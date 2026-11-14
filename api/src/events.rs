//! Per-analysis broadcast of progress events to SSE subscribers.

use std::{
    collections::HashMap,
    sync::{Arc, Mutex, PoisonError},
};

use junction_contracts::AnalysisEvent;
use tokio::sync::broadcast;
use uuid::Uuid;

/// Events buffered per subscriber before it lags; a lagging client reconnects for a snapshot.
const CAPACITY: usize = 64;

#[derive(Clone, Default)]
pub struct Hub {
    channels: Arc<Mutex<HashMap<Uuid, broadcast::Sender<AnalysisEvent>>>>,
}

impl Hub {
    /// Opens the channel of a new analysis.
    pub fn open(&self, id: Uuid) {
        self.lock()
            .entry(id)
            .or_insert_with(|| broadcast::channel(CAPACITY).0);
    }

    /// Subscribes to a running analysis; `None` once it has finished.
    pub fn subscribe(&self, id: Uuid) -> Option<broadcast::Receiver<AnalysisEvent>> {
        self.lock().get(&id).map(broadcast::Sender::subscribe)
    }

    pub fn send(&self, id: Uuid, event: AnalysisEvent) {
        if let Some(tx) = self.lock().get(&id) {
            // No subscribers is fine: the record is persisted anyway.
            let _ = tx.send(event);
        }
    }

    /// Sends the final event and closes the channel, which ends every subscriber's stream.
    pub fn finish(&self, id: Uuid, event: AnalysisEvent) {
        if let Some(tx) = self.lock().remove(&id) {
            let _ = tx.send(event);
        }
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<Uuid, broadcast::Sender<AnalysisEvent>>> {
        self.channels.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

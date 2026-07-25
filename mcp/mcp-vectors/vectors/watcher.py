"""
File system watcher for automatic re-indexing.

This module provides active watching of directories with debounced
re-indexing when files are created, modified, or deleted.

Implements single-process ownership via file-based locking - only one
process can actively watch at a time. If the owning process dies, the
lock is automatically released and another process can take over.
"""

import asyncio
import fcntl
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional, Set
from dataclasses import dataclass, field
from threading import Lock

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
)

from .config import DEFAULT_EXCLUDED_EXTENSIONS, DEFAULT_EXCLUDED_DIRECTORIES
from .gitignore import GitignoreMatcher
from .safety import ExclusionPolicy

logger = logging.getLogger("mcp-vectors.watcher")


@dataclass
class WatcherConfig:
    """Configuration for the file watcher."""
    watch_dir: Path
    excluded_extensions: Set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_EXTENSIONS))
    excluded_directories: Set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_DIRECTORIES))
    debounce_seconds: float = 2.0  # Wait this long after last change before processing
    batch_interval_seconds: float = 10.0  # Maximum time to batch changes before processing
    respect_gitignore: bool = True  # Skip paths ignored by .gitignore / .git/info/exclude


class IndexEventHandler(FileSystemEventHandler):
    """
    File system event handler that collects changes for batch processing.
    
    Uses debouncing to avoid re-indexing on every keystroke while editing.
    """
    
    def __init__(
        self,
        config: WatcherConfig,
        on_files_changed: Callable[[Set[Path]], None],
        on_files_deleted: Callable[[Set[Path]], None],
        on_dirs_touched: Optional[Callable[[Set[Path]], None]] = None,
    ):
        super().__init__()
        self.config = config
        self.on_files_changed = on_files_changed
        self.on_files_deleted = on_files_deleted
        self.on_dirs_touched = on_dirs_touched

        # Every path seen this batch (creates, modifies, and deletes alike). We
        # classify each by its real disk state at process time rather than trusting
        # per-event create/delete bookkeeping: an atomic save (write-temp then
        # rename-replace) emits both a change and a delete for the same target in
        # one batch, and order-dependent bookkeeping let the delete cannibalize the
        # change, removing the file from the index and never re-indexing it.
        self._pending_files: Set[Path] = set()
        # Parent directories touched this batch, reconciled against the index as a
        # safety net for per-file events the OS coalesces away (esp. macOS FSEvents).
        self._touched_dirs: Set[Path] = set()
        self._lock = Lock()
        self._last_event_time: float = 0
        self._batch_start_time: float = 0
        self._processing_scheduled = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._exclusion_policy = ExclusionPolicy(
            excluded_extensions=self.config.excluded_extensions,
            excluded_directories=self.config.excluded_directories,
        )
        self._gitignore_matcher = (
            GitignoreMatcher.for_path(self.config.watch_dir)
            if self.config.respect_gitignore
            else None
        )

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop for scheduling async callbacks."""
        self._loop = loop
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored based on shared exclusion policy."""
        decision = self._exclusion_policy.should_index_path(path)
        return decision.action == "skip" and (path.is_file() or not path.exists())

    def _is_supported_file(self, path: Path) -> bool:
        """Check if file should be indexed (not in exclusion list)."""
        return self._exclusion_policy.should_index_path(path).action == "index"
    
    def _schedule_processing(self):
        """Schedule batch processing after debounce delay."""
        if self._loop is None:
            logger.warning("Event loop not set, cannot schedule processing")
            return
        
        self._loop.call_soon_threadsafe(self._async_schedule_processing)
    
    def _async_schedule_processing(self):
        """Schedule processing from the async event loop."""
        if self._processing_scheduled:
            return
        
        self._processing_scheduled = True
        asyncio.create_task(self._delayed_process())
    
    async def _delayed_process(self):
        """Wait for debounce period then process changes."""
        try:
            while True:
                now = time.time()
                time_since_last = now - self._last_event_time
                time_since_batch_start = now - self._batch_start_time
                
                # Check if we should process
                should_process = (
                    time_since_last >= self.config.debounce_seconds or
                    time_since_batch_start >= self.config.batch_interval_seconds
                )
                
                if should_process:
                    break
                
                # Wait a bit more
                wait_time = min(
                    self.config.debounce_seconds - time_since_last,
                    self.config.batch_interval_seconds - time_since_batch_start,
                    0.5,  # Check at least every 500ms
                )
                await asyncio.sleep(max(0.1, wait_time))
            
            # Process the changes
            await self._process_changes()
            
        finally:
            self._processing_scheduled = False
    
    async def _process_changes(self):
        """Process accumulated file changes, classifying each path by disk state.

        A path that exists and is indexable is (re)indexed; a path that is gone is
        removed. This is what makes the watcher immune to atomic-save event ordering:
        after a rename-replace the target exists -> indexed, the temp is gone ->
        removed (a harmless no-op since it was never indexed).
        """
        with self._lock:
            candidates = self._pending_files.copy()
            touched_dirs = self._touched_dirs.copy()
            self._pending_files.clear()
            self._touched_dirs.clear()
            self._batch_start_time = 0

        changed: Set[Path] = set()
        deleted: Set[Path] = set()
        for path in candidates:
            if path.exists():
                if path.is_file() and self._is_supported_file(path):
                    changed.add(path)
            else:
                deleted.add(path)

        if changed:
            logger.info(f"Processing {len(changed)} changed file(s)")
            try:
                self.on_files_changed(changed)
            except Exception as e:
                logger.error(f"Error processing changed files: {e}")

        if deleted:
            logger.info(f"Processing {len(deleted)} deleted file(s)")
            try:
                self.on_files_deleted(deleted)
            except Exception as e:
                logger.error(f"Error processing deleted files: {e}")

        # Safety net: reconcile touched directories against the index so files that
        # appeared without a usable per-file event (FSEvents coalescing) are caught.
        if touched_dirs and self.on_dirs_touched:
            try:
                self.on_dirs_touched(touched_dirs)
            except Exception as e:
                logger.error(f"Error reconciling touched directories: {e}")

    def _add_change(self, path: Path, is_delete: bool = False):
        """Record a path touched this batch. Classification happens at process time.

        ``is_delete`` is advisory only: we no longer maintain separate add/remove
        sets here (which let a co-batched delete discard a pending change). Instead
        every touched path is recorded and reconciled against disk in
        :meth:`_process_changes`.
        """
        if self._should_ignore(path):
            return

        if self._gitignore_matcher:
            self._gitignore_matcher.preload_ancestors(path)
            if self._gitignore_matcher.is_ignored(path):
                return

        is_dir = path.is_dir()
        if is_dir:
            if self._exclusion_policy.should_traverse_path(path).action != "index":
                return
        elif path.exists() and not self._is_supported_file(path):
            # An existing-but-unsupported file is never indexable. A non-existent
            # path (a delete) is still recorded so its index entry can be removed.
            return

        touched_dir = path if is_dir else path.parent
        now = time.time()

        with self._lock:
            self._last_event_time = now
            if self._batch_start_time == 0:
                self._batch_start_time = now
            if not is_dir:
                self._pending_files.add(path)
            self._touched_dirs.add(touched_dir)

        self._schedule_processing()
    
    def on_created(self, event):
        """Handle file/directory creation."""
        if isinstance(event, (FileCreatedEvent, DirCreatedEvent)):
            path = Path(event.src_path)
            logger.debug(f"Created: {path}")
            
            if isinstance(event, DirCreatedEvent):
                # For directories, we'll get individual file events
                pass
            else:
                self._add_change(path)
    
    def on_modified(self, event):
        """Handle file modification."""
        if isinstance(event, FileModifiedEvent):
            path = Path(event.src_path)
            logger.debug(f"Modified: {path}")
            self._add_change(path)
    
    def on_deleted(self, event):
        """Handle file/directory deletion."""
        if isinstance(event, (FileDeletedEvent, DirDeletedEvent)):
            path = Path(event.src_path)
            logger.debug(f"Deleted: {path}")
            self._add_change(path, is_delete=True)
    
    def on_moved(self, event):
        """Handle file/directory move."""
        if isinstance(event, (FileMovedEvent, DirMovedEvent)):
            src_path = Path(event.src_path)
            dest_path = Path(event.dest_path)
            logger.debug(f"Moved: {src_path} -> {dest_path}")
            
            # Treat as delete + create
            self._add_change(src_path, is_delete=True)
            if not isinstance(event, DirMovedEvent):
                self._add_change(dest_path)


class FileWatcher:
    """
    File watcher that monitors a directory for changes and triggers re-indexing.
    
    Implements single-process ownership via file-based locking. Only one process
    can actively watch a directory at a time. If the owning process dies, the OS
    automatically releases the lock, allowing another process to take over.
    """
    
    # Directory for lock files
    LOCK_DIR = Path("/tmp/mcp-vectors-locks")
    
    def __init__(
        self,
        watch_dir: Path,
        index_callback: Callable[[list[Path]], asyncio.Future],
        delete_callback: Callable[[list[Path]], asyncio.Future],
        reconcile_callback: Optional[Callable[[list[Path]], asyncio.Future]] = None,
        excluded_extensions: Optional[Set[str]] = None,
        excluded_directories: Optional[Set[str]] = None,
        debounce_seconds: float = 2.0,
        batch_interval_seconds: float = 10.0,
        respect_gitignore: bool = True,
    ):
        """
        Initialize the file watcher.

        Args:
            watch_dir: Directory to watch
            index_callback: Async function to call when files need indexing
            delete_callback: Async function to call when files are deleted
            reconcile_callback: Optional async function called with touched directories,
                used as a safety net to reconcile them against the index
            excluded_extensions: Set of file extensions to exclude (uses defaults if None)
            excluded_directories: Set of directory names to exclude (uses defaults if None)
            debounce_seconds: Wait time after last change before processing
            batch_interval_seconds: Maximum time to batch changes
        """
        self.watch_dir = watch_dir
        self.index_callback = index_callback
        self.delete_callback = delete_callback
        self.reconcile_callback = reconcile_callback
        
        self.config = WatcherConfig(
            watch_dir=watch_dir,
            excluded_extensions=set(ext.lower() for ext in (excluded_extensions or DEFAULT_EXCLUDED_EXTENSIONS)),
            excluded_directories=set(excluded_directories or DEFAULT_EXCLUDED_DIRECTORIES),
            debounce_seconds=debounce_seconds,
            batch_interval_seconds=batch_interval_seconds,
            respect_gitignore=respect_gitignore,
        )
        
        self._observer: Optional[Observer] = None
        self._handler: Optional[IndexEventHandler] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock_file: Optional[object] = None
        self._has_lock = False
        # Track in-flight asyncio Tasks so stop() can cancel+await them.
        self._pending_tasks: set[asyncio.Task] = set()
    
    def _get_lock_path(self) -> Path:
        """Get the lock file path for this watch directory."""
        # Create a unique lock file name based on the watch directory path
        dir_hash = hashlib.md5(str(self.watch_dir.resolve()).encode()).hexdigest()[:12]
        return self.LOCK_DIR / f"watcher-{dir_hash}.lock"
    
    def _is_pid_alive(self, pid: int) -> bool:
        """
        Check if a process with the given PID is still running.
        
        Args:
            pid: Process ID to check
            
        Returns:
            True if process exists, False otherwise
        """
        try:
            os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence
            return True
        except OSError:
            return False
    
    def _check_and_cleanup_stale_lock(self) -> bool:
        """
        Check if the existing lock file is stale (owner process died).
        
        If the lock is stale, removes the lock file so a new lock can be acquired.
        
        Returns:
            True if lock was stale and cleaned up, False otherwise
        """
        lock_path = self._get_lock_path()
        
        if not lock_path.exists():
            return False
        
        try:
            with open(lock_path, "r") as f:
                content = f.read().strip()
                if not content:
                    # Empty lock file - consider it stale
                    logger.info(f"Removing empty lock file: {lock_path}")
                    lock_path.unlink()
                    return True
                
                lines = content.split('\n')
                if not lines:
                    return False
                
                try:
                    old_pid = int(lines[0])
                except ValueError:
                    # Malformed lock file
                    logger.warning(f"Malformed lock file (invalid PID), removing: {lock_path}")
                    lock_path.unlink()
                    return True
                
                # Check if the process is still alive
                if not self._is_pid_alive(old_pid):
                    logger.info(f"Stale lock detected (PID {old_pid} is dead), cleaning up: {lock_path}")
                    try:
                        lock_path.unlink()
                        return True
                    except OSError as e:
                        logger.warning(f"Failed to remove stale lock file: {e}")
                        return False
                else:
                    logger.debug(f"Lock held by active process PID {old_pid}")
                    return False
                    
        except (IOError, OSError) as e:
            logger.warning(f"Error checking lock file: {e}")
            return False
    
    def _acquire_lock(self) -> bool:
        """
        Attempt to acquire exclusive lock for this watch directory.
        
        First checks if any existing lock is stale (owner process died) and
        cleans it up before attempting to acquire.
        
        Returns:
            True if lock acquired, False if another process owns it
        """
        try:
            # Ensure lock directory exists
            self.LOCK_DIR.mkdir(parents=True, exist_ok=True)
            
            # Check for and clean up stale locks from dead processes
            self._check_and_cleanup_stale_lock()
            
            lock_path = self._get_lock_path()
            
            # IMPORTANT: Use "a" (append) mode to avoid truncating an existing lock file!
            # If we used "w", we would truncate the file before trying flock, which would
            # destroy the PID info even if another process holds the lock. This would cause
            # the stale lock detection to see an empty file and incorrectly remove it.
            self._lock_file = open(lock_path, "a+")
            
            # Try to acquire exclusive non-blocking lock
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Successfully acquired lock - now truncate and write our PID
            self._lock_file.seek(0)
            self._lock_file.truncate()
            self._lock_file.write(f"{os.getpid()}\n{self.watch_dir}\n")
            self._lock_file.flush()
            
            self._has_lock = True
            logger.info(f"Acquired watcher lock for: {self.watch_dir}")
            return True
            
        except (BlockingIOError, OSError) as e:
            # Lock is held by another process
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            logger.debug(f"Watcher lock already held for: {self.watch_dir} ({e})")
            return False
    
    def _release_lock(self):
        """Release the lock if we hold it."""
        if self._lock_file:
            try:
                if self._has_lock:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                logger.info(f"Released watcher lock for: {self.watch_dir}")
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")
            finally:
                self._lock_file = None
                self._has_lock = False
    
    def _track_task(self, task: asyncio.Task) -> None:
        """Register a task for stop()-time drain and auto-remove on completion."""
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    def _on_files_changed(self, paths: Set[Path]):
        """Handle changed files by scheduling index callback."""
        if self._loop is None:
            return

        async def do_index():
            try:
                await self.index_callback(list(paths))
            except Exception as e:
                logger.error(f"Index callback failed: {e}")

        def _schedule():
            task = asyncio.create_task(do_index())
            self._track_task(task)

        self._loop.call_soon_threadsafe(_schedule)

    def _on_files_deleted(self, paths: Set[Path]):
        """Handle deleted files by scheduling delete callback."""
        if self._loop is None:
            return

        async def do_delete():
            try:
                await self.delete_callback(list(paths))
            except Exception as e:
                logger.error(f"Delete callback failed: {e}")

        def _schedule():
            task = asyncio.create_task(do_delete())
            self._track_task(task)

        self._loop.call_soon_threadsafe(_schedule)

    def _on_dirs_touched(self, dirs: Set[Path]):
        """Reconcile touched directories against the index, if a callback is set."""
        if self._loop is None or self.reconcile_callback is None:
            return

        async def do_reconcile():
            try:
                await self.reconcile_callback(list(dirs))
            except Exception as e:
                logger.error(f"Reconcile callback failed: {e}")

        def _schedule():
            task = asyncio.create_task(do_reconcile())
            self._track_task(task)

        self._loop.call_soon_threadsafe(_schedule)
    
    def start(self, loop: asyncio.AbstractEventLoop) -> bool:
        """
        Start watching for file changes.
        
        Uses file-based locking to ensure only one process watches each directory.
        If another process already holds the lock, this method returns False and
        the watcher is not started.
        
        Args:
            loop: The asyncio event loop for callbacks
            
        Returns:
            True if watcher started successfully, False if lock not acquired
        """
        if self._running:
            logger.warning("Watcher is already running")
            return True
        
        if not self.watch_dir.exists():
            logger.error(f"Watch directory does not exist: {self.watch_dir}")
            return False
        exclusion_policy = ExclusionPolicy(excluded_directories=self.config.excluded_directories)
        decision = exclusion_policy.should_traverse_path(self.watch_dir)
        if decision.action != "index":
            logger.warning(f"Watch directory skipped by exclusion policy: {self.watch_dir}")
            return False

        # Try to acquire exclusive lock
        if not self._acquire_lock():
            logger.debug(f"Another process is watching: {self.watch_dir}")
            return False
        
        self._loop = loop
        
        self._handler = IndexEventHandler(
            config=self.config,
            on_files_changed=self._on_files_changed,
            on_files_deleted=self._on_files_deleted,
            on_dirs_touched=self._on_dirs_touched if self.reconcile_callback else None,
        )
        self._handler.set_event_loop(loop)
        
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.watch_dir),
            recursive=True,
        )
        
        self._observer.start()
        self._running = True
        
        logger.info(f"Started watching: {self.watch_dir}")
        logger.info(f"Debounce: {self.config.debounce_seconds}s, Batch interval: {self.config.batch_interval_seconds}s")
        return True
    
    async def stop(self) -> None:
        """Stop watching for file changes, drain in-flight tasks, and release the lock."""
        if not self._running:
            return

        if self._observer:
            self._observer.stop()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._observer.join(timeout=5.0)
            )
            self._observer = None

        # Cancel and await all in-flight index/delete/reconcile tasks so that
        # callers waiting on stop() see a fully quiesced state (no background work
        # touching the index after stop() returns).
        pending = list(self._pending_tasks)
        if pending:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        self._pending_tasks.clear()

        self._handler = None
        self._running = False
        self._loop = None

        # Release the lock so another process can take over
        self._release_lock()

        logger.info("File watcher stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running
    
    @property
    def has_lock(self) -> bool:
        """Check if this watcher holds the lock."""
        return self._has_lock

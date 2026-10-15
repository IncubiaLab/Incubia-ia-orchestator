"""SQLite-backed inbox/outbox ledger for the single-host stage-2 pilot."""
import fcntl
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import ConversationTurn, ExecutionScope
from incubia_orchestrator.modules.identity_tenant.domain.principal import Membership, Role
from incubia_orchestrator.modules.identity_tenant.ports.identity import TrustedBinding
from incubia_orchestrator.modules.conversation.ports.ledger import (
    ClaimConflict, ClaimToken, ConversationCommit, IdempotencyConflict, InboxReservation,
    PendingInboxEvent, RevisionConflict, ScopeConflict, conversation_claim_key,
)

class RunnerAlreadyActive(RuntimeError): pass


class SqliteLedger:
    """Durable ledger whose transactions never contain provider calls."""
    def __init__(self, path: Path, *, acquire_runner_lock: bool = False):
        self.path, self._lock_fd = path, None
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if acquire_runner_lock:
            self._acquire_lock()
        self._connection = sqlite3.connect(path, timeout=5, isolation_level=None)
        for pragma in ("journal_mode=WAL", "synchronous=FULL", "foreign_keys=ON", "busy_timeout=5000"):
            self._connection.execute(f"PRAGMA {pragma}")
        self._migrate()

    def _acquire_lock(self):
        fd = os.open(f"{self.path}.runner.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd); raise RunnerAlreadyActive("A runner already owns this ledger") from None
        self._lock_fd = fd

    @contextmanager
    def _transaction(self):
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._connection.execute("ROLLBACK"); raise
        else: self._connection.execute("COMMIT")

    def _migrate(self):
        self._connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
        if not self._connection.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            self._connection.executescript("""
CREATE TABLE bindings (channel TEXT NOT NULL,channel_account_ref TEXT NOT NULL,external_chat_ref TEXT NOT NULL,external_sender_ref TEXT NOT NULL,deployment_id TEXT NOT NULL,tenant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,actor_id TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(channel,channel_account_ref,external_chat_ref,external_sender_ref));
CREATE TABLE inbox_events (deployment_id TEXT NOT NULL,tenant_id TEXT NOT NULL,channel TEXT NOT NULL,channel_account_ref TEXT NOT NULL,external_event_id TEXT NOT NULL,payload_hash TEXT NOT NULL,payload_json TEXT,request_id TEXT NOT NULL,execution_id TEXT NOT NULL UNIQUE,state TEXT NOT NULL,received_at TEXT NOT NULL,terminal_at TEXT,PRIMARY KEY(deployment_id,tenant_id,channel,channel_account_ref,external_event_id));
CREATE TABLE conversations (deployment_id TEXT NOT NULL,tenant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,actor_id TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,facts_json TEXT NOT NULL DEFAULT '[]',PRIMARY KEY(deployment_id,tenant_id,conversation_id,actor_id));
CREATE TABLE turns (execution_id TEXT PRIMARY KEY,deployment_id TEXT NOT NULL,tenant_id TEXT NOT NULL,conversation_id TEXT NOT NULL,user_text TEXT NOT NULL,assistant_text TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE outcomes (execution_id TEXT PRIMARY KEY,outcome_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE deliveries (execution_id TEXT NOT NULL,response_id TEXT NOT NULL,destination_ref TEXT NOT NULL,payload_json TEXT,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_attempt_at TEXT,external_message_id TEXT,created_at TEXT NOT NULL,PRIMARY KEY(execution_id,response_id,destination_ref));
CREATE TABLE runner_state (channel_account_ref TEXT PRIMARY KEY,last_offset INTEGER NOT NULL DEFAULT 0);
INSERT INTO schema_migrations(version) VALUES (1);""")
        if not self._connection.execute("SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
            self._connection.executescript("""
CREATE TABLE discarded_updates (channel_account_ref TEXT NOT NULL,external_event_id TEXT NOT NULL,payload_hash TEXT NOT NULL,reason TEXT NOT NULL,received_at TEXT NOT NULL,PRIMARY KEY(channel_account_ref,external_event_id));
INSERT INTO schema_migrations(version) VALUES (2);""")
        if not self._connection.execute("SELECT 1 FROM schema_migrations WHERE version=3").fetchone():
            self._connection.executescript("""
ALTER TABLE turns ADD COLUMN actor_id TEXT NOT NULL DEFAULT '';
INSERT INTO schema_migrations(version) VALUES (3);""")
        if not self._connection.execute("SELECT 1 FROM schema_migrations WHERE version=4").fetchone():
            self._connection.executescript("""
CREATE TABLE dispatcher_claims (
    channel TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    lease_until TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(channel, account_ref)
);
CREATE INDEX dispatcher_claims_expiry_idx ON dispatcher_claims(lease_until);
INSERT INTO schema_migrations(version) VALUES (4);""")
            self._connection.executescript("""
CREATE TABLE resource_claims (
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    lease_until TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(deployment_id, tenant_id, resource_type, resource_key)
);
CREATE INDEX resource_claims_expiry_idx ON resource_claims(deployment_id, tenant_id, lease_until);""")
        if not self._connection.execute("SELECT 1 FROM schema_migrations WHERE version=5").fetchone():
            self._connection.executescript("""
CREATE TABLE memberships (
    deployment_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('actor', 'operator', 'admin')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    PRIMARY KEY (deployment_id, tenant_id, subject_id)
);
CREATE INDEX memberships_subject_idx ON memberships(deployment_id, subject_id, active);
INSERT OR IGNORE INTO memberships (deployment_id,tenant_id,subject_id,role,active)
SELECT deployment_id,tenant_id,actor_id,'actor',1 FROM bindings;
INSERT INTO schema_migrations(version) VALUES (5);""")

    @staticmethod
    def _hash(payload): return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    @staticmethod
    def _now(): return datetime.now(UTC).isoformat()

    def add_binding(self, *, channel, account, chat, sender, deployment_id, tenant_id,
                    conversation_id, actor_id):
        with self._transaction():
            self._connection.execute(
                "INSERT OR REPLACE INTO bindings VALUES (?,?,?,?,?,?,?,?,1)",
                (channel, account, chat, sender, deployment_id, tenant_id,
                 conversation_id, actor_id),
            )
            # Existing binding files are an administrative provisioning input.
            # Create the least-privileged membership only when absent; an
            # explicit revocation must not be silently undone by every runner
            # restart.
            self._connection.execute(
                "INSERT OR IGNORE INTO memberships "
                "(deployment_id,tenant_id,subject_id,role,active) VALUES (?,?,?,?,1)",
                (deployment_id, tenant_id, actor_id, Role.ACTOR.value),
            )

    def resolve_binding(self, *, channel, account, chat, sender):
        binding = self.resolve(channel=channel, account=account, chat=chat, sender=sender)
        return ((binding.deployment_id, binding.tenant_id, binding.conversation_id, binding.actor_id)
                if binding is not None else None)

    def resolve(self, *, channel, account, chat, sender):
        row = self._connection.execute(
            "SELECT deployment_id,tenant_id,conversation_id,actor_id FROM bindings "
            "WHERE channel=? AND channel_account_ref=? AND external_chat_ref=? "
            "AND external_sender_ref=? AND enabled=1",
            (channel, account, chat, sender),
        ).fetchone()
        return TrustedBinding(*row) if row is not None else None

    def get(self, deployment_id: str, tenant_id: str, subject_id: str) -> Membership | None:
        row = self._connection.execute(
            "SELECT deployment_id,tenant_id,subject_id,role,active FROM memberships "
            "WHERE deployment_id=? AND tenant_id=? AND subject_id=?",
            (deployment_id, tenant_id, subject_id),
        ).fetchone()
        if row is None:
            return None
        return Membership(row[0], row[1], row[2], Role(row[3]), bool(row[4]))

    def upsert_membership(self, *, deployment_id: str, tenant_id: str, subject_id: str,
                          role: Role | str = Role.ACTOR, active: bool = True) -> Membership:
        role = Role(role)
        with self._transaction():
            self._connection.execute(
                "INSERT INTO memberships(deployment_id,tenant_id,subject_id,role,active) "
                "VALUES (?,?,?,?,?) ON CONFLICT(deployment_id,tenant_id,subject_id) "
                "DO UPDATE SET role=excluded.role, active=excluded.active",
                (deployment_id, tenant_id, subject_id, role.value, int(active)),
            )
        return Membership(deployment_id, tenant_id, subject_id, role, active)

    def revoke_membership(self, *, deployment_id: str, tenant_id: str,
                          subject_id: str) -> bool:
        with self._transaction():
            return self._connection.execute(
                "UPDATE memberships SET active=0 WHERE deployment_id=? AND tenant_id=? "
                "AND subject_id=? AND active=1",
                (deployment_id, tenant_id, subject_id),
            ).rowcount == 1

    def revoke_binding(self, *, channel: str, account: str, chat: str, sender: str) -> bool:
        with self._transaction():
            return self._connection.execute(
                "UPDATE bindings SET enabled=0 WHERE channel=? AND channel_account_ref=? "
                "AND external_chat_ref=? AND external_sender_ref=? AND enabled=1",
                (channel, account, chat, sender),
            ).rowcount == 1

    def advance_offset(self, account, offset):
        with self._transaction():
            self._connection.execute("INSERT INTO runner_state(channel_account_ref,last_offset) VALUES (?,?) ON CONFLICT(channel_account_ref) DO UPDATE SET last_offset=MAX(last_offset,excluded.last_offset)", (account,offset))

    def last_offset(self, account):
        row = self._connection.execute("SELECT last_offset FROM runner_state WHERE channel_account_ref=?", (account,)).fetchone()
        return row[0] if row else 0

    def accept_update(self, account, update_id, payload, *, binding=None):
        """Persist one update and its polling cursor in the same transaction."""
        with self._transaction():
            existing = self._connection.execute("SELECT last_offset FROM runner_state WHERE channel_account_ref=?", (account,)).fetchone()
            if existing and update_id <= existing[0]:
                return None
            if binding is not None:
                deployment, tenant, _, _ = binding
                event_key = (deployment, tenant, "telegram", account, str(update_id))
                digest = self._hash(payload)
                row = self._connection.execute("SELECT payload_hash,request_id,execution_id,state FROM inbox_events WHERE deployment_id=? AND tenant_id=? AND channel=? AND channel_account_ref=? AND external_event_id=?", event_key).fetchone()
                if row and row[0] != digest:
                    raise IdempotencyConflict("Same event key has a different payload")
                if row:
                    reservation = InboxReservation(row[1], row[2], row[3], False)
                else:
                    request_id, execution_id = str(uuid4()), str(uuid4())
                    self._connection.execute("INSERT INTO inbox_events VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)", (*event_key, digest, json.dumps(payload, sort_keys=True), request_id, execution_id, "RECEIVED", self._now()))
                    reservation = InboxReservation(request_id, execution_id, "RECEIVED", True)
            else:
                self._connection.execute("INSERT OR IGNORE INTO discarded_updates VALUES (?,?,?,?,?)", (account, str(update_id), self._hash(payload), "UNBOUND_OR_UNSUPPORTED", self._now()))
                reservation = None
            self._connection.execute("INSERT INTO runner_state(channel_account_ref,last_offset) VALUES (?,?) ON CONFLICT(channel_account_ref) DO UPDATE SET last_offset=MAX(last_offset,excluded.last_offset)", (account, update_id))
            return reservation

    def pending_events(self, account):
        return self._connection.execute("SELECT execution_id,payload_json FROM inbox_events WHERE channel='telegram' AND channel_account_ref=? AND state='RECEIVED' ORDER BY received_at,external_event_id", (account,)).fetchall()

    def pending_inbox_events(self, account: str) -> tuple[PendingInboxEvent, ...]:
        rows = self._connection.execute(
            "SELECT request_id,execution_id,payload_json FROM inbox_events "
            "WHERE channel='telegram' AND channel_account_ref=? AND state='RECEIVED' "
            "ORDER BY received_at,external_event_id", (account,)).fetchall()
        return tuple(PendingInboxEvent(*row) for row in rows)

    def conversation_history(self, scope: ExecutionScope, *, limit: int = 20) -> tuple[ConversationTurn, ...]:
        if limit < 1:
            raise ValueError("History limit must be positive")
        rows = self._connection.execute(
            "SELECT user_text, assistant_text, created_at, execution_id FROM ("
            "SELECT user_text, assistant_text, created_at, execution_id FROM turns "
            "WHERE deployment_id=? AND tenant_id=? AND conversation_id=? AND actor_id=? "
            "ORDER BY created_at DESC, execution_id DESC LIMIT ?"
            ") recent ORDER BY created_at, execution_id",
            (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id, limit),
        ).fetchall()
        return tuple(ConversationTurn(row[0], row[1]) for row in rows)

    def pending_deliveries(self):
        return self._connection.execute("SELECT execution_id,response_id,destination_ref,payload_json FROM deliveries WHERE state='PENDING' ORDER BY created_at", ()).fetchall()

    def mark_delivery_unknown(self, execution_id, response_id, destination_ref):
        with self._transaction():
            self._connection.execute("UPDATE deliveries SET state='UNKNOWN_EFFECT' WHERE execution_id=? AND response_id=? AND destination_ref=? AND state='SENDING'", (execution_id,response_id,destination_ref))

    def mark_delivery_failed(self, execution_id, response_id, destination_ref, *, next_attempt_at=None):
        with self._transaction():
            self._connection.execute("UPDATE deliveries SET state='FAILED',next_attempt_at=? WHERE execution_id=? AND response_id=? AND destination_ref=? AND state='SENDING'", (next_attempt_at,execution_id,response_id,destination_ref))

    def inspect(self):
        events = self._connection.execute("SELECT execution_id FROM inbox_events WHERE state='NEEDS_INSPECTION'").fetchall()
        deliveries = self._connection.execute("SELECT execution_id,response_id,destination_ref FROM deliveries WHERE state='UNKNOWN_EFFECT'").fetchall()
        return {"events": events, "deliveries": deliveries}

    def reserve_inbox(self, deployment_id, tenant_id, account, event_id, payload, *, channel="telegram"):
        key, digest = (deployment_id, tenant_id, channel, account, event_id), self._hash(payload)
        with self._transaction():
            row = self._connection.execute("SELECT payload_hash,request_id,execution_id,state FROM inbox_events WHERE deployment_id=? AND tenant_id=? AND channel=? AND channel_account_ref=? AND external_event_id=?", key).fetchone()
            if row:
                if row[0] != digest: raise IdempotencyConflict("Same event key has a different payload")
                return InboxReservation(row[1], row[2], row[3], False)
            request_id, execution_id = str(uuid4()), str(uuid4())
            self._connection.execute("INSERT INTO inbox_events VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)", (*key, digest, json.dumps(payload, sort_keys=True), request_id, execution_id, "RECEIVED", self._now()))
            return InboxReservation(request_id, execution_id, "RECEIVED", True)

    def _acquire_resource_claim(self, scope, resource_type, resource_key, owner_id, lease_seconds):
        seconds = self._lease_seconds(lease_seconds)
        if not resource_type or not resource_key or not owner_id:
            raise ValueError("Claim resource, owner, and positive lease are required")
        now = datetime.now(UTC)
        now_text = now.isoformat()
        lease_text = datetime.fromtimestamp(now.timestamp() + seconds, UTC).isoformat()
        row = self._connection.execute(
            "SELECT owner_id,generation,lease_until FROM resource_claims "
            "WHERE deployment_id=? AND tenant_id=? AND resource_type=? AND resource_key=?",
            (scope.deployment_id, scope.tenant_id, resource_type, resource_key),
        ).fetchone()
        if row is None:
            generation = 1
            self._connection.execute(
                "INSERT INTO resource_claims VALUES (?,?,?,?,?,?,?,?)",
                (scope.deployment_id, scope.tenant_id, resource_type, resource_key,
                 owner_id, generation, lease_text, now_text),
            )
        else:
            current_owner, current_generation, current_lease = row
            if current_lease > now_text and current_owner != owner_id:
                return None
            generation = current_generation if current_owner == owner_id else current_generation + 1
            self._connection.execute(
                "UPDATE resource_claims SET owner_id=?,generation=?,lease_until=?,updated_at=? "
                "WHERE deployment_id=? AND tenant_id=? AND resource_type=? AND resource_key=?",
                (owner_id, generation, lease_text, now_text, scope.deployment_id,
                 scope.tenant_id, resource_type, resource_key),
            )
        return ClaimToken(scope.deployment_id, scope.tenant_id, resource_type,
                          resource_key, owner_id, generation)

    def claim(self, execution_id, *, scope, owner_id, lease_seconds=60):
        with self._transaction():
            token = self._acquire_resource_claim(
                scope, "execution", execution_id, owner_id, lease_seconds
            )
            if token is None:
                return None
            changed = self._connection.execute(
                "UPDATE inbox_events SET state='PROCESSING' WHERE execution_id=? "
                "AND deployment_id=? AND tenant_id=? AND state='RECEIVED'",
                (execution_id, scope.deployment_id, scope.tenant_id),
            ).rowcount == 1
            if not changed:
                self._expire_claim(token)
                return None
            return token

    def acquire_claim(self, scope, *, resource_type, resource_key, owner_id, lease_seconds=60):
        if resource_type == "execution":
            raise ValueError("Execution claims must be acquired through claim()")
        if resource_type == "conversation":
            resource_key = conversation_claim_key(scope)
        with self._transaction():
            return self._acquire_resource_claim(
                scope, resource_type, resource_key, owner_id, lease_seconds
            )

    def renew_claim(self, token, *, lease_seconds=60):
        seconds = self._lease_seconds(lease_seconds)
        now = datetime.now(UTC)
        lease_text = datetime.fromtimestamp(now.timestamp() + seconds, UTC).isoformat()
        with self._transaction():
            return self._connection.execute(
                "UPDATE resource_claims SET lease_until=?,updated_at=? "
                "WHERE deployment_id=? AND tenant_id=? AND resource_type=? AND resource_key=? "
                "AND owner_id=? AND generation=? AND lease_until>?",
                (lease_text, now.isoformat(), token.deployment_id, token.tenant_id,
                 token.resource_type, token.resource_key, token.owner_id,
                 token.generation, now.isoformat()),
            ).rowcount == 1

    def release_claim(self, token):
        with self._transaction():
            return self._connection.execute(
                "UPDATE resource_claims SET lease_until=?,updated_at=? "
                "WHERE deployment_id=? AND tenant_id=? AND resource_type=? AND resource_key=? "
                "AND owner_id=? AND generation=?",
                (self._now(), self._now(), token.deployment_id, token.tenant_id,
                 token.resource_type, token.resource_key, token.owner_id,
                 token.generation),
            ).rowcount == 1

    def _claim_is_current(self, token, scope, resource_type, resource_key):
        if (token.deployment_id, token.tenant_id, token.resource_type, token.resource_key) != (
                scope.deployment_id, scope.tenant_id, resource_type, resource_key):
            return False
        row = self._connection.execute(
            "SELECT 1 FROM resource_claims WHERE deployment_id=? AND tenant_id=? "
            "AND resource_type=? AND resource_key=? AND owner_id=? AND generation=? "
            "AND lease_until>?",
            (token.deployment_id, token.tenant_id, token.resource_type, token.resource_key,
             token.owner_id, token.generation, self._now()),
        ).fetchone()
        return row is not None

    def _expire_claim(self, token):
        self._connection.execute(
            "UPDATE resource_claims SET lease_until=?,updated_at=? "
            "WHERE deployment_id=? AND tenant_id=? AND resource_type=? AND resource_key=? "
            "AND owner_id=? AND generation=?",
            (self._now(), self._now(), token.deployment_id, token.tenant_id,
            token.resource_type, token.resource_key, token.owner_id, token.generation),
        )

    def return_to_received(self, execution_id, *, scope, claim_token):
        with self._transaction():
            if not self._claim_is_current(claim_token, scope, "execution", execution_id):
                return False
            changed = self._connection.execute(
                "UPDATE inbox_events SET state='RECEIVED' WHERE execution_id=? "
                "AND deployment_id=? AND tenant_id=? AND state='PROCESSING'",
                (execution_id, scope.deployment_id, scope.tenant_id),
            ).rowcount == 1
            if changed:
                self._expire_claim(claim_token)
            return changed

    def recover_interrupted(self, *, deployment_id, tenant_id):
        now = self._now()
        with self._transaction():
            return self._connection.execute(
                "UPDATE inbox_events SET state='RECEIVED' WHERE deployment_id=? AND tenant_id=? "
                "AND state='PROCESSING' AND EXISTS (SELECT 1 FROM resource_claims claim "
                "WHERE claim.deployment_id=inbox_events.deployment_id AND claim.tenant_id=inbox_events.tenant_id "
                "AND claim.resource_type='execution' AND claim.resource_key=inbox_events.execution_id "
                "AND claim.lease_until<=?)",
                (deployment_id, tenant_id, now),
            ).rowcount

    @staticmethod
    def _lease_seconds(value):
        if not 0 < value <= 300:
            raise ValueError("Claim lease must be between 0 and 300 seconds")
        return float(value)

    def acquire_dispatcher_claim(self, *, channel, account_ref, owner_id, lease_seconds=60):
        """Persist ownership for one channel account.

        SQLite uses this table instead of making the correctness of polling
        depend on the optional process lock. The lock remains available as a
        local operator safeguard, but the claim is the shared contract.
        """
        seconds = self._lease_seconds(lease_seconds)
        if not channel or not account_ref or not owner_id:
            raise ValueError("Dispatcher channel, account, and owner are required")
        now = datetime.now(UTC)
        lease_until = (now.timestamp() + seconds)
        now_text, lease_text = now.isoformat(), datetime.fromtimestamp(lease_until, UTC).isoformat()
        with self._transaction():
            row = self._connection.execute(
                "SELECT owner_id,generation,lease_until FROM dispatcher_claims "
                "WHERE channel=? AND account_ref=?", (channel, account_ref)
            ).fetchone()
            if row is None:
                generation = 1
                self._connection.execute(
                    "INSERT INTO dispatcher_claims(channel,account_ref,owner_id,generation,lease_until,updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (channel, account_ref, owner_id, generation, lease_text, now_text),
                )
            else:
                current_owner, current_generation, current_lease = row
                if current_lease > now_text and current_owner != owner_id:
                    return None
                generation = current_generation if current_owner == owner_id else current_generation + 1
                self._connection.execute(
                    "UPDATE dispatcher_claims SET owner_id=?,generation=?,lease_until=?,updated_at=? "
                    "WHERE channel=? AND account_ref=?",
                    (owner_id, generation, lease_text, now_text, channel, account_ref),
                )
        return ClaimToken("", "", "dispatcher", f"{channel}:{account_ref}", owner_id, generation)

    def renew_dispatcher_claim(self, token, *, lease_seconds=60):
        if token.resource_type != "dispatcher" or ":" not in token.resource_key:
            return False
        seconds = self._lease_seconds(lease_seconds)
        channel, account_ref = token.resource_key.split(":", 1)
        now = datetime.now(UTC)
        lease_text = datetime.fromtimestamp(now.timestamp() + seconds, UTC).isoformat()
        with self._transaction():
            return self._connection.execute(
                "UPDATE dispatcher_claims SET lease_until=?,updated_at=? "
                "WHERE channel=? AND account_ref=? AND owner_id=? AND generation=? "
                "AND lease_until>?",
                (lease_text, now.isoformat(), channel, account_ref, token.owner_id,
                 token.generation, now.isoformat()),
            ).rowcount == 1

    def release_dispatcher_claim(self, token):
        if token.resource_type != "dispatcher" or ":" not in token.resource_key:
            return False
        channel, account_ref = token.resource_key.split(":", 1)
        now = self._now()
        with self._transaction():
            return self._connection.execute(
                "UPDATE dispatcher_claims SET lease_until=?,updated_at=? "
                "WHERE channel=? AND account_ref=? AND owner_id=? AND generation=?",
                (now, now, channel, account_ref, token.owner_id, token.generation),
            ).rowcount == 1

    def complete(self, execution_id, response_id, destination_ref, public_payload, *, outcome=None, turn=None):
        with self._transaction():
            event = self._connection.execute("SELECT deployment_id,tenant_id FROM inbox_events WHERE execution_id=? AND state='PROCESSING'", (execution_id,)).fetchone()
            if event is None: raise RuntimeError("Only a claimed event can complete")
            now = self._now()
            if outcome is not None: self._connection.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?)", (execution_id, json.dumps(outcome, sort_keys=True), now))
            if turn is not None: self._connection.execute("INSERT OR IGNORE INTO turns VALUES (?,?,?,?,?,?,?)", (execution_id,event[0],event[1],"",turn[0],turn[1],now))
            self._connection.execute("INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?, 'PENDING',0,NULL,NULL,?)", (execution_id,response_id,destination_ref,json.dumps(public_payload, sort_keys=True),now))
            self._connection.execute("UPDATE inbox_events SET state='COMPLETED',terminal_at=? WHERE execution_id=?", (now,execution_id))

    def conversation_revision(self, scope) -> int:
        row = self._connection.execute(
            "SELECT revision FROM conversations WHERE deployment_id=? AND tenant_id=? "
            "AND conversation_id=? AND actor_id=?",
            (scope.deployment_id, scope.tenant_id, scope.conversation_id, scope.actor_id),
        ).fetchone()
        return row[0] if row else 0

    def commit_conversation(self, commit: ConversationCommit) -> int:
        """Atomically finish a claimed event and its canonical conversation turn."""
        with self._transaction():
            event = self._connection.execute(
                "SELECT deployment_id,tenant_id FROM inbox_events WHERE execution_id=? AND state='PROCESSING'",
                (commit.execution_id,),
            ).fetchone()
            if event is None:
                raise RuntimeError("Only a claimed event can complete")
            if event != (commit.scope.deployment_id, commit.scope.tenant_id):
                raise ScopeConflict("Execution scope does not match the accepted event")
            execution_claims = [
                claim for claim in commit.claim_tokens if claim.resource_type == "execution"
            ]
            conversation_claims = [
                claim for claim in commit.claim_tokens if claim.resource_type == "conversation"
            ]
            conversation_key = (
                f"{len(commit.scope.conversation_id)}:"
                f"{commit.scope.conversation_id}{commit.scope.actor_id}"
            )
            # Keep the pre-E3-04 local call shape usable for existing callers.
            # The durable claims are still required: when a caller omits the
            # token tuple, recover the current execution owner and acquire its
            # conversation claim inside this same transaction.
            if not commit.claim_tokens:
                row = self._connection.execute(
                    "SELECT owner_id,generation FROM resource_claims WHERE deployment_id=? "
                    "AND tenant_id=? AND resource_type='execution' AND resource_key=? "
                    "AND lease_until>?",
                    (commit.scope.deployment_id, commit.scope.tenant_id,
                     commit.execution_id, self._now()),
                ).fetchone()
                if row is not None:
                    owner_id, generation = row
                    execution_claims = [ClaimToken(
                        commit.scope.deployment_id, commit.scope.tenant_id,
                        "execution", commit.execution_id, owner_id, generation,
                    )]
                    conversation_claim = self._acquire_resource_claim(
                        commit.scope, "conversation", conversation_key, owner_id, 60
                    )
                    if conversation_claim is not None:
                        conversation_claims = [conversation_claim]
            if (len(execution_claims) != 1 or len(conversation_claims) != 1
                    or (commit.claim_tokens and len(commit.claim_tokens) != 2)
                    or not self._claim_is_current(
                        execution_claims[0], commit.scope, "execution", commit.execution_id
                    )
                    or not self._claim_is_current(
                        conversation_claims[0], commit.scope, "conversation", conversation_key
                )):
                raise ClaimConflict("Conversation commit has no current fencing claims")
            current = self.conversation_revision(commit.scope)
            if current != commit.expected_revision:
                raise RevisionConflict("Conversation revision changed")
            now = self._now()
            self._connection.execute(
                "INSERT OR IGNORE INTO conversations "
                "(deployment_id,tenant_id,conversation_id,actor_id,revision,facts_json) VALUES (?,?,?,?,0,'[]')",
                (commit.scope.deployment_id, commit.scope.tenant_id,
                 commit.scope.conversation_id, commit.scope.actor_id),
            )
            updated = self._connection.execute(
                "UPDATE conversations SET revision=revision+1 WHERE deployment_id=? AND tenant_id=? "
                "AND conversation_id=? AND actor_id=? AND revision=?",
                (commit.scope.deployment_id, commit.scope.tenant_id, commit.scope.conversation_id,
                 commit.scope.actor_id, commit.expected_revision),
            ).rowcount
            if updated != 1:
                raise RevisionConflict("Conversation revision changed")
            self._connection.execute("INSERT INTO outcomes VALUES (?,?,?)", (commit.execution_id,
                                     json.dumps(commit.outcome, sort_keys=True), now))
            self._connection.execute(
                "INSERT INTO turns (execution_id,deployment_id,tenant_id,conversation_id,user_text,assistant_text,created_at,actor_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (commit.execution_id, commit.scope.deployment_id, commit.scope.tenant_id,
                 commit.scope.conversation_id, commit.turn.user, commit.turn.assistant, now,
                 commit.scope.actor_id),
            )
            self._connection.execute("INSERT INTO deliveries VALUES (?,?,?,?, 'PENDING',0,NULL,NULL,?)",
                                     (commit.execution_id, commit.response_id, commit.destination_ref,
                                      json.dumps(commit.public_payload, sort_keys=True), now))
            self._connection.execute("UPDATE inbox_events SET state='COMPLETED',terminal_at=? WHERE execution_id=?",
                                     (now, commit.execution_id))
            self._expire_claim(execution_claims[0])
            self._expire_claim(conversation_claims[0])
            return commit.expected_revision + 1

    def recover(self):
        with self._transaction():
            self._connection.execute(
                "UPDATE inbox_events SET state='RECEIVED' WHERE state='PROCESSING' "
                "AND EXISTS (SELECT 1 FROM resource_claims claim "
                "WHERE claim.deployment_id=inbox_events.deployment_id "
                "AND claim.tenant_id=inbox_events.tenant_id "
                "AND claim.resource_type='execution' "
                "AND claim.resource_key=inbox_events.execution_id "
                "AND claim.lease_until<=?)",
                (self._now(),),
            )
            self._connection.execute("UPDATE deliveries SET state='UNKNOWN_EFFECT' WHERE state='SENDING'")

    def reserve_delivery(self, execution_id, response_id, destination_ref):
        with self._transaction(): return self._connection.execute("UPDATE deliveries SET state='SENDING',attempts=attempts+1 WHERE execution_id=? AND response_id=? AND destination_ref=? AND state='PENDING'", (execution_id,response_id,destination_ref)).rowcount == 1
    def mark_delivery_sent(self, execution_id, response_id, destination_ref, external_message_id):
        with self._transaction(): return self._connection.execute("UPDATE deliveries SET state='SENT',external_message_id=? WHERE execution_id=? AND response_id=? AND destination_ref=? AND state='SENDING'", (external_message_id,execution_id,response_id,destination_ref)).rowcount == 1
    def delivery_state(self, execution_id, response_id, destination_ref):
        row=self._connection.execute("SELECT state FROM deliveries WHERE execution_id=? AND response_id=? AND destination_ref=?",(execution_id,response_id,destination_ref)).fetchone()
        if row is None: raise KeyError("Unknown delivery")
        return row[0]
    def purge(self, *, payload_before, tombstone_before):
        with self._transaction():
            payloads=self._connection.execute("UPDATE inbox_events SET payload_json=NULL WHERE payload_json IS NOT NULL AND terminal_at IS NOT NULL AND terminal_at < ?",(payload_before.isoformat(),)).rowcount
            self._connection.execute("UPDATE deliveries SET payload_json=NULL WHERE payload_json IS NOT NULL AND state IN ('SENT','FAILED') AND created_at < ?",(payload_before.isoformat(),))
            tombstones=self._connection.execute("DELETE FROM inbox_events WHERE payload_json IS NULL AND terminal_at IS NOT NULL AND terminal_at < ?",(tombstone_before.isoformat(),)).rowcount
            return payloads,tombstones
    def backup_to(self, destination):
        """Create a consistent SQLite backup without copying a live WAL file."""
        target = sqlite3.connect(destination)
        try:
            self._connection.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("SQLite backup integrity check failed")
        finally:
            target.close()
    def close(self):
        self._connection.close()
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd,fcntl.LOCK_UN); os.close(self._lock_fd); self._lock_fd=None

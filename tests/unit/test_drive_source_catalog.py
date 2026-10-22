from datetime import datetime, timezone
from hashlib import sha256

import pytest

from incubia_orchestrator.modules.knowledge.domain import (
    AclState,
    ExportRequest,
    ExportResult,
    InventoryEntry,
    InventoryPage,
    SourceRef,
)
from incubia_orchestrator.modules.knowledge.ports import (
    DriveIdentityPort,
    DriveTransportPort,
    SourceCatalogPort,
    VerifiedIdentity,
)
from incubia_orchestrator.modules.knowledge.adapters.drive_catalog import (
    DriveCatalogConfig,
    DriveSourceCatalog,
)
from incubia_orchestrator.modules.knowledge.domain import (
    ExportTooLargeError,
    IdentityNotVerifiedError,
    InventoryLimitError,
    RootContainmentError,
    SourceCatalogError,
    UnsupportedExportError,
)
from tests.fakes.drive_transport import FakeDriveTransport


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ref(source_id="file-1", parents=("root",), **overrides):
    fields = dict(
        source_id=source_id,
        name="name",
        mime_type="application/vnd.google-apps.document",
        parents=parents,
        observed_version="v1",
        modified_time=NOW,
        size_bytes=10,
    )
    fields.update(overrides)
    return SourceRef(**fields)


# --- domain: SourceRef validation ---

def test_source_ref_requires_ids_mime_and_at_least_one_parent():
    ref()  # valid construction does not raise
    with pytest.raises(ValueError):
        ref(source_id="")
    with pytest.raises(ValueError):
        ref(name="")
    with pytest.raises(ValueError):
        ref(mime_type="")
    with pytest.raises(ValueError):
        ref(observed_version="")
    with pytest.raises(ValueError):
        ref(parents=())
    with pytest.raises(ValueError):
        ref(size_bytes=-1)


# --- domain: InventoryPage / InventoryEntry ---

def test_inventory_entry_defaults_acl_state_to_unknown():
    entry = InventoryEntry(ref=ref(), root_id="root", depth=1, classification="document")
    assert entry.acl_state == AclState.UNKNOWN


def test_inventory_entry_rejects_invalid_root_depth_or_classification():
    with pytest.raises(ValueError):
        InventoryEntry(ref=ref(), root_id="", depth=1, classification="document")
    with pytest.raises(ValueError):
        InventoryEntry(ref=ref(), root_id="root", depth=-1, classification="document")
    with pytest.raises(ValueError):
        InventoryEntry(ref=ref(), root_id="root", depth=1, classification="")


def test_inventory_page_holds_items_and_next_token():
    page = InventoryPage(items=(ref(),), next_page_token="tok")
    assert page.items == (ref(),)
    assert page.next_page_token == "tok"


# --- domain: ExportRequest / ExportResult ---

def test_export_request_requires_ids_mime_types_and_positive_max_bytes():
    ExportRequest(source_id="s1", mime_type="a", target_mime_type="b", max_bytes=10)
    with pytest.raises(ValueError):
        ExportRequest(source_id="", mime_type="a", target_mime_type="b", max_bytes=10)
    with pytest.raises(ValueError):
        ExportRequest(source_id="s1", mime_type="a", target_mime_type="b", max_bytes=0)


def test_export_result_rejects_truncated_true():
    ExportResult(source_id="s1", target_mime_type="text/markdown", content=b"x",
                 sha256="abc", truncated=False)
    with pytest.raises(ValueError):
        ExportResult(source_id="s1", target_mime_type="text/markdown", content=b"x",
                     sha256="abc", truncated=True)


# --- ports: Protocol shapes and VerifiedIdentity value ---

def test_verified_identity_requires_opaque_principal_digest():
    VerifiedIdentity(principal_digest="digest-abc", granted_scopes=("drive.readonly",))
    with pytest.raises(ValueError):
        VerifiedIdentity(principal_digest="", granted_scopes=())


def test_ports_declare_the_expected_methods():
    assert {"list_children", "get_metadata", "export"} <= set(dir(DriveTransportPort))
    assert "assert_verified" in dir(DriveIdentityPort)
    assert {"inventory", "export_document"} <= set(dir(SourceCatalogPort))


# --- adapter: DriveSourceCatalog ---

FOLDER_MIME = "application/vnd.google-apps.folder"


class AllowIdentity:
    def assert_verified(self):
        return VerifiedIdentity(principal_digest="digest", granted_scopes=("drive.readonly",))


class DenyIdentity:
    def assert_verified(self):
        raise RuntimeError("identity provider rejected the request")


class NoneIdentity:
    def assert_verified(self):
        return None


def folder_ref(source_id, parents, **overrides):
    return ref(source_id=source_id, parents=parents, mime_type=FOLDER_MIME, **overrides)


def test_inventory_denies_closed_and_makes_zero_transport_calls_when_identity_raises():
    transport = FakeDriveTransport({"root": (ref(parents=("root",)),)})
    catalog = DriveSourceCatalog(transport, DenyIdentity(), DriveCatalogConfig())
    with pytest.raises(IdentityNotVerifiedError):
        catalog.inventory("root")
    assert transport.list_calls == 0
    assert transport.metadata_calls == 0
    assert transport.export_calls == 0


def test_inventory_denies_closed_when_identity_returns_none():
    transport = FakeDriveTransport({"root": (ref(parents=("root",)),)})
    catalog = DriveSourceCatalog(transport, NoneIdentity(), DriveCatalogConfig())
    with pytest.raises(IdentityNotVerifiedError):
        catalog.inventory("root")
    assert transport.list_calls == 0


def test_export_document_denies_closed_and_makes_zero_transport_calls():
    transport = FakeDriveTransport({})
    catalog = DriveSourceCatalog(transport, DenyIdentity(), DriveCatalogConfig())
    entry = InventoryEntry(ref=ref(), root_id="root", depth=1, classification="document")
    with pytest.raises(IdentityNotVerifiedError):
        catalog.export_document(entry)
    assert transport.list_calls == 0
    assert transport.metadata_calls == 0
    assert transport.export_calls == 0


def test_inventory_follows_pagination_across_at_least_three_pages():
    children = tuple(ref(source_id=f"f{i}", parents=("root",)) for i in range(7))
    transport = FakeDriveTransport({"root": children}, page_size=3)
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert transport.list_calls == 3  # ceil(7 / 3)
    assert {entry.ref.source_id for entry in entries} == {c.source_id for c in children}


def test_root_containment_excludes_item_whose_parent_is_a_sibling_folder():
    sibling = folder_ref("sibling", parents=("grandparent",))
    stray = ref(source_id="stray-file", parents=("sibling",))
    transport = FakeDriveTransport({"root": (stray,)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert entries == ()


def test_root_containment_raises_when_item_claims_root_but_also_escapes():
    escaping = ref(source_id="multi-parent", parents=("root", "sibling-folder"))
    transport = FakeDriveTransport({"root": (escaping,)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    with pytest.raises(RootContainmentError):
        catalog.inventory("root")


def test_visited_set_terminates_a_parent_cycle_between_two_folders():
    folder_a = folder_ref("folder-a", parents=("root",))
    folder_b = folder_ref("folder-b", parents=("folder-a",))
    transport = FakeDriveTransport({
        "root": (folder_a,),
        "folder-a": (folder_b,),
        "folder-b": (folder_a,),  # cycle back to A
    })
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")  # must terminate, not recurse forever
    assert {entry.ref.source_id for entry in entries} == {"folder-a", "folder-b"}


def test_depth_cap_raises_inventory_limit_error():
    folder_a = folder_ref("folder-a", parents=("root",))
    folder_b = folder_ref("folder-b", parents=("folder-a",))
    transport = FakeDriveTransport({"root": (folder_a,), "folder-a": (folder_b,)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig(max_depth=1))
    with pytest.raises(InventoryLimitError):
        catalog.inventory("root")


def test_document_cap_raises_inventory_limit_error():
    children = tuple(ref(source_id=f"f{i}", parents=("root",)) for i in range(5))
    transport = FakeDriveTransport({"root": children})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig(max_documents=3))
    with pytest.raises(InventoryLimitError):
        catalog.inventory("root")


def test_page_cap_raises_inventory_limit_error():
    children = tuple(ref(source_id=f"f{i}", parents=("root",)) for i in range(10))
    transport = FakeDriveTransport({"root": children}, page_size=2)
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig(max_pages=2))
    with pytest.raises(InventoryLimitError):
        catalog.inventory("root")


def test_trashed_items_never_appear_in_inventory():
    live = ref(source_id="live", parents=("root",))
    trashed = ref(source_id="gone", parents=("root",), trashed=True)
    transport = FakeDriveTransport({"root": (live, trashed)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert {entry.ref.source_id for entry in entries} == {"live"}


def test_shortcut_to_target_outside_root_is_excluded_and_never_followed():
    shortcut = ref(source_id="shortcut-1", parents=("root",), mime_type="application/vnd.google-apps.shortcut",
                    shortcut_target_id="outside-folder")
    outside_folder = folder_ref("outside-folder", parents=("sibling",))
    transport = FakeDriveTransport({"root": (shortcut,)}, metadata={"outside-folder": outside_folder})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert entries == ()
    assert transport.list_calls == 1  # only root was listed; the shortcut target was never followed


def test_shortcut_to_target_inside_root_is_included_but_not_recursed_into():
    target_folder = folder_ref("target-folder", parents=("root",))
    inner = ref(source_id="inner-file", parents=("target-folder",))
    shortcut = ref(source_id="shortcut-1", parents=("root",), mime_type="application/vnd.google-apps.shortcut",
                    shortcut_target_id="target-folder")
    transport = FakeDriveTransport({"root": (shortcut,), "target-folder": (inner,)},
                                    metadata={"target-folder": target_folder})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert {entry.ref.source_id for entry in entries} == {"target-folder"}
    assert transport.list_calls == 1  # target-folder's own children were never listed


def test_every_inventory_entry_defaults_to_unknown_acl_and_is_never_upgraded():
    transport = FakeDriveTransport({"root": (ref(parents=("root",)),)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert entries and all(entry.acl_state is AclState.UNKNOWN for entry in entries)


def test_export_document_rejects_unsupported_target_mime_with_zero_transport_calls():
    unsupported = ref(mime_type="application/octet-stream")
    entry = InventoryEntry(ref=unsupported, root_id="root", depth=1, classification="document")
    transport = FakeDriveTransport({})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    with pytest.raises(UnsupportedExportError):
        catalog.export_document(entry)
    assert transport.export_calls == 0


def test_export_document_rejects_content_over_max_export_bytes():
    doc = ref(mime_type="application/vnd.google-apps.document")
    entry = InventoryEntry(ref=doc, root_id="root", depth=1, classification="document")
    content = b"x" * 50
    result = ExportResult(source_id=doc.source_id, target_mime_type="text/markdown", content=content,
                           sha256=sha256(content).hexdigest())
    transport = FakeDriveTransport({})
    transport.set_export_response(doc.source_id, result)
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig(max_export_bytes=10))
    with pytest.raises(ExportTooLargeError):
        catalog.export_document(entry)


def test_export_document_rejects_sha256_mismatch():
    doc = ref(mime_type="application/vnd.google-apps.document")
    entry = InventoryEntry(ref=doc, root_id="root", depth=1, classification="document")
    result = ExportResult(source_id=doc.source_id, target_mime_type="text/markdown", content=b"actual bytes",
                           sha256="0" * 64)
    transport = FakeDriveTransport({})
    transport.set_export_response(doc.source_id, result)
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    with pytest.raises(SourceCatalogError):
        catalog.export_document(entry)


def test_export_document_succeeds_for_a_valid_bounded_export():
    doc = ref(mime_type="application/vnd.google-apps.document")
    entry = InventoryEntry(ref=doc, root_id="root", depth=1, classification="document")
    content = b"hello world"
    result = ExportResult(source_id=doc.source_id, target_mime_type="text/markdown", content=content,
                           sha256=sha256(content).hexdigest())
    transport = FakeDriveTransport({})
    transport.set_export_response(doc.source_id, result)
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    assert catalog.export_document(entry) == result


# --- adapter: sanitized errors ---

def test_identity_denial_message_never_leaks_the_underlying_exception_text():
    class LeakyIdentity:
        def assert_verified(self):
            raise RuntimeError("secret-service-account@my-project.iam.gserviceaccount.com denied")

    transport = FakeDriveTransport({"root": (ref(parents=("root",)),)})
    catalog = DriveSourceCatalog(transport, LeakyIdentity(), DriveCatalogConfig())
    with pytest.raises(IdentityNotVerifiedError) as excinfo:
        catalog.inventory("root")
    message = str(excinfo.value)
    assert "secret-service-account" not in message
    assert "gserviceaccount" not in message
    assert "@" not in message


# --- fix round 1: bug reproductions against the pre-fix algorithm ---

def test_bugrepro_c1_multiparent_file_both_parents_in_root_must_not_raise():
    # file-x has two parents, folder-a and folder-c, BOTH legitimately inside the
    # root tree (folder-c is itself a child of folder-a). Order within folder-a's
    # own listing must not matter.
    file_x = ref(source_id="file-x", parents=("folder-a", "folder-c"))
    folder_c = folder_ref("folder-c", parents=("folder-a",))
    folder_a = folder_ref("folder-a", parents=("root",))
    transport = FakeDriveTransport({"root": (folder_a,), "folder-a": (file_x, folder_c)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")  # must NOT raise RootContainmentError
    assert {e.ref.source_id for e in entries} == {"folder-a", "folder-c", "file-x"}


def test_bugrepro_c2_in_root_file_must_not_be_silently_dropped():
    # file-y's only parent, folder-b, appears AFTER file-y in the same page.
    file_y = ref(source_id="file-y", parents=("folder-b",))
    folder_b = folder_ref("folder-b", parents=("root",))
    transport = FakeDriveTransport({"root": (file_y, folder_b)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert {e.ref.source_id for e in entries} == {"file-y", "folder-b"}


def test_bugrepro_m1_shortcut_itself_must_be_contained_not_just_its_target():
    target_folder = folder_ref("target-folder", parents=("root",))
    shortcut = ref(source_id="shortcut-1", parents=("somewhere-else",),
                    mime_type="application/vnd.google-apps.shortcut", shortcut_target_id="target-folder")
    transport = FakeDriveTransport({"root": (shortcut,)}, metadata={"target-folder": target_folder})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert entries == ()  # the shortcut's own parents don't lead to root


def test_bugrepro_i1_folder_cycle_emits_each_source_id_once_at_correct_depth():
    folder_a = folder_ref("folder-a", parents=("root",))
    folder_b = folder_ref("folder-b", parents=("folder-a",))
    transport = FakeDriveTransport({"root": (folder_a,), "folder-a": (folder_b,), "folder-b": (folder_a,)})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    entries = catalog.inventory("root")
    assert [(e.ref.source_id, e.depth) for e in entries] == [("folder-a", 1), ("folder-b", 2)]


def test_export_errors_never_contain_a_file_name_or_source_id():
    secret_name_ref = ref(source_id="super-secret-id-42", name="Q4-layoffs-plan.docx",
                           mime_type="application/octet-stream")
    entry = InventoryEntry(ref=secret_name_ref, root_id="root", depth=1, classification="document")
    transport = FakeDriveTransport({})
    catalog = DriveSourceCatalog(transport, AllowIdentity(), DriveCatalogConfig())
    with pytest.raises(UnsupportedExportError) as excinfo:
        catalog.export_document(entry)
    message = str(excinfo.value)
    assert "super-secret-id-42" not in message
    assert "Q4-layoffs-plan" not in message
    assert "http" not in message

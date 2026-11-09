def test_registered_with_cost_full():
    from app.core.manuscript_checks.registry import REGISTRY
    got = {c.name: c.cost for c in REGISTRY if c.name.startswith("pdf.")}
    assert got == {"pdf.page_limit": "full", "pdf.overfull_boxes": "full", "pdf.unresolved_refs": "full"}

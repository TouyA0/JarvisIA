from brain.integrations.android_tv import _parse_ui_dump, _resolve_app


def test_resolve_app_known_name_returns_deep_link_scheme():
    assert _resolve_app("youtube") == "vnd.youtube://"


def test_resolve_app_is_case_and_space_insensitive():
    assert _resolve_app("  Disney+  ") == "disneyplus://"


def test_resolve_app_passes_through_uri_unchanged():
    assert _resolve_app("vnd.youtube://abc123") == "vnd.youtube://abc123"


def test_resolve_app_passes_through_unknown_name_unchanged():
    assert _resolve_app("Molotov") == "Molotov"


def test_parse_ui_dump_extracts_clickable_element_with_text():
    xml = """<hierarchy>
        <node text="Rechercher" content-desc="" clickable="true" focusable="true"
              resource-id="com.app:id/search" bounds="[10,20][110,60]" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == [
        {"label": "Rechercher", "x": 60, "y": 40, "resource_id": "com.app:id/search"}
    ]


def test_parse_ui_dump_falls_back_to_content_desc_when_no_text():
    xml = """<hierarchy>
        <node text="" content-desc="Icône Recherche" clickable="false" focusable="true"
              resource-id="" bounds="[0,0][100,100]" />
    </hierarchy>"""
    elements = _parse_ui_dump(xml)
    assert elements == [{"label": "Icône Recherche", "x": 50, "y": 50, "resource_id": ""}]


def test_parse_ui_dump_skips_non_clickable_non_focusable_nodes():
    xml = """<hierarchy>
        <node text="Juste un titre" clickable="false" focusable="false" bounds="[0,0][10,10]" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == []


def test_parse_ui_dump_skips_elements_without_label():
    xml = """<hierarchy>
        <node text="" content-desc="" clickable="true" focusable="true" bounds="[0,0][10,10]" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == []


def test_parse_ui_dump_skips_node_without_valid_bounds():
    xml = """<hierarchy>
        <node text="Sans bounds" clickable="true" focusable="true" bounds="" />
    </hierarchy>"""
    assert _parse_ui_dump(xml) == []


def test_parse_ui_dump_returns_empty_list_on_malformed_xml():
    assert _parse_ui_dump("<not><valid") == []

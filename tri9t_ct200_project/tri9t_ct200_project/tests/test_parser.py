from app.parser import parse_text, flatten, sha256

def test_duplicate_headings_are_preserved_as_distinct_nodes():
    tree = parse_text("1 Introduction\nOverview text\n2 Introduction\nOther text")
    assert len(tree) == 2
    assert tree[0].heading == tree[1].heading
    assert tree[0] is not tree[1]

def test_numbered_parent_child_hierarchy():
    tree = parse_text("1 Safety\nIntro\n1.1 Warnings\nWarning body\n1.1.1 Electrical\nElectrical body\n2 Operation\nStart device")
    assert tree[0].heading == "1 Safety"
    assert tree[0].children[0].heading == "1.1 Warnings"
    assert tree[0].children[0].children[0].heading == "1.1.1 Electrical"
    assert tree[1].heading == "2 Operation"

def test_unclassified_lines_stay_in_body_and_hash_is_stable():
    tree = parse_text("1 Operation\nshort line\nAnother ordinary sentence.")
    assert "short line" in tree[0].body_text
    assert "Another ordinary sentence." in tree[0].body_text
    assert sha256("same") == sha256("same")

def test_same_heading_at_same_path_maps_to_same_logical_key():
    a = flatten(parse_text("1 Safety\nText A"))[0]["logical_key"]
    b = flatten(parse_text("1 Safety\nText B"))[0]["logical_key"]
    assert a == b

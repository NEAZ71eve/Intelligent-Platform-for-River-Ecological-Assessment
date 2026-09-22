import pytest
from training.class_mapping import load_mapping, fine_to_eval, eval_categories

def test_four_eval_categories():
    m = load_mapping()
    assert set(eval_categories(m)) == {"floating_debris", "bloom_blackwater",
                                        "outfall_discharge", "bank_problem"}

def test_fine_label_maps_to_eval():
    m = load_mapping()
    assert fine_to_eval(m, "bottle") == "floating_debris"
    assert fine_to_eval(m, "sewage_color") == "bloom_blackwater"
    assert fine_to_eval(m, "outfall") == "outfall_discharge"

def test_unknown_label_raises():
    m = load_mapping()
    with pytest.raises(KeyError):
        fine_to_eval(m, "nonexistent_label")

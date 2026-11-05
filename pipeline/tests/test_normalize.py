import pytest

import normalize as n


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("I сорт", "1"), ("1-СОРТА", "1"), ("первый сорт", "1"), ("ВТОРОЙ СОРТ", "2"), ("II сорт", "2"),
     ("3-сорта", "3"), ("третий сорт", "3"), ("В/С", "высший"), ("ВЫСШЕГО СОРТА", "высший"), ("", None)],
)  # fmt: skip
def test_grade(raw, expected):
    assert n.normalize_grade(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("II класс", "2"), ("2-КЛАСС", "2"), ("IV класс", "4"), ("1 класс", "1"), ("А500С", "А500С"), ("", None)],
)  # fmt: skip
def test_class(raw, expected):
    assert n.normalize_class(raw) == expected


def test_brand_and_size_spellings_agree():
    assert n.normalize_brand("ЦЕМ I 42,5 Н") == n.normalize_brand("ЦЕМ I 42,5Н")
    assert n.normalize_brand("Ne 24/1") == "NE 24/1"
    assert n.normalize_brand("М00к") == n.normalize_brand("М00К")
    assert n.normalize_size("Ø16ММ") == n.normalize_size("Ø16мм") == "Ø16мм"
    assert n.normalize_size("4Х1500Х6000 ММ") == "4х1500х6000мм"


def test_attributes_inside_name():
    got = n.extract_attributes("Хлопок сырец (спот) второй сорт 2 класс")
    assert (got["grade"], got["class"]) == ("2", "2")
    got = n.extract_attributes("Хлопок-сырец (форвард) I сорт II класс")
    assert (got["grade"], got["class"]) == ("1", "2")
    got = n.extract_attributes("Портландцемент ЦЕМ II/В-К 32,5 Н")
    assert got["brand"] == "ЦЕМ II/В-К 32,5Н"
    got = n.extract_attributes("Стекло флоат 4 мм")
    assert got["size"] == "4мм"
    got = n.extract_attributes("Мука пшеничная Высший сорт обогащенная витаминно-минеральной смесью")
    assert (got["grade"], got["type"]) == ("высший", "обогащенная витаминно-минеральной смесью")


def test_diesel_and_fuel_oil_share_an_hs_code_but_not_a_product():
    assert n.product_for("271019", "Топливо дизельное")[0] == "Дизельное топливо"
    assert n.product_for("271019", "МАЗУТ ТОПОЧНЫЙ")[0] == "Мазут"
    with pytest.raises(KeyError):
        n.product_for("271019", "Керосин")
    with pytest.raises(KeyError):
        n.product_for("999999", "Новый товар")


def test_spelling_variants_map_to_one_product():
    assert n.product_for("151229", "Хлопковое масло") == n.product_for("151229", "МАСЛО ХЛОПКОВОЕ")


def test_company_key_crosses_scripts_and_legal_forms():
    assert n.company_search_key('"ВАБЎК ТРАДЕ" МЧЖ') == "vabok trade"
    assert n.company_search_key("Mo‘jotat Klaster MChJ") == "mojotat klaster"
    assert n.company_search_key("QOJO‘LIT LOGISTIK MAS’ULIYATI CHEKLANGAN JAMIYATI") == "qojolit logistik"


def test_numbers():
    assert n.parse_number("304 547 938.4") == 304547938.4
    assert n.parse_number("") is None
    with pytest.raises(ValueError):
        n.parse_number("12,5")

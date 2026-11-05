"""Pure normalization rules for product attributes, regions, statuses, and company names.

Sellers fill in contract cards by hand, so one product appears under many spellings. The
canonical product comes from the HS code, checked against price levels per name variant.
HS 271019 is the only code covering two products: diesel and fuel oil trade at very different
prices, so it is split by name.
"""

import re

# hs code -> (Russian, English, Uzbek, extra search aliases)
PRODUCTS: dict[str, tuple[str, str, str, str]] = {
    "100199": ("Пшеница", "Wheat", "Bug‘doy", "пшеница продовольственная grain"),
    "100630": ("Рис", "Rice", "Guruch", "рис шлифованный"),
    "110100": ("Мука пшеничная", "Wheat flour", "Bug‘doy uni", "мука un flour"),
    "151219": ("Масло подсолнечное", "Sunflower oil", "Kungaboqar yog‘i", "подсолнечное масло"),
    "151229": ("Масло хлопковое", "Cottonseed oil", "Paxta yog‘i", "хлопковое масло cotton oil"),
    "170199": ("Сахар", "Sugar", "Shakar", "сахар белый сахар-песок"),
    "220190": ("Вода питьевая", "Drinking water", "Ichimlik suvi", "питьевая вода"),
    "230610": ("Шрот хлопковый", "Cottonseed meal", "Paxta shroti", "шрот хлопковых семян"),
    "230990": ("Комбикорм", "Compound feed", "Omuxta yem", "кормосмесь animal feed"),
    "250100": ("Соль пищевая", "Edible salt", "Osh tuzi", "соль поваренная salt tuz"),
    "252020": ("Гипс", "Gypsum", "Gips", "гипс строительный"),
    "252210": ("Известь", "Lime", "Ohak", "известь негашеная строительная"),
    "252329": ("Портландцемент", "Portland cement", "Portlandsement", "цемент cement sement"),
    "271012": ("Бензин", "Gasoline", "Benzin", "бензин автомобильный petrol"),
    "271112": ("Сжиженный газ", "Liquefied gas (LPG)", "Suyultirilgan gaz", "пропан бутан lpg"),
    "271320": ("Битум", "Bitumen", "Bitum", "битум нефтяной"),
    "280421": ("Аргон", "Argon", "Argon", "аргон газообразный"),
    "280430": ("Азот", "Nitrogen", "Azot", ""),
    "280700": ("Серная кислота", "Sulfuric acid", "Sulfat kislota", "кислота серная"),
    "281511": ("Сода каустическая", "Caustic soda", "Kaustik soda", ""),
    "310210": ("Карбамид", "Urea", "Karbamid", "мочевина mochevina"),
    "310230": ("Аммиачная селитра", "Ammonium nitrate", "Ammiakli selitra", "селитра аммиачная"),
    "320810": ("Эмаль", "Enamel paint", "Emal", "эмаль алкидная paint"),
    "390120": ("Полиэтилен", "Polyethylene", "Polietilen", "полиэтилен гранулированный"),
    "390210": ("Полипропилен", "Polypropylene", "Polipropilen", ""),
    "390410": ("Поливинилхлорид", "PVC", "Polivinilxlorid", "пвх polyvinyl chloride"),
    "391721": ("Трубы полиэтиленовые", "Polyethylene pipes", "Polietilen quvurlar", "труба пэ"),
    "440711": ("Пиломатериалы", "Sawn timber", "Yog‘och materiallari", "пиломатериал lumber"),
    "520100": ("Хлопок-сырец", "Raw cotton", "Paxta xomashyosi", "хлопок сырец paxta cotton"),
    "520512": ("Пряжа хлопковая", "Cotton yarn", "Paxta kalavasi", "пряжа хлопчатобумажная ip"),
    "690410": ("Кирпич", "Brick", "G‘isht", "кирпич керамический"),
    "700529": ("Стекло листовое", "Sheet glass", "List oyna", "стекло флоат float shisha"),
    "720853": ("Лист стальной", "Hot-rolled steel sheet", "Po‘lat list", "горячекатаный"),
    "721420": ("Арматура", "Rebar", "Armatura", "арматура стальная"),
    "721710": ("Проволока арматурная", "Reinforcing wire", "Armatura simi", "wire sim"),
    "740311": ("Катод медный", "Copper cathode", "Mis katod", "медный катод copper mis"),
    "760421": ("Профиль алюминиевый", "Aluminum profile", "Alyuminiy profil", ""),
    "848210": ("Подшипник", "Bearing", "Podshipnik", ""),
    "854449": ("Кабель силовой", "Power cable", "Kuch kabeli", "cable kabel"),
}
DIESEL = ("Дизельное топливо", "Diesel fuel", "Dizel yoqilg‘isi", "топливо дизельное солярка")
FUEL_OIL = ("Мазут", "Fuel oil", "Mazut", "мазут топочный")

# Uzbek (deals, participants) -> (Russian as written in contracts, English)
REGIONS: dict[str, tuple[str, str]] = {
    "Toshkent shahri": ("г. Ташкент", "Tashkent city"),
    "Toshkent viloyati": ("Ташкентская область", "Tashkent region"),
    "Andijon viloyati": ("Андижанская область", "Andijan region"),
    "Buxoro viloyati": ("Бухарская область", "Bukhara region"),
    "Farg‘ona viloyati": ("Ферганская область", "Fergana region"),
    "Jizzax viloyati": ("Джизакская область", "Jizzakh region"),
    "Xorazm viloyati": ("Хорезмская область", "Khorezm region"),
    "Namangan viloyati": ("Наманганская область", "Namangan region"),
    "Navoiy viloyati": ("Навоийская область", "Navoi region"),
    "Qashqadaryo viloyati": ("Кашкадарьинская область", "Kashkadarya region"),
    "Samarqand viloyati": ("Самаркандская область", "Samarkand region"),
    "Sirdaryo viloyati": ("Сырдарьинская область", "Syrdarya region"),
    "Surxondaryo viloyati": ("Сурхандарьинская область", "Surkhandarya region"),
    "Qoraqalpog‘iston Respublikasi": ("Республика Каракалпакстан", "Republic of Karakalpakstan"),
}

STATUSES: dict[str, str] = {
    "Новый": "new",
    "Не подписан": "unsigned",
    "Заключен": "concluded",
    "Ждёт оплату": "awaiting_payment",
    "Оплачен": "paid",
    "Исполнен": "executed",
    "Исполнен(Частично)": "partially_executed",
    "Аннулирован(Не оплачен)": "cancelled",
}
CURRENCIES = {"Узбекский сум": "UZS", "Доллар США": "USD"}
FORMS = {"Спот": "spot", "Форвард": "forward", "Фьючерс": "futures"}
AUCTIONS = {
    "Английский аукцион": "english",
    "Обратный аукцион": "reverse",
    "Двусторонний аукцион": "double",
}
CONTRACT_TYPES = {"Внутренний": "domestic", "Экспортный": "export"}

_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}
_WORDS = {"перв": "1", "втор": "2", "трет": "3"}

_GRADE = re.compile(
    r"(в/с|высш\w*(?:\s+сорт\w*)?|(?<![\w])(?:iii|ii|i|[123]|перв\w*|втор\w*|трет\w*)[\s-]*сорт\w*)",
    re.I,
)
_CLASS = re.compile(r"(?<![\w])(iv|iii|ii|i|[1-4])[\s-]*класс\w*", re.I)
_BRAND = re.compile(
    r"(ЦЕМ\s+I{1,2}(?:/[АВ]-[ШК])?\s*\d\d,\d\s*Н|АИ-\d\d|(?:HD|LL|LD|PE|PP|SG)-\d+|NE\s*\d+/\d"
    r"|БНД\s*\d+/\d+|ДТ-[ЕЗЛ]-К5|ВВГ\s*\dх[\d,]+|Г-\d|М-\d+|М0{1,2}К|ВР-1|ПФ-115|КС-\d+|СТ3СП|ПБ[АТ])",
    re.I,
)
_SIZE = re.compile(
    r"(Ø\s*\d+\s*мм|\d+\s*[хx]\s*\d+(?:\s*[хx]\s*\d+)?\s*мм|(?<![\w,])\d+\s*мм|\d+,\d\s*л\b)", re.I
)
_TYPES = (
    "рафинированное дезодорированное",
    "обогащенная витаминно-минеральной смесью",
    "обрезные хвойных пород",
    "рафинированное",
    "хлебопекарная",
    "тостированный",
    "дорожный",
    "суспензионный",
    "техническая",
    "йодированная",
    "твердая",
)


def product_for(hs_code: str, name: str) -> tuple[str, str, str, str]:
    """Canonical (ru, en, uz, aliases). Raises KeyError so an unknown product fails the build."""
    if hs_code == "271019":
        folded = name.casefold()
        if "мазут" in folded:
            return FUEL_OIL
        if "дизел" in folded:
            return DIESEL
        raise KeyError(f"HS 271019 name is neither diesel nor fuel oil: {name!r}")
    return PRODUCTS[hs_code]


def normalize_grade(value: str) -> str | None:
    """'I сорт', '1-СОРТА', 'первый сорт' -> '1'; 'В/С', 'высшего сорта' -> 'высший'."""
    text = value.strip().casefold()
    if not text:
        return None
    if text.startswith(("в/с", "высш")):
        return "высший"
    for stem, digit in _WORDS.items():
        if text.startswith(stem):
            return digit
    head = re.match(r"(iii|ii|i|[123])(?![\w])", text)
    if head:
        return _ROMAN.get(head.group(1), head.group(1))
    raise ValueError(f"Unknown grade: {value!r}")


def normalize_class(value: str) -> str | None:
    """'II класс', '2-КЛАСС' -> '2'. Rebar steel classes such as 'А500С' stay as written."""
    text = value.strip().casefold()
    if not text:
        return None
    head = re.match(r"(iv|iii|ii|i|[1-4])(?![\w])", text)
    if head:
        return _ROMAN.get(head.group(1), head.group(1))
    return value.strip().upper()


def normalize_brand(value: str) -> str | None:
    """'ЦЕМ I 42,5Н' and 'ЦЕМ I 42,5 Н' agree; 'Ne 24/1' -> 'NE 24/1'; 'М00к' -> 'М00К'."""
    text = re.sub(r"\s+", " ", value).strip().upper()
    if not text:
        return None
    text = re.sub(r"(\d,\d) Н$", r"\1Н", text)
    return "высший" if text == "ВЫСШИЙ" else text


def normalize_size(value: str) -> str | None:
    """'Ø16ММ' -> 'Ø16мм', '4Х1500Х6000 ММ' -> '4х1500х6000мм', '0,5Л' -> '0,5л'."""
    text = re.sub(r"\s+", "", value).lower().replace("x", "х").replace("ø", "Ø")
    return text or None


def normalize_type(value: str) -> str | None:
    return re.sub(r"\s+", " ", value).strip().casefold() or None


def extract_attributes(name: str) -> dict[str, str | None]:
    """Attributes written inside the product name, for cards whose attribute fields are blank."""
    folded = name.casefold()
    grade = _GRADE.search(name)
    klass = _CLASS.search(name)
    brand = _BRAND.search(name.replace("ё", "е"))
    size = _SIZE.search(name)
    return {
        "grade": normalize_grade(grade.group(1)) if grade else None,
        "class": normalize_class(klass.group(1)) if klass else None,
        "brand": normalize_brand(brand.group(1)) if brand else None,
        "size": normalize_size(size.group(1)) if size else None,
        "type": next((t for t in _TYPES if t in folded), None),
    }


_CYR = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh",
        "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o", "қ": "q",
        "ғ": "g", "ҳ": "h",
    }
)  # fmt: skip
_LEGAL = re.compile(
    r"\b(mas\W?uliyati cheklangan jamiyati|mchj|mchj|xk|ok|aj|qk|mas\W?uliyati|cheklangan|jamiyati)\b"
)


def company_search_key(name: str) -> str:
    """Latin, lowercase, no quotes or legal form, so 'ВАБЎК ТРАДЕ МЧЖ' finds 'vabok trade'."""
    text = name.casefold().translate(_CYR)
    text = re.sub(r"[‘’'`ʻʼ]", "", text)
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return re.sub(r"\s+", " ", _LEGAL.sub(" ", text)).strip()


def parse_number(value: str) -> float | None:
    """'304 547 938.4' -> 304547938.4. Blank -> None. Any other shape raises."""
    text = re.sub(r"[\s  ]", "", value)
    return float(text) if text else None

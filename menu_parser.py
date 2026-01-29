import re
from typing import List, Optional
from pydantic import BaseModel


class ParsedDish(BaseModel):
    name: str
    type: str
    composition: str
    quantity_grams: int
    price_rub: float



CATEGORY_MAP = {
    "вторые горячие блюда": "MAIN",
    "гарниры": "GARNISH",
    "готовое кулинарное блюдо": "PREPARED",
    "напитки": "DRINK",
    "салаты": "SALAD",
    "супы": "SOUP",
    "первые блюда": "SOUP",
    "хлеб": "BREAD",
    "выпечка": "BREAD"
}

IGNORE_HEADERS = [
    "название", "состав", "кол-во (г/шт.)", "цена",
    "период действия в меню", "штрихкод"
]


def parse_menu_text(content: str) -> List[ParsedDish]:
    lines = content.splitlines()
    results = []

    current_type = "MAIN"
    buffer = []

    number_pattern = re.compile(r'\d+')

    for line in lines:
        clean_line = line.strip()
        lower_line = clean_line.lower()

        if not clean_line:
            continue

        if lower_line in IGNORE_HEADERS:
            continue

        if lower_line in CATEGORY_MAP:
            current_type = CATEGORY_MAP[lower_line]
            buffer = []
            continue

        buffer.append(clean_line)


        if len(buffer) == 4:
            try:
                name = buffer[0]
                composition = buffer[1]

                w_match = number_pattern.search(buffer[2])
                weight = int(w_match.group()) if w_match else 0

                p_match = number_pattern.search(buffer[3])
                price = float(p_match.group()) if p_match else 0.0

                dish = ParsedDish(
                    name=name,
                    type=current_type,
                    composition=composition,
                    quantity_grams=weight,
                    price_rub=price
                )
                results.append(dish)
            except Exception as e:
                print(f"Ошибка при парсинге блюда {buffer[0]}: {e}")

            buffer = []

    return results
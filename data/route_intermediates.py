TYPICAL_ROUTES = [
    ["Лутовинівка", "Козельщина", "Нова Галещина", "Солониця", "Кременчук"],
    ["Лутовинівка", "Козельщина", "Нова Галещина", "Солониця", "Горішні Плавні"],
]


def get_search_city_pairs(from_city: str, to_city: str) -> tuple[list[str], list[str]]:
    """
    Returns (extra_from_cities, extra_to_cities) to broaden the search.
    For route [1,2,3,4,5] with from=2, to=4:
      extra_from_cities = [1]  (earlier starts that go to `to_city`)
      extra_to_cities   = [5]  (later ends that start from `from_city`)
    """
    extra_from, extra_to = set(), set()
    for route in TYPICAL_ROUTES:
        if from_city in route and to_city in route:
            i, j = route.index(from_city), route.index(to_city)
            if i < j:
                extra_from.update(route[:i])
                extra_to.update(route[j + 1:])
            else:
                extra_from.update(route[i + 1:])
                extra_to.update(route[:j])
    return list(extra_from), list(extra_to)

def get_covered_pairs(from_city: str, to_city: str) -> list[tuple[str, str]]:
    """
    Returns all (from, to) sub-segments covered by a trip from from_city to to_city.
    E.g. for route [1,2,3,4,5] with from=2, to=5: (2,3),(2,4),(2,5),(3,4),(3,5),(4,5)
    """
    pairs = set()
    for route in TYPICAL_ROUTES:
        if from_city in route and to_city in route:
            i, j = route.index(from_city), route.index(to_city)
            if i < j:
                segment = route[i:j + 1]
                for a in range(len(segment)):
                    for b in range(a + 1, len(segment)):
                        pairs.add((segment[a], segment[b]))
            elif i > j:
                segment = route[j:i + 1]
                for a in range(len(segment)):
                    for b in range(a + 1, len(segment)):
                        pairs.add((segment[b], segment[a]))
    pairs.add((from_city, to_city))
    return list(pairs)

def get_intermediates(from_city: str, to_city: str) -> list[str]:
    result = set()
    for route in TYPICAL_ROUTES:
        if from_city in route and to_city in route:
            i, j = route.index(from_city), route.index(to_city)
            if i < j:
                result.update(route[i + 1:j])
            else:
                result.update(route[j + 1:i])
    return list(result)

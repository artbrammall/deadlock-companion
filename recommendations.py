def eligible_heroes(roster, allies, enemies, current_hero):
    if len(allies) != 6 or len(enemies) != 6:
        return []

    picked = allies + enemies

    if "UNKNOWN" in picked or len(set(picked)) != 12:
        return []

    if current_hero not in allies:
        return []

    taken = set(picked) - {current_hero}
    candidates = set(roster) | {current_hero}

    return sorted(candidates - taken)
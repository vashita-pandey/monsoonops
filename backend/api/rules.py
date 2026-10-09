LEVELS = ["Normal", "Watch", "High"]
WARNING_LEVEL = {"green": 0, "yellow": 1, "orange": 2, "red": 2}


def evaluate(forecast_mm, site, warning=None):
    watch = float(site["thresholds"]["watchMm"])
    high = float(site["thresholds"]["highMm"])
    mm = float(forecast_mm)
    level = 0
    reasons = []

    if mm >= high:
        level = 2
        reasons.append(f"forecast {mm:g} mm is in the very heavy class (>= {high:g} mm)")
    elif mm >= watch:
        level = 1
        reasons.append(f"forecast {mm:g} mm is in the heavy class (>= {watch:g} mm)")
    else:
        reasons.append(f"forecast {mm:g} mm is below the watch threshold ({watch:g} mm)")

    if warning in WARNING_LEVEL and WARNING_LEVEL[warning] > level:
        level = WARNING_LEVEL[warning]
        reasons.append(f"official {warning} warning covers the district")

    if 0 < level < 2 and (site.get("lowLying") or site.get("floodHistory")):
        level += 1
        reasons.append("site is low-lying or has flood history, so raised one level")

    return LEVELS[level], "; ".join(reasons)
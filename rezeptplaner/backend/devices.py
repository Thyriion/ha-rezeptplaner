PREDEFINED_KITCHEN_DEVICES = [
    "Airfryer",
    "Dampfgarer",
    "Slow Cooker",
    "Thermomix",
    "Multikocher",
    "Kontaktgrill",
    "Grillplatte",
    "Sous-Vide-Stick",
    "Waffeleisen",
    "Raclette",
    "Fondue",
    "Reiskocher",
]


def normalize_device(name: str) -> str:
    """Return a canonical device name if it matches a predefined device case-insensitively."""
    lowered = name.strip().lower()
    for device in PREDEFINED_KITCHEN_DEVICES:
        if device.lower() == lowered:
            return device
    return name.strip()

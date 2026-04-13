"""
Preferences Manager for T.R.A.N.S. application.
Handles color schemes, fonts, and UI customization with save/load functionality.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from PySide6.QtCore import QObject, Signal, Slot, Property

logger = logging.getLogger(__name__)


# Pride flag color schemes with community meme names
PRESET_COLOR_SCHEMES = {
    # Trans Pride - "The Blahaj Aesthetic"
    "blahaj_aesthetic": {
        "name": "The Blahaj Aesthetic",
        "description": "Trans pride colors - cozy like a weighted shark plushie",
        "colors": {
            "bgDark": "#1a1a2e",
            "bgDarker": "#0d0d1a",
            "bgMedium": "#2a2a3e",
            "bgLight": "#3a3a4e",
            "accentPrimary": "#F5A9B8",    # Trans pink
            "accentSecondary": "#5BCEFA",   # Trans blue
            "accentTertiary": "#FFFFFF",    # White
            "textPrimary": "#FFFFFF",
            "textSecondary": "#F5A9B8",
            "textMuted": "#B0A0B8",
            "borderColor": "#5BCEFA",
            "success": "#66ff99",
            "warning": "#FFB7C5",
            "error": "#D60270"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Bisexual Pride - "Sitting Weird in Chairs"
    "sitting_weird": {
        "name": "Sitting Weird in Chairs",
        "description": "Bisexual pride colors - for the finger guns enthusiasts",
        "colors": {
            "bgDark": "#1a0d1a",
            "bgDarker": "#0d0609",
            "bgMedium": "#2a1a2a",
            "bgLight": "#3a2a3a",
            "accentPrimary": "#D60270",     # Bi magenta
            "accentSecondary": "#9B4F96",   # Bi purple
            "accentTertiary": "#0038A8",    # Bi blue
            "textPrimary": "#FFFFFF",
            "textSecondary": "#D60270",
            "textMuted": "#B090B0",
            "borderColor": "#9B4F96",
            "success": "#66ff99",
            "warning": "#D60270",
            "error": "#FF1493"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Lesbian Pride - "U-Haul Ready"
    "uhaul_ready": {
        "name": "U-Haul Ready",
        "description": "Lesbian pride colors - second date moving vibes",
        "colors": {
            "bgDark": "#1a0d0d",
            "bgDarker": "#0d0606",
            "bgMedium": "#2a1515",
            "bgLight": "#3a2020",
            "accentPrimary": "#D62900",     # Orange-red
            "accentSecondary": "#FF9B55",   # Orange
            "accentTertiary": "#D461A6",    # Pink
            "textPrimary": "#FFFFFF",
            "textSecondary": "#FF9B55",
            "textMuted": "#B09090",
            "borderColor": "#D461A6",
            "success": "#66ff99",
            "warning": "#FF9B55",
            "error": "#D62900"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Gay Pride - "Fruity as a Rainbow"
    "fruity_rainbow": {
        "name": "Fruity as a Rainbow",
        "description": "Gay pride rainbow - absolutely fabulous darling",
        "colors": {
            "bgDark": "#1a1a1a",
            "bgDarker": "#0d0d0d",
            "bgMedium": "#2a2a2a",
            "bgLight": "#3a3a3a",
            "accentPrimary": "#FF0018",     # Red
            "accentSecondary": "#FFA52C",   # Orange
            "accentTertiary": "#008018",    # Green
            "textPrimary": "#FFFFFF",
            "textSecondary": "#FFFF41",     # Yellow
            "textMuted": "#B0B0B0",
            "borderColor": "#0000F9",       # Blue
            "success": "#008018",
            "warning": "#FFA52C",
            "error": "#FF0018"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Non-Binary Pride - "Valid and Vibing"
    "valid_vibing": {
        "name": "Valid and Vibing",
        "description": "Non-binary pride - existing outside the binary since forever",
        "colors": {
            "bgDark": "#1a1a0d",
            "bgDarker": "#0d0d06",
            "bgMedium": "#2a2a1a",
            "bgLight": "#3a3a2a",
            "accentPrimary": "#FCF434",     # Yellow
            "accentSecondary": "#9C59D1",   # Purple
            "accentTertiary": "#2C2C2C",    # Black
            "textPrimary": "#FFFFFF",
            "textSecondary": "#FCF434",
            "textMuted": "#B0B090",
            "borderColor": "#9C59D1",
            "success": "#66ff99",
            "warning": "#FCF434",
            "error": "#FF6B6B"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Pansexual Pride - "Attracted to Pans (and everything else)"
    "attracted_to_pans": {
        "name": "Attracted to Pans",
        "description": "Pansexual pride - hearts not parts (including cookware)",
        "colors": {
            "bgDark": "#1a0d1a",
            "bgDarker": "#0d060d",
            "bgMedium": "#2a1a2a",
            "bgLight": "#3a2a3a",
            "accentPrimary": "#FF1B8D",     # Magenta/pink
            "accentSecondary": "#FFDA00",   # Yellow
            "accentTertiary": "#1BB3FF",    # Cyan
            "textPrimary": "#FFFFFF",
            "textSecondary": "#FFDA00",
            "textMuted": "#B090B0",
            "borderColor": "#FF1B8D",
            "success": "#66ff99",
            "warning": "#FFDA00",
            "error": "#FF1B8D"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Asexual Pride - "Garlic Bread Supremacy"
    "garlic_bread": {
        "name": "Garlic Bread Supremacy",
        "description": "Asexual pride - cake and garlic bread over everything",
        "colors": {
            "bgDark": "#1a1a1a",
            "bgDarker": "#0d0d0d",
            "bgMedium": "#2a2a2a",
            "bgLight": "#3a3a3a",
            "accentPrimary": "#A3A3A3",     # Gray
            "accentSecondary": "#FFFFFF",   # White
            "accentTertiary": "#800080",    # Purple
            "textPrimary": "#FFFFFF",
            "textSecondary": "#A3A3A3",
            "textMuted": "#808080",
            "borderColor": "#800080",
            "success": "#66ff99",
            "warning": "#A3A3A3",
            "error": "#FF6B6B"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Aromantic Pride - "No Romo"
    "no_romo": {
        "name": "No Romo",
        "description": "Aromantic pride - friendship is the real magic",
        "colors": {
            "bgDark": "#0d1a0d",
            "bgDarker": "#060d06",
            "bgMedium": "#1a2a1a",
            "bgLight": "#2a3a2a",
            "accentPrimary": "#3DA542",     # Green
            "accentSecondary": "#A7D379",   # Light green
            "accentTertiary": "#A3A3A3",    # Gray
            "textPrimary": "#FFFFFF",
            "textSecondary": "#A7D379",
            "textMuted": "#90B090",
            "borderColor": "#3DA542",
            "success": "#3DA542",
            "warning": "#A7D379",
            "error": "#FF6B6B"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Genderqueer Pride - "Breaking the Binary"
    "breaking_binary": {
        "name": "Breaking the Binary",
        "description": "Genderqueer pride - gender is a spectrum, not a checkbox",
        "colors": {
            "bgDark": "#1a0d1a",
            "bgDarker": "#0d060d",
            "bgMedium": "#2a1a2a",
            "bgLight": "#3a2a3a",
            "accentPrimary": "#B57EDC",     # Lavender
            "accentSecondary": "#FFFFFF",   # White
            "accentTertiary": "#4A8123",    # Green
            "textPrimary": "#FFFFFF",
            "textSecondary": "#B57EDC",
            "textMuted": "#A090B0",
            "borderColor": "#4A8123",
            "success": "#4A8123",
            "warning": "#B57EDC",
            "error": "#FF6B6B"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Agender Pride - "Gender? I Don't Know Her"
    "gender_who": {
        "name": "Gender? I Don't Know Her",
        "description": "Agender pride - free from the gender construct",
        "colors": {
            "bgDark": "#1a1a1a",
            "bgDarker": "#0d0d0d",
            "bgMedium": "#2a2a2a",
            "bgLight": "#3a3a3a",
            "accentPrimary": "#B9B9B9",     # Gray
            "accentSecondary": "#FFFFFF",   # White
            "accentTertiary": "#84B082",    # Green
            "textPrimary": "#FFFFFF",
            "textSecondary": "#B9B9B9",
            "textMuted": "#909090",
            "borderColor": "#84B082",
            "success": "#84B082",
            "warning": "#B9B9B9",
            "error": "#FF6B6B"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Progress Pride - "Intersectional Excellence"
    "intersectional": {
        "name": "Intersectional Excellence",
        "description": "Progress pride - centering BIPOC and trans voices",
        "colors": {
            "bgDark": "#1a1a1a",
            "bgDarker": "#0d0d0d",
            "bgMedium": "#2a2a2a",
            "bgLight": "#3a3a3a",
            "accentPrimary": "#F5A9B8",     # Trans pink
            "accentSecondary": "#5BCEFA",   # Trans blue
            "accentTertiary": "#613915",    # Brown
            "textPrimary": "#FFFFFF",
            "textSecondary": "#F5A9B8",
            "textMuted": "#B0B0B0",
            "borderColor": "#000000",       # Black
            "success": "#008018",
            "warning": "#FFA52C",
            "error": "#FF0018"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Polyamorous Pride - "Kitchen Table Poly"
    "kitchen_table": {
        "name": "Kitchen Table Poly",
        "description": "Polyamorous pride - ethical non-monogamy with metamour hangouts",
        "colors": {
            "bgDark": "#0d0d1a",
            "bgDarker": "#06060d",
            "bgMedium": "#1a1a2a",
            "bgLight": "#2a2a3a",
            "accentPrimary": "#0000FF",     # Blue
            "accentSecondary": "#FF0000",   # Red
            "accentTertiary": "#000000",    # Black
            "textPrimary": "#FFFFFF",
            "textSecondary": "#FFD700",     # Gold (infinity heart)
            "textMuted": "#9090B0",
            "borderColor": "#FF0000",
            "success": "#66ff99",
            "warning": "#FFD700",
            "error": "#FF0000"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Classic Dark - "Just Dark Mode"
    "just_dark": {
        "name": "Just Dark Mode",
        "description": "Classic dark theme - for the minimalists",
        "colors": {
            "bgDark": "#1a1a1a",
            "bgDarker": "#0d0d0d",
            "bgMedium": "#2a2a2a",
            "bgLight": "#3a3a3a",
            "accentPrimary": "#66B3FF",
            "accentSecondary": "#FF66B2",
            "accentTertiary": "#66FF99",
            "textPrimary": "#FFFFFF",
            "textSecondary": "#66B3FF",
            "textMuted": "#888888",
            "borderColor": "#555555",
            "success": "#66ff99",
            "warning": "#FFAA66",
            "error": "#FF6666"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Straight Dark - Monochrome dark with muted greys
    "straight_dark": {
        "name": "Straight Dark",
        "description": "For those who chose to stay in the dark",
        "colors": {
            "bgDark": "#121212",           # Near-black background
            "bgDarker": "#0a0a0a",          # Deepest black
            "bgMedium": "#1c1c1c",          # Slightly lighter
            "bgLight": "#262626",           # Card/panel background
            "accentPrimary": "#707070",     # Muted grey accent
            "accentSecondary": "#606060",   # Slightly darker grey
            "accentTertiary": "#505050",    # Even more muted
            "textPrimary": "#c8c8c8",       # Soft white (not pure white)
            "textSecondary": "#888888",     # Muted grey text
            "textMuted": "#5a5a5a",         # Very muted
            "borderColor": "#333333",       # Subtle border
            "success": "#6a6a6a",           # Muted success (grey-green tint)
            "warning": "#787878",           # Muted warning (grey)
            "error": "#8a7070"              # Muted error (grey-red tint)
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # =========== LIGHT THEMES ===========

    # Trans Pride Light - "Blahaj in the Sun"
    "blahaj_light": {
        "name": "Blahaj in the Sun",
        "description": "Trans pride light theme - sunny and cozy",
        "colors": {
            "bgDark": "#F5F0F8",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#E8E0F0",
            "bgLight": "#D8D0E0",
            "accentPrimary": "#D05080",     # Trans pink (darker for contrast)
            "accentSecondary": "#2090C0",   # Trans blue (darker)
            "accentTertiary": "#404050",    # Dark gray
            "textPrimary": "#1a1a2e",
            "textSecondary": "#D05080",
            "textMuted": "#606070",
            "borderColor": "#B0A0C0",
            "success": "#2E8B57",
            "warning": "#D05080",
            "error": "#C41E3A"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Bisexual Pride Light - "Lemon Bar Vibes"
    "lemon_bar": {
        "name": "Lemon Bar Vibes",
        "description": "Bisexual pride light theme - sweet and tangy like the stereotype",
        "colors": {
            "bgDark": "#FFF8F0",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#F8E8E8",
            "bgLight": "#F0D8D8",
            "accentPrimary": "#B00050",     # Bi magenta (darker)
            "accentSecondary": "#6B2D6B",   # Bi purple (darker)
            "accentTertiary": "#002080",    # Bi blue (darker)
            "textPrimary": "#1a0d1a",
            "textSecondary": "#B00050",
            "textMuted": "#605060",
            "borderColor": "#C090B0",
            "success": "#2E8B57",
            "warning": "#B00050",
            "error": "#CC1144"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Lesbian Pride Light - "Sunset Boulevard"
    "sunset_blvd": {
        "name": "Sunset Boulevard",
        "description": "Lesbian pride light theme - warm sunset vibes",
        "colors": {
            "bgDark": "#FFF5F0",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#FFE8E0",
            "bgLight": "#FFD8D0",
            "accentPrimary": "#B02000",     # Orange-red (darker)
            "accentSecondary": "#D07030",   # Orange (darker)
            "accentTertiary": "#A04080",    # Pink (darker)
            "textPrimary": "#1a0d0d",
            "textSecondary": "#B02000",
            "textMuted": "#705050",
            "borderColor": "#D0A0A0",
            "success": "#2E8B57",
            "warning": "#D07030",
            "error": "#B02000"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Non-Binary Light - "Sunshine Valid"
    "sunshine_valid": {
        "name": "Sunshine Valid",
        "description": "Non-binary pride light theme - bright and valid",
        "colors": {
            "bgDark": "#FFFEF0",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#FFF8D8",
            "bgLight": "#F8F0C8",
            "accentPrimary": "#C0A000",     # Yellow (darker)
            "accentSecondary": "#7040A0",   # Purple (darker)
            "accentTertiary": "#303030",    # Black/dark
            "textPrimary": "#1a1a0d",
            "textSecondary": "#7040A0",
            "textMuted": "#606050",
            "borderColor": "#C0B080",
            "success": "#2E8B57",
            "warning": "#C0A000",
            "error": "#D04040"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Pansexual Light - "Tropical Pan-ch"
    "tropical_panch": {
        "name": "Tropical Pan-ch",
        "description": "Pansexual pride light theme - fruity and tropical",
        "colors": {
            "bgDark": "#FFF8F8",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#FFE8F0",
            "bgLight": "#FFD8E8",
            "accentPrimary": "#D01070",     # Magenta/pink (darker)
            "accentSecondary": "#C0A000",   # Yellow (darker)
            "accentTertiary": "#0080C0",    # Cyan (darker)
            "textPrimary": "#1a0d1a",
            "textSecondary": "#D01070",
            "textMuted": "#605060",
            "borderColor": "#E090C0",
            "success": "#2E8B57",
            "warning": "#C0A000",
            "error": "#D01070"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Classic Light - "Just Light Mode"
    "just_light": {
        "name": "Just Light Mode",
        "description": "Classic light theme - clean and simple",
        "colors": {
            "bgDark": "#F5F5F5",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#E8E8E8",
            "bgLight": "#DADADA",
            "accentPrimary": "#0066CC",
            "accentSecondary": "#CC3399",
            "accentTertiary": "#33AA66",
            "textPrimary": "#1a1a1a",
            "textSecondary": "#0066CC",
            "textMuted": "#666666",
            "borderColor": "#BBBBBB",
            "success": "#33AA66",
            "warning": "#CC8800",
            "error": "#CC3333"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Straight Light - Monochrome light with muted greys
    "straight_light": {
        "name": "Straight Light",
        "description": "For those blinded by the light",
        "colors": {
            "bgDark": "#f0f0f0",            # Soft off-white background
            "bgDarker": "#f8f8f8",           # Brightest (but not pure white)
            "bgMedium": "#e6e6e6",           # Slightly darker
            "bgLight": "#dcdcdc",            # Card/panel background
            "accentPrimary": "#707070",      # Muted grey accent
            "accentSecondary": "#808080",    # Slightly lighter grey
            "accentTertiary": "#909090",     # Even lighter
            "textPrimary": "#2a2a2a",        # Soft black (not pure black)
            "textSecondary": "#5a5a5a",      # Muted grey text
            "textMuted": "#8a8a8a",          # Light muted
            "borderColor": "#c8c8c8",        # Subtle border
            "success": "#6a6a6a",            # Muted success (grey)
            "warning": "#787878",            # Muted warning (grey)
            "error": "#706a6a"               # Muted error (grey-ish)
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    },

    # Gay Pride Light - "Rainbow Sherbet"
    "rainbow_sherbet": {
        "name": "Rainbow Sherbet",
        "description": "Gay pride light theme - sweet, colorful, and absolutely fabulous",
        "colors": {
            "bgDark": "#FFF8F5",
            "bgDarker": "#FFFFFF",
            "bgMedium": "#FFF0E8",
            "bgLight": "#FFE8DD",
            "accentPrimary": "#CC0015",     # Red (darker for contrast)
            "accentSecondary": "#CC7020",   # Orange (darker)
            "accentTertiary": "#006015",    # Green (darker)
            "textPrimary": "#1a1a1a",
            "textSecondary": "#0000C0",     # Blue text
            "textMuted": "#505050",
            "borderColor": "#8B00C0",       # Purple/violet
            "success": "#006015",
            "warning": "#CC7020",
            "error": "#CC0015"
        },
        "font": {
            "family": ".AppleSystemUIFont",
            "sizeSmall": 10,
            "sizeMedium": 12,
            "sizeLarge": 14,
            "sizeHeader": 16
        }
    }
}


@dataclass
class ColorScheme:
    """Data class for a complete color scheme."""
    name: str
    description: str
    colors: Dict[str, str]
    font: Dict[str, Any]

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> 'ColorScheme':
        return ColorScheme(
            name=data.get('name', 'Custom'),
            description=data.get('description', ''),
            colors=data.get('colors', {}),
            font=data.get('font', {})
        )


class PreferencesManager(QObject):
    """Manager for application preferences including color schemes."""

    # Signals
    colorSchemeChanged = Signal(str)  # scheme_name
    fontChanged = Signal()
    preferencesLoaded = Signal()
    preferencesSaved = Signal()
    autosaveEnabledChanged = Signal(bool)
    autosaveIntervalChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_scheme_name = "blahaj_aesthetic"
        self._current_scheme = ColorScheme.from_dict(PRESET_COLOR_SCHEMES["blahaj_aesthetic"])
        self._custom_schemes: Dict[str, ColorScheme] = {}
        self._preferences_dir = Path.home() / ".trans_qml"
        self._preferences_file = self._preferences_dir / "preferences.json"
        self._schemes_dir = self._preferences_dir / "color_schemes"

        # Autosave settings
        self._autosave_enabled = True
        self._autosave_interval_minutes = 5

        self._ensure_dirs()
        self._load_preferences()

    def _ensure_dirs(self):
        """Ensure preference directories exist."""
        self._preferences_dir.mkdir(exist_ok=True)
        self._schemes_dir.mkdir(exist_ok=True)

    def _load_preferences(self):
        """Load preferences from file."""
        try:
            if self._preferences_file.exists():
                with open(self._preferences_file, 'r') as f:
                    data = json.load(f)
                    scheme_name = data.get('current_scheme', 'blahaj_aesthetic')
                    self._current_scheme_name = scheme_name

                    # Load autosave settings
                    self._autosave_enabled = data.get('autosave_enabled', True)
                    self._autosave_interval_minutes = data.get('autosave_interval_minutes', 5)

                    # Load custom schemes
                    for scheme_file in self._schemes_dir.glob("*.json"):
                        try:
                            with open(scheme_file, 'r') as sf:
                                scheme_data = json.load(sf)
                                self._custom_schemes[scheme_file.stem] = ColorScheme.from_dict(scheme_data)
                        except Exception as e:
                            logger.warning(f"Failed to load scheme {scheme_file}: {e}")

                    # Set current scheme
                    if scheme_name in PRESET_COLOR_SCHEMES:
                        self._current_scheme = ColorScheme.from_dict(PRESET_COLOR_SCHEMES[scheme_name])
                    elif scheme_name in self._custom_schemes:
                        self._current_scheme = self._custom_schemes[scheme_name]

                    self.preferencesLoaded.emit()
                    logger.info(f"Loaded preferences, current scheme: {scheme_name}")
        except Exception as e:
            logger.error(f"Error loading preferences: {e}")

    def _save_preferences(self):
        """Save preferences to file."""
        try:
            data = {
                'current_scheme': self._current_scheme_name,
                'version': '1.0',
                'autosave_enabled': self._autosave_enabled,
                'autosave_interval_minutes': self._autosave_interval_minutes,
            }
            with open(self._preferences_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.preferencesSaved.emit()
            logger.info("Preferences saved")
        except Exception as e:
            logger.error(f"Error saving preferences: {e}")

    @Slot(result=list)
    def getPresetSchemeNames(self) -> List[str]:
        """Get list of preset scheme names."""
        return list(PRESET_COLOR_SCHEMES.keys())

    @Slot(result=list)
    def getCustomSchemeNames(self) -> List[str]:
        """Get list of custom scheme names."""
        return list(self._custom_schemes.keys())

    @Slot(str, result='QVariant')
    def getSchemeInfo(self, scheme_name: str) -> Optional[Dict]:
        """Get info about a scheme."""
        if scheme_name in PRESET_COLOR_SCHEMES:
            return PRESET_COLOR_SCHEMES[scheme_name]
        elif scheme_name in self._custom_schemes:
            return self._custom_schemes[scheme_name].to_dict()
        return None

    @Slot(result='QVariant')
    def getCurrentScheme(self) -> Dict:
        """Get current color scheme."""
        return self._current_scheme.to_dict()

    @Slot(result=str)
    def getCurrentSchemeName(self) -> str:
        """Get current scheme name."""
        return self._current_scheme_name

    @Slot(str)
    def setScheme(self, scheme_name: str):
        """Set current color scheme by name."""
        if scheme_name in PRESET_COLOR_SCHEMES:
            self._current_scheme = ColorScheme.from_dict(PRESET_COLOR_SCHEMES[scheme_name])
            self._current_scheme_name = scheme_name
            self._save_preferences()
            self.colorSchemeChanged.emit(scheme_name)
            logger.info(f"Scheme changed to: {scheme_name}")
        elif scheme_name in self._custom_schemes:
            self._current_scheme = self._custom_schemes[scheme_name]
            self._current_scheme_name = scheme_name
            self._save_preferences()
            self.colorSchemeChanged.emit(scheme_name)
            logger.info(f"Custom scheme loaded: {scheme_name}")
        else:
            logger.warning(f"Unknown scheme: {scheme_name}")

    @Slot(str, str, str)
    def saveCurrentAsCustom(self, name: str, description: str, scheme_id: str):
        """Save current scheme as a custom scheme."""
        try:
            custom_scheme = ColorScheme(
                name=name,
                description=description,
                colors=self._current_scheme.colors.copy(),
                font=self._current_scheme.font.copy()
            )

            # Save to file
            scheme_file = self._schemes_dir / f"{scheme_id}.json"
            with open(scheme_file, 'w') as f:
                json.dump(custom_scheme.to_dict(), f, indent=2)

            self._custom_schemes[scheme_id] = custom_scheme
            logger.info(f"Saved custom scheme: {name}")
        except Exception as e:
            logger.error(f"Error saving custom scheme: {e}")

    @Slot(str)
    def deleteCustomScheme(self, scheme_id: str):
        """Delete a custom scheme."""
        try:
            if scheme_id in self._custom_schemes:
                scheme_file = self._schemes_dir / f"{scheme_id}.json"
                if scheme_file.exists():
                    scheme_file.unlink()
                del self._custom_schemes[scheme_id]
                logger.info(f"Deleted custom scheme: {scheme_id}")
        except Exception as e:
            logger.error(f"Error deleting custom scheme: {e}")

    @Slot(str, str)
    def setColor(self, color_key: str, color_value: str):
        """Set a specific color in the current scheme."""
        if color_key in self._current_scheme.colors:
            self._current_scheme.colors[color_key] = color_value
            self.colorSchemeChanged.emit(self._current_scheme_name)

    @Slot(str, result=str)
    def getColor(self, color_key: str) -> str:
        """Get a specific color from the current scheme."""
        return self._current_scheme.colors.get(color_key, "#FFFFFF")

    @Slot(str, 'QVariant')
    def setFontProperty(self, prop_name: str, value: Any):
        """Set a font property."""
        self._current_scheme.font[prop_name] = value
        self.fontChanged.emit()

    @Slot(str, result='QVariant')
    def getFontProperty(self, prop_name: str) -> Any:
        """Get a font property."""
        return self._current_scheme.font.get(prop_name)

    @Slot(result='QVariant')
    def getAllPresets(self) -> List[Dict]:
        """Get all preset schemes with metadata."""
        presets = []
        for scheme_id, scheme_data in PRESET_COLOR_SCHEMES.items():
            presets.append({
                'id': scheme_id,
                'name': scheme_data['name'],
                'description': scheme_data['description'],
                'isPreset': True
            })
        return presets

    @Slot(result='QVariant')
    def getAllCustomSchemes(self) -> List[Dict]:
        """Get all custom schemes with metadata."""
        customs = []
        for scheme_id, scheme in self._custom_schemes.items():
            customs.append({
                'id': scheme_id,
                'name': scheme.name,
                'description': scheme.description,
                'isPreset': False
            })
        return customs

    # Autosave settings
    @Slot(result=bool)
    def getAutosaveEnabled(self) -> bool:
        return self._autosave_enabled

    @Slot(bool)
    def setAutosaveEnabled(self, enabled: bool):
        if self._autosave_enabled != enabled:
            self._autosave_enabled = enabled
            self._save_preferences()
            self.autosaveEnabledChanged.emit(enabled)
            logger.info(f"Autosave {'enabled' if enabled else 'disabled'}")

    @Slot(result=int)
    def getAutosaveInterval(self) -> int:
        return self._autosave_interval_minutes

    @Slot(int)
    def setAutosaveInterval(self, minutes: int):
        minutes = max(1, min(60, minutes))
        if self._autosave_interval_minutes != minutes:
            self._autosave_interval_minutes = minutes
            self._save_preferences()
            self.autosaveIntervalChanged.emit(minutes)
            logger.info(f"Autosave interval set to {minutes} minutes")

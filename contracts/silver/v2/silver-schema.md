# Silver Schema v2

Silver v2 is the active clean-cut normalization contract for fresh listing
ingestions. The runtime records `silver-schema-v2` on every normalized row and
does not accept the previous contract version.

Silver keeps source facts typed when the listing exposes them: total and
covered surface, rooms, bedrooms, bathrooms, toilettes, parking spaces, floor,
age, disposition, orientation, title, description, amenities, and media URLs.
Missing facts remain null; invalid facts produce bounded normalization errors.

Qualitative features are preserved as source evidence in `amenities` and
`description_text` and are derived as versioned criteria observations. Absence
of a mention is unknown, not a negative assertion.

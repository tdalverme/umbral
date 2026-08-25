const CATEGORY_COLORS = [
  "#e05252",
  "#e08a2e",
  "#c7a72b",
  "#4e9f62",
  "#2b9c9c",
  "#4c78c2",
  "#6d5bd0",
  "#a855a8",
  "#d44b78",
  "#0f766e",
  "#64748b",
  "#7c9c45",
  "#3a91b4",
  "#9a5b2f",
  "#7c3aed",
  "#be123c",
] as const;

export interface CategoryColorEntry {
  category: string;
  color: string;
}

function hslToHex(hue: number, saturation: number, lightness: number): string {
  const chroma = (1 - Math.abs((2 * lightness) / 100 - 1)) * (saturation / 100);
  const segment = hue / 60;
  const intermediate = chroma * (1 - Math.abs((segment % 2) - 1));
  const match = lightness / 100 - chroma / 2;
  const [red, green, blue] =
    segment < 1
      ? [chroma, intermediate, 0]
      : segment < 2
        ? [intermediate, chroma, 0]
        : segment < 3
          ? [0, chroma, intermediate]
          : segment < 4
            ? [0, intermediate, chroma]
            : segment < 5
              ? [intermediate, 0, chroma]
              : [chroma, 0, intermediate];

  return `#${[red, green, blue]
    .map((channel) => Math.round((channel + match) * 255).toString(16).padStart(2, "0"))
    .join("")}`;
}

function colorForIndex(index: number): string {
  return CATEGORY_COLORS[index] ?? hslToHex((index * 137.508) % 360, 68, 48);
}

export function categoryColorEntries(categories: readonly string[]): CategoryColorEntry[] {
  const uniqueCategories = [...new Set(categories.filter(Boolean))].sort((left, right) => left.localeCompare(right));
  return uniqueCategories.map((category, index) => ({ category, color: colorForIndex(index) }));
}

export function categoryColorExpression(categories: readonly string[]): unknown[] {
  const entries = categoryColorEntries(categories);
  return [
    "match",
    ["get", "category"],
    ...entries.flatMap(({ category, color }) => [category, color]),
    "#64748b",
  ];
}

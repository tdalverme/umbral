import Image from "next/image";

type BrandLogoProps = {
  className?: string;
  layout?: "horizontal" | "symbol";
  priority?: boolean;
  tone?: "color" | "dark" | "light";
};

const assets = {
  horizontal: {
    color: "/brand/umbral-logo-horizontal-color.svg",
    dark: "/brand/umbral-logo-horizontal-dark.svg",
    light: "/brand/umbral-logo-horizontal-light.svg",
  },
  symbol: {
    color: "/brand/umbral-symbol-color.svg",
    dark: "/brand/umbral-symbol-dark.svg",
    light: "/brand/umbral-symbol-light.svg",
  },
} as const;

export function BrandLogo({ className, layout = "horizontal", priority, tone = "color" }: BrandLogoProps) {
  const src = assets[layout][tone];
  const width = layout === "horizontal" ? 280 : 64;
  const height = 64;

  return <Image src={src} alt="Umbral" width={width} height={height} className={className} priority={priority} />;
}

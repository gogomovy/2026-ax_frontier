export const SECTOR_IDS = [
  "loan",
  "deposit",
  "pension",
  "wealth",
  "trust",
  "fx",
  "card",
] as const;

export type SectorId = (typeof SECTOR_IDS)[number];

export const ALLOWED_EXTENSIONS = ["pdf", "txt", "hwp"] as const;

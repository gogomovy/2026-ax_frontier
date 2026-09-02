import path from "node:path";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { DEFAULT_OFFICIAL_HOSTS, SECTOR_IDS, type SectorId } from "./constants.ts";
import {
  clampSummary,
  deserializeEvidenceRef,
  diskFileName,
  isDuplicateHost,
  isHostAllowed,
  isPathInside,
  matchesRelated,
  serializeEvidenceRef,
  sliceSummary,
  type EvidenceRef,
} from "./rules.ts";

const sectorArb = fc.constantFrom(...SECTOR_IDS);
const tagArb = fc.stringMatching(/^[a-zA-Z0-9_-]{1,12}$/);

describe("EvidenceRef round-trip", () => {
  it("JSON round-trips", () => {
    fc.assert(
      fc.property(
        fc.record({
          evidenceId: fc.uuid(),
          kind: fc.constantFrom("policy", "decision", "article"),
          targetId: fc.uuid(),
        }),
        (ref: EvidenceRef) => {
          expect(deserializeEvidenceRef(serializeEvidenceRef(ref))).toEqual(ref);
        },
      ),
    );
  });
});

describe("host allowlist", () => {
  it("allows listed hosts and subdomains", () => {
    expect(isHostAllowed("www.fsc.go.kr", DEFAULT_OFFICIAL_HOSTS)).toBe(true);
    expect(isHostAllowed("fsc.go.kr", DEFAULT_OFFICIAL_HOSTS)).toBe(true);
    expect(isHostAllowed("example.com", DEFAULT_OFFICIAL_HOSTS)).toBe(false);
  });

  it("hostname check is equivalent to suffix matching", () => {
    fc.assert(
      fc.property(fc.stringMatching(/^[a-z0-9.-]{1,40}$/), (host: string) => {
        const allowed = isHostAllowed(host, DEFAULT_OFFICIAL_HOSTS);
        const expected = DEFAULT_OFFICIAL_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
        expect(allowed).toBe(expected);
      }),
    );
  });
});

describe("listRelated filter", () => {
  it("matches sector and tag intersection; articles must be confirmed", () => {
    fc.assert(
      fc.property(
        sectorArb,
        fc.array(tagArb, { maxLength: 4 }),
        fc.array(tagArb, { maxLength: 4 }),
        fc.boolean(),
        fc.constantFrom("policy", "decision", "article"),
        (
          sector: SectorId,
          itemTags: string[],
          queryTags: string[],
          confirmed: boolean,
          kind: "policy" | "decision" | "article",
        ) => {
          const item = { kind, sectors: [sector] as SectorId[], tags: itemTags, confirmed };
          const result = matchesRelated(item, sector, queryTags);
          if (kind === "article" && confirmed !== true) {
            expect(result).toBe(false);
            return;
          }
          if (queryTags.length === 0) {
            expect(result).toBe(true);
            return;
          }
          expect(result).toBe(queryTags.some((tag) => itemTags.includes(tag)));
        },
      ),
    );
  });
});

describe("summary", () => {
  it("initial summary is a prefix and never exceeds the save cap", () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 8000 }), (text: string) => {
        const sliced = sliceSummary(text);
        expect(sliced.length).toBeLessThanOrEqual(500);
        expect(clampSummary(`${sliced}${"x".repeat(5000)}`).length).toBeLessThanOrEqual(4000);
      }),
    );
  });
});

describe("path confinement", () => {
  it("rejects paths outside the root", () => {
    const root = path.resolve("/tmp/knowledge");
    expect(isPathInside(root, path.join(root, "policy", "a", "v1", "1.pdf"))).toBe(true);
    expect(isPathInside(root, path.join(root, "..", "etc", "passwd"))).toBe(false);
  });
});

describe("domain duplicate", () => {
  it("detects the same host regardless of case", () => {
    fc.assert(
      fc.property(fc.stringMatching(/^[a-z0-9.-]{1,30}$/), (host: string) => {
        expect(isDuplicateHost([host], host)).toBe(true);
        expect(isDuplicateHost([host], host.toUpperCase())).toBe(true);
        expect(isDuplicateHost([], host)).toBe(false);
      }),
    );
  });
});

describe("disk names", () => {
  it("does not embed user filenames", () => {
    expect(diskFileName(1, "pdf")).toBe("1.pdf");
  });
});

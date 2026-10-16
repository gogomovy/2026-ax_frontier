import { describe, expect, it } from "vitest";
import { canRevert, defaultRevertTarget, goalVersions, isArchived, isMissingRoute, reasonError, valueError } from "./goalChange";

const goal = { version: 3, targetValue: 7.0 };

describe("되돌리기 · 다시 수정 규칙", () => {
  it("사유는 공백을 빼고 최소 글자 수 이상", () => {
    expect(reasonError("", 5)).toBe("사유를 입력해 주세요");
    expect(reasonError("     ", 5)).toBe("사유를 입력해 주세요");
    expect(reasonError("짧음", 5)).toContain("5자 이상");
    expect(reasonError("  다섯글자임  ", 5)).toBeNull();
  });

  it("목표값은 비우거나 숫자가 아니면 안 된다", () => {
    expect(valueError("")).not.toBeNull();
    expect(valueError("abc")).not.toBeNull();
    expect(valueError("7.5")).toBeNull();
    expect(valueError("-1")).toBeNull();
  });

  it("예전 API 의 경로 없음(404 Not Found · 405)과 '목표 없음' 404 를 구분한다", () => {
    expect(isMissingRoute(404, "Not Found")).toBe(true);
    expect(isMissingRoute(405, "Method Not Allowed")).toBe(true);
    expect(isMissingRoute(404, "목표 없음")).toBe(false);
    expect(isMissingRoute(422, "Not Found")).toBe(false);
  });

  it("버전 사슬 — 기준 + 확정 버전, 예전 확정은 기준+1", () => {
    expect(goalVersions(goal)).toEqual([{ version: 3, value: 7.0, base: true }]);
    expect(goalVersions(goal, { targetValue: 8.0 })).toEqual([{ version: 3, value: 7.0, base: true }, { version: 4, value: 8.0 }]);
    const ov = { targetValue: 7.8, version: 5, versions: [{ version: 4, value: 8.0 }, { version: 5, value: 7.8 }] };
    expect(goalVersions(goal, ov).map((v) => v.version)).toEqual([3, 4, 5]);
    expect(defaultRevertTarget(goal, ov)).toEqual({ version: 4, value: 8.0 });
    expect(defaultRevertTarget(goal, { status: "active" })).toEqual({ version: 3, value: 7.0, base: true });
  });

  it("처리 기록이 있어야 되돌릴 수 있고, 보관 상태는 삭제로 본다", () => {
    expect(canRevert(undefined)).toBe(false);
    expect(canRevert({ status: "active" })).toBe(true);
    expect(isArchived({ status: "archived" })).toBe(true);
    expect(isArchived({ status: "active" })).toBe(false);
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "../i18n";
import { PolicyUploadForm } from "../components/PolicyUploadForm";

describe("PolicyUploadForm", () => {
  it("rejects submit without a file", () => {
    const onSubmit = vi.fn();
    render(<PolicyUploadForm submitting={false} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId("policy-upload-title-input"), { target: { value: "문서" } });
    fireEvent.click(screen.getByTestId("policy-upload-sectors-loan"));
    fireEvent.click(screen.getByTestId("policy-upload-submit-button"));
    expect(screen.getByTestId("policy-upload-validation-error")).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
